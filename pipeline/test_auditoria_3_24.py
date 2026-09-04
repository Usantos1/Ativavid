# -*- coding: utf-8 -*-
"""Regressões achadas pela auditoria multiagente do intervalo 3.15-3.23.

Cada teste aqui nasceu de um defeito CONFIRMADO por leitura do código real,
não de suposição. Os graves: a Fila inteira em branco por um número
infinito no JSON, o motor de música preso em "instalado" depois de um
download interrompido, e o trecho apagado não ser o trecho marcado quando o
vídeo está tocando.
"""
import json
import math
from pathlib import Path

import pipeline.run_fast as rf
from app import musica_local
from app.jobs_view import _qualidade_do_corte

RAIZ = Path(__file__).resolve().parent.parent


# ---------- a Fila não pode ficar em branco por causa de um projeto ----------

def test_valor_infinito_no_json_nao_derruba_a_fila(tmp_path):
    """`quedaDb: -Infinity` (silêncio absoluto, e JSON aceita) fazia o
    int() da nota levantar OverflowError DENTRO do /api/jobs — e a resposta
    inteira morria: a Fila ficava em branco a cada atualização, por causa
    de UM projeto."""
    (tmp_path / "verificacao.json").write_text(json.dumps({
        "silenciosSobrando": [], "silencioTotalS": 0,
        "takesBaixos": [{"trecho": 2, "quedaDb": float("-inf")}],
        "emendasEstouradas": 0}), encoding="utf-8")
    job = {}
    _qualidade_do_corte(job, tmp_path)          # não pode levantar
    assert "corteQualidade" not in job


def test_texto_no_lugar_de_numero_tambem_nao_derruba(tmp_path):
    (tmp_path / "verificacao.json").write_text(json.dumps({
        "silencioTotalS": "muito", "takesBaixos": [{"trecho": 1,
                                                    "quedaDb": None}]}),
        encoding="utf-8")
    job = {}
    _qualidade_do_corte(job, tmp_path)
    assert "corteQualidade" not in job


def test_silencio_digital_nao_e_voz_baixa(tmp_path):
    """O verify_cut só marca LOW-LEVEL quando rms > -90 dB; o filtro da
    3.15 ignorava essa guarda e o card acusava "voz 77 dB mais baixa" em
    trecho que o próprio verificador tinha marcado "ok"."""
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [], "junctions": [],
        "range_levels": [{"index": 0, "delta_db": -77.0, "rms_db": -99.0},
                         {"index": 1, "delta_db": -8.0, "rms_db": -28.0}]})
    d = json.loads((tmp_path / "verificacao.json").read_text(encoding="utf-8"))
    assert [x["trecho"] for x in d["takesBaixos"]] == [1]


def test_sem_rms_gravado_o_aviso_continua(tmp_path):
    """Calar por falta de dado esconderia defeito de verdade."""
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [], "junctions": [],
        "range_levels": [{"index": 3, "delta_db": -9.0}]})
    d = json.loads((tmp_path / "verificacao.json").read_text(encoding="utf-8"))
    assert len(d["takesBaixos"]) == 1


def test_verificacao_velha_nao_sobrevive_a_um_render_sem_resposta(tmp_path):
    """Rerender cuja verificação não produziu JSON deixava o arquivo do
    corte ANTERIOR no lugar — a ficha passava a descrever defeitos de um
    vídeo que não existe mais."""
    (tmp_path / "verificacao.json").write_text('{"flags": 9}', encoding="utf-8")
    rf._gravar_diagnostico_do_corte(tmp_path, {})
    assert not (tmp_path / "verificacao.json").exists()


