# -*- coding: utf-8 -*-
"""Abertura com a manchete sozinha: centro da tela, legenda depois.

Pedido do usuário (29/08): "a headline começa do segundo zero até 4
segundos, e ela deve ser no centro da tela, e depois destes segundos pode
começar a legenda".

Nesses primeiros segundos a legenda repetiria, palavra por palavra, o que
a manchete já diz em corpo grande — por isso ela espera.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.run_fast import _hook_end_sec, _legenda_comeca_depois  # noqa: E402


def _cue(ini_ms, fim_ms, palavras):
    return {"startMs": ini_ms, "endMs": fim_ms,
            "lines": [[{"text": t, "fromMs": a, "toMs": b}
                       for t, a, b in palavras]]}


def _cues(tmp: Path, lista):
    (tmp / "caption-cues.json").write_text(json.dumps(lista), encoding="utf-8")


def test_a_legenda_anterior_a_manchete_sai():
    tmp = Path(tempfile.mkdtemp())
    try:
        _cues(tmp, [
            _cue(200, 1800, [("Fala", 200, 900), ("turma", 900, 1800)]),
            _cue(5000, 6000, [("depois", 5000, 6000)]),
        ])
        assert _legenda_comeca_depois(tmp, 4.0) == 1
        restou = json.loads((tmp / "caption-cues.json").read_text(encoding="utf-8"))
        assert len(restou) == 1 and restou[0]["startMs"] == 5000
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_cue_que_atravessa_a_fronteira_e_aparada():
    """Ela não é jogada fora: começa no limite, sem as palavras de trás."""
    tmp = Path(tempfile.mkdtemp())
    try:
        _cues(tmp, [_cue(3000, 5200, [("antes", 3000, 3900),
                                      ("depois", 4200, 5200)])])
        _legenda_comeca_depois(tmp, 4.0)
        c = json.loads((tmp / "caption-cues.json").read_text(encoding="utf-8"))[0]
        assert c["startMs"] == 4000.0
        palavras = [w["text"] for linha in c["lines"] for w in linha]
        assert palavras == ["depois"], palavras
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_sem_o_pedido_nada_muda():
    tmp = Path(tempfile.mkdtemp())
    try:
        _cues(tmp, [_cue(200, 1800, [("Fala", 200, 1800)])])
        assert _legenda_comeca_depois(tmp, 0) == 0
        assert len(json.loads((tmp / "caption-cues.json").read_text(encoding="utf-8"))) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_quatro_segundos_no_video_do_usuario():
    """`curta` já dá 0→4s em vídeo de 16s ou mais — que é o caso dele."""
    assert _hook_end_sec("realce", {"headlineDuration": "curta"}, 37.0) == 4.0
    assert _hook_end_sec("realce", {"headlineDuration": "curta"}, 8.0) == 2.0


def test_tempo_exato_em_segundos_por_preset():
    """"quero poder ajustar o tempo da headline na tela em segundos, por
    preset / empresa" (03/09). `headlineSeconds` manda; vazio = faixas."""
    assert _hook_end_sec("realce", {"headlineSeconds": 6}, 37.0) == 6.0
    assert _hook_end_sec("realce", {"headlineSeconds": "2,5"}, 37.0) == 2.5, "virgula do BR"
    assert _hook_end_sec("realce", {"headlineSeconds": 60}, 20.0) == 20.0, "nunca passa do video"
    assert _hook_end_sec("realce", {"headlineSeconds": 0.1}, 20.0) == 0.5, "piso de meio segundo"
    assert _hook_end_sec("realce", {"headlineSeconds": "", "headlineDuration": "curta"}, 37.0) == 4.0
    assert _hook_end_sec("realce", {"headlineSeconds": "abc"}, 37.0) == 4.0
    assert _hook_end_sec("pilula", {"headlineSeconds": 3}, 37.0) == 37.0, "pilula e barra de contexto: video todo"
    from app.brand_presets import STYLE_KEYS
    assert "headlineSeconds" in STYLE_KEYS, "sem isso o preset nao guarda o tempo"
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert 'id="autoHlSeconds"' in html
    assert "['autoHlSeconds', 'headlineSeconds', '']" in js and "['autoHlSeconds', 'headlineSeconds']" in js


def test_o_centro_chega_aos_dois_motores():
    ed = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert '"centro": str(preset.get("headlinePos")' in ed
    rp = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = rp.index('if hook.get("centro")')
    assert "self.h - len(linhas) * lh * tam" in rp[i:i + 240], rp[i:i + 240]
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "const envolucro" in tsx and "H.centro" in tsx
    # Contado, nao fixo: o numero cresce a cada estilo novo, e o que importa
    # e que nenhum ramo abra o quadro com estilo proprio — quem faz isso
    # ignora o "centro" e a manchete nasce no alto mesmo com ele marcado.
    # So o corpo do HookInner: `flex-end` tambem aparece em outras partes
    # do arquivo, que nao tem nada com a manchete.
    corpo = tsx[tsx.index("const HookInner"):tsx.index("const HookIntro")]
    ramos = corpo.count("if (styleId === '")
    # um envolucro por ramo, mais o caso de sobra, menos a `manchete` — que
    # ancora na BASE de proposito
    assert corpo.count("<AbsoluteFill style={envolucro}>") == ramos, (
        f"{ramos} ramos de headline, "
        f"{corpo.count('<AbsoluteFill style={envolucro}>')} com o centro")
    assert corpo.count("justifyContent: 'flex-end', alignItems: 'center'") == 1, (
        "so a manchete ancora na base; um segundo caso ficaria sem o centro")
