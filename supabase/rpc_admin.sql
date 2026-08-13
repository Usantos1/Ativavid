-- ATIVAVID — login admin (Supabase Auth) + RPCs de gestão
-- 1) Authentication → Providers → Email ON
-- 2) Authentication → Users → Add user (seu e-mail + senha) OU cliente cria conta no app
-- 3) Rode schema.sql (account_access) + este SQL
-- 4) INSERT abaixo com o SEU e-mail de admin

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

create table if not exists public.admins (
  email text primary key,
  label text,
  created_at timestamptz not null default now()
);

alter table public.admins enable row level security;

-- >>> TROQUE pelo seu e-mail de admin <<<
insert into public.admins (email, label)
values ('lojaprimecamp@gmail.com', 'owner')
on conflict (email) do nothing;

create or replace function public.ativavid_is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1
    from public.admins a
    where lower(a.email) = lower(coalesce(auth.jwt() ->> 'email', ''))
  );
$$;

revoke all on function public.ativavid_is_admin() from public;
grant execute on function public.ativavid_is_admin() to authenticated, anon, service_role;

create or replace function public.ativavid_admin_license(
  p_action text,
  p_email text default null,
  p_days int default 365,
  p_max_devices int default 1,
  p_notes text default null,
  p_device_id text default null,
  p_license_key text default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_key text;
  v_until timestamptz;
  v_days int;
  v_max int;
  v_row licenses%rowtype;
  v_acc account_access%rowtype;
  v_lid uuid;
  v_uid uuid;
  v_email text;
  v_list json;
begin
  if not public.ativavid_is_admin() then
    return json_build_object(
      'ok', false,
      'error', 'forbidden',
      'message', 'Só admin autenticado pode gerenciar licenças.'
    );
  end if;

  if p_action = 'whoami' then
    return json_build_object(
      'ok', true,
      'admin', true,
      'email', auth.jwt() ->> 'email'
    );
  end if;

  -- Liberar acesso por conta (primário): e-mail + X dias
  if p_action = 'grant_access' then
    v_email := lower(trim(coalesce(p_email, '')));
    if length(v_email) = 0 or position('@' in v_email) = 0 then
      return json_build_object(
        'ok', false, 'error', 'email_required',
        'message', 'Informe o e-mail do cliente.'
      );
    end if;
    v_days := greatest(1, least(coalesce(p_days, 7), 3650));
    v_max := greatest(1, least(coalesce(p_max_devices, 1), 10));
    v_until := now() + make_interval(days => v_days);

    begin
      select id into v_uid
      from auth.users
      where lower(email) = v_email
      limit 1;
    exception when others then
      v_uid := null;
    end;

    insert into account_access (
      email, user_id, status, valid_until, max_devices, notes, updated_at
    ) values (
      v_email,
      v_uid,
      'active',
      v_until,
      v_max,
      nullif(trim(coalesce(p_notes, '')), ''),
      now()
    )
    on conflict (email) do update
      set status = 'active',
          valid_until = excluded.valid_until,
          max_devices = excluded.max_devices,
          user_id = coalesce(account_access.user_id, excluded.user_id),
          notes = coalesce(excluded.notes, account_access.notes),
          updated_at = now()
    returning * into v_acc;

    return json_build_object(
      'ok', true,
      'access', row_to_json(v_acc),
      'email', v_acc.email,
      'validUntil', v_acc.valid_until,
      'maxDevices', v_acc.max_devices,
      'pendingSignup', (v_acc.user_id is null),
      'message', case
        when v_acc.user_id is null then
          'Acesso liberado. Cliente ainda precisa criar conta com este e-mail.'
        else
          'Acesso liberado na conta do cliente.'
      end
    );
  end if;

  if p_action = 'list_access' then
    select coalesce(json_agg(row_to_json(t) order by t.updated_at desc), '[]'::json)
      into v_list
    from (
      select id, email, user_id, status, valid_until, max_devices, notes, created_at, updated_at
      from account_access
      order by updated_at desc
      limit 100
    ) t;
    return json_build_object('ok', true, 'access', v_list);
  end if;

  if p_action = 'revoke_access' then
    v_email := lower(trim(coalesce(p_email, '')));
    if length(v_email) = 0 then
      return json_build_object(
        'ok', false, 'error', 'email_required',
        'message', 'Informe o e-mail para revogar.'
      );
    end if;
    update account_access
      set status = 'revoked', updated_at = now()
      where email = v_email
    returning * into v_acc;
    if not found then
      return json_build_object(
        'ok', false, 'error', 'not_found',
        'message', 'Nenhum acesso encontrado para este e-mail.'
      );
    end if;
    return json_build_object(
      'ok', true,
      'access', row_to_json(v_acc),
      'message', 'Acesso revogado: ' || v_email
    );
  end if;

  if p_action = 'list' then
    select coalesce(json_agg(row_to_json(t) order by t.created_at desc), '[]'::json)
      into v_list
    from (
      select license_key, email, status, valid_until, max_devices, provider, created_at
      from licenses
      order by created_at desc
      limit 100
    ) t;
    return json_build_object('ok', true, 'licenses', v_list);
  end if;

  if p_action = 'create' then
    v_days := greatest(1, least(coalesce(p_days, 365), 3650));
    v_max := greatest(1, least(coalesce(p_max_devices, 1), 10));
    v_until := now() + make_interval(days => v_days);
    v_key := 'ATIV-' || upper(substr(encode(gen_random_bytes(2), 'hex'), 1, 4))
          || '-' || upper(substr(encode(gen_random_bytes(2), 'hex'), 1, 4))
          || '-' || upper(substr(encode(gen_random_bytes(2), 'hex'), 1, 4));

    insert into licenses (
      license_key, email, status, valid_until, max_devices, provider, notes
    ) values (
      v_key,
      nullif(trim(coalesce(p_email, '')), ''),
      'active',
      v_until,
      v_max,
      'manual',
      nullif(trim(coalesce(p_notes, '')), '')
    )
    returning * into v_row;

    return json_build_object(
      'ok', true,
      'licenseKey', v_row.license_key,
      'license', row_to_json(v_row),
      'message', 'Licença criada. Envie a chave ao cliente.'
    );
  end if;

  if p_action = 'list_devices' then
    if p_license_key is not null and length(trim(p_license_key)) > 0 then
      select id into v_lid from licenses where license_key = upper(trim(p_license_key));
      if v_lid is null then
        return json_build_object('ok', false, 'error', 'not_found', 'message', 'Licença não encontrada.');
      end if;
      select coalesce(json_agg(row_to_json(d)), '[]'::json) into v_list
      from (
        select device_id, license_id, account_access_id, label, last_seen, created_at
        from devices where license_id = v_lid
        order by last_seen desc nulls last
        limit 100
      ) d;
    else
      select coalesce(json_agg(row_to_json(d)), '[]'::json) into v_list
      from (
        select device_id, license_id, account_access_id, label, last_seen, created_at
        from devices
        order by last_seen desc nulls last
        limit 100
      ) d;
    end if;
    return json_build_object('ok', true, 'devices', v_list);
  end if;

  if p_action = 'release_device' then
    if p_device_id is null or length(trim(p_device_id)) = 0 then
      return json_build_object('ok', false, 'error', 'device_id_required', 'message', 'Informe o device id.');
    end if;
    delete from devices where device_id = trim(p_device_id);
    return json_build_object('ok', true, 'message', 'Device liberado: ' || trim(p_device_id));
  end if;

  return json_build_object('ok', false, 'error', 'unknown_action');
end;
$$;

revoke all on function public.ativavid_admin_license(text, text, int, int, text, text, text) from public;
grant execute on function public.ativavid_admin_license(text, text, int, int, text, text, text) to authenticated, service_role;
