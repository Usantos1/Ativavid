# -*- coding: utf-8 -*-
"""O aviso de versão nova diz O QUE mudou.

Conferido na máquina do usuário, com ele na 4.07 e a 4.09 publicada:

    {"updateAvailable": true, "message": "Nova versão 4.09 disponível",
     "notes": []}

`notes` vazio — o aviso dizia que existe versão nova e não dizia nada
sobre ela. `_resumo_das_notas` só entendia LISTA (`- ` / `* `) e o corpo
das releases era uma frase corrida. Aviso mudo é quase o mesmo que não
avisar.

O texto certo já existia, no CHANGELOG, escrito para ele —
`tools/notas_da_versao.py` tira a seção da versão para virar o corpo da
release.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from app.update_check import _resumo_das_notas  # noqa: E402
from notas_da_versao import secao  # noqa: E402

CHANGELOG = """# Changelog

## 4.09

- **Primeira nota.** Continua nesta linha aqui.
- **Segunda nota.** Outro texto.

## 4.08

- **Nota da versão anterior.**
"""


def test_corpo_com_lista_vira_notas():
    n = _resumo_das_notas("- Primeira coisa.\n- Segunda coisa.\n- Terceira.")
    assert n == ["Primeira coisa.", "Segunda coisa.", "Terceira."]


def test_corpo_SEM_lista_tambem_vira_notas():
    """Era o caso real: o corpo da release era uma frase corrida."""
    n = _resumo_das_notas(
        "A recusa da IA não vira mais a legenda do post; a lista de "
        "prontos mostra o vídeo.")
    assert len(n) == 1 and "recusa da IA" in n[0]


def test_titulo_de_markdown_nao_vira_nota():
    n = _resumo_das_notas("## 4.09\n\n- Uma nota de verdade.")
    assert n == ["Uma nota de verdade."]


def test_corpo_vazio_nao_inventa():
    assert _resumo_das_notas("") == []
    assert _resumo_das_notas(None) == []


def test_a_secao_do_changelog_sai_inteira():
    s = secao("4.09", CHANGELOG)
    assert "Primeira nota" in s and "Segunda nota" in s
    assert "versão anterior" not in s, "vazou para a seção seguinte"


def test_secao_inexistente_devolve_vazio():
    assert secao("9.99", CHANGELOG) == ""


def test_a_versao_pode_vir_com_v():
    assert secao("v4.08", CHANGELOG).startswith("- **Nota da versão anterior")


def test_o_changelog_de_verdade_tem_a_versao_atual():
    """Release sem seção no CHANGELOG sai com aviso mudo."""
    versao = (REPO / "VERSION").read_text(encoding="utf-8").strip()
    assert secao(versao), f"CHANGELOG.md sem seção `## {versao}`"


def test_nenhuma_secao_do_changelog_esta_vazia():
    """Cabeçalho repetido some do aviso sem dar erro.

    Cinco versões (5.0.53 a 5.0.57) saíram com `## X` escrito duas vezes
    seguidas. O `secao()` casa o PRIMEIRO e para no `##` seguinte — que era
    a cópia —, então devolvia string vazia e o aviso de versão nova ficava
    mudo justamente nas versões com novidade. Só a versão publicada naquele
    dia era conferida; as anteriores, nunca mais.
    """
    import re

    texto = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    versoes = re.findall(r"^##\s+(\d+\.\d+\.\d+)\s*$", texto, re.M)
    assert len(versoes) == len(set(versoes)), (
        f"cabeçalho repetido: "
        f"{sorted({v for v in versoes if versoes.count(v) > 1})}")
    vazias = [v for v in versoes if not secao(v, texto)]
    assert not vazias, f"seções sem texto no CHANGELOG: {vazias}"
