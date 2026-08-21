// Webhook Stripe / Mercado Pago → libera acesso da conta (e registra a venda)
//
// Deploy: supabase functions deploy payments-webhook --no-verify-jwt
//   (--no-verify-jwt é obrigatório: quem chama é o gateway, não um usuário.
//    A autenticação real é a ASSINATURA do evento, verificada abaixo.)
//
// Secrets obrigatórios (a função recusa o evento se faltarem):
//   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET   → para eventos Stripe
//   MP_ACCESS_TOKEN, MP_WEBHOOK_SECRET         → para eventos Mercado Pago
// Opcionais:
//   ACCESS_DAYS (padrão 365), LICENSE_PREFIX (padrão ATIV)
//   STRIPE_PRICE_ID  → se definido, só esse preço libera acesso
//
// O que ele NÃO faz mais, de propósito:
//   - não aceita evento sem assinatura válida
//   - não tem branch "manual" (o admin usa o RPC autenticado)
//   - não devolve a chave no corpo da resposta
import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";
import Stripe from "https://esm.sh/stripe@14.21.0?target=deno";

const ACCESS_DAYS = Number(Deno.env.get("ACCESS_DAYS") || "365");

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

// --- Stripe ---------------------------------------------------------------

async function parseStripe(req: Request, raw: string): Promise<Sale | Response> {
  const secret = Deno.env.get("STRIPE_SECRET_KEY");
  const whSecret = Deno.env.get("STRIPE_WEBHOOK_SECRET");
  if (!secret || !whSecret) return json({ error: "stripe_not_configured" }, 500);

  const sig = req.headers.get("stripe-signature");
  if (!sig) return json({ error: "missing_signature" }, 401);

  const stripe = new Stripe(secret, { apiVersion: "2024-06-20" });
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
    if (s.payment_status !== "paid") {
      return { provider: "stripe", providerRef: String(s.id), email: null, outcome: "ignore" };
    }
    const wantPrice = Deno.env.get("STRIPE_PRICE_ID");
    if (wantPrice) {
      // Confere que a compra é DESTE produto: sem isso, qualquer checkout da
      // mesma conta Stripe (um produto de R$ 9,90) liberava o ATIVAVID.
      const items = await stripe.checkout.sessions.listLineItems(s.id, { limit: 20 });
      const match = items.data.some((li) => li.price?.id === wantPrice);
      if (!match) {
        return { provider: "stripe", providerRef: String(s.id), email: null, outcome: "ignore" };
      }
    }
    return {
      provider: "stripe",
      providerRef: String(s.id),
      email: s.customer_details?.email || s.customer_email || null,
      outcome: "paid",
    };
  }

  // Devolução / disputa perdida → revoga.
  if (evt.type === "charge.refunded" || evt.type === "charge.dispute.created") {
    const obj = evt.data.object as Stripe.Charge | Stripe.Dispute;
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
    return {
      provider: "stripe",
      providerRef: ref,
      email: (obj as Stripe.Charge).billing_details?.email || null,
      outcome: ref ? "refunded" : "ignore",
    };
  }

  return { provider: "stripe", providerRef: String(evt.id), email: null, outcome: "ignore" };
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

async function parseMercadoPago(req: Request, evt: Record<string, unknown>): Promise<Sale | Response> {
  const token = Deno.env.get("MP_ACCESS_TOKEN");
  const whSecret = Deno.env.get("MP_WEBHOOK_SECRET");
  if (!token || !whSecret) return json({ error: "mp_not_configured" }, 500);

  const paymentId = String(
    (evt.data as Record<string, unknown> | undefined)?.id ?? evt.id ?? "",
  );
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
  const manifest = `id:${paymentId};request-id:${requestId};ts:${parts.ts};`;
  const expected = await hmacHex(whSecret, manifest);
  if (!timingSafeEqual(expected, parts.v1)) {
    console.error("mp signature rejeitada");
    return json({ error: "invalid_signature" }, 401);
  }

  // O corpo do MP traz só IDs: status e e-mail vêm da API. Antes, o código lia
  // evt.data.payer.email (sempre undefined) e emitia licença em payment.created,
  // ou seja, antes de o pagamento ser aprovado.
  const res = await fetch(`https://api.mercadopago.com/v1/payments/${paymentId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
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
  //    do mesmo evento inofensiva.
  const { error: insErr } = await sb.from("licenses").insert({
    license_key: makeKey(Deno.env.get("LICENSE_PREFIX") || "ATIV"),
    email: sale.email,
    status: "active",
    valid_until: validUntil,
    max_devices: 1,
    provider: sale.provider,
    provider_ref: sale.providerRef,
  });
  if (insErr && insErr.code !== "23505") throw insErr; // 23505 = já registrado

  // 2) O que de fato libera o cliente: acesso pela conta do e-mail da compra.
  //    Assim ele entra com o e-mail que usou para pagar e já está liberado —
  //    sem chave para digitar e sem depender de alguém enviar e-mail na mão.
  if (sale.email) {
    const { error } = await sb.from("account_access").upsert(
      {
        email: sale.email.trim().toLowerCase(),
        status: "active",
        valid_until: validUntil,
        max_devices: 1,
        notes: `${sale.provider}:${sale.providerRef}`,
        updated_at: new Date().toISOString(),
      },
      { onConflict: "email" },
    );
    if (error) throw error;
  } else {
    console.error("venda sem e-mail — liberar na mão:", sale.provider, sale.providerRef);
  }
}

async function revoke(sale: Sale) {
  const sb = db();
  const { data } = await sb
    .from("licenses")
    .update({ status: "revoked", updated_at: new Date().toISOString() })
    .eq("provider", sale.provider)
    .eq("provider_ref", sale.providerRef)
    .select("email");

  const email = sale.email || data?.[0]?.email || null;
  if (email) {
    await sb
      .from("account_access")
      .update({ status: "revoked", updated_at: new Date().toISOString() })
      .eq("email", email.trim().toLowerCase());
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
  const parsed = isStripe ? await parseStripe(req, raw) : await parseMercadoPago(req, evt);
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
