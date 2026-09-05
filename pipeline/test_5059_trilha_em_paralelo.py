# -*- coding: utf-8 -*-
"""5.0.59: a espera pela trilha sai da frente do desenho.

MEDIDO em 132 projetos reais desde 01/09: 30 deles pararam para esperar a
música, com MEDIANA de 99,4 s (o pior, 164 s) — 45 minutos somados, num job
cuja mediana inteira é 118 s. O desenho do overlay não usa a trilha (ela só
entra na mistura), então esperar ANTES de desenhar é tempo jogado fora.

Aqui a espera vira um bloco guardado que só é cobrado quando alguém
realmente precisa do arquivo: no motor próprio, depois do layout e do SFX;
no caminho de duas etapas, depois do desenho inteiro; no Remotion completo
(que renderiza o áudio junto) e no longform, antes — como sempre foi.

O mesmo arquivo guarda o conserto que essa leitura encontrou: a passada
única — o caminho NORMAL do motor próprio — não aceitava o `duck` que a
5.0.57 passou a mandar. Toda chamada levantava `TypeError`, era engolida
pelo `except` do fallback e o render caía calado no caminho de duas etapas,
sem abaixar a trilha sob a voz e escrevendo um overlay.mov de ~150 MB.
"""
from __future__ import annotations

import ast
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import overlay_compose, overlay_path, render_proprio  # noqa: E402

OP = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")
RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- a regressão
def test_a_passada_unica_aceita_o_que_o_caller_manda():
    """A guarda que faltava na 5.0.57.

    Um `kwarg` que a função não tem não dá erro de importação nem de teste:
    ele levanta `TypeError` em tempo de render, dentro de um `except
    Exception` que existe para cair no caminho lento. O defeito fica só no
    log — e o cliente só vê o render demorar três vezes mais.
    """
    alvos = {
        "render_final_uma_passada": render_proprio.render_final_uma_passada,
        "compose_overlay": overlay_compose.compose_overlay,
        "render_overlay_proprio": render_proprio.render_overlay_proprio,
        "validate_overlay_alpha": overlay_compose.validate_overlay_alpha,
    }
    vistos = 0
    for arq, fonte in (("app/overlay_path.py", OP), ("pipeline/run_fast.py", RF)):
        for no in ast.walk(ast.parse(fonte)):
            if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Name):
                continue
            fn = alvos.get(no.func.id)
            if fn is None:
                continue
            vistos += 1
            nomes = [k.arg for k in no.keywords if k.arg]
            faltando = [n for n in nomes
                        if n not in inspect.signature(fn).parameters]
            assert not faltando, (
                f"{arq}:{no.lineno} manda {faltando} para "
                f"{no.func.id}(), que não aceita — TypeError calado no render")
    assert vistos >= 4, f"a varredura não achou as chamadas ({vistos})"


def test_duck_na_passada_unica():
    """A trilha abaixa sob a voz nos DOIS caminhos, com a mesma receita."""
    assert "duck" in inspect.signature(render_proprio.render_final_uma_passada).parameters
    com = ";".join(render_proprio._grafo_audio(0, 1, 2, 0.12, 10.0, 8.5, duck=True))
    sem = ";".join(render_proprio._grafo_audio(0, 1, 2, 0.12, 10.0, 8.5, duck=False))
    assert "asplit=2[voice][voiceduck]" in com
    assert "[musicd]" in com and "[music]amix" not in com
    assert "sidechaincompress" not in sem and "[music]amix" in sem
    for k in ("DUCK_LIMIAR", "DUCK_REDUCAO", "DUCK_ATAQUE", "DUCK_SOLTA"):
        assert f"{getattr(overlay_compose, k)}" in com, k


