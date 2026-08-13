// ATIVAVID — licença / trial (uma Function, várias actions)
// Deploy: supabase functions deploy license --no-verify-jwt
// Secrets: LICENSE_SIGNING_SECRET (opcional), TRIAL_DAYS=7

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const TRIAL_DAYS = Number(Deno.env.get("TRIAL_DAYS") || "7");
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}

function admin() {
  return createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );
}

function daysLeft(started: string): number {
  const start = new Date(started).getTime();
  const end = start + TRIAL_DAYS * 86400000;
  return Math.max(0, Math.ceil((end - Date.now()) / 86400000));
}

function trialActive(started: string): boolean {
  const start = new Date(started).getTime();
  return Date.now() < start + TRIAL_DAYS * 86400000;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method_not_allowed" }, 405);

  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const action = String(body.action || "status");
  const deviceId = String(body.deviceId || "").trim();
  if (!deviceId) return json({ error: "device_id_required" }, 400);

  const sb = admin();

  if (action === "status" || action === "trial") {
    // Licença ativa neste device?
    const { data: device } = await sb
      .from("devices")
      .select("license_id, licenses(status, valid_until, license_key)")
      .eq("device_id", deviceId)
      .maybeSingle();

    const lic = (device as { licenses?: { status: string; valid_until: string; license_key: string } | null } | null)
      ?.licenses;
    if (lic && lic.status === "active" && new Date(lic.valid_until).getTime() > Date.now()) {
      await sb.from("devices").update({ last_seen: new Date().toISOString() }).eq("device_id", deviceId);
      return json({
        entitled: true,
        mode: "licensed",
        validUntil: lic.valid_until,
        licenseKeyHint: lic.license_key.slice(0, 9) + "…",
      });
    }

    // Trial
    let { data: trial } = await sb.from("trials").select("*").eq("device_id", deviceId).maybeSingle();
    if (!trial && action === "trial") {
      const { data: created, error } = await sb
        .from("trials")
        .insert({ device_id: deviceId })
        .select("*")
        .single();
      if (error) return json({ error: error.message }, 500);
      trial = created;
    }

    if (trial && trialActive(trial.started_at)) {
      return json({
        entitled: true,
        mode: "trial",
        trialStartedAt: trial.started_at,
        trialDaysLeft: daysLeft(trial.started_at),
        trialDaysTotal: TRIAL_DAYS,
      });
    }

    return json({
      entitled: false,
      mode: "blocked",
      trialDaysLeft: 0,
      trialDaysTotal: TRIAL_DAYS,
      message: "Trial encerrado. Ative uma licença anual para continuar.",
    });
  }

  if (action === "activate") {
    const key = String(body.key || "").trim().toUpperCase();
    if (!key) return json({ error: "key_required" }, 400);

    const { data: lic, error } = await sb
      .from("licenses")
      .select("*")
      .eq("license_key", key)
      .maybeSingle();
    if (error) return json({ error: error.message }, 500);
    if (!lic) return json({ error: "invalid_key", message: "Chave inválida." }, 404);
    if (lic.status !== "active") return json({ error: "revoked", message: "Chave revogada." }, 403);
    if (new Date(lic.valid_until).getTime() <= Date.now()) {
      return json({ error: "expired", message: "Licença expirada." }, 403);
    }

    const { count } = await sb
      .from("devices")
      .select("*", { count: "exact", head: true })
      .eq("license_id", lic.id);

    const { data: existing } = await sb
      .from("devices")
      .select("*")
      .eq("device_id", deviceId)
      .maybeSingle();

    const already = existing?.license_id === lic.id;
    if (!already && (count || 0) >= (lic.max_devices || 1)) {
      return json({
        error: "device_limit",
        message: "Esta chave já está ativa em outro PC. Desative lá ou fale com o suporte.",
      }, 403);
    }

    const { error: upErr } = await sb.from("devices").upsert(
      {
        device_id: deviceId,
        license_id: lic.id,
        last_seen: new Date().toISOString(),
      },
      { onConflict: "device_id" },
    );
    if (upErr) return json({ error: upErr.message }, 500);

    return json({
      entitled: true,
      mode: "licensed",
      validUntil: lic.valid_until,
      licenseKeyHint: key.slice(0, 9) + "…",
    });
  }

  return json({ error: "unknown_action" }, 400);
});
