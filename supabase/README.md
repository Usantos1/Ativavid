# Licença ATIVAVID via Supabase (sem VPS)

## Acesso por conta (recomendado)

1. Rode `schema.sql` (ou pelo menos a tabela `account_access`)
2. Rode `rpc_license.sql` e `rpc_admin.sql`
3. Auth → Providers → Email ON (em dev: desative “Confirm email”)
4. No app:
   - Cliente: **Criar conta** (e-mail/senha) → Entrar
   - Admin: painel **Liberar acesso** com o e-mail + dias (7/14/30/365)
5. Cliente clica **Atualizar** em Licença → edita

Admin pode liberar **antes** do cliente criar a conta (fica pending no e-mail).

## Chave ATIV- (legado)

Ainda funciona: admin cria chave → cliente ativa. Preferência: conta + liberar dias.

## Login admin

1. Conta no Supabase Auth + e-mail na tabela `admins`
2. No app: Entrar → painel de licenças/acessos

## Gate de versão

Tabela `app_config` — ver comentários em `rpc_license.sql`.

## Edge Functions (opcional / webhook)

```bash
supabase functions deploy payments-webhook --no-verify-jwt
```
