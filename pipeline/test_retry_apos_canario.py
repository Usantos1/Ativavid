# -*- coding: utf-8 -*-
"""Tentar novamente depois do canário não pode morrer em WinError 32.

O vídeo dele do Fusca (31/08): "Não foi possível concluir este vídeo",
com `result.json` dizendo só "[WinError 32] O arquivo já está sendo usado
por outro processo". Nenhum processo segurava nada.

A cadeia: a validação do canário (`canary_run.py`) economiza a cópia de
160 MB ligando `remotion/public/cut.mp4` ao `cut.mp4` por **hardlink**.
No "Tentar novamente", `ensure_seekable_for_remotion` chama
`shutil.copy2(src, dest)` com os dois nomes apontando para o MESMO inode —
e no Windows isso dá exatamente o WinError 32 (reproduzido à parte com um
arquivo qualquer). Pior: no caminho de reencode, o ffmpeg escreveria por
cima do arquivo que está lendo.

Estes testes usam arquivos de verdade (ffmpeg gera os vídeos), porque o
defeito mora no sistema de arquivos, não na lógica.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))

from remotion_gate import ensure_seekable_for_remotion  # noqa: E402

FFMPEG = shutil.which("ffmpeg")


def _video(dest: Path, g: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=64x64:rate=12",
         "-c:v", "libx264", "-g", str(g), "-pix_fmt", "yuv420p", str(dest)],
        check=True)


@pytest.mark.skipif(not FFMPEG, reason="sem ffmpeg")
def test_dest_hardlink_do_src_nao_explode(tmp_path):
    """O caso do Fusca: keyframes densos, dest JA e o proprio cut."""
    src = tmp_path / "cut.mp4"
    _video(src, g=6)   # gap curto -> caminho da copia
    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    dest = pub / "cut.mp4"
    os.link(src, dest)
    antes = src.stat().st_size
    ensure_seekable_for_remotion(src, dest)   # antes: WinError 32 aqui
    assert dest.exists() and src.stat().st_size == antes
    assert os.path.samefile(src, dest), "denso: o proprio arquivo ja serve"


@pytest.mark.skipif(not FFMPEG, reason="sem ffmpeg")
def test_reencode_sobre_hardlink_nao_come_a_fonte(tmp_path):
    """Keyframes esparsos + hardlink: o ffmpeg NAO pode escrever por cima
    do arquivo que esta lendo — o link tem de ser quebrado antes."""
    src = tmp_path / "cut.mp4"
    _video(src, g=999)  # 1 keyframe so -> gap grande -> reencode
    pub = tmp_path / "remotion" / "public"
    pub.mkdir(parents=True)
    dest = pub / "cut.mp4"
    os.link(src, dest)
    antes = src.stat().st_size
    ensure_seekable_for_remotion(src, dest, fps=12.0)
    assert src.stat().st_size == antes, "a fonte nao pode mudar"
    assert dest.exists() and not os.path.samefile(src, dest)


def test_o_conserto_esta_no_lugar():
    s = (REPO / "helpers" / "remotion_gate.py").read_text(encoding="utf-8")
    i = s.index("def ensure_seekable_for_remotion(")
    bloco = s[i:s.index("\ndef lock_dir", i)]
    assert "os.path.samefile(src, dest)" in bloco
    assert bloco.index("samefile") < bloco.index("shutil.copy2"), \
        "a checagem tem de vir antes da copia"
