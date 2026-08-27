# -*- coding: utf-8 -*-
"""O que a verificação do corte acha para de sumir no fim do render.

O verify_cut sempre mediu pausa morta, take baixo, estouro de emenda e
clipping — e o resultado morria com o processo: 158 projetos entregues, zero
com uma linha guardada (varredura 27/08). Nos 10 videos mais recentes do
usuario: 6 com pausa sobrando (0,4-0,7s cada) e 6 com um trecho mais baixo
que o resto. Defeito pequeno, que so aparece assistindo — agora a ficha
conta.
"""
import json
from pathlib import Path

import pipeline.run_fast as rf
from app.jobs_view import _qualidade_do_corte

RAIZ = Path(__file__).resolve().parent.parent

VDATA = {
    "flags": 3,
    "silences": [{"start": 22.68, "end": 23.37},
                 {"start": 73.89, "end": 74.54},
                 {"start": 10.0, "end": 10.15}],   # respiração: nao conta
    "range_levels": [{"index": 0, "delta_db": -1.2, "verdict": "ok"},
                     {"index": 5, "delta_db": -8.5, "verdict": "LOW-LEVEL"}],
    "junctions": [{"n": 1, "verdict": "ok"},
                  {"n": 2, "verdict": "encavalado 208ms"}],
    "peak_db": -3.28,
}


def test_grava_o_diagnostico_com_os_numeros_reais(tmp_path):
    rf._gravar_diagnostico_do_corte(tmp_path, VDATA)
    d = json.loads((tmp_path / "verificacao.json").read_text(encoding="utf-8"))
    assert len(d["silenciosSobrando"]) == 2, "a respiração de 0,15s entrou"
    assert d["silencioTotalS"] == 1.34
    assert d["takesBaixos"] == [{"trecho": 5, "quedaDb": -8.5}]
    assert d["emendasEstouradas"] == 0, "'encavalado' nao e estouro"


def test_a_ficha_conta_em_portugues_de_gente(tmp_path):
    rf._gravar_diagnostico_do_corte(tmp_path, VDATA)
    job = {}
    _qualidade_do_corte(job, tmp_path)
    nota = job["corteQualidade"]
    assert "2 pausas somando 1,3s" in nota, nota
    assert "0:22" in nota, "sem o minuto, o usuario nao sabe onde olhar"
    assert "1 trecho com a voz 9 dB mais baixa" in nota, nota


def test_pausa_curta_nao_vira_aviso(tmp_path):
    """Sem limiar, 6 de 10 videos ganhariam aviso por 0,4s de respiro — e
    aviso que aparece sempre vira ruido que se aprende a ignorar."""
    rf._gravar_diagnostico_do_corte(
        tmp_path, {"silences": [{"start": 5.0, "end": 5.45}],
                   "range_levels": [], "junctions": []})
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert "corteQualidade" not in job


def test_video_limpo_nao_ganha_nota(tmp_path):
    rf._gravar_diagnostico_do_corte(
        tmp_path, {"flags": 0, "silences": [], "range_levels": [],
                   "junctions": [], "peak_db": -4.0})
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert "corteQualidade" not in job


def test_sem_arquivo_nada_quebra(tmp_path):
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert job == {}


def test_o_pipeline_grava_no_ponto_da_verificacao():
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.find('status["verify_flags"]')
    assert i > 0
    assert "_gravar_diagnostico_do_corte(edit_dir, vdata)" in s[i:i + 200]


def test_a_ficha_do_card_mostra_a_linha():
    js = (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert '["Revisar no corte", j.corteQualidade]' in js
    assert "j.corteQualidade ||" in js, "campo fora da assinatura do card"


# ---------- o aviso segue o MODO (3.17) ----------

def _projeto(tmp_path, modo: str, silencio_s: float = 4.9):
    (tmp_path / "job_intent.json").write_text(
        json.dumps({"editingIntent": modo}), encoding="utf-8")
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [{"start": 4.0 + i, "end": 4.0 + i + silencio_s / 6}
                     for i in range(6)],
        "range_levels": [], "junctions": [],
    })
    job = {}
    _qualidade_do_corte(job, tmp_path)
    return job


def test_modo_sem_cortes_nao_reclama_de_pausa(tmp_path):
    """Caso real (27/08, primeiro video a receber o aviso novo): rodado em
    "Sem cortes", ganhou "6 pausas somando 4,9s" — mandando arrumar
    exatamente o que o modo escolhido manda manter."""
    assert "corteQualidade" not in _projeto(tmp_path, "intact")


def test_video_completo_e_edicao_leve_tambem_preservam(tmp_path):
    for modo in ("complete", "light"):
        d = tmp_path / modo
        d.mkdir()
        assert "corteQualidade" not in _projeto(d, modo), modo


def test_modo_que_corta_continua_avisando(tmp_path):
    for modo in ("dynamic", "shorts"):
        d = tmp_path / modo
        d.mkdir()
        job = _projeto(d, modo)
        assert "pausas somando" in job.get("corteQualidade", ""), modo


def test_sem_modo_gravado_o_aviso_vale(tmp_path):
    """Projeto antigo, sem job_intent.json: o padrao do app e dynamic (que
    corta), entao calar seria esconder defeito de verdade."""
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [{"start": 4.0, "end": 5.5}],
        "range_levels": [], "junctions": []})
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert "corteQualidade" in job


def test_voz_baixa_avisa_ate_no_modo_sem_cortes(tmp_path):
    """Take mais baixo que o resto e defeito em QUALQUER modo — nada a ver
    com preservar a fonte."""
    (tmp_path / "job_intent.json").write_text(
        json.dumps({"editingIntent": "intact"}), encoding="utf-8")
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [],
        "range_levels": [{"index": 2, "delta_db": -9.0}],
        "junctions": []})
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert "voz 9 dB mais baixa" in job.get("corteQualidade", "")
