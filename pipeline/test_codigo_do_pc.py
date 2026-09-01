# -*- coding: utf-8 -*-
"""O cliente precisa conseguir DIZER qual computador e o dele.

Pergunta dele em 31/08, olhando o painel: "como o cliente vai ver esse
win-8256b455…?". Resposta ate a 4.37: nao via. O id so aparecia em dois
lugares — o dialogo de admin (que e dele, nao do cliente) e o botao de
suporte, que so aparece para quem JA paga. Ou seja: quem precisa se
identificar para comprar, destravar ou pedir ajuda nao tinha o numero.

Agora o codigo curto (`8256B455`) aparece na tela da licenca E na janela
que abre quando ele esbarra no bloqueio, com um botao que copia o id
INTEIRO — que e o que o painel precisa para bloquear ou liberar. Do lado
dele, a lista de maquinas mostra o mesmo codigo curto e tem busca.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
import sys
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
from pipeline.ancoras import bloco_da_funcao  # noqa: E402
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")

NODE = shutil.which("node")


def _rodar(entradas: list[str]) -> list[str]:
    """Roda a funcao DE VERDADE, tirada do studio.js."""
    i = JS.index("function codigoDoPc(")
    fonte = JS[i:JS.index("\n}", i) + 2]
    script = fonte + "\nconsole.log(JSON.stringify(" \
        + json.dumps(entradas) + ".map(codigoDoPc)));"
    r = subprocess.run([NODE, "-e", script], capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.mark.skipif(not NODE, reason="node nao esta no PATH")
def test_o_codigo_curto_e_ditavel_e_identifica_a_maquina():
    saida = _rodar([
        "win-8256b455-cd50-4270-b5b2-4312f8a1b2c3",   # o PC da pergunta
        "win-c87046e3-96e1-48b5-881b-72aa0b1c2d3e",   # o laptop dele
        "av-9f2c1d3e4a5b6c7d8e9f0a1b2c3d4e5f",        # sem MachineGuid
        "",
        None,
    ])
    assert saida[0] == "8256B455"
    assert saida[1] == "C87046E3"
    assert saida[0] != saida[1], "duas maquinas nao podem ter o mesmo codigo"
    assert saida[2] == "9F2C1D3E"
    assert saida[3] == "" and saida[4] == ""
    for cod in saida[:3]:
        assert len(cod) == 8 and cod.isalnum()


def test_o_codigo_aparece_onde_o_cliente_esta():
    """A janela do bloqueio e a tela da licenca — os dois lugares em que
    ele pode estar quando precisa se identificar."""
    i = HTML.index('id="dlgLicense"')
    dialogo = HTML[i:HTML.index("</dialog>", i)]
    assert 'id="licDlgPcCod"' in dialogo and 'id="btnLicDlgPcCopiar"' in dialogo
    i = HTML.index('id="licenseDevice"')
    caixa = HTML[i:HTML.index("</div>", HTML.index('id="licPcFull"'))]
    assert 'id="licPcCod"' in caixa and 'id="btnLicPcCopiar"' in caixa


def test_copiar_manda_o_ID_INTEIRO_e_nao_o_codigo_curto():
    """O painel bloqueia pelo id completo; colar o codigo curto no suporte
    daria uma busca, nunca uma acao."""
    i = JS.index("async function copiarCodigoDoPc()")
    bloco = JS[i:JS.index("\nfunction renderSuporte", i)]
    assert "state.license && state.license.deviceId" in bloco
    assert "codigoDoPc" not in bloco, "copiaria o codigo curto"


def test_a_janela_do_bloqueio_preenche_o_codigo_ao_abrir():
    bloco = bloco_da_funcao(JS, "openLicenseDialog")
    assert bloco.index("mostrarCodigoDoPc(L)") < bloco.index("dlg.showModal()")


def test_o_painel_acha_a_maquina_pelo_codigo_ditado():
    i = JS.index("async function loadAberturas()")
    bloco = JS[i:JS.index("\nfunction wireAberturas", i)]
    assert "adminAberturasBusca" in bloco
    assert "codigoDoPc(m.deviceId).toLowerCase().includes(filtro)" in bloco
    assert "visiveis.map" in bloco, "a tabela tem de desenhar o resultado filtrado"
