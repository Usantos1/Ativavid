# -*- coding: utf-8 -*-
"""O desenho rápido pode ficar desligado, e nada dizia.

Achado nos arquivos do próprio app (30/08):

    canary-state.json   paused: true
                        pausedReason: "TRUE_PEAK -0.9>-1.0"
    render-stats.json   413 jobs · 31 fallbacks
                        overlay médio 421s · FULL médio 1383s (3,3x)

`pause_canary` faz duas coisas: marca a pausa E grava
`overlayRollout=off`. Dali em diante TODO vídeo sai pelo caminho completo,
sem nada na tela. Nos projetos dele há **6 vídeos** assim depois que o
motor próprio passou a existir (21/08): `renderPath=FULL`, sem falha
nenhuma, com motivos que o rápido atende.

Ou seja: um estouro de áudio de 0,09 dB podia desligar o motor rápido da
máquina inteira, calado. A 4.29 tirou o gatilho; aqui o ESTADO fica
visível — no diagnóstico e no card do vídeo.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "helpers"))

JV = (REPO / "app" / "jobs_view.py").read_text(encoding="utf-8")
DR = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")


def _timing(tmp_path: Path, nome: str, dados: dict) -> Path:
    import json

    proj = tmp_path / nome
    edit = proj / "edit"
    edit.mkdir(parents=True)
    (edit / "timing.json").write_text(json.dumps(dados), encoding="utf-8")
    return edit


def _nota(edit: Path) -> str:
    from app.jobs_view import _aviso_do_motor

    job: dict = {}
    _aviso_do_motor(job, edit)
    return str(job.get("motorNota") or "")


RAPIDO = ["captions", "hook", "end_card", "flash"]


def test_full_sem_falha_depois_do_motor_e_noticia(tmp_path):
    edit = _timing(tmp_path, "20260829-173842_x", {
        "renderPath": "FULL", "renderPathReasons": RAPIDO})
    assert "desligado" in _nota(edit)


def test_antes_do_motor_existir_nao_avisa(tmp_path):
    """Avisar sobre o que ninguem podia mudar ensina a ignorar aviso — a
    licao que o proprio arquivo ja carregava."""
    edit = _timing(tmp_path, "20260818-224627_x", {
        "renderPath": "FULL", "renderPathReasons": RAPIDO})
    assert "desligado" not in _nota(edit)


def test_full_por_motivo_legitimo_nao_vira_aviso(tmp_path):
    """`video_layout` e `tracking` NAO cabem no caminho rapido: ali o FULL
    e a escolha certa."""
    edit = _timing(tmp_path, "20260829-173842_x", {
        "renderPath": "FULL",
        "renderPathReasons": ["video_layout", "captions"]})
    assert "desligado" not in _nota(edit)


def test_queda_do_rapido_continua_com_a_nota_de_sempre(tmp_path):
    edit = _timing(tmp_path, "20260829-173842_x", {
        "renderPath": "FULL", "fallbackUsed": True,
        "renderPathReasons": ["OVERLAY_FAILED", "FALLBACK_FULL_REMOTION",
                              *RAPIDO]})
    n = _nota(edit)
    assert "falhou" in n and "desligado" not in n


def test_as_razoes_do_rapido_batem_com_o_classificador():
    """Se o classificador ganhar uma razao nova de overlay e esta lista
    nao, o aviso passa a chamar de "desligado" um FULL legitimo."""
    from app.render_path import classify_render_path
    from app.jobs_view import _RAZOES_DO_RAPIDO

    ed = {
        "captions": {"enabled": True}, "hook": {"enabled": True, "logo": "x"},
        "endCard": {"enabled": True}, "inserts": [{"a": 1}],
        "transitions": [{"type": "flash", "at": 1}],
    }
    cls = classify_render_path(ed)
    assert set(cls["overlayReasons"]) <= _RAZOES_DO_RAPIDO, (
        set(cls["overlayReasons"]) - _RAZOES_DO_RAPIDO)


# --------------------------------------------------------- o diagnostico

def test_o_diagnostico_checa_o_motor_rapido():
    assert "def checar_motor_rapido()" in DR
    i = DR.index("for fn in (checar_programas")
    assert "checar_motor_rapido" in DR[i:i + 260], "o check nao entra na rodada"


def test_o_diagnostico_conta_a_pausa_e_como_sair():
    i = DR.index("def checar_motor_rapido()")
    bloco = DR[i:DR.index("\ndef ", i + 10)]
    assert "pausedReason" in bloco
    assert "pausedAt" in bloco
    assert "3x mais lento" in bloco
    assert "Motor de render: Automatico" in bloco, "sem saida nao e conselho"
