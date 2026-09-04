# -*- coding: utf-8 -*-
"""Quem abriu o ATIVAVID, quando, em qual maquina.

Pedido de 30/08: "todo mundo que baixar e abrir gerar log pra gente
bloquear o computador em caso de compartilhamento ilegal".

Duas pontas, porque uma so nao resolve:

  LOCAL   `~/ATIVAVID/aberturas.jsonl`, uma linha por abertura. Funciona
          sem internet e sem servidor nenhum — e o que o suporte pede
          quando precisa entender uma maquina especifica.

  SERVIDOR um aviso solto para a funcao `ativavid_open` do Supabase. Se
          ela ainda nao existir, o servidor responde 404 e este modulo
          ignora — nada quebra, nada trava. O SQL para ligar isso esta em
          `supabase/registro_de_uso.sql`.

O que vai: identificador da maquina (o mesmo que a licenca ja usa), nome
do computador, usuario do Windows, versao do app e em que estado a
licenca estava. Nada de conteudo dos videos, nada de arquivos.

Nunca derruba nem atrasa a abertura: roda em segundo plano e engole
qualquer erro. Registro de uso nao vale um app que nao abre.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_PATH = Path.home() / "ATIVAVID" / "aberturas.jsonl"
# ~2000 aberturas; passou disso, a metade mais velha sai. O arquivo e para
# o suporte ler, nao para virar um banco de dados.
LIMITE_BYTES = 400_000


def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dados_da_maquina() -> dict[str, Any]:
    """O cartao de visita desta instalacao."""
    from app import license as lic

    try:
        st = lic.entitlement(refresh=False)
        modo = str(st.get("mode") or ("licensed" if st.get("entitled") else ""))
        email = str(st.get("accountEmail") or "")
        chave = str(st.get("licenseKeyHint") or "")
    except Exception:  # noqa: BLE001
        modo, email, chave = "", "", ""
    if not email:
        # 5.0.15: `accountEmail` so vem para quem esta liberado POR CONTA.
        # Quem entrou e esta em trial, bloqueado ou com chave abria o app
        # todo dia com email vazio (o proprio dono aparecia como "—" nas
        # aberturas de 04/09). O e-mail logado vale para o registro.
        try:
            from app import auth as au

            email = str(au._load().get("email") or "").strip().lower()
        except Exception:  # noqa: BLE001
            email = ""
    try:
        maquina = socket.gethostname()
    except OSError:
        maquina = ""
    return {
        "quando": _agora(),
        "device": lic.device_id(),
        "maquina": maquina,
        "usuario": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        "so": f"{platform.system()} {platform.release()}",
        "versao": lic._app_version(),
        "licenca": modo,
        "email": email,
        "chave": chave,
    }


def _girar(caminho: Path) -> None:
    """Corta o arquivo pela metade quando ele passa do limite."""
    try:
        if caminho.stat().st_size <= LIMITE_BYTES:
            return
        linhas = caminho.read_text(encoding="utf-8").splitlines()
        caminho.write_text("\n".join(linhas[len(linhas) // 2:]) + "\n",
                           encoding="utf-8")
    except OSError:
        pass


def anotar(evento: str = "abriu", extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Grava uma linha no log local. Devolve o que gravou."""
    linha = dados_da_maquina()
    linha["evento"] = evento
    if extra:
        linha.update(extra)
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _girar(LOG_PATH)
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return linha


def _avisar_servidor(linha: dict[str, Any]) -> None:
    """Manda a abertura para o Supabase, se a funcao la souber receber.

    Funcao PROPRIA (`ativavid_open`), e nao mais uma acao dentro da
    `ativavid_license`: duas assinaturas com parametros opcionais deixam o
    PostgREST ambiguo — foi por isso que a versao de 3 argumentos dela
    precisou ser derrubada. Resposta ignorada de proposito: este aviso nao
    pode influenciar o estado da licenca.
    """
    try:
        from app import license as lic

        if not lic.configured():
            return
        payload = {
            "p_device_id": linha.get("device"),
            "p_app_version": linha.get("versao"),
            "p_host": linha.get("maquina"),
            "p_user": linha.get("usuario"),
            "p_os": linha.get("so"),
            "p_licenca": linha.get("licenca"),
        }
        # O e-mail logado vai junto (4.93): sem ele o painel nao tinha como
        # dizer DE QUEM era um PC em trial — "esse tem conta de e-mail e
        # nao exibe ali" (03/09). Servidor com a funcao antiga (sem
        # `p_email`) responde 404 PGRST202; ai manda do jeito antigo.
        email = str(linha.get("email") or "").strip().lower()
        if email:
            code, _ = lic._http_rpc(dict(payload, p_email=email), fn="ativavid_open")
            if 200 <= code < 300:
                return
            # Qualquer outra resposta cai no jeito antigo: so o 404 (RPC sem
            # `p_email`) era tratado, e um JWT vencido (401) numa maquina
            # bloqueada perdia a abertura em silencio.
        lic._http_rpc(payload, fn="ativavid_open")
    except Exception:  # noqa: BLE001 — nunca atrapalha a abertura
        pass


def registrar_abertura() -> None:
    """Chamada no arranque do app. Nao bloqueia nem atrasa."""
    def _trabalho() -> None:
        try:
            linha = anotar("abriu")
            _avisar_servidor(linha)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_trabalho, daemon=True,
                     name="registro-abertura").start()


def ler(limite: int = 200) -> list[dict[str, Any]]:
    """As ultimas aberturas, da mais nova para a mais velha."""
    try:
        linhas = LOG_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for ln in reversed(linhas):
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
        if len(out) >= limite:
            break
    return out
