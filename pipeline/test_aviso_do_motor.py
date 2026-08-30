# -*- coding: utf-8 -*-
"""O card conta quando o vídeo saiu pelo caminho lento — e por quê.

O motor próprio desenha sem abrir o Chrome e é 3,3x mais rápido (423s
contra 1391s de média nos 404 jobs do usuário). Quando ele fica de fora, o
vídeo demora o triplo e nada na tela contava: o motivo ia para o
`timing.json` e morria lá.

O aviso é raro de propósito — 170 dos 187 projetos não mostram nada.
Avisar sobre o que não dá para mudar ensina a ignorar aviso: o caminho
completo "puro" (33 projetos, de antes do motor próprio existir) fica de
fora; o caminho completo por FALHA do rápido (15) entra.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.jobs_view import _aviso_do_motor  # noqa: E402


def _timing(tmp_path: Path, d: dict) -> Path:
    (tmp_path / "timing.json").write_text(json.dumps(d), encoding="utf-8")
    return tmp_path


def test_motivo_registrado_aparece_inteiro(tmp_path):
    j = {}
    _aviso_do_motor(j, _timing(tmp_path, {
        "overlayEngineSkip": "legenda estilo-novo nao suportado"}))
    assert "estilo-novo" in j["motorNota"]


def test_queda_do_rapido_e_noticia(tmp_path):
    j = {}
    _aviso_do_motor(j, _timing(tmp_path, {
        "renderPath": "FULL",
        "renderPathReasons": ["OVERLAY_FAILED", "FALLBACK_FULL_REMOTION",
                              "captions"]}))
    assert "falhou" in j["motorNota"]


def test_caminho_completo_puro_nao_avisa(tmp_path):
    """33 projetos são de antes do motor próprio existir — não há o que
    fazer, e aviso que não se pode atender ensina a ignorar aviso."""
    j = {}
    _aviso_do_motor(j, _timing(tmp_path, {
        "renderPath": "FULL",
        "renderPathReasons": ["captions", "hook", "end_card", "flash"]}))
    assert "motorNota" not in j


def test_motor_proprio_nao_avisa_nada(tmp_path):
    j = {}
    _aviso_do_motor(j, _timing(tmp_path, {
        "renderPath": "OVERLAY", "overlayEngine": "proprio"}))
    assert "motorNota" not in j


def test_remotion_sem_motivo_diz_que_nao_sabe(tmp_path):
    """Dizer que foi lento continua sendo verdade; inventar o motivo não."""
    j = {}
    _aviso_do_motor(j, _timing(tmp_path, {
        "renderPath": "OVERLAY", "overlayEngine": "remotion"}))
    assert "não registrado" in j["motorNota"]


def test_sem_timing_nao_levanta(tmp_path):
    j = {}
    _aviso_do_motor(j, tmp_path)
    assert j == {}


def test_a_tela_mostra_a_linha():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'linhas.push(["Render", j.motorNota])' in js
    # e a assinatura do card inclui o campo, senão a linha não repinta
    assert 'j.motorNota || "",' in js
