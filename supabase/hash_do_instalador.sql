-- 5.0.41 — SHA-256 do instalador na política de versão.
--
-- Até aqui o app baixava o exe da `download_url` e o EXECUTAVA sem conferir
-- nada: um instalador trocado no GitHub (conta invadida, release editada)
-- rodaria em toda máquina de cliente no próximo "Atualizar agora". Agora o
-- `tools/publicar_versao.py` grava o hash do exe que acabou de subir, o RPC
-- devolve o hash junto com a URL, e o app só executa o que bate. Para
-- trocar o instalador seria preciso invadir o GitHub E o Supabase.
--
-- Rodar no SQL Editor do Supabase. Pode rodar mais de uma vez.
-- Enquanto não rodar: o `publicar_versao.py` avisa e grava sem o hash, e o
-- app segue atualizando como antes (sem conferência).

alter table public.app_config add column if not exists download_sha256 text;

create or replace function public.ativavid_update_payload(p_app_version text)
returns json
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  cfg app_config%rowtype;
  cur text;
  below_min boolean := false;
  below_latest boolean := false;
  force_u boolean := false;
  msg text;
begin
  select * into cfg from app_config where id = 1;
  if not found then
    return json_build_object(
      'currentOk', true,
      'force', false,
      'updateAvailable', false,
      'minVersion', null,
      'latestVersion', null,
      'downloadUrl', null,
      'downloadSha256', null,
      'message', null
    );
  end if;

  cur := nullif(trim(coalesce(p_app_version, '')), '');
  if cur is null then
    -- Cliente antigo sem versão: não força (evita brick), mas avisa se houver latest
    below_latest := true;
  else
    below_min := public.ativavid_version_lt(cur, cfg.min_version);
    below_latest := public.ativavid_version_lt(cur, cfg.latest_version);
  end if;

  force_u := below_min;
  msg := coalesce(
    nullif(trim(cfg.update_message), ''),
    'Atualize o ATIVAVID para continuar.'
  );
  if force_u then
    msg := 'Esta versão não é mais suportada. Atualize para continuar.';
  end if;

  return json_build_object(
    'currentOk', not force_u,
    'force', force_u,
    'updateAvailable', (force_u or below_latest),
    'minVersion', cfg.min_version,
    'latestVersion', cfg.latest_version,
    'downloadUrl', cfg.download_url,
    'downloadSha256', nullif(lower(trim(coalesce(cfg.download_sha256, ''))), ''),
    'message', case when force_u or below_latest then msg else null end,
    'appVersion', cur
  );
end;
$$;
