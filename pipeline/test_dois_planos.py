# -*- coding: utf-8 -*-
"""Anual e mensal na mesma tela, cada um com o seu link.

O produto virou **ATIVAVID Pro** com dois preços: anual R$ 399 (R$ 33,25/
mês) e mensal R$ 59. O mensal existe para derrubar a barreira de entrada;
o anual fica em destaque porque se paga em 7 meses e põe o dinheiro na
frente — que é o que importa para o caixa de uma loja.

Defeito de DINHEIRO pego antes de publicar a função: `ACCESS_DAYS` (365)
valia para qualquer compra, então o mensal de R$ 59 liberaria um ano
inteiro. Agora os dias saem do `price.recurring` da própria compra — ano
vira 365, mês vira 35 (30 + 5 de folga para a renovação poder atrasar sem
derrubar ninguém). Plano novo criado na Stripe já entra certo.

Conferido ao vivo: os dois planos aparecem para um cliente em teste e cada
clique abre o link do seu preço.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
FN = (REPO / "supabase" / "functions" / "payments-webhook"
      / "index.ts").read_text(encoding="utf-8")
LIC = (REPO / "app" / "license.py").read_text(encoding="utf-8")
SET = (REPO / "app" / "settings_store.py").read_text(encoding="utf-8")


def test_o_mensal_nao_libera_um_ano():
    """R$ 59 dando 365 dias seria prejuizo por linha de codigo."""
    i = FN.index("function diasDoPreco")
    bloco = FN[i:FN.index("\nconst ignorar", i)]
    assert 'r.interval === "year"' in bloco and "365 * n" in bloco
    assert 'r.interval === "month"' in bloco and "30 * n + 5" in bloco
    # e o grant tem de USAR isso, nao o ACCESS_DAYS fixo
    assert "p_days: dias," in FN
    assert "const dias = sale.dias && sale.dias > 0 ? sale.dias : ACCESS_DAYS;" in FN


def test_a_funcao_aceita_os_dois_precos():
    assert "precosAceitos" in FN and 'split(",")' in FN
    assert "precoServe(li.price?.id)" in FN


def test_os_dois_planos_estao_na_tela():
    i = HTML.index('id="licPlanos"')
    bloco = HTML[i:HTML.index("</div>", HTML.index('id="btnLicenseMensal"'))]
    assert 'id="btnLicenseCheckout"' in bloco and 'id="btnLicenseMensal"' in bloco
    assert "lic-plano--destaque" in bloco, "o anual tem de se destacar"


def test_cada_plano_abre_o_SEU_link():
    i = JS.index('const btnMensalPay = $("#btnLicenseMensal")')
    assert "openCheckout(state.license?.checkoutUrlMensal)" in JS[i:i + 300]


def test_plano_sem_link_nao_aparece():
    i = JS.index('const btnMensal = $("#btnLicenseMensal")')
    assert "btnMensal.hidden = !lic.checkoutUrlMensal" in JS[i:i + 200]


def test_os_dois_links_saem_da_mesma_fonte():
    """Ate a 4.44 o anual vinha carona no payload do entitlement e o mensal
    da config: dois caminhos para a mesma coisa, e um podia faltar sem
    ninguem notar (foi o que apareceu no teste)."""
    i = LIC.index('"checkoutUrl": st.get("checkoutUrl")')
    bloco = LIC[i:i + 260]
    assert '_cfg().get("checkout")' in bloco
    assert '_cfg().get("mensal")' in bloco


def test_o_link_mensal_vem_empacotado_na_build():
    assert '"checkoutUrlMensal"' in SET
    i = SET.index("_MANAGED_KEYS")
    assert "checkoutUrlMensal" in SET[i:i + 220], "senao o cliente nao recebe"


def test_a_build_nao_sai_sem_o_link_de_pagamento():
    """O `checkoutUrl` vazio ja saiu publicado uma vez: o botao Assinar
    nao existia e ninguem conseguia comprar, sem erro nenhum na tela. A
    guarda da build so avisava em amarelo, que se perde no log."""
    ps = (REPO / "installer" / "build.ps1").read_text(encoding="utf-8")
    i = ps.index("if (-not $cfg.checkoutUrl)")
    ate_o_mensal = ps[i:ps.index("checkoutUrlMensal", i)]
    assert "exit 3" in ate_o_mensal, "aviso amarelo nao barra build nenhuma"
    depois = ps[ps.index("checkoutUrlMensal", i):]
    assert "Aviso" in depois[:300], "o mensal e opcional, mas tem de ser dito"
