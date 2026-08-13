// Webhook Stripe ou Mercado Pago → cria licença anual
// Deploy: supabase functions deploy payments-webhook --no-verify-jwt
// Secrets: STRIPE_WEBHOOK_SECRET ou MP_WEBHOOK_SECRET, LICENSE_PREFIX=ATIV

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, stripe-signature",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

function makeKey(prefix = "ATIV"): string {
  const chunk = () =>
    crypto.getRandomValues(new Uint8Array(2)).reduce((s, b) => s + b.toString(16).padStart(2, "0"), "").toUpperCase();
  return `${prefix}-${chunk()}${chunk()}-${chunk()}${chunk()}-${chunk()}${chunk()}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  const sb = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const raw = await req.text();
  let email: string | null = null;
  let provider = "manual";
  let providerRef: string | null = null;

  // Stripe Checkout: checkout.session.completed
  try {
    const evt = JSON.parse(raw);
    if (evt?.type === "checkout.session.completed") {
      provider = "stripe";
      providerRef = String(evt.data?.object?.id || "");
      email = evt.data?.object?.customer_details?.email || evt.data?.object?.customer_email || null;
    } else if (evt?.action === "payment.created" || evt?.type === "payment") {
      // stub Mercado Pago — ajuste conforme o payload real do seu webhook
      provider = "mercadopago";
      providerRef = String(evt.data?.id || evt.id || "");
      email = evt.data?.payer?.email || evt.payer?.email || null;
    } else if (evt?.manual === true && evt?.email) {
      // admin local: { "manual": true, "email": "x@y.com", "days": 365 }
      provider = "manual";
      email = String(evt.email);
      providerRef = `manual-${Date.now()}`;
    } else {
      return json({ ok: true, ignored: true });
    }
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  // TODO: validar assinatura Stripe/MP com STRIPE_WEBHOOK_SECRET / MP_WEBHOOK_SECRET

  const days = 365;
  const validUntil = new Date(Date.now() + days * 86400000).toISOString();
  const licenseKey = makeKey(Deno.env.get("LICENSE_PREFIX") || "ATIV");

  const { data, error } = await sb
    .from("licenses")
    .insert({
      license_key: licenseKey,
      email,
      status: "active",
      valid_until: validUntil,
      max_devices: 1,
      provider,
      provider_ref: providerRef,
    })
    .select("*")
    .single();

  if (error) return json({ error: error.message }, 500);

  return json({
    ok: true,
    licenseKey: data.license_key,
    email: data.email,
    validUntil: data.valid_until,
    // Em produção: envie a chave por e-mail; não devolva em webhooks públicos sem cuidado.
  });
});
