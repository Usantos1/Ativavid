# -*- coding: utf-8 -*-
"""Modelo Whisper residente entre jobs (5.0.73).

Cada job e um processo (`helpers/transcribe.py`), entao o `_CARREGADO` de
`whisper_local` morria com ele e o `medium` era carregado de novo a cada
video. MEDIDO na telemetria real (`~/ATIVAVID/transcricao-log.jsonl`):
3,6 s de mediana em dias normais, 8,1 s num lote de 24 (maximo 52,7 s) —
mais ~2 s de imports e a carga do VAD, que o faster-whisper tambem guarda
por processo. Este modulo segura o motor num processo proprio, que fica
vivo entre jobs e se encerra sozinho depois de `OCIOSO_S` sem pedidos.

Protocolo: HTTP em 127.0.0.1, porta efemera e token aleatorio, os dois
gravados em `INFO` (na pasta temporaria, como a vaga). Um pedido por vez —
o motor ja e assim, e a vaga entre processos continua valendo, porque e o
proprio `MotorWhisperLocal.transcrever` que roda la dentro. O cliente
(`transcrever`) tenta o servico; se nao existe, sobe um e espera; se nada
responde, transcreve no proprio processo, exatamente como antes. O
resultado e o MESMO codigo com o MESMO modelo — so muda quem chama.

Autorizado por ele em 05/09 ("faz tudo"), com a condicao de validar
palavra por palavra contra o caminho atual em videos reais antes de
publicar. `ATIVAVID_WHISPER_RESIDENTE=0` desliga (volta ao processo
proprio).
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent.parent
_TMP = Path(tempfile.gettempdir())
INFO = _TMP / "ativavid-whisper-residente.json"
TRINCO = _TMP / "ativavid-whisper-residente.subindo"
LOG = _TMP / "ativavid-whisper-residente.log"

# Dois relogios de ociosidade. Sem pedidos por OCIOSO_MODELO_S o modelo e
# solto (devolve os 2,66 GB de VRAM — a placa e a mesma do render); sem
# pedidos por OCIOSO_SAIR_S o processo sai. Entre um e outro o servico fica
# vivo e barato (imports e VAD ja feitos), e o proximo video paga so a
# carga do modelo. Num lote o intervalo entre transcricoes e o render do
# job anterior (1-2 min): 5 min cobre isso.
OCIOSO_MODELO_S = float(os.environ.get("ATIVAVID_WHISPER_RESIDENTE_OCIOSO") or 5 * 60)
OCIOSO_SAIR_S = float(os.environ.get("ATIVAVID_WHISPER_RESIDENTE_SAIR") or 30 * 60)
TEMPO_MAX_PEDIDO_S = 45 * 60     # vaga (ate 20 min) + transcricao longa
TRINCO_VELHO_S = 90.0            # subida abandonada: trinco mais velho que isso cai

# Para a telemetria do helper: hit | carga | fallback | desligado.
_ULTIMO = "desligado"


def ligado() -> bool:
    return (os.environ.get("ATIVAVID_WHISPER_RESIDENTE") or "1").strip() != "0"


def ultimo() -> str:
    return _ULTIMO


def _versao() -> str:
    try:
        return (RAIZ / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _pid_vivo(pid: int) -> bool:
    from app.transcricao.whisper_local import _pid_vivo as vivo

    return vivo(pid)


# ------------------------------------------------------------ resultado
# `ResultadoDeTranscricao` atravessa o HTTP como JSON e volta igual: os
# tres dataclasses sao planos, so `palavras` e tupla (vira lista no JSON).

def _para_dict(r: Any) -> dict:
    return dataclasses.asdict(r)


def _de_dict(d: dict) -> Any:
    from app.transcricao import Palavra, ResultadoDeTranscricao, Segmento

    segmentos = [
        Segmento(
            texto=str(s.get("texto") or ""), inicio=float(s["inicio"]),
            fim=float(s["fim"]), confianca=s.get("confianca"),
            palavras=tuple(
                Palavra(texto=str(p.get("texto") or ""), inicio=float(p["inicio"]),
                        fim=float(p["fim"]), confianca=p.get("confianca"))
                for p in (s.get("palavras") or ())),
        )
        for s in (d.get("segmentos") or [])
    ]
    return ResultadoDeTranscricao(
        texto=str(d.get("texto") or ""), segmentos=segmentos,
        idioma=str(d.get("idioma") or ""), duracao=float(d.get("duracao") or 0.0),
        motor=str(d.get("motor") or ""), modelo=str(d.get("modelo") or ""),
        backend=str(d.get("backend") or ""), tempos=dict(d.get("tempos") or {}),
    )


# --------------------------------------------------------------- cliente

def _ler_info() -> dict | None:
    """O servico anunciado em INFO (o anuncio; se ele vive, quem diz e o
    `/ping` — um OpenProcess entre arvores de processo diferentes nao e
    prova de nada)."""
    try:
        d = json.loads(INFO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("port") or not d.get("token"):
        return None
    return d


def _pedir(info: dict, caminho: str, corpo: dict | None, timeout: float) -> dict:
    c = HTTPConnection("127.0.0.1", int(info["port"]), timeout=timeout)
    try:
        if corpo is None:
            c.request("GET", caminho)
        else:
            dados = json.dumps({**corpo, "token": info["token"]}).encode("utf-8")
            c.request("POST", caminho, body=dados,
                      headers={"Content-Type": "application/json",
                               "Content-Length": str(len(dados))})
        r = c.getresponse()
        return json.loads(r.read().decode("utf-8") or "{}")
    finally:
        c.close()


def _responde(info: dict) -> bool:
    try:
        r = _pedir(info, "/ping", None, timeout=2.0)
    except Exception:  # noqa: BLE001
        return False
    return bool(r.get("ok")) and int(r.get("pid") or 0) == int(info.get("pid") or -1)


def _subir() -> None:
    """Sobe o servico DESTACADO: sobrevive ao fim do helper e do job."""
    from app.win_process import child_env, resolve_python_cmd

    cmd = [*resolve_python_cmd(RAIZ), "-m", "app.transcricao.residente"]
    env = child_env(os.environ.copy())
    partes = [str(RAIZ), str(RAIZ / "helpers")]
    for p in (env.get("PYTHONPATH") or "").split(os.pathsep):
        if p.strip() and p not in partes:
            partes.append(p.strip())
    env["PYTHONPATH"] = os.pathsep.join(partes)
    flags = 0
    for nome in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
        flags |= getattr(subprocess, nome, 0)
    subprocess.Popen(
        cmd, cwd=str(RAIZ), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        close_fds=True, creationflags=flags,
    )


def _trinco_pegar() -> bool:
    """So um cliente sobe o servico por vez. Trinco abandonado cai sozinho."""
    try:
        if TRINCO.exists() and time.time() - TRINCO.stat().st_mtime > TRINCO_VELHO_S:
            TRINCO.unlink()
    except OSError:
        pass
    try:
        fd = os.open(str(TRINCO), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(str(os.getpid()))
    return True


def _trinco_soltar() -> None:
    try:
        TRINCO.unlink()
    except OSError:
        pass


def _servico_vivo() -> tuple[dict | None, str]:
    """Um servico vivo, desta versao, respondendo — ou (None, motivo).

    Versao velha (o app atualizou por baixo dele): pede para sair, e o
    chamador sobe outro. Mudo: o anuncio e de um processo que morreu (ou
    esta preso); quem sobe o proximo troca o anuncio."""
    info = _ler_info()
    if info is None:
        return None, "sem anuncio"
    if not _responde(info):
        return None, f"anuncio de pid {info.get('pid')} nao responde"
    if info.get("versao") != _versao():
        try:
            _pedir(info, "/encerrar", {}, timeout=3.0)
        except Exception:  # noqa: BLE001
            pass
        return None, f"versao {info.get('versao')} != {_versao()}"
    return info, ""


def _subir_para_o_proximo() -> bool:
    """Sobe o servico SEM esperar por ele: este video e transcrito no
    proprio processo, como hoje, e o proximo ja acha o servico de pe.

    MEDIDO (lab de 05/09, 3 videos reais): esperar o servico nascer e
    carregar custava +4,6 s no primeiro video em relacao a hoje; nao
    esperar custa ~0 — e quem transcreve um video por vez nunca fica mais
    lento do que esta. O trinco e solto pelo proprio servico quando ele se
    anuncia (ou envelhece em TRINCO_VELHO_S se ele nao nasceu)."""
    if not _trinco_pegar():
        return False
    try:
        _subir()
        return True
    except Exception as e:  # noqa: BLE001
        _trinco_soltar()
        print(f"WHISPER_RESIDENTE nao subiu {type(e).__name__}: {str(e)[:120]}",
              flush=True)
        return False


def transcrever(motor: Any, audio: Path, *, idioma: str | None = None,
                fonte_original: Path | None = None) -> Any:
    """`motor.transcrever(...)` pelo servico residente, ou no proprio
    processo quando ele nao existe/nao responde. Mesmo resultado."""
    global _ULTIMO

    def no_processo(motivo: str) -> Any:
        global _ULTIMO
        _ULTIMO = "fallback" if motivo else "desligado"
        if motivo:
            print(f"WHISPER_RESIDENTE {motivo} — transcrevendo no proprio processo",
                  flush=True)
        return motor.transcrever(audio, idioma=idioma, fonte_original=fonte_original)

    if not ligado():
        return no_processo("")
    info, motivo = _servico_vivo()
    if info is None:
        subiu = _subir_para_o_proximo()
        return no_processo(f"{motivo}; " + ("subindo um para o proximo video" if subiu
                                             else "outro processo esta subindo um"))
    t0 = time.perf_counter()
    try:
        resp = _pedir(info, "/transcrever", {
            "audio": str(audio), "idioma": idioma,
            "fonte_original": str(fonte_original) if fonte_original else None,
            "modelo": getattr(motor, "_pedido", None),
        }, timeout=TEMPO_MAX_PEDIDO_S)
    except Exception as e:  # noqa: BLE001
        return no_processo(f"falhou {type(e).__name__}: {str(e)[:120]}")
    # As linhas que o motor imprimiu la (TRANSCRIPTION ENGINE, WHISPER_*)
    # saem aqui, no lugar de sempre: o pipeline as procura no stdout do helper.
    saida = str(resp.get("saida") or "")
    if saida:
        sys.stdout.write(saida if saida.endswith("\n") else saida + "\n")
        sys.stdout.flush()
    if not resp.get("ok"):
        return no_processo(f"erro no servico: {str(resp.get('erro') or '?')[:160]}")
    r = _de_dict(resp["resultado"])
    carga = float(r.tempos.get("carregar_modelo") or 0.0)
    _ULTIMO = "carga" if carga > 0 else "hit"
    r.tempos["residente"] = round(time.perf_counter() - t0, 3)
    print(f"WHISPER_RESIDENTE {_ULTIMO} pid={info['pid']} carga={carga:.1f}s "
          f"pedidos={int(resp.get('pedidos') or 0)}", flush=True)
    return r


# --------------------------------------------------------------- servico

class _Servico:
    def __init__(self) -> None:
        self.token = secrets.token_hex(16)
        self.ultimo = time.monotonic()
        self.ocupado = threading.Lock()
        self.carregado = False
        self.pedidos = 0
        self.servidor: ThreadingHTTPServer | None = None


def _log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


class _Handler(BaseHTTPRequestHandler):
    servico: _Servico

    def log_message(self, *a: Any) -> None:  # noqa: D102 — o log e o nosso
        pass

    def _json(self, code: int, d: dict) -> None:
        dados = json.dumps(d, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_GET(self) -> None:  # noqa: N802
        s = self.servico
        if self.path == "/ping":
            self._json(200, {"ok": True, "pid": os.getpid(), "versao": _versao(),
                             "carregado": s.carregado, "pedidos": s.pedidos,
                             "ocupado": s.ocupado.locked()})
            return
        self._json(404, {"ok": False})

    def do_POST(self) -> None:  # noqa: N802
        s = self.servico
        try:
            n = int(self.headers.get("Content-Length") or 0)
            corpo = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
        except Exception:  # noqa: BLE001
            self._json(400, {"ok": False, "erro": "corpo invalido"})
            return
        if corpo.get("token") != s.token:
            self._json(403, {"ok": False, "erro": "token"})
            return
        if self.path == "/encerrar":
            _log("pedido de encerramento")
            self._json(200, {"ok": True})
            threading.Thread(target=s.servidor.shutdown, daemon=True).start()
            return
        if self.path != "/transcrever":
            self._json(404, {"ok": False})
            return
        with s.ocupado:
            s.ultimo = time.monotonic()
            saida = io.StringIO()
            t0 = time.perf_counter()
            try:
                from app.transcricao.whisper_local import MotorWhisperLocal

                motor = MotorWhisperLocal(corpo.get("modelo") or None)
                fonte = corpo.get("fonte_original")
                with contextlib.redirect_stdout(saida):
                    r = motor.transcrever(
                        Path(corpo["audio"]), idioma=corpo.get("idioma") or None,
                        fonte_original=Path(fonte) if fonte else None)
                s.carregado = True
                s.pedidos += 1
                resp = {"ok": True, "resultado": _para_dict(r),
                        "saida": saida.getvalue(), "pedidos": s.pedidos}
                _log(f"transcrito {Path(corpo['audio']).name} em "
                     f"{time.perf_counter() - t0:.1f}s (carga "
                     f"{r.tempos.get('carregar_modelo', 0)}s) pedido #{s.pedidos}")
            except Exception as e:  # noqa: BLE001
                resp = {"ok": False, "erro": f"{type(e).__name__}: {str(e)[:300]}",
                        "saida": saida.getvalue()}
                _log(f"falha: {resp['erro']}")
            finally:
                s.ultimo = time.monotonic()
        self._json(200, resp)


def _escrever_info(d: dict) -> None:
    tmp = INFO.with_suffix(f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.replace(tmp, INFO)


def _apagar_info_se_minha() -> None:
    try:
        d = json.loads(INFO.read_text(encoding="utf-8"))
        if int(d.get("pid") or 0) == os.getpid():
            INFO.unlink()
    except (OSError, ValueError):
        pass


def _soltar_modelo(s: _Servico) -> None:
    try:
        from app.transcricao.whisper_local import liberar

        liberar()
    except Exception:  # noqa: BLE001
        pass
    s.carregado = False


def _vigiar(s: _Servico, versao_inicial: str) -> None:
    """Ocioso por OCIOSO_MODELO_S: solta o modelo (VRAM). Ocioso por
    OCIOSO_SAIR_S, ou o app atualizou por baixo (VERSION mudou): sai."""
    while True:
        time.sleep(5.0)
        if s.ocupado.locked():
            continue
        parado = time.monotonic() - s.ultimo
        if s.carregado and parado > OCIOSO_MODELO_S:
            _log(f"ocioso ha {parado:.0f}s: soltando o modelo")
            with s.ocupado:
                _soltar_modelo(s)
        atualizou = _versao() != versao_inicial
        if parado > OCIOSO_SAIR_S or atualizou:
            _log("app atualizou: encerrando" if atualizou
                 else f"ocioso ha {parado:.0f}s: encerrando")
            with s.ocupado:
                _soltar_modelo(s)
            _apagar_info_se_minha()
            if s.servidor is not None:
                s.servidor.shutdown()
            return


def servir() -> int:
    """O processo do servico. `python -m app.transcricao.residente`."""
    try:
        f = open(LOG, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = f
        sys.stderr = f
    except OSError:
        pass
    outro = _ler_info()
    if outro is not None and int(outro.get("pid") or 0) != os.getpid() and _responde(outro):
        _log(f"ja existe um servico vivo (pid {outro.get('pid')}); saindo")
        _trinco_soltar()   # quem me subiu nao pode ficar segurando o trinco
        return 0
    s = _Servico()
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    _Handler.servico = s
    s.servidor = srv
    versao = _versao()
    _escrever_info({"pid": os.getpid(), "port": srv.server_address[1],
                    "token": s.token, "versao": versao, "inicio": time.time()})
    _trinco_soltar()   # anunciado: quem subiu pode parar de segurar
    _log(f"servindo em 127.0.0.1:{srv.server_address[1]} pid={os.getpid()} "
         f"versao={versao} solta o modelo em {OCIOSO_MODELO_S:.0f}s, "
         f"sai em {OCIOSO_SAIR_S:.0f}s")
    threading.Thread(target=_vigiar, args=(s, versao), daemon=True).start()
    try:
        srv.serve_forever(poll_interval=0.5)
    finally:
        _apagar_info_se_minha()
        srv.server_close()
        _log("encerrado")
    return 0


if __name__ == "__main__":
    if str(RAIZ) not in sys.path:
        sys.path.insert(0, str(RAIZ))
    raise SystemExit(servir())
