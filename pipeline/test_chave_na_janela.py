# -*- coding: utf-8 -*-
"""A chave de ativação só aparece para quem diz que tem uma.

Pedido dele em 31/08, com o print da tela de licença na frente: a caixa
"Chave de ativação" ocupava o mesmo peso do preço para TODO mundo — e ela
serve para a minoria que comprou fora do app. Agora ela vive numa janela,
aberta pelo botão "Tenho uma chave".

De quebra, o botão fazia coisa errada: ele tentava ativar o que estivesse
na caixa (vazia) e devolvia "Falha ao ativar" para quem só queria ver onde
digitar.

E o plano ganhou NOME antes do preço ("Pro anual · R$ 399 / ano"): sem
nome era só um número, e é o nome que deixa caber mais de um plano na
mesma tela depois.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_a_caixa_saiu_da_tela():
    assert "licClientKeyCard" not in HTML
    assert "licClientKeyCard" not in JS


def test_a_janela_existe_e_tem_o_necessario():
    i = HTML.index('id="dlgChave"')
    bloco = HTML[i:HTML.index("</dialog>", i)]
    assert 'id="licenseKeyInput"' in bloco
    assert 'id="btnLicenseActivateInline"' in bloco
    assert 'id="btnChaveCancelar"' in bloco, "sem saida, so o Esc"


def test_tenho_uma_chave_ABRE_a_janela_em_vez_de_ativar_vazio():
    i = JS.index('const btnLicAct = $("#btnLicenseActivate")')
    bloco = JS[i:i + 900]
    assert "showModal()" in bloco
    assert "campo?.focus()" in bloco
    # o defeito antigo: chamar a ativacao direto do botao
    assert "return activateFromInput()" not in bloco


def test_a_janela_fecha_quando_a_chave_vale():
    i = JS.index('const btnLicActInline = $("#btnLicenseActivateInline")')
    bloco = JS[i:i + 700]
    assert "state.license || {}).entitled" in bloco
    assert "d.close()" in bloco


def test_o_plano_tem_nome_antes_do_preco():
    i = JS.index("const nome = lic.planLabel")
    bloco = JS[i:i + 300]
    assert '"Pro anual"' in bloco
    assert "${nome} · ${preco}" in bloco
