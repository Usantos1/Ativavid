-- ATIVAVID licença + gate de versão via RPC
-- Rode no SQL Editor do Supabase (depois de schema.sql)

-- Acesso por conta (idempotente se já rodou schema.sql)
create table if not exists public.account_access (
  id uuid primary key default gen_random_uuid(),
  email text not null unique,
  user_id uuid,
  status text not null default 'active'
    check (status in ('active', 'revoked')),
  valid_until timestamptz not null,
  max_devices int not null default 1,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.devices
  add column if not exists account_access_id uuid references public.account_access(id) on delete set null;

alter table public.account_access enable row level security;

-- Política de versão (uma linha). GitHub só hospeda o .exe; aqui decide se a build pode usar.
create table if not exists public.app_config (
  id int primary key default 1 check (id = 1),
  min_version text not null default '0.1.0',
  latest_version text not null default '0.1.0',
  download_url text,
  update_message text,
  updated_at timestamptz not null default now()
);

alter table public.app_config enable row level security;

insert into public.app_config (id, min_version, latest_version, download_url, update_message)
values (
  1,
  '0.1.0',
  '0.1.24',
  'https://github.com/Usantos1/Ativavid/releases/download/v0.1.24/Instalar.ATIVAVID.exe',
  'Há uma nova versão do ATIVAVID. Atualize para continuar com suporte e correções.'
)
on conflict (id) do nothing;

comment on table public.app_config is
  'Política de update: min_version trava builds antigas; latest + download_url para CTA. Suba min_version para forçar update.';

-- Compara semver simples (0.1.23 < 0.1.24). Ignora prefixo v.
create or replace function public.ativavid_version_lt(a text, b text)
returns boolean
language plpgsql
immutable
as $$
declare
  pa text[];
  pb text[];
  i int;
  n int;
  na int;
  nb int;
begin
  pa := string_to_array(regexp_replace(lower(coalesce(trim(a), '0')), '^v', ''), '.');
  pb := string_to_array(regexp_replace(lower(coalesce(trim(b), '0')), '^v', ''), '.');
  n := greatest(coalesce(array_length(pa, 1), 0), coalesce(array_length(pb, 1), 0), 1);
  for i in 1..n loop
    begin
      na := coalesce(nullif(regexp_replace(coalesce(pa[i], '0'), '[^0-9].*$', ''), '')::int, 0);
    exception when others then
      na := 0;
    end;
    begin
      nb := coalesce(nullif(regexp_replace(coalesce(pb[i], '0'), '[^0-9].*$', ''), '')::int, 0);
    exception when others then
      nb := 0;
    end;
    if na < nb then return true; end if;
    if na > nb then return false; end if;
  end loop;
  return false;
end;
$$;

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
    'message', case when force_u or below_latest then msg else null end,
    'appVersion', cur
  );
end;
$$;

create or replace function public.ativavid_with_update(p_base json, p_app_version text)
returns json
language sql
stable
as $$
  select (coalesce(p_base::jsonb, '{}'::jsonb) || jsonb_build_object(
    'update', public.ativavid_update_payload(p_app_version)
  ))::json;
$$;

-- Assinatura antiga (3 args) → remove para PostgREST não ambíguo
drop function if exists public.ativavid_license(text, text, text);

