# -*- coding: utf-8 -*-
"""O webhook de pagamento não pode voltar a aceitar evento sem assinatura.

A versão anterior deployava com `--no-verify-jwt`, tinha a validação de
assinatura como um TODO e um branch `manual` que aceitava qualquer POST
anônimo — devolvendo a chave anual no corpo da resposta. Um curl pirateava o
produto.

Não há Deno nesta máquina, então o type-check só acontece no deploy. Estes
testes seguram as invariantes que, se quebrarem, voltam a dar acesso de graça
ou tiram dias já pagos de um cliente.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

WEBHOOK = REPO / "supabase" / "functions" / "payments-webhook" / "index.ts"
RPC = REPO / "supabase" / "rpc_license.sql"


def _js() -> str:
    return WEBHOOK.read_text(encoding="utf-8")


def test_nao_existe_branch_manual():
    """`{manual:true,email}` liberava licença anual para qualquer chamador."""
    js = _js()
    assert "manual === true" not in js
    assert re.search(r'evt\??\.manual', js) is None


def test_assinatura_e_verificada_nos_dois_gateways():
    js = _js()
    assert "constructEventAsync" in js, "Stripe sem verificação de assinatura"
    assert "invalid_signature" in js
    assert "hmacHex" in js and "timingSafeEqual" in js, "MP sem HMAC"
    assert "TODO" not in js, "sobrou um TODO onde antes estava a validação"


def test_nenhuma_venda_e_gravada_antes_de_verificar_a_assinatura():
    """O insert em licenses tem de vir depois do parse assinado."""
    js = _js()
    pos_sig = js.index("constructEventAsync")
    pos_insert = js.index('.from("licenses").insert')
    assert pos_sig < pos_insert, "gravação de venda antes da verificação"


def test_resposta_nao_carrega_a_chave():
    """A resposta vai para o Stripe/MP, não para o comprador: devolver a chave
    ali só a expõe em log de terceiro."""
    js = _js()
    corpo = js[js.index("Deno.serve"):]
    assert "licenseKey" not in corpo


def test_price_id_e_obrigatorio():
    """Sem conferir o preço, qualquer checkout da conta Stripe libera o app."""
    js = _js()
    assert "STRIPE_PRICE_ID" in js
    trecho = js[js.index("function parseStripe"):js.index("// --- Mercado Pago")]
    # Virou LISTA de precos (4.45: anual + mensal). A regra que este teste
    # guarda continua a mesma: sem preco declarado, a funcao recusa.
    assert "!precosAceitos.length" in trecho, "PRICE_ID virou opcional — falha aberta"
    assert "stripe_not_configured" in trecho


def test_stripe_no_deno_usa_fetch_http_client():
    """Sem createFetchHttpClient o stripe-node v14 tenta node:http e toda
    chamada de API quebra em runtime."""
    js = _js()
    assert "createFetchHttpClient" in js
    assert 'apiVersion: "2023-10-16"' in js, "apiVersion fora do tipo de stripe@14"


def test_pagamento_assincrono_e_status_pago_sao_conferidos():
    """Boleto/Pix: completed chega antes de compensar, com payment_status unpaid."""
    js = _js()
    assert "async_payment_succeeded" in js
    assert 'payment_status !== "paid"' in js


def test_reembolso_parcial_nao_revoga_o_ano():
    js = _js()
    assert "amount_refunded" in js, "estorno de R$1 revogaria o acesso inteiro"


def test_mercado_pago_assina_o_id_da_query_em_minusculas():
    """A doc do MP é explícita: o valor assinado é o data.id da URL, minúsculo."""
    js = _js()
    trecho = js[js.index("function parseMercadoPago"):]
    assert 'searchParams.get("data.id")' in trecho
    assert "toLowerCase()" in trecho
    assert "stale_signature" in trecho, "sem janela de replay"


def test_mercado_pago_ignora_topico_que_nao_e_pagamento():
    """merchant_order e afins chegam na mesma URL; buscar em /v1/payments dá 404
    e responder erro faz o MP reentregar até desativar o webhook."""
    js = _js()
    trecho = js[js.index("function parseMercadoPago"):]
    assert 'topico !== "payment"' in trecho
    assert "res.status === 404" in trecho


def test_falha_de_rede_no_parse_nao_derruba_a_funcao():
    js = _js()
    corpo = js[js.index("Deno.serve"):]
    assert "parse_failed" in corpo, "parse fora de try — 500 mudo em falha de rede"


def test_acesso_e_concedido_pela_rpc_que_soma():
    """Upsert cru sobrescreve valid_until: quem renova antes de vencer perde os
    dias que ainda tinha pagos."""
    js = _js()
    assert 'rpc("grant_account_access"' in js
    assert '.from("account_access").upsert' not in js


def test_reentrega_do_mesmo_evento_nao_estende_o_acesso():
    js = _js()
    trecho = js[js.index("async function grant("):js.index("async function revoke(")]
    assert "provider_ref" in trecho and "23505" in trecho
    assert "return;" in trecho, "sem saída antecipada, a reentrega somava +365"


def test_revoke_nao_engole_erro():
    """Reembolso que falha ao gravar respondia 200 e o Stripe nunca reentregava."""
    js = _js()
    trecho = js[js.index("async function revoke("):js.index("Deno.serve")]
    assert "upErr" in trecho and "accErr" in trecho
    assert trecho.count("throw") >= 2


def test_access_days_invalido_nao_quebra():
    """Number('abc') -> NaN -> new Date(NaN).toISOString() lança."""
    js = _js()
    assert "Number.isFinite" in js


def test_rpc_de_acesso_soma_sobre_o_que_resta():
    sql = RPC.read_text(encoding="utf-8")
    assert "grant_account_access" in sql, "a função que o webhook chama não existe"
    trecho = sql[sql.index("function public.grant_account_access"):]
    assert "greatest(account_access.valid_until, now())" in trecho, (
        "voltou a sobrescrever valid_until em vez de somar"
    )
    assert "to service_role" in trecho, "grant de execução faltando"
