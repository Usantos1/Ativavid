# -*- coding: utf-8 -*-
"""Take de vídeo da Biblioteca vira b-roll de verdade.

O usuário guarda takes curtos (reação, meme, piada — "quando alguém dá uma
patada, entra o cavalo dando patada") para a IA usar no meio da fala. Três
coisas precisavam ser verdade ao mesmo tempo, e nenhuma era:

1. o pipeline descartava clipe (`kind != "image"` → `continue`);
2. o `InsertCard` do template só sabia desenhar `<Img>`;
3. o b-roll procurava a biblioteca em `Path.home()`, e no C: do usuário
   sobrou uma pasta Biblioteca VAZIA (os Projetos são um junction para o
   E:) — a mesma armadilha que a 3.03 consertou na trilha.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def test_pipeline_aceita_clipe_como_broll():
    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index("def _attach_auto_broll")
    j = s.index("\ndef ", i + 10)
    bloco = s[i:j]
    assert '.mp4' in bloco and '.mov' in bloco, "clipe não entra no b-roll"
    assert 'it.get("kind") != "image"' not in bloco, \
        "o clipe voltou a ser descartado"
    assert '"kind": "video" if video else "image"' in bloco


def test_broll_procura_a_biblioteca_da_raiz_dos_projetos():
    """`Path.home()` aponta para a cópia MORTA no C:."""
    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index("def _attach_auto_broll")
    j = s.index("\ndef ", i + 10)
    bloco = s[i:j]
    assert "pick_for_query(query, projects_root=" in bloco, bloco[:400]
    assert "public.parents[3]" in bloco


def test_template_toca_o_take():
    s = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(
        encoding="utf-8")
    assert "const ehVideo" in s
    i = s.index("const InsertCard")
    trecho = s[i:s.index("const Inserts", i)]   # a funcao inteira, nao uma janela fixa
    assert "ehVideo(src)" in trecho and "OffthreadVideo" in trecho, trecho[:300]
    assert "muted" in trecho, "o som do take passaria por cima da fala"


def test_motor_proprio_recusa_insert_de_video_em_vez_de_ignorar():
    """Ele só sabe desenhar imagem parada: recusar custa tempo de render,
    fingir que sabe custa o take (sai vídeo sem o b-roll, calado)."""
    from app.render_proprio import motivo_nao_suportado
    base = {"captions": {"enabled": False, "style": "karaoke"},
            "width": 1080, "height": 1920}
    com_video = dict(base, inserts=[{"src": "pexels/lib-cavalo.mp4",
                                     "start": 1.0, "end": 3.0}])
    motivo = motivo_nao_suportado(com_video, REPO / "assets")
    assert motivo and "insert de video" in motivo, motivo
    com_foto = dict(base, inserts=[{"src": "pexels/lib-produto.jpg",
                                    "start": 1.0, "end": 3.0}])
    assert "insert de video" not in (motivo_nao_suportado(com_foto,
                                                          REPO / "assets") or "")
