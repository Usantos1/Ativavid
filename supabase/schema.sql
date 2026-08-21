-- ATIVAVID licença / trial — rode no SQL Editor do Supabase
-- Depois: Deploy das Edge Functions em supabase/functions/

create extension if not exists pgcrypto;

create table if not exists public.licenses (
  id uuid primary key default gen_random_uuid(),
  license_key text not null unique,
  email text,
  status text not null default 'active'
    check (status in ('active', 'expired', 'revoked')),
  valid_until timestamptz not null,
  max_devices int not null default 1,
  provider text,          -- stripe | mercadopago | manual
  provider_ref text,      -- id do pagamento / assinatura
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.devices (
  id uuid primary key default gen_random_uuid(),
  device_id text not null unique,
  license_id uuid references public.licenses(id) on delete set null,
  label text,
  last_seen timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.trials (
  device_id text primary key,
  started_at timestamptz not null default now(),
  email text
);

-- Política de update (gate de versão). Detalhes em rpc_license.sql.
create table if not exists public.app_config (
  id int primary key default 1 check (id = 1),
  min_version text not null default '0.1.0',
  latest_version text not null default '0.1.0',
  download_url text,
  update_message text,
  updated_at timestamptz not null default now()
);

-- Acesso por conta (e-mail/senha). Admin libera X dias; cliente faz login.
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

create index if not exists licenses_key_idx on public.licenses (license_key);
-- Idempotência do webhook: o Stripe/MP reentrega o mesmo evento em timeout e
-- permite reenvio manual. Sem isto, um pagamento virava N licenças.
create unique index if not exists licenses_provider_ref_uq
  on public.licenses (provider, provider_ref)
  where provider_ref is not null;
create index if not exists devices_license_idx on public.devices (license_id);
create index if not exists devices_account_idx on public.devices (account_access_id);
create index if not exists account_access_user_idx on public.account_access (user_id);
create index if not exists account_access_email_idx on public.account_access (lower(email));

alter table public.licenses enable row level security;
alter table public.devices enable row level security;
alter table public.trials enable row level security;
alter table public.app_config enable row level security;
alter table public.account_access enable row level security;

comment on table public.account_access is
  'Acesso por conta: admin libera X dias por e-mail; vincula user_id no 1º login';

-- Clientes NÃO leem tabelas direto — só via Edge Function (service role).
-- Sem policies públicas de SELECT/INSERT.

comment on table public.licenses is 'Chaves anuais ATIVAVID (ex.: R$ 399/ano)';
comment on table public.trials is 'Trial de 7 dias por device_id';
