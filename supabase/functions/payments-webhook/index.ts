// Webhook Stripe / Mercado Pago → libera acesso da conta (e registra a venda)
//
// Deploy: supabase functions deploy payments-webhook --no-verify-jwt
//   (--no-verify-jwt é obrigatório: quem chama é o gateway, não um usuário.
//    A autenticação real é a ASSINATURA do evento, verificada abaixo.)
//
// Secrets obrigatórios (a função recusa o evento se faltarem):
//   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID  → Stripe
//   MP_ACCESS_TOKEN, MP_WEBHOOK_SECRET                         → Mercado Pago
// Opcionais:
//   ACCESS_DAYS (padrão 365), LICENSE_PREFIX (padrão ATIV)
//
// STRIPE_PRICE_ID é obrigatório de propósito: sem ele, QUALQUER checkout da
// mesma conta Stripe (um produto de R$ 9,90) liberaria o ATIVAVID.
//
// Requer a função grant_account_access (supabase/rpc_license.sql).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";
import Stripe from "https://esm.sh/stripe@14.21.0?target=deno";

const _dias = Number(Deno.env.get("ACCESS_DAYS"));
const ACCESS_DAYS = Number.isFinite(_dias) && _dias > 0 ? _dias : 365;
const MP_TOLERANCIA_MS = 15 * 60 * 1000;

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function db() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

function stripeClient(secret: string) {
  // createFetchHttpClient é obrigatório no Deno: sem ele o stripe-node v14 tenta
  // node:http e TODA chamada de API quebra (a verificação de assinatura passaria,
  // mas listLineItems e sessions.list lançariam).
  return new Stripe(secret, {
    apiVersion: "2023-10-16",
    httpClient: Stripe.createFetchHttpClient(),
  });
}

function makeKey(prefix = "ATIV"): string {
  const chunk = () =>
    crypto.getRandomValues(new Uint8Array(2))
      .reduce((s, b) => s + b.toString(16).padStart(2, "0"), "")
      .toUpperCase();
  return `${prefix}-${chunk()}-${chunk()}-${chunk()}`;
}

type Sale = {
  provider: "stripe" | "mercadopago";
  providerRef: string;
  email: string | null;
  /** paid = libera; refunded = revoga; ignore = evento que não nos interessa */
  outcome: "paid" | "refunded" | "ignore";
};

const ignorar = (provider: Sale["provider"], ref: string): Sale => ({
  provider,
  providerRef: ref,
  email: null,
  outcome: "ignore",
});

// --- Stripe ---------------------------------------------------------------

