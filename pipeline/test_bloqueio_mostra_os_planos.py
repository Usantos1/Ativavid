# -*- coding: utf-8 -*-
"""No PC bloqueado, o que salta aos olhos é assinar — e a chave sumiu.

Print dele em 31/08, na máquina bloqueada: a janela "Ative o ATIVAVID"
mostrava um preço só (R$ 399 / ano), um campo "Chave" e, de botão vermelho,
**Ativar**. Ou seja: o maior destaque da tela onde a pessoa acabou de
esbarrar no bloqueio ia para a saída da minoria que comprou fora do app;
"Assinar agora" era um dos quatro botões cinzas do rodapé, e o plano
mensal — que existe desde a 4.45 — nem aparecia.

Agora a janela mostra os DOIS planos como botões (anual em destaque,
mensal ao lado), cada um abrindo o seu link, e a chave de ativação saiu do
app inteiro: quem já pagou entra pela conta, porque toda compra cria a
conta sozinha pelo webhook da Stripe. Liberar na mão continua existindo,
pelo painel (`/api/admin/access`), por conta e não por chave.

A rota `/api/license/activate` fica de pé no servidor de propósito: chave
já ativada num PC continua valendo. O que acabou foi o lugar de digitar
uma nova.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
LIC = (REPO / "app" / "license.py").read_text(encoding="utf-8")


def _janela() -> str:
    i = HTML.index('id="dlgLicense"')
    return HTML[i:HTML.index("</dialog>", i)]


def test_os_dois_planos_estao_na_janela_do_bloqueio():
    b = _janela()
    assert 'id="btnLicDlgAnual"' in b and 'id="btnLicDlgMensal"' in b
    assert "R$ 399" in b and "R$ 59" in b


def test_assinar_e_o_que_mais_aparece():
    """O destaque vermelho era do `export-btn` "Ativar"; agora nao ha
    nenhum botao de acao com mais peso que os planos."""
    b = _janela()
    assert "lic-plano--destaque" in b, "o anual tem de se destacar"
    assert "export-btn" not in b, "nenhuma outra acao pode roubar o destaque"
    # e os planos vem ANTES das saidas discretas
    assert b.index('id="btnLicDlgAnual"') < b.index('id="btnLicDlgLogin"')


def test_a_saida_de_quem_ja_pagou_e_a_conta():
    b = _janela()
    assert 'id="btnLicDlgLogin"' in b
    i = JS.index('const btnDlgLogin = $("#btnLicDlgLogin")')
    assert 'openLoginDialog("login")' in JS[i:i + 300]


def test_cada_plano_da_janela_abre_o_SEU_link():
    i = JS.index('for (const id of ["#btnLicenseCheckout", "#btnLicDlgAnual"]')
    assert "openCheckout(b.dataset.url" in JS[i:i + 220]
    j = JS.index('for (const id of ["#btnLicenseMensal", "#btnLicDlgMensal"]')
    assert "b.dataset.url || state.license?.checkoutUrlMensal" in JS[j:j + 260]


def test_plano_sem_link_nao_aparece_na_janela():
    i = JS.index("function openLicenseDialog(")
    b = JS[i:JS.index("\nfunction openCheckout(", i)]
    assert "anual.hidden = !L.checkoutUrl" in b
    assert "mensal.hidden = !L.checkoutUrlMensal" in b


def test_a_chave_de_ativacao_saiu_do_app():
    for morto in ("dlgChave", "licenseKeyInput", "licDlgKey",
                  "btnLicenseActivate", "btnLicDlgActivate"):
        assert morto not in HTML, f"{morto} ainda esta na tela"
        assert morto not in JS, f"{morto} ainda esta no script"
    assert "activateLicenseKey" not in JS
    assert "dlg-chave" not in CSS


def test_nao_sobrou_preco_chumbado_de_um_plano_so():
    """`priceLabel` dizia "R$ 399 / ano" para todo mundo — com dois planos
    isso vira mentira, e o preco agora mora em cada plano da tela."""
    assert "priceLabel" not in LIC
    assert "priceLabel" not in JS


def test_nao_ha_botao_de_adiar():
    """Pedido dele em 31/08: "esse botao a gente nao quer, porque o unico
    objetivo e a pessoa assinar". O app ja esta bloqueado nesta janela."""
    b = _janela()
    assert "btnLicDlgLater" not in b
    assert "Agora não" not in b
    assert "btnLicDlgLater" not in JS


def test_o_link_vai_junto_com_o_botao():
    """Print dele: os planos APARECIAM e o clique dizia "Assinatura
    indisponivel agora". `renderLicense` tinha um `return` (quando o painel
    de Licenca ainda nao existe na tela) ANTES de gravar `state.license`, e
    a janela desenha com o payload recem-chegado enquanto o clique lia o
    estado velho, vazio."""
    i = JS.index("function renderLicense(")
    cabeca = JS[i:i + 700]
    assert "state.license = lic;" in cabeca, "o estado tem de entrar antes do return"
    assert cabeca.index("state.license = lic;") < cabeca.index("if (!hint) return;")
    # e o botao carrega o proprio endereco, para nao depender do estado
    j = JS.index("function openLicenseDialog(")
    b = JS[j:JS.index("\nfunction openCheckout(", j)]
    assert "anual.dataset.url" in b and "mensal.dataset.url" in b
    assert "openCheckout(b.dataset.url" in JS
