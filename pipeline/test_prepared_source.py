"""Fonte preparada: tonemap + grade aplicados uma vez, não a cada segmento.

O tonemap HDR domina o corte (medido: 294,4 s para 29,1 s de vídeo, CPU a
99%). Aplicando-o uma vez sobre a fonte, a 1ª execução empata e as
reexecuções caem para 32,4 s — 9,1x. Estes testes travam as regras que
tornam isso seguro.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

import render  # noqa: E402


def _fake_src(tmp_path: Path, name: str = "a.mov") -> Path:
    p = tmp_path / name
    p.write_bytes(b"x" * 2048)
    return p


def test_desligado_por_variavel(tmp_path, monkeypatch):
    monkeypatch.setenv("ATIVAVID_PREP_SOURCE", "0")
    assert render.prepared_source(_fake_src(tmp_path), "scale=-2:1920", "eq=x") is None


def test_fonte_sdr_nao_prepara(tmp_path, monkeypatch):
    """Sem tonemap não há o que economizar — evita gerar arquivo à toa."""
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: False)
    assert render.prepared_source(_fake_src(tmp_path), "scale=-2:1920", "eq=x") is None


def test_chave_muda_com_grade_escala_e_fonte(tmp_path):
    src = _fake_src(tmp_path)
    base = render._prep_key(src, "scale=-2:1920", "eq=a")
    assert base == render._prep_key(src, "scale=-2:1920", "eq=a")   # estável
    assert base != render._prep_key(src, "scale=-2:1080", "eq=a")   # escala
    assert base != render._prep_key(src, "scale=-2:1920", "eq=b")   # grade
    src.write_bytes(b"y" * 4096)                                    # fonte mudou
    assert base != render._prep_key(src, "scale=-2:1920", "eq=a")


def test_cache_invalido_e_refeito(tmp_path, monkeypatch):
    """Chave divergente não pode devolver o arquivo velho."""
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: True)
    src = _fake_src(tmp_path)
    prep = src.with_suffix(src.suffix + ".prep.mp4")
    keyf = src.with_suffix(src.suffix + ".prepkey")
    prep.write_bytes(b"video")
    keyf.write_text("chave-de-outra-coisa", encoding="utf-8")
    chamou = []
    monkeypatch.setattr(render, "_run_ffmpeg",
                        lambda *a, **k: chamou.append(1))
    render.prepared_source(src, "scale=-2:1920", "eq=a", quiet=True)
    assert chamou, "cache inválido foi aceito sem regerar"


def test_cache_valido_e_reaproveitado(tmp_path, monkeypatch):
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: True)
    src = _fake_src(tmp_path)
    prep = src.with_suffix(src.suffix + ".prep.mp4")
    keyf = src.with_suffix(src.suffix + ".prepkey")
    prep.write_bytes(b"video")
    keyf.write_text(render._prep_key(src, "scale=-2:1920", "eq=a"), encoding="utf-8")
    monkeypatch.setattr(render, "_run_ffmpeg",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("regerou à toa")))
    assert render.prepared_source(src, "scale=-2:1920", "eq=a", quiet=True) == prep


def test_falha_do_ffmpeg_cai_no_caminho_normal(tmp_path, monkeypatch):
    """Nunca pode derrubar o corte: erro ao preparar devolve None."""
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: True)
    monkeypatch.setattr(render, "_run_ffmpeg",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert render.prepared_source(_fake_src(tmp_path), "scale=-2:1920", "eq=a",
                                  quiet=True) is None


def test_duracao_divergente_descarta(tmp_path, monkeypatch):
    """Arquivo truncado não pode virar cache — o corte sairia curto."""
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: True)
    src = _fake_src(tmp_path)
    monkeypatch.setattr(render, "_run_ffmpeg",
                        lambda *a, **k: src.with_suffix(src.suffix + ".prep.tmp.mp4")
                        .write_bytes(b"curto"))
    monkeypatch.setattr(render, "probe_duration",
                        lambda p: 5.0 if "tmp" in p.name else 40.0)
    assert render.prepared_source(src, "scale=-2:1920", "eq=a", quiet=True) is None


# ---------- cenários de invalidação exigidos na auditoria da v2.17 ----------

def _hit(src, scale="scale=-2:1920", grade="eq=a") -> bool:
    """True = cache aceito (HIT); False = seria refeito (MISS)."""
    keyf = src.with_suffix(src.suffix + ".prepkey")
    return keyf.exists() and keyf.read_text(encoding="utf-8").strip() == \
        render._prep_key(src, scale, grade)


def _armar(tmp_path):
    src = _fake_src(tmp_path)
    src.with_suffix(src.suffix + ".prep.mp4").write_bytes(b"v")
    src.with_suffix(src.suffix + ".prepkey").write_text(
        render._prep_key(src, "scale=-2:1920", "eq=a"), encoding="utf-8")
    return src


def test_hit_quando_nada_mudou(tmp_path):
    assert _hit(_armar(tmp_path)) is True


def test_headline_ou_legenda_nao_invalidam(tmp_path):
    """Headline e legenda são desenhadas depois do corte: não entram na chave."""
    src = _armar(tmp_path)
    assert _hit(src) is True  # a chave não tem nada de headline/legenda
    assert "headline" not in render._prep_key(src, "scale=-2:1920", "eq=a")


def test_fonte_trocada_invalida(tmp_path):
    src = _armar(tmp_path)
    src.write_bytes(b"outro conteudo bem diferente" * 99)
    assert _hit(src) is False


def test_grade_trocada_invalida(tmp_path):
    assert _hit(_armar(tmp_path), grade="eq=OUTRA") is False


def test_resolucao_trocada_invalida(tmp_path):
    assert _hit(_armar(tmp_path), scale="scale=-2:1080") is False


def test_tonemap_faz_parte_da_chave(tmp_path):
    """Se a cadeia de tonemap mudar no código, o cache tem de cair."""
    src = _armar(tmp_path)
    antes = render._prep_key(src, "scale=-2:1920", "eq=a")
    original = render.TONEMAP_CHAIN
    try:
        render.TONEMAP_CHAIN = original + ",eq=gamma=1.01"
        assert render._prep_key(src, "scale=-2:1920", "eq=a") != antes
    finally:
        render.TONEMAP_CHAIN = original


def test_temporario_e_por_processo(tmp_path, monkeypatch):
    """Dois renders simultâneos não podem escrever no mesmo arquivo temporário."""
    import os as _os
    monkeypatch.delenv("ATIVAVID_PREP_SOURCE", raising=False)
    monkeypatch.setattr(render, "is_hdr_source", lambda _p: True)
    src = _fake_src(tmp_path)
    vistos = []
    monkeypatch.setattr(render, "_run_ffmpeg",
                        lambda cmd, **k: vistos.append(cmd[-1]))
    monkeypatch.setattr(render, "probe_duration", lambda p: 10.0)
    render.prepared_source(src, "scale=-2:1920", "eq=a", quiet=True)
    assert vistos, "não chamou o ffmpeg"
    assert str(_os.getpid()) in vistos[0], f"temporário sem pid: {vistos[0]}"

def test_prepara_fontes_em_paralelo(monkeypatch, tmp_path):
    """x2 com duas fontes 4K60: o prep sequencial dominava o CUT. As duas
    devem preparar AO MESMO TEMPO (2 por vez), com falha isolada por fonte."""
    import threading
    import time as _t

    import render

    ativos, pico = [0], [0]
    trava = threading.Lock()

    def _falso(sp, scale, grade, **kw):
        with trava:
            ativos[0] += 1
            pico[0] = max(pico[0], ativos[0])
        _t.sleep(0.15)
        with trava:
            ativos[0] -= 1
        if "ruim" in str(sp):
            raise RuntimeError("fonte quebrada")
        return sp.with_suffix(".prep.mp4")

    monkeypatch.setattr(render, "prepared_source", _falso)
    out = render.prepare_sources_parallel(
        {"a.mov", "b.mov", "ruim.mov"},
        lambda n: tmp_path / n,
        lambda sp: "scale=1920:-2",
        "")
    assert pico[0] == 2, f"duas por vez, medido {pico[0]}"
    assert out["a.mov"] is not None and out["b.mov"] is not None
    assert out["ruim.mov"] is None, "falha de uma fonte nao derruba as outras"


def test_uma_fonte_nao_abre_pool(monkeypatch, tmp_path):
    import render

    chamadas = []
    monkeypatch.setattr(render, "prepared_source",
                        lambda sp, sc, gr, **kw: chamadas.append(sp) or None)
    render.prepare_sources_parallel({"x.mov"}, lambda n: tmp_path / n,
                                    lambda sp: "s", "")
    assert len(chamadas) == 1