def test_o_numero_de_trechos_nivelados_chega_ao_timing():
    """`nivelAjustado` era gravado no _RENDER_META e morria ali — sem
    chegar ao timing.json não dá para medir o efeito do nivelamento nos
    vídeos reais depois."""
    s = (RAIZ / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'payload["nivelAjustado"]' in s


def test_clima_de_video_longo_tem_nome(tmp_path):
    (tmp_path / "timing.json").write_text(
        json.dumps({"musicaFonte": "longform--mg-20260827.mp3"}),
        encoding="utf-8")
    from app.jobs_view import _aviso_de_trilha
    job = {}
    _aviso_de_trilha(job, tmp_path)
    assert "vídeo longo" in job["trilhaNota"], job["trilhaNota"]


# ---------- motor de música: instalação pela metade ----------

def test_venv_pela_metade_nao_conta_como_instalado(tmp_path, monkeypatch):
    """Fechar o app no meio do download deixava a pasta criada — e
    `instalado()` era "a pasta existe". O cliente ficava preso em "IA local
    instalada", sem botão, com um motor que nunca compõe."""
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    (tmp_path / "MotorMusica" / "Scripts").mkdir(parents=True)
    (tmp_path / "MotorMusica" / "Scripts" / "python.exe").write_bytes(b"")
    assert musica_local.instalado() is False
    assert musica_local.instalacao_incompleta() is True


def test_instalacao_completa_e_reconhecida(tmp_path, monkeypatch):
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    base = tmp_path / "MotorMusica"
    (base / "Scripts").mkdir(parents=True)
    (base / "Scripts" / "python.exe").write_bytes(b"")
    (base / musica_local.MARCA).write_text("{}", encoding="utf-8")
    assert musica_local.instalado() is True
    assert musica_local.instalacao_incompleta() is False


def test_motor_antigo_sem_marca_e_adotado(tmp_path, monkeypatch):
    """Quem instalou antes desta versão não pode ser obrigado a baixar 4,8
    GB de novo: torch no disco vale como pronto."""
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    base = tmp_path / "MotorMusica"
    (base / "Scripts").mkdir(parents=True)
    (base / "Scripts" / "python.exe").write_bytes(b"")
    (base / "Lib" / "site-packages" / "torch").mkdir(parents=True)
    (base / "Lib" / "site-packages" / "torch" / "__init__.py").write_text("")
    assert musica_local.instalado() is True
    assert (base / musica_local.MARCA).is_file(), "não gravou a marca"


def test_modelo_que_nao_baixa_e_falha_de_instalacao(tmp_path, monkeypatch):
    """O modelo pesa 2,3 GB e o launcher desiste em 240s: sem ele, a
    primeira música de TODO vídeo estouraria o prazo e a trilha cairia para
    a biblioteca — parecendo que o motor não funciona."""
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    monkeypatch.setattr(musica_local, "tem_gpu_nvidia", lambda: True)
    monkeypatch.setattr(musica_local, "_uv", lambda: "uv")
    monkeypatch.setattr(musica_local, "instalado", lambda raiz=None: False)
    monkeypatch.setattr(
        musica_local, "_rodar",
        lambda cmd, minutos=60: (False, "sem rede") if "-c" in cmd
        else (True, "ok"))
    ok, motivo = musica_local.instalar(raiz_projetos=tmp_path)
    assert not ok and "modelo" in motivo


def test_marca_so_e_escrita_no_fim(tmp_path, monkeypatch):
    monkeypatch.setattr(musica_local, "pasta_motor",
                        lambda raiz=None: tmp_path / "MotorMusica")
    monkeypatch.setattr(musica_local, "tem_gpu_nvidia", lambda: True)
    monkeypatch.setattr(musica_local, "_uv", lambda: "uv")
    monkeypatch.setattr(musica_local, "instalado", lambda raiz=None: False)
    (tmp_path / "MotorMusica").mkdir()
    monkeypatch.setattr(musica_local, "_rodar",
                        lambda cmd, minutos=60: (True, "ok"))
    ok, _ = musica_local.instalar(raiz_projetos=tmp_path)
    assert ok
    assert (tmp_path / "MotorMusica" / musica_local.MARCA).is_file()


def test_a_gpu_nao_e_consultada_a_cada_poll(monkeypatch):
    """O estado é pedido de 3 em 3 segundos durante a instalação; um
    nvidia-smi por vez (com janela de console) era barulho e custo."""
    musica_local._GPU_CACHE.clear()
    chamadas = []
    monkeypatch.setattr(musica_local.subprocess, "run",
                        lambda *a, **k: chamadas.append(1) or type(
                            "R", (), {"returncode": 0, "stdout": "RTX"})())
    musica_local.tem_gpu_nvidia()
    musica_local.tem_gpu_nvidia()
    musica_local.tem_gpu_nvidia()
    assert len(chamadas) == 1
    musica_local._GPU_CACHE.clear()


def test_subprocessos_do_motor_escondem_a_janela():
    """Sem CREATE_NO_WINDOW, cada chamada abre um CMD preto na tela do
    cliente — e há uma a cada poll."""
    s = (RAIZ / "app" / "musica_local.py").read_text(encoding="utf-8")
    assert "_sem_janela()" in s
    assert s.count("**_sem_janela()") >= 2


def test_duas_instalacoes_nao_correm_juntas():
    """Dois cliques (ou duas abas) disparavam dois `uv pip install` no
    MESMO venv — jeito conhecido de corromper o ambiente."""
    s = (RAIZ / "app" / "local_server.py").read_text(encoding="utf-8")
    i = s.index("def _musica_instalar_em_fundo")
    corpo = s[i:i + 900]
    assert "_MUSICA_LOCK" in corpo and "with _MUSICA_LOCK" in corpo


def test_o_estado_nao_varre_o_venv_durante_o_download(tmp_path, monkeypatch):
    """A varredura do venv (~30 mil arquivos) rodava a cada 3 segundos."""
    s = (RAIZ / "app" / "musica_local.py").read_text(encoding="utf-8")
    i = s.index("def estado(")
    corpo = s[i:i + 900]
    assert "if pronto:" in corpo, "o tamanho é calculado sempre"


# ---------- timeline: o trecho apagado é o trecho marcado ----------

def test_a_timeline_nao_rola_sozinha_durante_um_arrasto():
    """O gesto é ancorado em pixels de tela. Se o conteúdo desliza no meio
    (auto-scroll do play, que desde a 3.22 o próprio arrasto disparava), o
    mesmo pixel passa a valer outro tempo e o trecho apagado não é o que
    ficou marcado."""
    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("// keep needle visible")
    guarda = js[js.rindex("if (", 0, i):i]
    assert "!drag" in guarda, guarda


def test_clique_no_take_removido_nao_teleporta_a_agulha():
    """O fantasma ocupa pixels mas dura zero: os pixels dele já pertencem,
    em tempo, ao take seguinte.

    Desde 04/09 o CLIQUE no take nao move a agulha de jeito nenhum (só a
    minutagem move), entao o fantasma nao tem como teleportar nada. O que
    sobra guardado aqui e o ARRASTO de intervalo, que ainda leva a agulha
    e por isso ainda precisa pular o take removido."""
    js = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("if (clip && S.tab === 1) {")
    corpo = js[i:js.index("return;", i)]
    assert "seekDraft" not in corpo, "o clique no take voltou a mover a agulha"
    j = js.index("} else if (drag.type === 'clip-range') {")
    assert "removed" in js[j:j + 500]


def test_nada_de_infinito_escapa_para_o_json(tmp_path):
    """Cinto e suspensório: o que for gravado tem de ser sempre finito."""
    rf._gravar_diagnostico_do_corte(tmp_path, {
        "silences": [{"start": 1.0, "end": 2.0}],
        "junctions": [],
        "range_levels": [{"index": 0, "delta_db": float("-inf")},
                         {"index": 1, "delta_db": float("nan")}],
        "peak_db": -3.2})
    bruto = (tmp_path / "verificacao.json").read_text(encoding="utf-8")
    assert "Infinity" not in bruto and "NaN" not in bruto, bruto
    d = json.loads(bruto)
    assert all(math.isfinite(float(x["quedaDb"])) for x in d["takesBaixos"])