create or replace function public.ativavid_license(
  p_action text,
  p_device_id text,
  p_key text default null,
  p_app_version text default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_trial trials%rowtype;
  v_lic licenses%rowtype;
  v_acc account_access%rowtype;
  v_status text;
  v_until timestamptz;
  v_lkey text;
  v_lid uuid;
  v_max int;
  v_count int;
  v_days int := 7;
  v_left int;
  v_hint text;
  v_has_trial boolean := false;
  v_base json;
  v_upd json;
  v_jwt_email text;
  v_jwt_uid uuid;
  v_bound boolean;
begin
  if p_device_id is null or length(trim(p_device_id)) = 0 then
    return public.ativavid_with_update(
      json_build_object('entitled', false, 'mode', 'error', 'error', 'device_id_required'),
      p_app_version
    );
  end if;

  if p_action in ('status', 'trial') then
    -- 1) Conta logada com account_access
    begin
      v_jwt_email := lower(nullif(trim(coalesce(auth.jwt() ->> 'email', '')), ''));
      begin
        v_jwt_uid := nullif(auth.jwt() ->> 'sub', '')::uuid;
      exception when others then
        v_jwt_uid := null;
      end;
    exception when others then
      v_jwt_email := null;
      v_jwt_uid := null;
    end;

    if v_jwt_email is not null or v_jwt_uid is not null then
      select * into v_acc
      from account_access a
      where a.status = 'active'
        and a.valid_until > now()
        and (
          (v_jwt_uid is not null and a.user_id = v_jwt_uid)
          or (v_jwt_email is not null and a.email = v_jwt_email)
        )
      order by a.valid_until desc
      limit 1;

      if found then
        if v_acc.user_id is null and v_jwt_uid is not null then
          update account_access
            set user_id = v_jwt_uid, updated_at = now()
            where id = v_acc.id
          returning * into v_acc;
        end if;

        select exists (
          select 1 from devices d
          where d.device_id = p_device_id and d.account_access_id = v_acc.id
        ) into v_bound;

        if not v_bound then
          select count(*)::int into v_count
          from devices where account_access_id = v_acc.id;
          if v_count >= coalesce(v_acc.max_devices, 1) then
            v_base := json_build_object(
              'entitled', false,
              'mode', 'blocked',
              'error', 'device_limit',
              'message', 'Esta conta já está ativa em outro PC. Peça ao admin para liberar o device.',
              'accountEmail', v_acc.email,
              'validUntil', v_acc.valid_until
            );
          else
            insert into devices (device_id, account_access_id, last_seen)
            values (p_device_id, v_acc.id, now())
            on conflict (device_id) do update
              set account_access_id = excluded.account_access_id,
                  last_seen = excluded.last_seen;
            v_bound := true;
          end if;
        else
          update devices set last_seen = now()
          where device_id = p_device_id and account_access_id = v_acc.id;
        end if;

        if v_bound then
          v_base := json_build_object(
            'entitled', true,
            'mode', 'account',
            'validUntil', v_acc.valid_until,
            'accountEmail', v_acc.email,
            'maxDevices', v_acc.max_devices
          );
        end if;

        v_upd := public.ativavid_update_payload(p_app_version);
        if coalesce((v_upd ->> 'force')::boolean, false) then
          v_base := (
            coalesce(v_base::jsonb, '{}'::jsonb)
            || jsonb_build_object(
              'entitled', false,
              'mode', 'update_required',
              'message', coalesce(v_upd ->> 'message', 'Atualize o ATIVAVID para continuar.')
            )
          )::json;
        end if;
        return (coalesce(v_base::jsonb, '{}'::jsonb) || jsonb_build_object('update', v_upd))::json;
      end if;
    end if;

    -- 2) Chave ATIV- já ativada neste device (legado)
    select l.status, l.valid_until, l.license_key
      into v_status, v_until, v_lkey
    from devices d
    join licenses l on l.id = d.license_id
    where d.device_id = p_device_id
    limit 1;

    if found and v_status = 'active' and v_until > now() then
      update devices set last_seen = now() where device_id = p_device_id;
      v_hint := left(v_lkey, 9) || '…';
      v_base := json_build_object(
        'entitled', true,
        'mode', 'licensed',
        'validUntil', v_until,
        'licenseKeyHint', v_hint
      );
    else
      -- 3) Trial por device
      select * into v_trial from trials where device_id = p_device_id;
      v_has_trial := found;

      if not v_has_trial and p_action = 'trial' then
        insert into trials (device_id) values (p_device_id)
        returning * into v_trial;
        v_has_trial := true;
      end if;

      if v_has_trial and v_trial.started_at + make_interval(days => v_days) > now() then
        v_left := ceil(
          extract(epoch from (v_trial.started_at + make_interval(days => v_days) - now())) / 86400.0
        )::int;
        v_base := json_build_object(
          'entitled', true,
          'mode', 'trial',
          'trialStartedAt', v_trial.started_at,
          'trialDaysLeft', greatest(v_left, 0),
          'trialDaysTotal', v_days
        );
      else
        v_base := json_build_object(
          'entitled', false,
          'mode', 'blocked',
          'trialDaysLeft', 0,
          'trialDaysTotal', v_days,
          'message', case
            when v_jwt_email is not null then
              'Conta sem acesso liberado. Peça ao admin para liberar dias neste e-mail, ou ative uma chave.'
            else
              'Trial encerrado. Crie uma conta e peça acesso, ou ative uma chave.'
          end
        );
      end if;
    end if;

    v_upd := public.ativavid_update_payload(p_app_version);
    if coalesce((v_upd ->> 'force')::boolean, false) then
      v_base := (
        coalesce(v_base::jsonb, '{}'::jsonb)
        || jsonb_build_object(
          'entitled', false,
          'mode', 'update_required',
          'message', coalesce(v_upd ->> 'message', 'Atualize o ATIVAVID para continuar.')
        )
      )::json;
    end if;
    return (coalesce(v_base::jsonb, '{}'::jsonb) || jsonb_build_object('update', v_upd))::json;
  end if;

  if p_action = 'activate' then
    if p_key is null or length(trim(p_key)) = 0 then
      return public.ativavid_with_update(
        json_build_object(
          'entitled', false, 'mode', 'error',
          'error', 'key_required', 'message', 'Informe a chave.'
        ),
        p_app_version
      );
    end if;

    select * into v_lic
    from licenses
    where license_key = upper(trim(p_key));

    if not found then
      return public.ativavid_with_update(
        json_build_object(
          'entitled', false, 'mode', 'blocked',
          'error', 'invalid_key', 'message', 'Chave inválida.'
        ),
        p_app_version
      );
    end if;
    if v_lic.status <> 'active' then
      return public.ativavid_with_update(
        json_build_object(
          'entitled', false, 'mode', 'blocked',
          'error', 'revoked', 'message', 'Chave revogada.'
        ),
        p_app_version
      );
    end if;
    if v_lic.valid_until <= now() then
      return public.ativavid_with_update(
        json_build_object(
          'entitled', false, 'mode', 'blocked',
          'error', 'expired', 'message', 'Licença expirada.'
        ),
        p_app_version
      );
    end if;

    select count(*)::int into v_count from devices where license_id = v_lic.id;
    if not exists (
         select 1 from devices where device_id = p_device_id and license_id = v_lic.id
       )
       and v_count >= coalesce(v_lic.max_devices, 1) then
      return public.ativavid_with_update(
        json_build_object(
          'entitled', false,
          'mode', 'blocked',
          'error', 'device_limit',
          'message', 'Esta chave já está ativa em outro PC.'
        ),
        p_app_version
      );
    end if;

    insert into devices (device_id, license_id, last_seen)
    values (p_device_id, v_lic.id, now())
    on conflict (device_id) do update
      set license_id = excluded.license_id,
          last_seen = excluded.last_seen;

    v_hint := left(v_lic.license_key, 9) || '…';
    v_base := json_build_object(
      'entitled', true,
      'mode', 'licensed',
      'validUntil', v_lic.valid_until,
      'licenseKeyHint', v_hint
    );
    v_upd := public.ativavid_update_payload(p_app_version);
    if coalesce((v_upd ->> 'force')::boolean, false) then
      v_base := (
        coalesce(v_base::jsonb, '{}'::jsonb)
        || jsonb_build_object(
          'entitled', false,
          'mode', 'update_required',
          'message', coalesce(v_upd ->> 'message', 'Atualize o ATIVAVID para continuar.')
        )
      )::json;
    end if;
    return (coalesce(v_base::jsonb, '{}'::jsonb) || jsonb_build_object('update', v_upd))::json;
  end if;

  return public.ativavid_with_update(
    json_build_object('entitled', false, 'mode', 'error', 'error', 'unknown_action'),
    p_app_version
  );
end;
$$;

revoke all on function public.ativavid_license(text, text, text, text) from public;
grant execute on function public.ativavid_license(text, text, text, text) to anon, authenticated, service_role;

revoke all on function public.ativavid_update_payload(text) from public;
grant execute on function public.ativavid_update_payload(text) to anon, authenticated, service_role;

revoke all on function public.ativavid_with_update(json, text) from public;
grant execute on function public.ativavid_with_update(json, text) to anon, authenticated, service_role;

revoke all on function public.ativavid_version_lt(text, text) from public;
grant execute on function public.ativavid_version_lt(text, text) to anon, authenticated, service_role;

-- Exemplo para FORÇAR update (descomente quando publicar a release):
-- update public.app_config set
--   min_version = '0.1.24',
--   latest_version = '0.1.24',
--   download_url = 'https://github.com/Usantos1/Ativavid/releases/download/v0.1.24/Instalar.ATIVAVID.exe',
--   update_message = 'Atualize para a versão 0.1.24 para continuar.',
--   updated_at = now()
-- where id = 1;
