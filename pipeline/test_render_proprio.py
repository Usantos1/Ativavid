# -*- coding: utf-8 -*-
"""Renderizador próprio (app/render_proprio): gate, contrato e motores."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.render_proprio import (  # noqa: E402
    Renderizador,
    motivo_nao_suportado,
    render_overlay_proprio,
)

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def _ed(**mud) -> dict:
    base = {"width": 1080, "height": 1920, "fps": 30,
            "captions": {"style": "stacked"},
            "hook": {"enabled": True, "style": "realce", "lines": ["a", "b"],
                     "endSec": 2.0, "accent": "#e30004"},
            "endCard": {"enabled": True, "lines": ["Segue @x", "direct"],
                        "lastSec": 1.0, "dim": 0.82}}
    base.update(mud)
    return base


def _public(tmp_path: Path, cues=None) -> Path:
    pub = tmp_path / "public"
    pub.mkdir(parents=True, exist_ok=True)
    if cues is None:
        cues = [{"i": 0, "preset": "STACK_MIXED", "exit": "blur_up",
                 "startMs": 0, "endMs": 900, "styleOffset": 0,
                 "lines": [[{"text": "Olá", "fromMs": 0, "toMs": 400}]]}]
    (pub / "caption-cues.json").write_text(json.dumps(cues), encoding="utf-8")
    return pub


# ------------------------------------------------------------------- gate ----
def test_projeto_padrao_e_suportado(tmp_path):
    assert motivo_nao_suportado(_ed(), _public(tmp_path)) is None


def test_gate_derruba_o_que_nao_desenha(tmp_path):
    pub = _public(tmp_path)
    casos = [
        (_ed(captions={"style": "impacto"}), "estilo de legenda"),
        (_ed(hook={"enabled": True, "style": "card", "lines": ["a"]}), "headline"),
        (_ed(elements={"listCounter": True}), "contador"),
        (_ed(elements={"emojiCaptions": True}), "emoji"),
        (_ed(inserts=[{"file": "x.png"}]), "inserts"),
        (_ed(width=720), "resolucao"),
        (_ed(endCard={"enabled": True, "logo": "logo.png"}), "logo"),
    ]
    for ed, trecho in casos:
        motivo = motivo_nao_suportado(ed, pub)
        assert motivo and trecho in motivo, (trecho, motivo)


def test_preset_desconhecido_derruba(tmp_path):
    pub = _public(tmp_path, cues=[{"i": 0, "preset": "NOVO_ESTILO",
                                   "startMs": 0, "endMs": 500,
                                   "lines": [[{"text": "x", "fromMs": 0}]]}])
    assert "preset" in (motivo_nao_suportado(_ed(), pub) or "")


def test_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("ATIVAVID_RENDER_PROPRIO", "0")
    assert "desligado" in motivo_nao_suportado(_ed(), _public(tmp_path))


# ---------------------------------------------------------------- contrato ----
def test_render_produz_overlay_com_os_quadros_pedidos(tmp_path):
    """Smoke real: 20 quadros, 1 legenda + headline + cartão."""
    pub = _public(tmp_path)
    out = tmp_path / "overlay.mov"
    render_overlay_proprio(pub, _ed(), frames=20, fps=30.0,
                           width=1080, height=1920, out=out)
    assert out.exists() and out.stat().st_size > 1000
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, **NOWIN)
    # first_record: a saída pode vir repetida (stream group)
    primeiro = next(l for l in r.stdout.splitlines() if l.strip())
    assert int(primeiro.strip().rstrip(",")) == 20


def test_overlay_tem_alpha_e_tinta_onde_deve(tmp_path):
    pub = _public(tmp_path)
    out = tmp_path / "overlay.mov"
    render_overlay_proprio(pub, _ed(hook={"enabled": False},
                                    endCard={"enabled": False}),
                           frames=12, fps=30.0, width=1080, height=1920, out=out)
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(out), "-vf", "select=eq(n\\,8)",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True, **NOWIN)
    import numpy as np
    q = np.frombuffer(r.stdout, dtype=np.uint8).reshape(1920, 1080, 4)
    assert (q[..., 3] > 8).sum() > 500, "a legenda 'Olá' tem de aparecer"
    assert (q[:900, :, 3] > 8).sum() == 0, "acima da faixa deve ser transparente"


def test_fps_diferente_muda_o_relogio(tmp_path):
    """Projetos de câmera são 24 fps — o tempo em quadros muda junto."""
    pub = _public(tmp_path)
    r30 = Renderizador(pub, _ed(hook={"enabled": False}, endCard={"enabled": False}),
                       frames=30, fps=30.0)
    r24 = Renderizador(pub, _ed(hook={"enabled": False}, endCard={"enabled": False}),
                       frames=24, fps=24.0)
    # a mesma cue de 900 ms termina em quadros diferentes
    assert r30.camadas[0].fim_f == int(0.9 * 30)
    assert r24.camadas[0].fim_f == int(0.9 * 24)


def test_sfx_eventos_seguem_o_template(tmp_path):
    cues = [
        {"i": 0, "preset": "SOLO_OUTLINE", "startMs": 0, "endMs": 500,
         "lines": [[{"text": "Não", "fromMs": 0}]]},
        {"i": 1, "preset": "STACK_MIXED", "startMs": 600, "endMs": 1200,
         "lines": [[{"text": "oi", "fromMs": 600}]]},
    ]
    r = Renderizador(_public(tmp_path, cues), _ed(endCard={"enabled": False}),
                     frames=40, fps=30.0)
    nomes = [e[0] for e in r.eventos_sfx]
    assert nomes.count("whoosh.mp3") == 1          # headline
    assert nomes.count("caption-click.mp3") == 2   # uma por cue
    assert nomes.count("caption-scratch.mp3") == 1  # so no Recorte
    vols = {e[0]: e[2] for e in r.eventos_sfx if e[0] == "caption-click.mp3"}


# ------------------------------------------------------------------ motores ----
def test_motores_diferentes_nunca_se_emendam():
    from app.overlay_path import _incremental_ranges

    velho = {"_template": "t", "_engine": "remotion",
             "edit-data.json": {}, "captions.json": [], "caption-cues.json": []}
    novo = dict(velho, _engine="proprio")
    assert _incremental_ranges(velho, novo, 30.0, 100) is None
