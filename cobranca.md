# Cobrança — como o ATIVAVID vende (31/08/2026)

Estava solto num arquivo fora do git, já desatualizado. Fica aqui porque
nenhum destes números aparece no código.

## Os planos

| plano | preço | preço na Stripe | dias liberados |
|---|---|---|---|
| Pro anual (destaque) | R$ 399,00 | `price_1UAW3TLTWXhkTodteggD3tF8` | 365 |
| Pro mensal | R$ 59,00 | `price_1UAXhiLTWXhkTodtORcvpg24` | 35 |

Produto `ATIVAVID Pro` · `prod_VArnZcv0xgWiA5`.

O mensal dá **35** dias de propósito: 30 do mês mais 5 de folga, para a
renovação poder atrasar sem derrubar ninguém. Os dias saem do próprio
preço da compra (`price.recurring`), então plano novo criado na Stripe já
entra certo — sem mexer em código.

## O caminho do dinheiro

1. O cliente clica em Assinar no app. Os dois links vêm do
   `license_config.json` embutido na build (`checkoutUrl` e
   `checkoutUrlMensal`), e também são chaves publicáveis em
   `app/settings_store.py` — dá para trocar o link de quem já instalou
   **sem** build nova.
2. A Stripe cobra e dispara o evento.
3. A função `payments-webhook` (Supabase `koolbdivdqnqxlukctqu`) confere a
   assinatura, confere se o preço é um dos aceitos (`STRIPE_PRICE_ID`,
   lista separada por vírgula) e chama `grant_account_access`.
4. O acesso aparece no app em Licença → Contas.

Segredos da função: `STRIPE_SECRET_KEY` e `STRIPE_WEBHOOK_SECRET` — chaves
suas, configuradas por você. Reembolso revoga o acesso.

## Cupom de teste

`TESTE98` (98%, uma vez, 1 resgate) vale só no link de teste
`https://buy.stripe.com/9B68wQgFH6HP2Tk6oodwc02` — mensal por R$ 1,18.

A Stripe **não deixa ligar "permitir códigos promocionais" depois** que o
link foi criado. Por isso o link de teste é separado: para aceitar cupom
nos links de venda seria preciso criar links novos e trocar a
configuração.

Depois de qualquer compra de teste, cancele a assinatura — o desconto vale
só o primeiro mês.

## O que conferir depois de uma compra

1. Entrega **bem-sucedida** no webhook da Stripe.
2. Conta criada com a validade certa (365 ou 35 dias).
3. Acesso aparecendo no app naquele e-mail.
4. Reembolso revogando.

A regra dos dias está travada por teste em `pipeline/test_dois_planos.py`.
