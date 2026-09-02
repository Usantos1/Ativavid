# -*- coding: utf-8 -*-
"""O mix de áudio do corte não pode estourar a linha de comando.

Caso real de 02/09: vídeo de YouTube de 15min virou 280 trechos; os 280
`-i` + o filter_complex passaram dos ~32k caracteres do CreateProcess e o
corte morreu com WinError 206 (a primeira fonte LONGA do usuário — os
reels de <3min nunca chegaram perto). O mix agora soma em LOTES: amix com
normalize=0 é soma pura, então somar por partes e somar as partes dá o
mesmo sinal; o limiter só entra no mix final.
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for _p in (REPO, REPO / "helpers"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _tom(destino: Path, dur: float, freq: int) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi",
         "-i", f"sine=frequency={freq}:duration={dur}:sample_rate=48000",
         "-c:a", "pcm_s16le", str(destino)],
        check=True, capture_output=True)


def _dur_wav(p: Path) -> float:
    with wave.open(str(p), "rb") as w:
        return w.getnframes() / w.getframerate()


def test_lote_grande_mixa_em_partes_e_cobre_o_video_todo(tmp_path, monkeypatch):
    """5 trechos com lote de 2 = 3 parciais + mix final. A duração do wav
    final tem de alcançar o ÚLTIMO trecho (offset + duração), como no
    comando único."""
    import render

    monkeypatch.setattr(render, "_MIX_LOTE", 2)
    work = tmp_path / "clips_graded"
    work.mkdir()
    plan = []
    for k in range(5):
        wav = tmp_path / f"a{k}.wav"
        _tom(wav, 0.3, 300 + 100 * k)
        plan.append({"audio_path": wav, "a_off": 0.5 * k})
    saida = render._mixar_audio(plan, work)
    assert saida.exists()
    # ultimo trecho: offset 2,0s + 0,3s de tom = 2,3s
    assert abs(_dur_wav(saida) - 2.3) < 0.05, _dur_wav(saida)
    # os parciais sao limpos depois do mix final
    assert not list(work.glob("_jcut_mix*.wav"))


def test_lote_pequeno_segue_num_comando_so(tmp_path, monkeypatch):
    import render

    chamadas = []
    real = render._mix_lote

    def espiao(entradas, destino, limitar):
        chamadas.append((len(entradas), limitar))
        real(entradas, destino, limitar)

    monkeypatch.setattr(render, "_mix_lote", espiao)
    work = tmp_path / "clips_graded"
    work.mkdir()
    wav = tmp_path / "a.wav"
    _tom(wav, 0.3, 440)
    render._mixar_audio([{"audio_path": wav, "a_off": 0.0}], work)
    assert chamadas == [(1, True)], chamadas


def test_o_limiter_so_entra_no_mix_final():
    s = (REPO / "helpers" / "render.py").read_text(encoding="utf-8")
    i = s.index("def _mixar_audio")
    bloco = s[i:s.index("\ndef assemble_jcut", i)]
    assert "limitar=False" in bloco and "limitar=True" in bloco
    # e o assemble usa o mix novo em vez do comando gigante
    j = s.index("def assemble_jcut")
    assert "_mixar_audio(plan, work)" in s[j:j + 900]
