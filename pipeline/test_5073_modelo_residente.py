# -*- coding: utf-8 -*-
"""5.0.73: o modelo Whisper fica residente entre jobs.

Cada job é um processo, então o `medium` era carregado de novo a cada
vídeo: 3,6 s de mediana em dias normais, 8,1 s num lote (máx 52,7 s), mais
imports e o VAD — telemetria real. `app/transcricao/residente.py` segura o
motor num processo próprio (HTTP em 127.0.0.1, porta efêmera, token), que
solta o modelo após 5 min ocioso e sai após 30 min ou quando o app
atualiza. O helper tenta o serviço; sem serviço, sobe um para o PRÓXIMO
vídeo e transcreve no próprio processo, como hoje — quem transcreve um
vídeo por vez nunca fica mais lento.

Validado no laboratório com 3 vídeos reais dele (207/262/122 palavras):
texto e tempos idênticos, palavra por palavra, entre o processo próprio e
o serviço — é o mesmo `MotorWhisperLocal.transcrever`, só muda quem chama.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers", REPO / "pipeline"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from app.transcricao import Palavra, ResultadoDeTranscricao, Segmento  # noqa: E402
from app.transcricao import residente  # noqa: E402

RESULTADO = ResultadoDeTranscricao(
    texto="eu vendi ontem", idioma="por", duracao=2.0, motor="whisper-local",
    modelo="medium", backend="cuda",
    tempos={"carregar_modelo": 0.0, "transcrever": 1.2},
    segmentos=[Segmento("eu vendi ontem", 0.0, 2.0, confianca=-0.1, palavras=(
        Palavra("eu", 0.0, 0.2, 0.9), Palavra("vendi", 0.2, 0.7, 0.8),
        Palavra("ontem", 1.6, 2.0, None)))],
)


@pytest.fixture()
def isolado(tmp_path, monkeypatch):
    """Nunca encostar no INFO/trinco/log de verdade da máquina."""
    monkeypatch.setattr(residente, "INFO", tmp_path / "info.json")
    monkeypatch.setattr(residente, "TRINCO", tmp_path / "subindo")
    monkeypatch.setattr(residente, "LOG", tmp_path / "log.txt")
    monkeypatch.setenv("ATIVAVID_WHISPER_RESIDENTE", "1")
    residente._ULTIMO = "desligado"
    return tmp_path


class _Motor:
    def __init__(self, modelo=None):
        self._pedido = modelo
        self.chamadas = 0

    def transcrever(self, audio, *, idioma=None, fonte_original=None, **k):
        self.chamadas += 1
        print("TRANSCRIPTION ENGINE local model=medium device=cuda", flush=True)
        return RESULTADO


# ------------------------------------------------------------ o contrato

def test_o_resultado_atravessa_o_json_e_volta_igual():
    d = json.loads(json.dumps(residente._para_dict(RESULTADO)))
    r = residente._de_dict(d)
    assert r == RESULTADO
    assert r.palavras() == RESULTADO.palavras()
    assert r.para_schema_scribe() == RESULTADO.para_schema_scribe()


def test_desligado_pela_variavel_transcreve_no_processo(isolado, monkeypatch, capsys):
    monkeypatch.setenv("ATIVAVID_WHISPER_RESIDENTE", "0")
    m = _Motor()
    assert residente.transcrever(m, Path("a.wav")) is RESULTADO
    assert m.chamadas == 1 and residente.ultimo() == "desligado"
    assert "WHISPER_RESIDENTE" not in capsys.readouterr().out


def test_sem_servico_sobe_um_para_o_proximo_e_transcreve_aqui(isolado, monkeypatch, capsys):
    """O primeiro vídeo não espera o serviço nascer: MEDIDO +4,6 s se
    esperasse. Ele sobe destacado e o próximo vídeo o encontra de pé."""
    subiu = []
    monkeypatch.setattr(residente, "_subir", lambda: subiu.append(1))
    m = _Motor()
    assert residente.transcrever(m, Path("a.wav")) is RESULTADO
    assert m.chamadas == 1 and subiu == [1]
    assert residente.ultimo() == "fallback"
    saida = capsys.readouterr().out
    assert "WHISPER_RESIDENTE sem anuncio; subindo um para o proximo video" in saida
    # o trinco fica com quem subiu ate o servico se anunciar
    assert residente.TRINCO.exists()
    # segundo processo no mesmo instante: nao sobe outro
    m2 = _Motor()
    residente.transcrever(m2, Path("b.wav"))
    assert subiu == [1] and m2.chamadas == 1


def test_com_servico_de_pe_o_motor_local_nem_e_chamado(isolado, monkeypatch, capsys):
    info = {"pid": 4242, "port": 1, "token": "t", "versao": residente._versao()}
    monkeypatch.setattr(residente, "_servico_vivo", lambda: (info, ""))
    pedidos = []

    def pedir(i, caminho, corpo, timeout):
        pedidos.append((caminho, corpo))
        return {"ok": True, "resultado": residente._para_dict(RESULTADO),
                "saida": "TRANSCRIPTION ENGINE local model=medium device=cuda\n"
                         "WHISPER_GUARDA 5 -> 4 palavras (x)\n", "pedidos": 3}

    monkeypatch.setattr(residente, "_pedir", pedir)
    m = _Motor("medium")
    r = residente.transcrever(m, Path("a.wav"), idioma="pt", fonte_original=Path("v.mov"))
    assert m.chamadas == 0
    assert r.palavras() == RESULTADO.palavras() and r.tempos["residente"] >= 0
    assert pedidos[0][0] == "/transcrever"
    assert pedidos[0][1]["modelo"] == "medium" and pedidos[0][1]["idioma"] == "pt"
    assert pedidos[0][1]["fonte_original"].endswith("v.mov")
    saida = capsys.readouterr().out
    # as linhas do motor saem no stdout do helper, onde o pipeline as procura
    assert "TRANSCRIPTION ENGINE local model=medium device=cuda" in saida
    assert "WHISPER_GUARDA 5 -> 4" in saida
    assert "WHISPER_RESIDENTE hit pid=4242 carga=0.0s pedidos=3" in saida
    assert residente.ultimo() == "hit"


@pytest.mark.parametrize("resposta", [
    {"ok": False, "erro": "RuntimeError: cuda"},
    RuntimeError("conexao caiu"),
])
def test_servico_que_falha_cai_para_o_processo(isolado, monkeypatch, capsys, resposta):
    monkeypatch.setattr(residente, "_servico_vivo",
                        lambda: ({"pid": 1, "port": 1, "token": "t"}, ""))

    def pedir(*a, **k):
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    monkeypatch.setattr(residente, "_pedir", pedir)
    m = _Motor()
    assert residente.transcrever(m, Path("a.wav")) is RESULTADO
    assert m.chamadas == 1 and residente.ultimo() == "fallback"
    assert "transcrevendo no proprio processo" in capsys.readouterr().out


# ------------------------------------------------------------- o servico

@pytest.fixture()
def servico(isolado, monkeypatch):
    """O servidor HTTP de verdade, com o motor falso no lugar do Whisper."""
    mod = types.ModuleType("app.transcricao.whisper_local")
    mod.MotorWhisperLocal = _Motor
    mod.liberar = lambda: None
    mod._pid_vivo = lambda pid: True
    monkeypatch.setitem(sys.modules, "app.transcricao.whisper_local", mod)
    s = residente._Servico()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), residente._Handler)
    residente._Handler.servico = s
    s.servidor = srv
    th = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    th.start()
    info = {"pid": 4242, "port": srv.server_address[1], "token": s.token}
    yield types.SimpleNamespace(info=info, estado=s, servidor=srv)
    srv.shutdown()
    srv.server_close()


def test_o_servico_transcreve_e_devolve_o_que_o_motor_imprimiu(servico):
    r = residente._pedir(servico.info, "/transcrever",
                         {"audio": "a.wav", "idioma": "pt", "fonte_original": None,
                          "modelo": None}, timeout=5)
    assert r["ok"] is True and r["pedidos"] == 1
    assert residente._de_dict(r["resultado"]) == RESULTADO
    assert "TRANSCRIPTION ENGINE local model=medium device=cuda" in r["saida"]
    ping = residente._pedir(servico.info, "/ping", None, timeout=5)
    assert ping["ok"] and ping["carregado"] is True and ping["pedidos"] == 1


def test_token_errado_e_recusado(servico):
    info = dict(servico.info, token="errado")
    r = residente._pedir(info, "/transcrever", {"audio": "a.wav"}, timeout=5)
    assert r == {"ok": False, "erro": "token"}
    assert servico.estado.pedidos == 0


def test_encerrar_derruba_o_servico(servico):
    assert residente._pedir(servico.info, "/encerrar", {}, timeout=5) == {"ok": True}
    # o serve_forever sai sozinho; um pedido novo nao encontra ninguem
    import time
    for _ in range(50):
        try:
            residente._pedir(servico.info, "/ping", None, timeout=0.5)
            time.sleep(0.05)
        except OSError:
            break
    else:
        pytest.fail("o servico nao encerrou")


def test_o_servico_solta_o_modelo_e_sai_por_ociosidade_ou_atualizacao():
    """`_vigiar` é um laço com sono; a lógica é lida: dois relógios e a
    VERSION como gatilho de saída (o app atualizou por baixo)."""
    import inspect

    src = inspect.getsource(residente._vigiar)
    assert "s.carregado and parado > OCIOSO_MODELO_S" in src
    assert "_soltar_modelo(s)" in src
    assert "parado > OCIOSO_SAIR_S or atualizou" in src
    assert "_versao() != versao_inicial" in src
    assert "_apagar_info_se_minha()" in src
    assert residente.OCIOSO_MODELO_S <= residente.OCIOSO_SAIR_S


def test_o_instalador_derruba_o_servico_antes_de_copiar():
    """O serviço roda `<app>\\.venv\\Scripts\\python.exe -m app.transcricao.residente`
    e segura DLLs do torch/ctranslate2. O `PrepareToInstall` do instalador
    já mata python com o diretório do app na linha de comando — o serviço
    entra nessa regra por construção."""
    iss = (REPO / "installer" / "ativa-vid.iss").read_text(encoding="utf-8-sig")
    assert "^(python|pythonw|wscript|node|ffmpeg)" in iss
    assert "CommandLine -like" in iss and "ExpandConstant('{app}')" in iss
    # o conftest troca `_subir` por um no-op em todo teste: ler o arquivo
    modulo = Path(residente.__file__).read_text(encoding="utf-8")
    i = modulo.index("def _subir(")
    src = modulo[i:modulo.index("\ndef ", i + 1)]
    assert "resolve_python_cmd(RAIZ)" in src
    assert '"-m", "app.transcricao.residente"' in src
    assert "DETACHED_PROCESS" in src, "sobrevive ao fim do helper e do job"


# --------------------------------------------------------- a integracao

def test_o_helper_transcreve_pelo_residente_e_conta_na_telemetria():
    s = (REPO / "helpers" / "transcribe.py").read_text(encoding="utf-8")
    assert "resultado = residente.transcrever(motor, audio, idioma=language," in s
    assert "residente=residente.ultimo()," in s
    assert 'seg_residente=resultado.tempos.get("residente")' in s
    assert s.count("motor.transcrever(") == 0, "o unico caminho e o residente (que cai para o motor)"


def test_o_marcador_chega_ao_log_do_job():
    from leitura_de_codigo import apenas_codigo

    s = apenas_codigo(REPO / "pipeline" / "run_fast.py")
    i = s.index("_MARCADORES_TRANSCRICAO = (")
    assert '"WHISPER_RESIDENTE"' in s[i:s.index(")", i)]
