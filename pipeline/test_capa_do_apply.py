# -*- coding: utf-8 -*-
"""O apply devolve a CAPA embutida que ele perdia.

`seal_delivery_cover` só roda no fim do pipeline completo; o apply refaz o
final.mp4 e o arquivo promovido saía SEM o JPEG anexado (`attached_pic`) — que
é o que o Instagram usa como capa ao postar.

MEDIDO nos entregues do usuário: dos últimos 40 em `publicar/`, os que vieram
só do pipeline tinham a capa (13 de 15); os que passaram por apply tinham
perdido quase todos.

A regra que importa: com `cover.jpg` presente, só o remux barato de anexar —
NUNCA regenerar, porque `cover.jpg` pode ser uma capa que o usuário escolheu
pelo botão Capa do editor, e regenerar atropelava a escolha dele.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _ffmpeg() -> str:
    from app.overlay_compose import _ffmpeg as f

    return f()


def _tem_capa(p: Path) -> bool:
    from app.overlay_compose import probe_json

    st = probe_json(p).get("streams") or []
    return any((s.get("disposition") or {}).get("attached_pic") for s in st)


@pytest.fixture()
def projeto(tmp_path):
    """Um final.mp4 real de 2s + um cover.jpg 'escolhido pelo usuário'."""
    edit = tmp_path / "edit"
    edit.mkdir()
    final = edit / "final.mp4"
    subprocess.run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(final),
    ], check=True, capture_output=True)
    cover = edit / "cover.jpg"
    subprocess.run([
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:size=320x240:duration=0.1",
        "-frames:v", "1", "-q:v", "3", str(cover),
    ], check=True, capture_output=True)
    return edit, final, cover


def _log(msg):
    _log.linhas.append(str(msg))


def test_embute_a_capa_existente_sem_regenerar(projeto):
    from app.apply_execute import _reembutir_capa
    from app.overlay_compose import count_frames

    edit, final, cover = projeto
    bytes_antes = cover.read_bytes()
    quadros_antes = count_frames(final)
    _log.linhas = []
    _reembutir_capa(edit, final, _log)
    assert _tem_capa(final), "o final continua sem a capa embutida"
    assert cover.read_bytes() == bytes_antes, (
        "a capa escolhida pelo usuário foi regenerada"
    )
    assert count_frames(final) == quadros_antes, "o remux mexeu no vídeo"
    assert any("COVER_OK" in ln for ln in _log.linhas)


def test_ja_com_capa_nao_faz_nada(projeto):
    """Idempotente: um segundo apply não remuxa de novo nem loga nada."""
    from app.apply_execute import _reembutir_capa

    edit, final, cover = projeto
    _log.linhas = []
    _reembutir_capa(edit, final, _log)
    mtime = final.stat().st_mtime_ns
    _log.linhas = []
    _reembutir_capa(edit, final, _log)
    assert final.stat().st_mtime_ns == mtime, "remuxou um arquivo que já tinha capa"
    assert not _log.linhas, f"logou sem ter o que fazer: {_log.linhas}"


def test_falha_da_capa_nunca_derruba_o_apply(projeto, tmp_path):
    """A capa é acabamento: o vídeo corrigido já está promovido. Qualquer erro
    aqui vira warning no log, nunca exceção."""
    from app.apply_execute import _reembutir_capa

    edit, final, cover = projeto
    cover.write_bytes(b"nao sou um jpeg")
    _log.linhas = []
    _reembutir_capa(edit, final, _log)   # não pode levantar
    assert any("COVER_WARN" in ln for ln in _log.linhas)
    assert final.stat().st_size > 1000, "o final foi corrompido pela falha"


def test_o_apply_chama_depois_do_promote_e_antes_do_pack():
    """A ordem é o que faz o entregue em publicar/ sair com a capa."""
    src = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")
    i_promote = src.index('log("QUICK_APPLY_PROMOTE_FINAL")')
    i_capa = src.index("_reembutir_capa(edit, live_final, log)")
    i_pack = src.index("hooks.sync_pack(edit, live_final)")
    assert i_promote < i_capa < i_pack, (
        "a capa tem de voltar depois do promote e antes do sync_pack"
    )
