# -*- coding: utf-8 -*-
"""5.0.51: quatro transições e quatro estilos de cor novos.

"QUERO MAIS TRANSICOES E MAIS ESTILOS DE CORES" (05/09, 03h50). As
transições seguem a regra das outras quatro: catálogo único
(`app/transicoes.py`), desenho no template E no motor rápido, opção no
editor, nome no cartão do preset, cor da marca declarada. Os looks de cor
são filtros ffmpeg em `helpers/grade.py` — cada um tem de ser aceito pelo
ffmpeg de verdade, senão o vídeo cai sem correção e sem aviso.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

from app.transicoes import NOMES, TIPOS, USAM_A_COR_DA_MARCA  # noqa: E402

NOVAS = ("cortina", "blocos", "moldura", "traco", "cortinalado", "pulso")
CORES_NOVAS = ("frio_limpo", "vibrante", "preto_branco", "vintage", "teal_laranja", "pastel_suave")
TSX = (REPO / "assets" / "shortform" / "src" / "CustomGraphics.tsx").read_text(encoding="utf-8")
PROPRIO = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_catalogo_e_tipos():
    for t in NOVAS:
        assert t in NOMES and t in TIPOS
    assert USAM_A_COR_DA_MARCA == {"faixa", "cortina", "blocos", "moldura", "cortinalado", "pulso"}
    assert "traco" not in USAM_A_COR_DA_MARCA, "o traco e branco, como o flash"


def test_os_dois_motores_desenham_as_quatro():
    for t in NOVAS:
        assert f"tipo === '{t}'" in TSX, f"o template nao desenha `{t}`"
        assert f'"{t}"' in PROPRIO, f"motor proprio sem `{t}`"
    assert "'cortina' | 'blocos' | 'moldura' | 'traco'" in TSX, "fora do tipo — o tsc reprova"
    assert "| 'cortinalado' | 'pulso'" in TSX
    assert "def _transicao_nova(self, tipo: str, c: int, f: int, k: float):" in PROPRIO


def test_as_novas_ficam_antes_da_faixa_no_motor_proprio():
    # O teste da faixa (5.0.25) recorta o ramo dela entre dois
    # `est = f - (c - FLASH_LEAD)`; um ramo novo no meio quebraria o recorte.
    assert PROPRIO.index('if tipo in ("cortina", "blocos", "moldura", "traco", "cortinalado", "pulso"):') < PROPRIO.index('if tipo == "faixa":')


def test_mesma_conta_nos_dois_motores():
    # cortina: cobre = interp(p, [0, .45, .55, 1], [0, 1, 1, 0]); altura 50% * cobre
    assert "[0, 0.45, 0.55, 1], [0, 1, 1, 0]" in TSX and "[0, 0.45, 0.55, 1], [0, 1, 1, 0]" in PROPRIO
    # blocos: 6x10, instante t0 = ((i*7 + j*13) % 10) / 10 * 0.6, janela 0.4
    assert "(((i * 7 + j * 13) % 10) / 10) * 0.6" in TSX and "((i * 7 + j * 13) % 10) / 10 * 0.6" in PROPRIO
    assert "p < t0 + 0.4" in TSX and "p < t0 + 0.4" in PROPRIO
    # moldura: pico em [c-2, c, c+3] -> 0.9k; espessura 6% da largura
    assert "[c - 2, c, c + 3], [0, 0.9 * k, 0]" in TSX and "[c - 2, c, c + 3], [0, 0.9 * k, 0]" in PROPRIO
    assert "width * 0.06" in TSX and "self.w * 0.06" in PROPRIO
    # cortinalado: mesma cobertura, largura 50% * cobre; pulso: pico do brilho na cor da marca
    assert "self.w * 0.5 * cobre" in PROPRIO and "(50 * cobre).toFixed(2)" in TSX
    assert "[c - 2, c, c + 3], [0, 0.62 * k, 0]" in TSX and "[c - 2, c, c + 3], [0, 0.62 * k, 0]" in PROPRIO
    # traco: giro de -18deg no CSS = +18 no PIL
    i = PROPRIO.index('if tipo == "traco":')
    assert "rotate(\n                18, expand=True" in PROPRIO[i:i + 900] or "rotate(18" in PROPRIO[i:i + 900]


def test_editor_menu_e_cartao_conhecem_as_quatro():
    i = HTML.index('<select id="autoTransicao">')
    bloco = HTML[i:HTML.index("</select>", i)]
    for t in NOVAS:
        assert f'value="{t}"' in bloco, f"`{t}` nao aparece no editor"
        assert f"{t}:" in PJS[PJS.index("const COR_DA_TRANSICAO"):PJS.index("const COR_DA_TRANSICAO") + 500], f"regua sem cor para `{t}`"
    j = SJS.index("  transicao: {")
    for t in NOVAS:
        assert f"{t}:" in SJS[j:j + 400], f"cartao do preset sem nome para `{t}`"


def test_o_motor_rapido_nao_recusa_as_novas():
    # a guarda do motor le NOMES: nova no catalogo = aceita, sem cair no lento
    assert "from app.transicoes import NOMES as TRANSICOES" in PROPRIO


# ------------------------------------------------------------------ cores
def test_estilos_de_cor_no_catalogo_e_no_editor():
    import grade

    for c in CORES_NOVAS:
        assert c in grade.PRESETS and grade.get_preset(c), c
    i = HTML.index('<select id="autoColorGrade"')
    bloco = HTML[i:HTML.index("</select>", i)]
    for c in CORES_NOVAS:
        assert f'value="{c}"' in bloco, f"`{c}` nao aparece no editor"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="sem ffmpeg")
@pytest.mark.parametrize("nome", CORES_NOVAS)
def test_o_ffmpeg_aceita_cada_look(nome):
    """Filtro com erro de sintaxe derruba o render ou sai sem correcao — e
    ninguem ve. O ffmpeg de verdade e o unico juiz."""
    import grade

    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=gray:s=64x64:d=0.1", "-vf", grade.get_preset(nome), "-f", "null", "-"],
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[:300]