def test_o_grafo_da_passada_unica_e_valido_no_ffmpeg():
    """Um grafo com rótulo solto o ffmpeg só reprova na hora do render."""
    if not _tem_ffmpeg():
        pytest.skip("ffmpeg fora do PATH")
    partes = render_proprio._grafo_audio(0, 1, 2, 0.12, 1.0, 0.5, duck=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=f=300:d=1",
         "-f", "lavfi", "-i", "sine=f=800:d=1",
         "-f", "lavfi", "-i", "sine=f=100:d=1",
         "-filter_complex", ";".join(partes),
         "-map", "[pre]", "-t", "1", "-f", "null", "-"],
        capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:]


def _tem_ffmpeg() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=20)
        return True
    except Exception:  # noqa: BLE001
        return False


# ------------------------------------------------------------- a sobreposição
def test_a_trilha_e_cobrada_o_mais_tarde_possivel():
    corpo = inspect.getsource(render_proprio.render_final_uma_passada)
    assert corpo.index("_gravar_sfx") < corpo.index("resolver_trilha()"), (
        "perguntar pela trilha antes do SFX joga fora a sobreposição")
    assert corpo.index("resolver_trilha()") < corpo.index('inputs = ["-i"'), (
        "o ffmpeg abre o mp3 no começo: depois disso é tarde demais")

    duas = OP.split("alpha = validate_overlay_alpha(", 1)[1]
    assert duas.index("_resolver_trilha()") < duas.index("compose_overlay("), (
        "no caminho de duas etapas a trilha entra só na mistura")
    assert "_resolver_trilha()" not in OP.split(
        "alpha = validate_overlay_alpha(", 1)[0].split("def _resolver_trilha", 1)[1], (
        "nenhuma leitura adiantada antes do desenho")


def test_quem_renderiza_o_audio_junto_cobra_antes():
    """Remotion completo e longform misturam o áudio eles mesmos: para esses
    a trilha tem de estar no edit-data antes de começarem."""
    lf = RF.index("    overlay_final = False\n    if is_longform:\n")
    assert "_fechar_trilha()" in RF[lf:lf + 400]
    full = RF.index('        (remotion / "out").mkdir(exist_ok=True)')
    assert "_fechar_trilha()" in RF[full - 300:full]
    assert "antes_do_compose=_fechar_trilha," in RF


def test_o_bloco_adiado_nao_deixa_nome_para_tras():
    """O maior risco de embrulhar um trecho numa função: um nome que ele
    escrevia e o resto do job lia continua existindo, mas com o valor
    velho — e o defeito é mudo."""
    arv = ast.parse(RF)
    bloco = _achar(arv, "_bloco_da_trilha")
    fora = _achar(arv, "run_fast_pipeline") or _pai_de(arv, bloco)
    assert bloco is not None and fora is not None

    nonlocais = {n for no in ast.walk(bloco)
                 if isinstance(no, ast.Nonlocal) for n in no.names}
    assert "music" in nonlocais, "`music = False` precisa sair do bloco"

    escritos = {no.id for no in ast.walk(bloco)
                if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store)}
    escritos -= nonlocais
    depois = set()
    for no in ast.walk(fora):
        if (isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load)
                and no.lineno > bloco.end_lineno):
            depois.add(no.id)
    vazando = sorted(escritos & depois)
    assert not vazando, f"{vazando} nasciam no [7/9] e são lidos depois"


def test_o_fechador_e_idempotente_e_marca_o_tempo():
    fonte = RF.split("def _fechar_trilha():", 1)[1].split("\n    def ", 1)[0]
    assert '_trilha_pendente["fn"] = None' in fonte
    assert fonte.index('_trilha_pendente["fn"] = None') < fonte.index("fn()"), (
        "zerar depois de rodar deixaria uma reentrada esperar duas vezes")
    assert '_timing_mark("MUSIC_WAIT"' in fonte, (
        "sem a marca, a espera some do timing.json em vez de encolher")


def _achar(arv, nome):
    for no in ast.walk(arv):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    return None


def _pai_de(arv, alvo):
    for no in ast.walk(arv):
        if isinstance(no, ast.FunctionDef) and no is not alvo:
            if any(f is alvo for f in ast.walk(no)):
                return no
    return None
