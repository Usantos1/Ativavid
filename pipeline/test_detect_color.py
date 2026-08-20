"""Detecção de cor: a medição precisa REALMENTE acontecer.

Ela ficou morta no Windows sem ninguém notar. O filtro recebia
`metadata=print:file=C:\\Users\\...\\tmp.txt` e o `:` da letra de unidade é
separador de opção no parser de filtro do ffmpeg: o grafo nem abria, o
`check=True` levantava e um `except CalledProcessError: return None` engolia.
Toda execução caía em `confidence=low, grade=""` — e o pipeline seguia com o
aviso "color confidence low" que ninguém investigou.

O teste que faltava é o que exercita o caminho de verdade: gerar um clipe e
exigir que `stats` volte preenchido.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

import detect_color  # noqa: E402

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(
    subprocess, "CREATE_NO_WINDOW") else {}
sem_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None,
                                reason="ffmpeg não está no PATH")


def _clipe(tmp_path: Path, extra: str = "") -> Path:
    """Clipe minúsculo (1s, 160x120) — barato o bastante para rodar sempre."""
    out = tmp_path / "c.mp4"
    vf = f"format=yuv420p{',' + extra if extra else ''}"
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1",
         "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast", str(out)],
        check=True, **NOWIN)
    return out


@sem_ffmpeg
def test_medicao_acontece_de_verdade(tmp_path):
    """O teste que teria pego o bug: `stats` preenchido, não None.

    Roda a partir de um diretório com `:` no caminho absoluto (todo caminho
    do Windows tem), que é exatamente a condição que quebrava.
    """
    r = detect_color.detect(_clipe(tmp_path), samples=4)
    assert r["stats"] is not None, "a análise de imagem não rodou"
    assert r["stats"]["frames"] > 0
    for chave in ("black_floor", "white_ceiling", "y_mean", "sat_mean"):
        assert isinstance(r["stats"][chave], float), chave


@sem_ffmpeg
def test_material_normal_nao_ganha_expansao_log(tmp_path):
    """Fonte comum tem de sair com grade vazio — senão o conserto passaria a
    aplicar uma expansão LOG em vídeo que não precisa."""
    r = detect_color.detect(_clipe(tmp_path), samples=4)
    assert r["profile"] == "rec709"
    assert not r["grade"]
    assert r["confidence"] == "high"


@sem_ffmpeg
def test_material_flat_e_reconhecido(tmp_path):
    """Preto levantado + faixa comprimida + saturação baixa é a assinatura de
    LOG. É para ISTO que o tier estatístico existe, e era o que estava
    inalcançável enquanto a medição falhava."""
    # curva achatada de propósito: pretos altos, brancos baixos, sem cor
    plano = _clipe(tmp_path, "eq=saturation=0.05,colorlevels=romin=0.32:gomin=0.32:bomin=0.32:romax=0.62:gomax=0.62:bomax=0.62")
    r = detect_color.detect(plano, samples=4)
    assert r["stats"] is not None
    assert r["score"] >= 3, r["evidence"]
    assert r["grade"], "material flat tem de receber a expansão medida"


def test_arquivo_do_filtro_e_relativo():
    """Trava a forma do conserto: caminho absoluto dentro do filtro volta a
    quebrar no `:` da unidade, e a falha é silenciosa."""
    fonte = (REPO / "helpers" / "detect_color.py").read_text(encoding="utf-8")
    assert "metadata=print:file=meta.txt" in fonte
    assert "cwd=tmpdir" in fonte
    assert "file={meta}" not in fonte


# ------------------------------------------- o mesmo bug estava no grade ----
@sem_ffmpeg
def test_grade_automatico_mede_de_verdade(tmp_path):
    """`helpers/grade.py` tinha o MESMO `metadata=print:file=<caminho
    absoluto>`. A falha era ainda mais discreta que no detect_color: o
    arquivo saía vazio, nenhum YAVG era lido, e a função devolvia "valores
    neutros (sem correção)" — ou seja, com `colorGrade: auto` a graduação
    por segmento nunca corrigiu nada no Windows."""
    sys.path.insert(0, str(REPO / "helpers"))
    import grade

    st = grade._sample_frame_stats(_clipe(tmp_path), 0.0, 1.0, n_samples=4)
    neutro = {"y_mean": 0.5, "y_std": 0.18, "sat_mean": 0.25}
    assert st != neutro, "caiu no neutro: a análise não rodou"
    assert 0.0 < st["y_mean"] < 1.0


def test_grade_usa_caminho_relativo_no_filtro():
    """Trava a forma: caminho absoluto volta a quebrar no `:` da unidade, e
    quebra sem levantar erro nenhum."""
    fonte = (REPO / "helpers" / "grade.py").read_text(encoding="utf-8")
    assert "metadata=print:file=meta.txt" in fonte
    assert "cwd=tmpdir" in fonte
    assert "file={metadata_path}" not in fonte
