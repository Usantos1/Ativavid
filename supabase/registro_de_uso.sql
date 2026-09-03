-- ATIVAVID — registro de aberturas e bloqueio por computador
--
-- Pedido de 30/08/2026: "todo mundo que baixar e abrir gerar log pra gente
-- bloquear o computador em caso de compartilhamento ilegal".
--
-- COMO USAR: Supabase → SQL Editor → cole este arquivo inteiro → Run.
-- Pode rodar mais de uma vez; tudo aqui é "if not exists" / "or replace".
--
-- O app já funciona sem isto: ele grava o log localmente em
-- %USERPROFILE%\ATIVAVID\aberturas.jsonl de qualquer jeito, e o aviso para
-- o servidor é ignorado enquanto a função abaixo não existir.

-- ---------------------------------------------------------------- tabela
create table if not exists public.aberturas (
  id           bigserial primary key,
  device_id    text not null,
  host         text,
  os_user      text,
  so           text,
  app_version  text,
  licenca      text,
  criado_em    timestamptz not null default now()
);

create index if not exists aberturas_device_idx
  on public.aberturas (device_id, criado_em desc);
create index if not exists aberturas_criado_idx
  on public.aberturas (criado_em desc);

-- Ninguém lê esta tabela pelo app: só o painel do admin (service role).
alter table public.aberturas enable row level security;

-- O bloqueio mora no device, junto do que já existia.
alter table public.devices add column if not exists blocked_at     timestamptz;
alter table public.devices add column if not exists blocked_reason text;
alter table public.devices add column if not exists host           text;
alter table public.devices add column if not exists os_user        text;

-- 4.93: o e-mail logado no app vai junto com a abertura. Sem ele o painel
-- não tinha como dizer DE QUEM era um PC em trial ("esse tem conta de
-- e-mail e não exibe ali", 03/09).
alter table public.aberturas add column if not exists email text;
alter table public.devices   add column if not exists email text;

-- ------------------------------------------------------------- a abertura
-- Função PRÓPRIA (e não mais uma ação dentro de ativavid_license): duas
-- assinaturas com parâmetros opcionais deixam o PostgREST ambíguo — por
-- isso a assinatura antiga (6 argumentos) CAI antes de criar a nova.
drop function if exists public.ativavid_open(text, text, text, text, text, text);

create or replace function public.ativavid_open(
  p_device_id   text,
  p_app_version text default null,
  p_host        text default null,
  p_user        text default null,
  p_os          text default null,
  p_licenca     text default null,
  p_email       text default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_email text := lower(nullif(trim(coalesce(p_email, '')), ''));
begin
  if p_device_id is null or length(trim(p_device_id)) = 0 then
    return json_build_object('ok', false, 'error', 'device_id_required');
  end if;

  insert into public.aberturas (device_id, host, os_user, so, app_version, licenca, email)
  values (trim(p_device_id), p_host, p_user, p_os, p_app_version, p_licenca, v_email);

  -- O device pode nem ter licença ainda: é justamente quem baixou e abriu.
  insert into public.devices (device_id, label, host, os_user, email, last_seen)
  values (trim(p_device_id), p_host, p_host, p_user, v_email, now())
  on conflict (device_id) do update
    set last_seen = now(),
        host      = coalesce(excluded.host, public.devices.host),
        os_user   = coalesce(excluded.os_user, public.devices.os_user),
        email     = coalesce(excluded.email, public.devices.email);

  return json_build_object('ok', true);
end;
$$;

grant execute on function public.ativavid_open(text, text, text, text, text, text, text)
  to anon, authenticated;

notify pgrst, 'reload schema';

-- ------------------------------------------------------- o gate do device
-- Chame isto no INÍCIO do bloco 'status'/'trial' da ativavid_license:
--
--     if public.ativavid_device_blocked(p_device_id) then
--       return public.ativavid_with_update(
--         json_build_object(
--           'entitled', false,
--           'mode', 'blocked',
--           'message', 'Este computador foi bloqueado. Fale com o suporte.'
--         ), p_app_version);
--     end if;
--
-- O app 4.27+ já entende `mode=blocked` e grava o veredito: depois disso,
-- ficar offline não devolve a licença (e atrasar o relógio também não).
create or replace function public.ativavid_device_blocked(p_device_id text)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.devices
    where device_id = trim(p_device_id) and blocked_at is not null
  );
$$;

-- O APP consulta esta funcao a cada validacao (4.28): enquanto a
-- ativavid_license nao checar o bloqueio, quem checa e o cliente.
grant execute on function public.ativavid_device_blocked(text) to anon, authenticated;

-- ------------------------------------------------------------ admin
-- Bloquear / desbloquear uma máquina. Só service role (o painel do admin).
create or replace function public.ativavid_block_device(
  p_device_id text,
  p_reason    text default null,
  p_block     boolean default true
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_n int;
begin
  -- Sem esta guarda um device_id vazio criava uma linha em branco na
  -- tabela (aconteceu ao testar em 30/08).
  if p_device_id is null or length(trim(p_device_id)) = 0 then
    return json_build_object('ok', false, 'error', 'device_id_required');
  end if;

  insert into public.devices (device_id) values (trim(p_device_id))
  on conflict (device_id) do nothing;

  update public.devices
     set blocked_at     = case when p_block then now() else null end,
         blocked_reason = case when p_block then p_reason else null end
   where device_id = trim(p_device_id);
  get diagnostics v_n = row_count;
  return json_build_object('ok', v_n > 0, 'device_id', trim(p_device_id),
                           'blocked', p_block);
end;
$$;

revoke execute on function public.ativavid_block_device(text, text, boolean) from anon, authenticated;

-- ------------------------------------------------------------ consultas
-- Máquinas que mais abriram nos últimos 30 dias (para achar compartilhamento):
--
--   select d.device_id, d.host, d.os_user, d.blocked_at,
--          count(a.id) as aberturas, max(a.criado_em) as ultima
--     from public.devices d
--     left join public.aberturas a on a.device_id = d.device_id
--          and a.criado_em > now() - interval '30 days'
--    group by d.device_id, d.host, d.os_user, d.blocked_at
--    order by aberturas desc;
--
-- Uma licença aberta em mais de um computador:
--
--   select l.license_key, count(distinct d.device_id) as maquinas
--     from public.licenses l
--     join public.devices d on d.license_id = l.id
--    group by l.license_key
--   having count(distinct d.device_id) > 1;
