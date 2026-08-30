# -*- coding: utf-8 -*-
"""O karaokê desenhava o `stacked` POR CIMA dele.

Achado em 30/08 varrendo os 15 estilos contra o Remotion: catorze ficaram
entre 0,93 e 1,04 de razão de tinta, e o karaokê deu **2,557** — duas
legendas na tela ao mesmo tempo.

Eram dois defeitos que só doem juntos:

  1. `_montar_tudo` zerava `self.cues` em TODO estilo menos o karaokê, então
     o laço de cues desenhava o stacked em cima dele. No template o
     `<Karaoke/>` é o `else` do despachante — nada mais desenha legenda.
  2. `run_fast` só escrevia `caption-cues.json` vazio **se ele não
     existisse**. Num projeto já renderizado em `stacked` que depois trocou
     de estilo, o arquivo antigo ficava — e era ele que alimentava (1).

Depois do conserto: 2,557 -> **1,010** (p5 1,00 · p95 1,03).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def test_todo_estilo_zera_as_cues():
    """A regra é do despachante inteiro, não de um estilo: quem monta a
    própria legenda não deixa o laço de cues desenhar outra por cima."""
    i = PY.index("def _montar_tudo")
    bloco = PY[i:PY.index("for cue in self.cues:", i)]
    ramos = [j for j in range(len(bloco)) if bloco.startswith("elif estilo", j)]
    # 4 `elif` + o `if` do primeiro estilo
    assert len(ramos) == 4, f"o despachante mudou: {len(ramos)} ramos"
    ramos.insert(0, bloco.index("if estilo == "))
    for n, j in enumerate(ramos):
        fim = ramos[n + 1] if n + 1 < len(ramos) else len(bloco)
        cabeca = bloco[j:bloco.index(":", j)]
        assert "self.cues = []" in bloco[j:fim], f"não zera as cues: {cabeca}"


def test_o_arquivo_de_cues_nao_sobrevive_a_troca_de_estilo():
    """"vazio se não existir" deixava as cues do stacked para trás."""
    i = RUN.index('cap_style = preset.get("captions")')
    bloco = RUN[i:i + 1500]
    assert 'if not cues.exists():' not in bloco, "voltou o vazio condicional"
    assert '(public / "caption-cues.json").write_text("[]", encoding="utf-8")' in bloco
