// APOSENTADA. O app fala com a RPC `ativavid_license` (supabase/rpc_license.sql).
//
// Esta função era um segundo caminho de licença, deployado com --no-verify-jwt e
// rodando com service role. Ela não consultava account_access nem app_config, ou
// seja: não aplicava o force-update, não enxergava acesso por conta, e criava
// trial para qualquer device_id que chegasse — sem autenticação nenhuma.
// Manter as duas implementações só produzia divergência.
//
// Para fechar o buraco em produção, faça UMA das duas:
//   supabase functions delete license          (preferido)
//   supabase functions deploy license          (publica este 410)
Deno.serve(() =>
  new Response(
    JSON.stringify({
      error: "gone",
      message: "Endpoint desativado. Atualize o ATIVAVID para a versão atual.",
    }),
    { status: 410, headers: { "Content-Type": "application/json" } },
  )
);
