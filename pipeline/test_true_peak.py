# -*- coding: utf-8 -*-
"""Pico acima de -1,0 dBTP é defeito de ÁUDIO — a resposta é o áudio.

O app tratava pico alto como "o caminho rápido errou" e devolvia o vídeo
INTEIRO para o Remotion. Medido no `canary-state.json` do usuário, semana de
14 a 20/08/2026:

  - 23 jobs caíram para o Remotion completo, somando **12,6 h** de máquina
  - **8 deles seguiram acima de -1,0 dBTP depois de refeitos** — ou seja, a
    queda não consertou o defeito que a motivou
  - o último: 1657 s de re-render para entregar -0,9 dBTP

O conserto certo é renormalizar só a faixa de som, com o vídeo copiado.
Medido no arquivo real que o usuário publicou: -0,9 → -1,3 dBTP, LUFS parado
em -14,0, capa preservada, **48 s** — 35x mais barato que refazer tudo.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import overlay_compose as oc  # noqa: E402

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}


def _capa(dest: Path) -> Path:
    """Uma capa JPEG para embutir, como o final de verdade tem.

    JPEG e nao PNG de propósito: no mp4 a capa entra como mjpeg copiado. Com
    PNG passando pelo libx264 do stream principal, o ffmpeg não escreve nada
    ("at least one of its streams received no packets")."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                    "-i", "color=c=red:s=64x64:d=1", "-frames:v", "1", str(dest)],
                   capture_output=True, **NOWIN)
    return dest


def _final_falso(tmp: Path, *, capa: bool = True, pico_alto: bool = True) -> Path:
    """Um final.mp4 com a mesma forma do real: vídeo + áudio + capa."""
    # `aevalsrc`, nao `sine`: o gerador `sine` do ffmpeg emite em amplitude
    # 0,125 (-18 dBFS), entao `volume=0,98` sobre ele dava -16 dBTP e a
    # fixture nunca ficava acima do limite — o teste passava sem testar.
    amp = "0.95" if pico_alto else "0.02"
    onda = f"{amp}*sin(2*PI*440*t)"
    out = tmp / "final.mp4"
    argv = ["ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=s=180x320:r=30:d=3",
            "-f", "lavfi", "-i",
            f"aevalsrc=exprs={onda}|{onda}:s=48000:d=3:c=stereo"]
    if capa:
        argv += ["-i", str(_capa(tmp / "capa.jpg"))]
    argv += ["-map", "0:v", "-map", "1:a"]
    if capa:
        argv += ["-map", "2:v", "-c:v:1", "copy", "-disposition:v:1", "attached_pic"]
    argv += ["-c:v:0", "libx264", "-crf", "30", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-t", "3", str(out)]
    r = subprocess.run(argv, capture_output=True, text=True, **NOWIN)
    if r.returncode != 0 or not out.exists():
        pytest.skip(f"ffmpeg não montou a fixture: {(r.stderr or '')[-200:]}")
    return out


def _tipos(p: Path) -> list[str]:
    return [s.get("codec_type") for s in (oc.probe_json(p).get("streams") or [])]


def test_pico_alto_e_corrigido_no_audio_com_o_video_copiado(tmp_path):
    final = _final_falso(tmp_path)
    antes = oc.ebur128_summary(final)
    if antes.get("truePeakDb") is None or antes["truePeakDb"] <= -1.0:
        pytest.skip(f"a fixture não ficou acima do limite: {antes}")
    v_antes = oc.video_info(final)

    depois = oc.garantir_true_peak(final)

    assert depois["truePeakDb"] <= -1.0, depois
    # o vídeo é COPIADO: mesma contagem de quadros, mesmas dimensões
    v_depois = oc.video_info(final)
    assert v_depois["frames"] == v_antes["frames"]
    assert (v_depois["width"], v_depois["height"]) == (v_antes["width"], v_antes["height"])


def test_a_capa_embutida_sobrevive(tmp_path):
    """O final tem TRÊS fluxos, não dois: vídeo, áudio e a capa — que também
    é um stream de vídeo. Uma guarda de "1 vídeo + 1 áudio" pularia o
    conserto em todo projeto real, calada. Foi o que aconteceu no primeiro
    teste com o arquivo de verdade."""
    final = _final_falso(tmp_path)
    assert _tipos(final).count("video") == 2, "a fixture precisa ter capa"
    antes = oc.ebur128_summary(final)
    assert antes["truePeakDb"] > -1.0, f"a fixture tem de forçar o conserto: {antes}"
    depois = oc.garantir_true_peak(final)
    assert depois["truePeakDb"] <= -1.0, depois
    fluxos = oc.probe_json(final).get("streams") or []
    assert [s.get("codec_type") for s in fluxos].count("video") == 2
    assert any((s.get("disposition") or {}).get("attached_pic") for s in fluxos)


def test_pico_ja_dentro_do_limite_nao_reencoda(tmp_path, monkeypatch):
    """Sem defeito, sem trabalho — nem um ffmpeg a mais."""
    final = _final_falso(tmp_path, pico_alto=False)
    chamou = []
    real = oc._run
    monkeypatch.setattr(oc, "_run", lambda cmd: (chamou.append(cmd), real(cmd))[1])
    oc.garantir_true_peak(final)
    escritas = [c for c in chamou if "-c:v" in c and "copy" in c]
    assert not escritas, escritas


def test_legenda_embutida_faz_ele_desistir(tmp_path, monkeypatch):
    """O comando do conserto perderia um stream de legenda ou de dados.
    Melhor devolver o comportamento de hoje que entregar arquivo mutilado."""
    final = _final_falso(tmp_path)
    monkeypatch.setattr(oc, "probe_json", lambda _p: {"streams": [
        {"codec_type": "video"}, {"codec_type": "audio"}, {"codec_type": "subtitle"}]})
    chamou = []
    monkeypatch.setattr(oc, "_run", lambda cmd: chamou.append(cmd))
    monkeypatch.setattr(oc, "ebur128_summary", lambda _p: {"truePeakDb": -0.3,
                                                           "integratedLufs": -14.0})
    oc.garantir_true_peak(final)
    assert not chamou, "não podia ter chamado o ffmpeg"


def test_o_alvo_tem_folga_de_proposito():
    """O loudnorm entrega uns 0,1 a 0,2 dB ACIMA do que se pede — foi assim
    que o caminho completo, pedindo TP=-1, publicou -0,9, -0,8 e até -0,3.
    Pedir -1,0 para um limite de -1,0 não deixaria margem nenhuma."""
    import inspect

    sig = inspect.signature(oc.garantir_true_peak)
    assert sig.parameters["limite"].default == -1.0
    assert sig.parameters["alvo"].default <= -1.4
