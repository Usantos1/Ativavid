# -*- coding: utf-8 -*-
"""O pacote de trilhas e efeitos que o cliente baixa uma vez.

Por que existe: a IA local de musica so roda em placa NVIDIA, e o plano B
sempre foi "deixe MP3s em ATIVAVID/Biblioteca/Trilhas" — uma pasta que
nasce VAZIA. Numa maquina sem NVIDIA (caso real de 04/09: uma cliente com
Intel UHD) isso significava video sem trilha nenhuma, para sempre, sem que
ninguem soubesse o que fazer.

O pacote e o acervo do proprio dono do app: 376 trilhas e 219 efeitos,
596 arquivos, ~370 MB. Baixa como o instalador baixa — pedaco a pedaco,
com barra — e descompacta na Biblioteca REAL (a que fica ao lado dos
Projetos; a do `Path.home()` ja escondeu trilha e b-roll de quem leu a
errada).

O que ele NUNCA faz: apagar ou sobrescrever arquivo do usuario. Quem ja
tem uma pasta cheia recebe so o que falta, e o numero de novos aparece na
tela. Rodar duas vezes nao duplica nada.
"""
from __future__ import annotations

import json
import threading
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

# As duas pastas que o pacote traz. Qualquer outra coisa dentro do ZIP e
# ignorada: o arquivo vem da internet e nao manda no disco de ninguem.
PASTAS = ("Trilhas", "Efeitos")
EXTENSOES = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".csv"}
MB_TOTAL = 370

_PROGRESSO: dict[str, Any] = {
    "estado": "parado",   # parado | baixando | instalando | pronto | erro
    "baixado": 0,
    "total": 0,
    "novos": 0,
    "erro": "",
}
_TRAVA = threading.Lock()
_EM_ANDAMENTO = False


def pasta_da_biblioteca(raiz_projetos: Path | None = None) -> Path:
    from app.broll_library import library_root

    return library_root(raiz_projetos)


def _conta(raiz: Path) -> int:
    n = 0
    for p in PASTAS:
        try:
            n += sum(1 for f in (raiz / p).rglob("*")
                     if f.is_file() and f.suffix.lower() in EXTENSOES
                     and f.suffix.lower() != ".csv")
        except OSError:
            continue
    return n


TAG = "biblioteca"      # release fixa, separada das versoes do app
_URL_CACHE: dict[str, Any] = {}


def url_do_pacote() -> str:
    """O asset .zip da release `biblioteca`, pelo mesmo caminho do instalador.

    Release PROPRIA e nao a `latest`: assim trocar o pacote nao exige lancar
    versao do app, e lancar versao do app nao troca o pacote sem querer.

    Cacheado na sessao: a tela pergunta o estado de tempos em tempos e nao
    ha por que bater na API do GitHub a cada vez.
    """
    if "url" in _URL_CACHE:
        return str(_URL_CACHE["url"])
    url = ""
    try:
        from app.update_check import configured_repo

        gh = configured_repo()
        if gh:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{gh}/releases/tags/{TAG}",
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": "ATIVAVID"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for asset in (data.get("assets") or []):
                nome = str((asset or {}).get("name") or "").lower()
                if nome.endswith(".zip") and (asset or {}).get("browser_download_url"):
                    url = str(asset["browser_download_url"])
                    break
    except Exception:  # noqa: BLE001 — sem rede o botao so nao aparece
        return ""       # sem cache: da para tentar de novo quando voltar
    _URL_CACHE["url"] = url
    return url


def estado(raiz_projetos: Path | None = None) -> dict[str, Any]:
    raiz = pasta_da_biblioteca(raiz_projetos)
    return {
        "arquivos": _conta(raiz),
        "pasta": str(raiz),
        "mbTotal": MB_TOTAL,
        "url": url_do_pacote(),
        "rodando": _EM_ANDAMENTO,
        **{k: v for k, v in _PROGRESSO.items()},
    }


def progresso() -> dict[str, Any]:
    return dict(_PROGRESSO)


def _seguro(nome: str) -> Path | None:
    """O caminho de dentro do ZIP, se ele for aceitavel.

    Zip vindo da internet nao escreve onde quiser: nada de caminho
    absoluto, nada de `..`, so as duas pastas conhecidas e so as extensoes
    de audio. Sem isto um ZIP trocado escreveria em qualquer lugar do
    disco (zip slip).
    """
    p = Path(nome.replace("\\", "/"))
    if p.is_absolute() or any(x == ".." for x in p.parts):
        return None
    if len(p.parts) < 2 or p.parts[0] not in PASTAS:
        return None
    if p.suffix.lower() not in EXTENSOES:
        return None
    return p


def instalar(*, raiz_projetos: Path | None = None) -> dict[str, Any]:
    """(ok, quantos entraram). Nunca levanta; nunca sobrescreve."""
    global _EM_ANDAMENTO
    url = url_do_pacote()
    if not url:
        return {"ok": False, "error": "o pacote ainda não foi publicado"}
    raiz = pasta_da_biblioteca(raiz_projetos)
    tmp = raiz / "_pacote.part"
    _PROGRESSO.update({"estado": "baixando", "baixado": 0, "total": 0,
                       "novos": 0, "erro": ""})
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        # Pedaco a pedaco para a tela ter barra: sao ~370 MB, e sem ela o
        # app fica mudo por minutos (mesma licao do instalador).
        with urllib.request.urlopen(url, timeout=180) as resp, open(tmp, "wb") as f:
            _PROGRESSO["total"] = int(resp.headers.get("Content-Length") or 0)
            while True:
                pedaco = resp.read(512 * 1024)
                if not pedaco:
                    break
                f.write(pedaco)
                _PROGRESSO["baixado"] = int(_PROGRESSO["baixado"]) + len(pedaco)
    except (OSError, ValueError) as e:
        _PROGRESSO.update({"estado": "erro", "erro": str(e)[:200]})
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"download falhou: {e}"}

    _PROGRESSO["estado"] = "instalando"
    novos = 0
    try:
        with zipfile.ZipFile(tmp) as z:
            for item in z.infolist():
                if item.is_dir():
                    continue
                rel = _seguro(item.filename)
                if rel is None:
                    continue
                destino = raiz / rel
                if destino.exists():
                    continue          # o do usuario manda
                destino.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as origem, open(destino, "wb") as saida:
                    saida.write(origem.read())
                novos += 1
    except (OSError, zipfile.BadZipFile) as e:
        _PROGRESSO.update({"estado": "erro", "erro": str(e)[:200]})
        return {"ok": False, "error": f"o pacote veio quebrado: {e}"}
    finally:
        tmp.unlink(missing_ok=True)

    _PROGRESSO.update({"estado": "pronto", "novos": novos})
    return {"ok": True, "novos": novos, "arquivos": _conta(raiz)}


def instalar_em_fundo(raiz_projetos: Path | None = None) -> dict[str, Any]:
    """Dispara e devolve na hora — a tela pergunta o progresso depois.

    A trava impede dois downloads de 370 MB ao mesmo tempo (dois cliques
    no botao, ou o botao e o Diagnostico juntos).
    """
    global _EM_ANDAMENTO
    with _TRAVA:
        if _EM_ANDAMENTO:
            return {"ok": True, "jaRodando": True}
        _EM_ANDAMENTO = True

    def _rodar() -> None:
        global _EM_ANDAMENTO
        try:
            instalar(raiz_projetos=raiz_projetos)
        finally:
            _EM_ANDAMENTO = False

    threading.Thread(target=_rodar, daemon=True,
                     name="biblioteca-pacote").start()
    return {"ok": True, "iniciado": True}