async function parseStripe(req: Request, raw: string): Promise<Sale | Response> {
  const secret = Deno.env.get("STRIPE_SECRET_KEY");
  const whSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET");
  const wantPrice = Deno.env.get("STRIPE_PRICE_ID");
  if (!secret || !whSecret || !wantPrice) {
    console.error("stripe sem secrets (precisa de SECRET_KEY, WEBHOOK_SECRET e PRICE_ID)");
    return json({ error: "stripe_not_configured" }, 500);
  }

  const sig = req.headers.get("stripe-signature");
  if (!sig) return json({ error: "missing_signature" }, 401);

  const stripe = stripeClient(secret);
  let evt: Stripe.Event;
  try {
    evt = await stripe.webhooks.constructEventAsync(
      raw,
      sig,
      whSecret,
      undefined,
      Stripe.createSubtleCryptoProvider(),
    );
  } catch (e) {
    console.error("stripe signature rejeitada:", (e as Error).message);
    return json({ error: "invalid_signature" }, 401);
  }

  // Pagamento confirmado. async_payment_succeeded é o evento do boleto/Pix,
  // que chega DEPOIS de compensar — completed sozinho pode vir unpaid.
  if (
    evt.type === "checkout.session.completed" ||
    evt.type === "checkout.session.async_payment_succeeded"
  ) {
    const s = evt.data.object as Stripe.Checkout.Session;
    if (s.payment_status !== "paid") return ignorar("stripe", String(s.id));
    const items = await stripe.checkout.sessions.listLineItems(s.id, { limit: 100 });
    if (!items.data.some((li) => li.price?.id === wantPrice)) {
      return ignorar("stripe", String(s.id));
    }
    return {
      provider: "stripe",
      providerRef: String(s.id),
      email: s.customer_details?.email || s.customer_email || null,
      outcome: "paid",
    };
  }

  // Renovação de assinatura recorrente (não chega em pagamento avulso).
  if (evt.type === "invoice.payment_succeeded") {
    const inv = evt.data.object as Stripe.Invoice;
    const temPreco = (inv.lines?.data || []).some((li) => li.price?.id === wantPrice);
    if (!temPreco || !inv.id) return ignorar("stripe", String(inv.id || evt.id));
    return {
      provider: "stripe",
      providerRef: String(inv.id),
      email: inv.customer_email || null,
      outcome: "paid",
    };
  }

  // Devolução / disputa perdida / assinatura cancelada → revoga.
  if (evt.type === "charge.refunded" || evt.type === "charge.dispute.created") {
    const obj = evt.data.object as Stripe.Charge | Stripe.Dispute;
    if (evt.type === "charge.refunded") {
      // Reembolso PARCIAL não pode revogar o ano inteiro por R$ 1 estornado.
      const c = obj as Stripe.Charge;
      if (!c.refunded && (c.amount_refunded ?? 0) < c.amount) {
        return ignorar("stripe", String(c.id));
      }
    }
    const paymentIntent = String(
      (obj as Stripe.Charge).payment_intent || (obj as Stripe.Dispute).payment_intent || "",
    );
    let ref = "";
    if (paymentIntent) {
      const sessions = await stripe.checkout.sessions.list({
        payment_intent: paymentIntent,
        limit: 1,
      });
      ref = sessions.data[0]?.id || "";
    }
    const email = (obj as Stripe.Charge).billing_details?.email || null;
    return ref
      ? { provider: "stripe", providerRef: ref, email, outcome: "refunded" }
      : ignorar("stripe", String(evt.id));
  }

  return ignorar("stripe", String(evt.id));
}

// --- Mercado Pago ---------------------------------------------------------

async function hmacHex(secret: string, message: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const mac = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(message));
  return Array.from(new Uint8Array(mac))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

async function parseMercadoPago(
  req: Request,
  evt: Record<string, unknown>,
): Promise<Sale | Response> {
  const token = Deno.env.get("MP_ACCESS_TOKEN");
  const whSecret = Deno.env.get("MP_WEBHOOK_SECRET");
  if (!token || !whSecret) return json({ error: "mp_not_configured" }, 500);

  // O MP assina o `data.id` da QUERY STRING, em minúsculas — não o do corpo.
  const url = new URL(req.url);
  const rawId = url.searchParams.get("data.id") ??
    String((evt.data as Record<string, unknown> | undefined)?.id ?? "");
  const paymentId = rawId.toLowerCase();
  if (!paymentId) return json({ error: "missing_payment_id" }, 400);

  // x-signature: "ts=<unix>,v1=<hmac>" sobre "id:<id>;request-id:<rid>;ts:<ts>;"
  const sigHeader = req.headers.get("x-signature") || "";
  const requestId = req.headers.get("x-request-id") || "";
  const parts = Object.fromEntries(
    sigHeader.split(",").map((p) => {
      const [k, ...v] = p.split("=");
      return [k.trim(), v.join("=").trim()];
    }),
  );
  if (!parts.ts || !parts.v1) return json({ error: "missing_signature" }, 401);
  if (Math.abs(Date.now() - Number(parts.ts)) > MP_TOLERANCIA_MS) {
    return json({ error: "stale_signature" }, 401);
  }
  // O segmento request-id só entra quando o header veio: concatenar vazio
  // produz um manifest diferente do que o MP assinou.
  const manifest = `id:${paymentId};` +
    (requestId ? `request-id:${requestId};` : "") +
    `ts:${parts.ts};`;
  if (!timingSafeEqual(await hmacHex(whSecret, manifest), parts.v1)) {
    console.error("mp signature rejeitada");
    return json({ error: "invalid_signature" }, 401);
  }

  // merchant_order, subscription_preapproval e afins chegam na MESMA URL, com
  // assinatura válida. Buscá-los em /v1/payments dá 404, e responder erro faz o
  // MP reentregar de 15 em 15 minutos até desativar o webhook.
  const topico = String(evt.type ?? evt.topic ?? "");
  if (topico !== "payment") return ignorar("mercadopago", paymentId);

  // O corpo do MP traz só IDs: status e e-mail vêm da API. Antes, o código lia
  // evt.data.payer.email (sempre undefined) e emitia licença em payment.created,
  // ou seja, antes de o pagamento ser aprovado.
  const res = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 404) return ignorar("mercadopago", paymentId);
  if (!res.ok) {
    console.error("mp api falhou:", res.status);
    return json({ error: "mp_lookup_failed" }, 502);
  }
  const pay = await res.json();
  const status = String(pay?.status || "");
  const email = pay?.payer?.email || null;
  const outcome: Sale["outcome"] = status === "approved"
    ? "paid"
    : (status === "refunded" || status === "charged_back")
    ? "refunded"
    : "ignore";
  return { provider: "mercadopago", providerRef: paymentId, email, outcome };
}

