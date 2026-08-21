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

def test_nvdec_desligado_quando_prep_e_concorrente(monkeypatch, tmp_path):
    """Medido: duas instancias NVDEC+NVENC saturam o motor de video (284s
    contra 151s do sequencial CPU). Em prep concorrente o NVDEC tem de vir
    desligado; sozinho, ligado."""
    import render

    flags = {}

    def _falso(sp, scale, grade, *, quiet=False, permitir_nvdec=True):
        flags[sp.name] = permitir_nvdec
        return None

    monkeypatch.setattr(render, "prepared_source", _falso)
    render.prepare_sources_parallel({"a.mov", "b.mov"}, lambda n: tmp_path / n,
                                    lambda sp: "s", "")
    assert flags == {"a.mov": False, "b.mov": False}
    flags.clear()
    render.prepare_sources_parallel({"x.mov"}, lambda n: tmp_path / n,
                                    lambda sp: "s", "")
    assert flags == {"x.mov": True}



# ------------------------------------------ reserva de NVDEC entre processos ----
def test_um_prep_por_vez_pega_o_nvdec():
    """Medido na 4K60 HDR do usuário, máquina livre: dois preps com NVDEC ao
    mesmo tempo custam 98,7s — PIOR que os 89,1s de rodar um depois do outro.
    Um na GPU e outro na CPU dá 89,8s e mantém os dois jobs andando."""
    render._NVDEC_LOCK.unlink(missing_ok=True)
    with render._reservar_nvdec() as primeiro:
        assert primeiro is True
        with render._reservar_nvdec() as segundo:
            assert segundo is False, "o segundo não pode pegar a GPU também"
    # solto depois do bloco
    with render._reservar_nvdec() as depois:
        assert depois is True


def test_lock_de_processo_morto_e_tomado(tmp_path, monkeypatch):
    """Um prep que morreu no meio não pode deixar a GPU inutilizada."""
    render._NVDEC_LOCK.unlink(missing_ok=True)
    render._NVDEC_LOCK.write_text("999999999", encoding="utf-8")   # PID inexistente
    monkeypatch.setattr(render, "_pid_alive", lambda _p: False)
    with render._reservar_nvdec() as peguei:
        assert peguei is True, "lock de PID morto tem de ser tomado"
    render._NVDEC_LOCK.unlink(missing_ok=True)


def test_lock_de_processo_vivo_e_respeitado(monkeypatch):
    render._NVDEC_LOCK.unlink(missing_ok=True)
    render._NVDEC_LOCK.write_text("4242", encoding="utf-8")
    monkeypatch.setattr(render, "_pid_alive", lambda _p: True)
    with render._reservar_nvdec() as peguei:
        assert peguei is False, "dono vivo tem de ser respeitado"
    render._NVDEC_LOCK.unlink(missing_ok=True)


def test_reserva_solta_o_lock_mesmo_com_erro():
    """Sem isto, um prep que estoura deixaria a GPU reservada para sempre."""
    render._NVDEC_LOCK.unlink(missing_ok=True)
    try:
        with render._reservar_nvdec() as peguei:
            assert peguei is True
            raise RuntimeError("prep estourou")
    except RuntimeError:
        pass
    assert not render._NVDEC_LOCK.exists()


def test_interruptor_do_fps_do_prep(tmp_path, monkeypatch):
    """`ATIVAVID_PREP_FPS=0` volta ao comportamento antigo — mesmo estilo do
    ATIVAVID_PREP_SOURCE=0. Serviu para o A/B fim a fim (702s -> 410s) e fica
    como escape se a máquina de alguém reagir mal."""
    src = _fake_src(tmp_path)
    monkeypatch.setattr(render, "source_fps", lambda _p: 60.0)
    monkeypatch.setattr(render, "shortform_target_fps", lambda _p: "30")
    monkeypatch.delenv("ATIVAVID_PREP_FPS", raising=False)
    assert render._prep_fps(src) == "30"
    monkeypatch.setenv("ATIVAVID_PREP_FPS", "0")
    assert render._prep_fps(src) == ""
