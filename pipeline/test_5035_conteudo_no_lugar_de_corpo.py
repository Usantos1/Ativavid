# -*- coding: utf-8 -*-
"""5.0.35: o papel do meio chama-se "Conteúdo" na tela.

Ele (04/09): "corpo não pega bem falar que vou gravar o corpo". Escolheu
"Conteúdo" entre Meio, Miolo e Recheio — e o motivo de peso: começa com C,
então o código dos vídeos (G4 · C3 · CTA1) e os arquivos "c1…" já gravados
continuam batendo.

A regra: muda o que se LÊ; ids, prefixo e rótulo do código ficam.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def _multi_html():
    i = HTML.index('data-papel="gancho"')
    return HTML[i - 1200:i + 1400]


def test_a_caixa_do_meio_diz_conteudos():
    bloco = _multi_html()
    assert "<h4>Conteúdos</h4>" in bloco
    assert "<h4>Corpos</h4>" not in bloco


def test_a_ordem_na_tela_e_gancho_conteudo_cta():
    assert "gancho → conteúdo → CTA" in HTML
    assert "gancho → corpo → CTA" not in HTML
    assert "gancho → conteúdo → CTA" in SJS
    assert "gancho → corpo → CTA" not in SJS


def test_a_contagem_fala_conteudo():
    assert "conteúdo(s) ×" in SJS and "corpo(s) ×" not in SJS


def test_nenhum_texto_visivel_do_hub_diz_corpo():
    """Texto entre tags e strings de toast/textContent do Multiplicador —
    `corpo` como id de dado continua permitido."""
    bloco = _multi_html()
    visivel = re.sub(r"<[^>]+>", " ", re.sub(r"<!--.*?-->", " ", bloco, flags=re.S))
    assert not re.search(r"\bcorpos?\b", visivel, re.I), visivel[:300]


def test_os_ids_e_o_codigo_continuam_com_c():
    from app.multiplicador import PAPEIS, _PREFIXO, _ROTULO, validar, MultiplicadorInvalido
    assert PAPEIS == ("gancho", "corpo", "cta")
    assert _PREFIXO["corpo"] == "c" and _ROTULO["corpo"] == "C"
    assert 'data-papel="corpo"' in HTML, "o id da caixa não pode mudar (o JS e a API usam)"
    import pytest
    with pytest.raises(MultiplicadorInvalido, match="conteúdo"):
        validar({"gancho": ["g1"], "corpo": [], "cta": ["a1"]})
