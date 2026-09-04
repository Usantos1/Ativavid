-- ============================================================
--  ATIVAVID 5.0.3 — AULAS (central de ajuda dentro do app)
-- ============================================================
--  Cole ESTE arquivo inteiro no SQL Editor do Supabase e clique em Run.
--  Pode rodar mais de uma vez.
--
--  A lista de aulas (links do YouTube) mora aqui. Quem lê é qualquer
--  app (anon), quem escreve é o admin (public.admins), pela tela
--  "Aulas" do próprio ATIVAVID. Precisa do rpc_admin.sql já rodado
--  (função public.ativavid_is_admin).
-- ============================================================

create table if not exists public.aulas (
  id          uuid primary key default gen_random_uuid(),
  titulo      text not null,
  descricao   text not null default '',
  youtube_id  text not null,
  secao       text not null default 'Começando',
  ordem       int  not null default 100,
  ativo       boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

alter table public.aulas enable row level security;
-- sem policies: só as funções abaixo (security definer) leem e escrevem

-- ---------------------------------------------------------------- leitura
create or replace function public.ativavid_aulas()
returns json
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    json_agg(
      json_build_object(
        'id', id, 'titulo', titulo, 'descricao', descricao,
        'youtubeId', youtube_id, 'secao', secao, 'ordem', ordem
      )
      order by secao, ordem, created_at
    ),
    '[]'::json)
  from public.aulas
  where ativo;
$$;

revoke all on function public.ativavid_aulas() from public;
grant execute on function public.ativavid_aulas() to anon, authenticated, service_role;

-- ---------------------------------------------------------------- admin
drop function if exists public.ativavid_admin_aulas(text, uuid, text, text, text, text, int, boolean);

create or replace function public.ativavid_admin_aulas(
  p_action    text,
  p_id        uuid    default null,
  p_titulo    text    default null,
  p_descricao text    default null,
  p_youtube   text    default null,
  p_secao     text    default null,
  p_ordem     int     default null,
  p_ativo     boolean default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_id   uuid;
  v_list json;
begin
  if not public.ativavid_is_admin() then
    return json_build_object('ok', false, 'error', 'forbidden',
                             'message', 'Só o admin mexe nas aulas.');
  end if;

  if p_action = 'upsert' then
    if coalesce(p_titulo, '') = '' and p_id is null then
      return json_build_object('ok', false, 'error', 'titulo', 'message', 'A aula precisa de título.');
    end if;
    if coalesce(p_youtube, '') = '' and p_id is null then
      return json_build_object('ok', false, 'error', 'youtube', 'message', 'A aula precisa do link do YouTube.');
    end if;
    if p_id is null then
      insert into public.aulas (titulo, descricao, youtube_id, secao, ordem, ativo)
      values (p_titulo, coalesce(p_descricao, ''), p_youtube,
              coalesce(nullif(p_secao, ''), 'Começando'),
              coalesce(p_ordem, 100), coalesce(p_ativo, true))
      returning id into v_id;
    else
      update public.aulas
         set titulo     = coalesce(nullif(p_titulo, ''), titulo),
             descricao  = coalesce(p_descricao, descricao),
             youtube_id = coalesce(nullif(p_youtube, ''), youtube_id),
             secao      = coalesce(nullif(p_secao, ''), secao),
             ordem      = coalesce(p_ordem, ordem),
             ativo      = coalesce(p_ativo, ativo),
             updated_at = now()
       where id = p_id;
      v_id := p_id;
    end if;
  elsif p_action = 'delete' then
    delete from public.aulas where id = p_id;
  elsif p_action <> 'list' then
    return json_build_object('ok', false, 'error', 'unknown_action');
  end if;

  select coalesce(
    json_agg(
      json_build_object(
        'id', id, 'titulo', titulo, 'descricao', descricao,
        'youtubeId', youtube_id, 'secao', secao, 'ordem', ordem, 'ativo', ativo
      )
      order by secao, ordem, created_at
    ),
    '[]'::json)
  into v_list
  from public.aulas;

  return json_build_object('ok', true, 'id', v_id, 'aulas', v_list);
end;
$$;

revoke all on function public.ativavid_admin_aulas(text, uuid, text, text, text, text, int, boolean) from public;
grant execute on function public.ativavid_admin_aulas(text, uuid, text, text, text, text, int, boolean) to authenticated, service_role;
