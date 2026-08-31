# -*- coding: utf-8 -*-
"""Quem esbarra no bloqueio precisa ter como pagar.

Montando o checkout da Stripe em 31/08 (produto ATIVAVID — Licença anual,
R$ 399/ano recorrente, link de pagamento e webhook), apareceu o furo que
tornaria tudo inútil: o `license_config.json` — o arquivo que vai dentro de
CADA instalação — tinha `checkoutUrl` vazio. O botão "Assinar agora" só
aparece quando esse campo existe (`pay.hidden = !L.checkoutUrl`), então o
cliente com trial vencido via a janela da licença sem uma forma de comprar.

Silencioso dos dois lados: ele não via botão, e nada avisava o dono.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
DOUTOR = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")


def test_o_botao_de_assinar_depende_do_link():
    """Se esta regra mudar, o teste abaixo perde o sentido."""
    i = JS.index("function openLicenseDialog(")
    bloco = JS[i:JS.index("\nfunction openCheckout(", i)]
    assert "anual.hidden = !L.checkoutUrl" in bloco
    assert "mensal.hidden = !L.checkoutUrlMensal" in bloco


def test_o_doutor_avisa_quando_nao_ha_como_pagar():
    i = DOUTOR.index("def checar_caminho_de_pagamento(")
    bloco = DOUTOR[i:DOUTOR.index("\ndef checar_motor_rapido", i)]
    assert "Sem link de pagamento" in bloco
    # o caso que morde: link só na máquina do dono, vazio na build
    assert "bundled_license_config()" in bloco
    assert "Link de pagamento so nesta maquina" in bloco


def test_a_checagem_roda_no_diagnostico():
    i = DOUTOR.index("for fn in (checar_programas")
    assert "checar_caminho_de_pagamento" in DOUTOR[i:i + 400]


def test_o_link_do_cliente_vem_da_build_e_nao_da_maquina_do_dono():
    """`load_settings` deixa o bundled MANDAR: o que vale para o cliente e o
    que foi empacotado, nao o que alguem salvou nas configuracoes."""
    src = (REPO / "app" / "settings_store.py").read_text(encoding="utf-8")
    i = src.index("def load_settings")
    bloco = src[i:i + 1200]
    assert "data.update(bundled_license_config())" in bloco