// --- efeitos --------------------------------------------------------------

async function grant(sale: Sale) {
  const sb = db();
  const validUntil = new Date(Date.now() + ACCESS_DAYS * 86400000).toISOString();

  // 1) Registro da venda. O unique (provider, provider_ref) torna a reentrega
  //    do mesmo evento inofensiva — e é o que detecta a reentrega.
  const { error: insErr } = await sb.from("licenses").insert({
    license_key: makeKey(Deno.env.get("LICENSE_PREFIX") || "ATIV"),
    email: sale.email,
    status: "active",
    valid_until: validUntil,
    max_devices: 1,
    provider: sale.provider,
    provider_ref: sale.providerRef,
  });
  if (insErr) {
    // 23505 também sai de colisão de license_key: aí NÃO é reentrega, é uma
    // venda que precisa ser gravada.
    const reentrega = insErr.code === "23505" &&
      String(insErr.details ?? "").includes("provider_ref");
    if (!reentrega) throw insErr;
    console.log("evento reentregue, acesso já concedido:", sale.provider, sale.providerRef);
    return;
  }

  // 2) O que de fato libera o cliente: acesso pela conta do e-mail da compra.
  //    Via RPC porque ela SOMA sobre o que resta — um upsert cru sobrescreveria
  //    valid_until e quem renovasse antes de vencer perderia os dias pagos.
  if (sale.email) {
    const { error } = await sb.rpc("grant_account_access", {
      p_email: sale.email,
      p_days: ACCESS_DAYS,
      p_notes: `${sale.provider}:${sale.providerRef}`,
    });
    if (error) throw error;
  } else {
    console.error("venda sem e-mail — liberar na mão:", sale.provider, sale.providerRef);
  }
}

async function revoke(sale: Sale) {
  const sb = db();
  const { data, error: upErr } = await sb
    .from("licenses")
    .update({ status: "revoked", updated_at: new Date().toISOString() })
    .eq("provider", sale.provider)
    .eq("provider_ref", sale.providerRef)
    .select("email");
  if (upErr) throw upErr;

  const email = sale.email || data?.[0]?.email || null;
  if (email) {
    const { error: accErr } = await sb
      .from("account_access")
      .update({ status: "revoked", updated_at: new Date().toISOString() })
      .eq("email", email.trim().toLowerCase());
    if (accErr) throw accErr;
  }
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  const raw = await req.text();
  let evt: Record<string, unknown>;
  try {
    evt = JSON.parse(raw);
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const isStripe = req.headers.has("stripe-signature");
  let parsed: Sale | Response;
  try {
    parsed = isStripe ? await parseStripe(req, raw) : await parseMercadoPago(req, evt);
  } catch (e) {
    // parseStripe/parseMercadoPago fazem rede (listLineItems, sessions.list,
    // API do MP): sem este try, uma falha derrubava a função com 500 mudo.
    console.error("falha ao interpretar evento:", (e as Error).message);
    return json({ error: "parse_failed" }, 500);
  }
  if (parsed instanceof Response) return parsed;

  try {
    if (parsed.outcome === "paid") await grant(parsed);
    else if (parsed.outcome === "refunded") await revoke(parsed);
  } catch (e) {
    // 500 faz o gateway reentregar — o que é o certo para falha nossa.
    console.error("falha ao aplicar venda:", (e as Error).message);
    return json({ error: "apply_failed" }, 500);
  }

  return json({ ok: true, outcome: parsed.outcome });
});
