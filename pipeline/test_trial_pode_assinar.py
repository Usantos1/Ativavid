# -*- coding: utf-8 -*-
"""Quem está no teste também pode comprar.

Pergunta dele em 31/08, olhando a tela de um PC em trial: "no trial ele
não pode assinar o pro anual?". Não podia. A faixa de compra aparecia com
`needsPay = !entitled` — e no trial a pessoa ESTÁ entitled. Ou seja: quem
se convenceu no segundo dia não tinha botão nenhum; precisava esperar o
teste vencer e ser BARRADO para poder pagar. Venda perdida por desenho.

Agora a faixa aparece no teste, com o prazo no recado ("Seu teste acaba em
3 dias"), e some para quem já tem licença ativa. Admin continua sem ver —
o dono não compra do próprio produto.

Conferido ao vivo com o app servindo um trial de 3 dias:
  cliente  -> "R$ 399 / ano · Seu teste acaba em 3 dias..." + Assinar agora
  admin    -> faixa escondida
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _bloco() -> str:
    i = JS.index("function syncLicenseChrome()")
    return JS[i:JS.index("\n/* Contato do dono", i)]


def test_o_teste_ve_a_faixa_de_compra():
    b = _bloco()
    assert 'const noTeste = lic.mode === "trial";' in b
    assert "const mostraCompra = needsPay || (!isAdmin && lic.configured && noTeste);" in b
    assert "pay.hidden = !mostraCompra" in b


def test_o_dono_nao_ve():
    """Admin nao compra do proprio produto."""
    b = _bloco()
    i = b.index("const mostraCompra")
    assert "!isAdmin" in b[i:i + 120]


def test_o_recado_diz_quanto_falta():
    b = _bloco()
    assert "lic.trialDaysLeft" in b
    assert "Seu teste acaba" in b
    assert "acaba amanhã" in b, "1 dia no plural fica errado"


def test_sem_link_o_botao_nao_existe():
    """Botao que leva a um toast de desculpa e pior que botao nenhum —
    foi o que a 4.41 consertou no `license_config.json`."""
    b = _bloco()
    assert "btnComprar.hidden = !lic.checkoutUrl" in b


def test_quem_ja_pagou_nao_ve_oferta():
    b = _bloco()
    # licensed/account nao entram: needsPay exige !entitled e noTeste exige trial
    assert 'lic.mode === "trial"' in b
    assert "!lic.entitled" in b
