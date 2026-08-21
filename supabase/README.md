# Licença ATIVAVID via Supabase (sem VPS)

## Ordem de instalação

1. `schema.sql`
2. `rpc_license.sql`
3. `rpc_admin.sql` (troque o e-mail de admin no INSERT)

Os dois RPCs terminam com `notify pgrst, 'reload schema'`, então o PostgREST
enxerga a assinatura nova na hora. Sem isso o app reclamava de "função ausente"
logo depois de você rodar o SQL.

## Authentication → obrigatório

**Confirm email LIGADO.** O acesso por conta casa `account_access` pelo e-mail
do usuário, e o RPC agora exige `email_confirmed_at`. Com a confirmação
desligada, qualquer um cria conta com o e-mail de um cliente já liberado e herda
o acesso pago — e o vínculo é permanente.

Pelo mesmo motivo, `ativavid_is_admin` só reconhece admin com e-mail confirmado.

## Acesso por conta (recomendado)

1. Cliente: **Criar conta** (e-mail/senha) → confirma o e-mail → Entrar
2. Admin: painel **Liberar acesso** com o e-mail + dias (7/14/30/365)
3. Cliente clica **Atualizar** em Licença → edita

O admin pode liberar **antes** de o cliente criar a conta: fica pendente no
e-mail e vincula sozinho no primeiro login confirmado. Um novo `grant_access`
reatribui o vínculo, caso ele tenha ido para a conta errada.

## Chave ATIV- (legado)

Ainda funciona: admin cria chave → cliente ativa. Preferência: conta + liberar
dias. Considere aposentar — manter os dois caminhos dobra a superfície.

## Pagamento (Edge Function)

```bash
supabase functions deploy payments-webhook --no-verify-jwt
```

`--no-verify-jwt` é correto aqui: quem chama é o gateway, não um usuário. A
autenticação real é a **assinatura do evento**, que a função verifica — e sem os
secrets abaixo ela recusa tudo, de propósito.

Secrets:

| Secret | Para quê |
| --- | --- |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | eventos Stripe |
| `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET` | eventos Mercado Pago |
| `STRIPE_PRICE_ID` | opcional: só esse preço libera acesso |
| `ACCESS_DAYS` | opcional, padrão 365 |

O webhook **libera `account_access` pelo e-mail do pagamento** — o cliente entra
com o e-mail que usou para pagar e já está liberado, sem chave para digitar.
A venda também é registrada em `licenses` (com `provider_ref` único, para a
reentrega do mesmo evento não virar duas licenças). Reembolso e disputa
revogam.

Eventos tratados: `checkout.session.completed`,
`checkout.session.async_payment_succeeded` (boleto/Pix), `charge.refunded`,
`charge.dispute.created`; no MP, o status vem da API de pagamentos — o corpo do
webhook só traz IDs.

## Função `license` (aposentada)

`supabase/functions/license/` virou um 410. Era um segundo caminho de licença
que não aplicava o gate de versão nem enxergava `account_access`. Se ela já foi
deployada alguma vez, remova:

```bash
supabase functions delete license
```

## Gate de versão

Tabela `app_config` — ver comentários em `rpc_license.sql`.
