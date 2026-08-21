# Licença ATIVAVID via Supabase (sem VPS)

## Ordem de instalação

1. `schema.sql`
2. `rpc_license.sql`
3. `rpc_admin.sql` (troque o e-mail de admin no INSERT)

Os dois RPCs terminam com `notify pgrst, 'reload schema'`, então o PostgREST
enxerga a assinatura nova na hora. Sem isso o app reclamava de "função ausente"
logo depois de você rodar o SQL.

## Identidade: user_id, nunca e-mail

O acesso por conta casa **só pelo `user_id`** do JWT. Casar por e-mail deixava
qualquer um registrar o endereço de um cliente já liberado e herdar o acesso
pago, com o vínculo virando permanente.

Exigir e-mail confirmado **não resolve sozinho**: com "Confirm email"
desligado, o Auth preenche `email_confirmed_at` no próprio cadastro, então a
checagem passa para o invasor também. Ligar o Confirm email continua sendo
recomendado (e exige SMTP próprio — o mailer embutido do Supabase tem limite
baixo demais para venda), mas a proteção não depende disso.

Quem vincula e-mail a conta é o **admin**, no `grant_access`.

## Acesso por conta (recomendado)

1. Admin: **Criar conta + liberar** com o e-mail do cliente (um passo — já
   resolve o `user_id`)
2. Cliente: **Entrar** com esse e-mail e senha
3. Cliente clica **Atualizar** em Licença → edita

Se você liberar um e-mail que **ainda não tem conta**, os dias ficam
reservados mas o acesso **não vale** — o RPC responde `pendingSignup: true` e
o painel avisa. Depois que o cliente se cadastrar, clique em **Liberar** de
novo: aí o `user_id` é resolvido e o acesso passa a valer. `py
tools/checar_licenca.py` lista os que estão nesse estado.

Um novo `grant_access` também reatribui o vínculo, caso ele tenha ido para a
conta errada.

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
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` | eventos Stripe (os três) |
| `MP_ACCESS_TOKEN`, `MP_WEBHOOK_SECRET` | eventos Mercado Pago |
| `ACCESS_DAYS` | opcional, padrão 365 |

`STRIPE_PRICE_ID` é obrigatório de propósito: sem conferir o preço, qualquer
checkout da mesma conta Stripe (um produto de R$ 9,90) liberaria o ATIVAVID.

O webhook depende da função `grant_account_access` — ela vem no
`rpc_license.sql`, então rode o SQL antes de deployar.

O webhook **libera `account_access` pelo e-mail do pagamento** — o cliente entra
com o e-mail que usou para pagar e já está liberado, sem chave para digitar.
A venda também é registrada em `licenses` (com `provider_ref` único, para a
reentrega do mesmo evento não virar duas licenças). Reembolso e disputa
revogam.

Eventos tratados: `checkout.session.completed`,
`checkout.session.async_payment_succeeded` (boleto/Pix),
`invoice.payment_succeeded` (renovação, se a cobrança for assinatura
recorrente), `charge.refunded` (só reembolso total) e
`charge.dispute.created`. No MP, o status vem da API de pagamentos — o corpo
do webhook só traz IDs, e tópicos que não são `payment` são ignorados.

O acesso **soma** sobre o que resta: renovar faltando 200 dias dá 565, não 365.

## Função `license` (aposentada)

`supabase/functions/license/` virou um 410. Era um segundo caminho de licença
que não aplicava o gate de versão nem enxergava `account_access`. Se ela já foi
deployada alguma vez, remova:

```bash
supabase functions delete license
```

## Gate de versão

Tabela `app_config`. **Não edite a mão** — ela ficou parada em `0.1.24` até o
app chegar na 2.50, e com a tabela velha o `download_url` do force-update
mandaria o cliente instalar uma build de meses atrás.

No fim de cada release, depois de publicar o `.exe` no GitHub:

```bash
py tools/publicar_versao.py
```

Ele confere que a release existe com instalador anexado antes de gravar, e
só anuncia (`latest_version`). Para **bloquear** builds antigas:

```bash
py tools/publicar_versao.py --forcar
```

`--forcar` sobe `min_version` e trava todo cliente em versão anterior até
atualizar. Use como botão de emergência, não de rotina.

## Conferir o projeto

```bash
py tools/checar_licenca.py
```

Diz o que falta (Confirm email, SQL desatualizado, RLS, funções no ar,
política de versão) em vez de você descobrir por um cliente travado.
