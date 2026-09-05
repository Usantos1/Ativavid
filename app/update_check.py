"""Atualização do app — checa releases GitHub + abre URL / instalador."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "VERSION"
DEFAULT_VERSION = "0.1.0"

# Versão/código deste PROCESSO — congelados no 1º uso.
# Depois do instalador atualizar o VERSION no disco, um processo antigo
# ainda reportaria a versão nova se lesse o arquivo a cada /api/health —
# e o handoff acharia que já está atualizado (titlebar/JS velhos).
_RUNNING_VERSION: str | None = None
_BOOT_FINGERPRINT: str | None = None


def current_version() -> str:
    """Versão no disco agora (pode mudar após instalar sem reiniciar)."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip() or DEFAULT_VERSION
    py = REPO / "pyproject.toml"
    if py.exists():
        for line in py.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[-1].strip().strip('"').strip("'") or DEFAULT_VERSION
    return DEFAULT_VERSION


def running_version() -> str:
    """Versão com que ESTE processo subiu (não muda se o arquivo VERSION for trocado)."""
    global _RUNNING_VERSION
    if _RUNNING_VERSION is None:
        _RUNNING_VERSION = current_version()
    return _RUNNING_VERSION


def _studio_stamp() -> str:
    p = REPO / "assets" / "studio" / "studio.js"
    try:
        st = p.stat()
        return f"{int(st.st_mtime_ns)}-{st.st_size}"
    except OSError:
        return "0"


def disk_fingerprint() -> str:
    """Assinatura do build no disco (versão + studio.js)."""
    return f"{current_version()}|{_studio_stamp()}"


def boot_fingerprint() -> str:
    """Assinatura do build com que este processo subiu."""
    global _BOOT_FINGERPRINT
    if _BOOT_FINGERPRINT is None:
        _BOOT_FINGERPRINT = f"{running_version()}|{_studio_stamp()}"
    return _BOOT_FINGERPRINT


def configured_repo() -> str:
    """owner/name — settings, env, ou constante vazia."""
    env = (os.environ.get("ATIVAVID_GITHUB_REPO") or os.environ.get("GITHUB_REPO") or "").strip()
    if env:
        return env
    try:
        from app.settings_store import load_settings

        s = load_settings().get("githubRepo") or ""
        if isinstance(s, str) and s.strip():
            return s.strip()
    except Exception:
        pass
    return "Usantos1/Ativavid"


def _versao_tupla(v: Any) -> tuple[int, ...]:
    """"2.47" -> (2, 47). Pedaco nao numerico vale 0, para nunca levantar."""
    partes = []
    for pedaco in str(v or "").lstrip("vV").split("."):
        digitos = "".join(c for c in pedaco if c.isdigit())
        partes.append(int(digitos) if digitos else 0)
    return tuple(partes) or (0,)


def _e_mais_nova(candidata: Any, atual: Any) -> bool:
    """Compara NUMERO, nao texto.

    O ramo do GitHub usava `tag != cur`: qualquer tag diferente virava
    "atualizacao", inclusive uma mais VELHA — o app ofereceria um downgrade.
    """
    a, b = _versao_tupla(candidata), _versao_tupla(atual)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def check_update(*, channel: str = "stable") -> dict[str, Any]:
    cur = current_version()
    gh = configured_repo()
    result: dict[str, Any] = {
        "ok": True,
        "enabled": True,
        "channel": channel or "stable",
        "currentVersion": cur,
        "latestVersion": None,
        "updateAvailable": False,
        "force": False,
        "releaseUrl": None,
        "downloadUrl": None,
        "downloadSha256": None,
        "githubRepo": gh or None,
        "setupPath": str(REPO / "installer" / "setup.ps1"),
        "message": f"Build local {cur}.",
        "source": "local",
    }

    # Preferência: política do Supabase (via cache de licença)
    try:
        from app import license as lic

        if lic.configured():
            st = lic.public_status()
            upd = st.get("update") if isinstance(st.get("update"), dict) else None
            latest_sb = str((upd or {}).get("latestVersion") or "").lstrip("v")
            # A politica do Supabase so manda quando tem NOVIDADE de verdade,
            # ou quando e update obrigatorio. Ela estava parada numa versao
            # antiga (0.1.24 contra 2.47 instalada) e, como este ramo retornava
            # aqui, o GitHub nunca era consultado: TODA release publicada ficou
            # invisivel para o app, que dizia "sem atualizacao" para sempre.
            manda_supabase = bool(upd) and (
                bool(upd.get("force"))
                or (bool(latest_sb) and _e_mais_nova(latest_sb, cur))
            )
            if manda_supabase:
                latest = latest_sb or None
                result["latestVersion"] = latest
                result["force"] = bool(upd.get("force"))
                # A COMPARACAO que acabou de ser feita decide, nao a flag
                # gravada no cache. A flag foi calculada quando o cache foi
                # escrito — antes da release — e vinha False: o app sabia
                # que 5.0.28 > 5.0.27 (entrou neste ramo por isso) e ainda
                # assim dizia "Voce esta em 5.0.27 — sem atualizacao" (print
                # dele, 04/09). Toda release ficava invisivel por ate 30 min
                # para quem clicasse em Verificar.
                result["updateAvailable"] = bool(
                    upd.get("force")
                    or (bool(latest_sb) and _e_mais_nova(latest_sb, cur)))
                result["downloadUrl"] = upd.get("downloadUrl") or None
                # O hash so vem da politica do Supabase (o GitHub e o que
                # ele protege): instalador trocado la nao passa aqui.
                result["downloadSha256"] = (
                    str(upd.get("downloadSha256") or "").strip().lower() or None)
                result["releaseUrl"] = (
                    upd.get("downloadUrl")
                    or (f"https://github.com/{gh}/releases" if gh else None)
                )
                result["source"] = "supabase"
                if result["force"]:
                    result["message"] = upd.get("message") or (
                        f"Atualize para v{latest or '?'} para continuar."
                    )
                    result["tooltip"] = f"Update obrigatório · v{latest or '?'}"
                elif result["updateAvailable"]:
                    result["message"] = upd.get("message") or f"Nova versão {latest} disponível"
                    result["tooltip"] = f"Atualizar para v{latest} · clique"
                else:
                    result["message"] = f"Você está em {cur} — sem atualização."
                    result["tooltip"] = f"v{cur} · em dia · clique para checar"
                return result
    except Exception:  # noqa: BLE001
        pass

    if not gh:
        result["message"] = f"v{cur} · clique para checar"
        result["tooltip"] = f"v{cur} · clique para checar"
        return result
    url = f"https://api.github.com/repos/{gh}/releases/latest"
    try:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ATIVAVID"},
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = str(data.get("tag_name") or "").lstrip("v")
        result["latestVersion"] = tag or None
        # O QUE muda na versao nova. O corpo da release ja vinha na resposta
        # e era jogado fora: "Nova versao disponivel" nao diz se vale o
        # clique. Tres linhas bastam — quem quiser o resto abre o release.
        result["notes"] = _resumo_das_notas(data.get("body"))
        result["releaseUrl"] = data.get("html_url")
        result["source"] = "github"
        # Asset .exe se existir (instalador)
        assets = data.get("assets") if isinstance(data.get("assets"), list) else []
        for asset in assets:
            name = str((asset or {}).get("name") or "").lower()
            browser = (asset or {}).get("browser_download_url")
            if not browser:
                continue
            if name.endswith(".exe") or "install" in name or "instalar" in name:
                result["downloadUrl"] = browser
                break
        if not result["downloadUrl"]:
            result["downloadUrl"] = f"https://github.com/{gh}/releases/latest"
        if not result.get("releaseUrl"):
            result["releaseUrl"] = f"https://github.com/{gh}/releases/latest"
        if tag and _e_mais_nova(tag, cur):
            result["updateAvailable"] = True
            result["message"] = f"Nova versão {tag} disponível"
            result["tooltip"] = f"Atualizar para v{tag} · clique"
        else:
            result["message"] = f"Você está em {cur} — sem atualização."
            result["tooltip"] = f"v{cur} · em dia · clique para checar"
    except Exception as e:  # noqa: BLE001
        err = str(e)
        result["releaseUrl"] = f"https://github.com/{gh}/releases"
        if "404" in err:
            result["message"] = f"v{cur} · sem releases em {gh} (publique um Release no GitHub)."
            result["tooltip"] = f"v{cur} · sem release · clique"
        else:
            result["message"] = f"Não consegui checar online ({e}). Versão local: {cur}."
            result["tooltip"] = f"v{cur} · offline · clique para tentar"
    return result


def _resumo_das_notas(corpo: object, limite: int = 3) -> list[str]:
    """As primeiras linhas de lista do changelog, sem marcacao."""
    import re as _re

    texto = str(corpo or "")
    fora: list[str] = []
    atual = ""

    def _fechar() -> None:
        nonlocal atual
        limpa = _re.sub(r"[*_`]+", "", atual).strip()
        limpa = _re.sub(r"\s+", " ", limpa)
        if limpa:
            fora.append(limpa[:200])
        atual = ""

    tem_lista = any(l.strip().startswith(("- ", "* "))
                    for l in texto.splitlines())
    for linha in texto.splitlines():
        nua = linha.strip()
        if nua.startswith(("- ", "* ")):
            _fechar()
            atual = nua[2:]
        elif atual and nua and not nua.startswith("#"):
            # o changelog quebra a linha no meio da frase: sem juntar, a
            # nota chegava cortada ("O aviso de versao nova agora aparece")
            atual += " " + nua
        elif not nua:
            _fechar()
        elif not tem_lista and nua and not nua.startswith("#"):
            # Corpo SEM lista. Conferido na maquina do usuario com ele na
            # 4.07: `notes` vinha vazio e o aviso dizia que havia versao
            # nova sem dizer nada sobre ela. Aviso mudo e quase o mesmo que
            # nao avisar.
            atual = nua
        if len(fora) >= limite:
            return fora[:limite]
    _fechar()
    return fora[:limite]


def open_url(url: str) -> dict[str, Any]:
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "URL inválida"}
    try:
        if sys.platform == "win32":
            os.startfile(url)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", url], check=False)
        else:
            subprocess.run(["xdg-open", url], check=False)
        return {"ok": True, "url": url}
    except OSError as e:
        return {"ok": False, "error": str(e)}


_PROGRESSO: dict[str, Any] = {"estado": "parado", "baixado": 0, "total": 0,
                              "erro": "", "versao": ""}


def progresso_da_atualizacao() -> dict[str, Any]:
    """Quanto já baixou — a tela pergunta a cada instante para a barra."""
    d = dict(_PROGRESSO)
    t, b = int(d.get("total") or 0), int(d.get("baixado") or 0)
    d["pct"] = int(b * 100 / t) if t > 0 else 0
    return d


def _sha256_do_arquivo(caminho: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def baixar_e_instalar(assincrono: bool = False) -> dict[str, Any]:
    """Baixa o instalador da versao nova e o executa — UM clique.

    O ciclo manual era: aviso de versao -> abrir o navegador -> baixar ->
    achar o exe -> rodar (e o usuario pedia "cade o instalador?" a cada
    release). O app ja sabe a URL do exe pela politica de versao; baixar
    para %TEMP% e executar fecha o ciclo — o proprio instalador derruba o
    app (PrepareToInstall) e o reabre no Concluir.
    """
    info = check_update()
    url = str(info.get("downloadUrl") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "a política de versão não trouxe a URL do instalador"}
    nome = url.rsplit("/", 1)[-1] or ""
    if not nome.lower().endswith(".exe"):
        return {"ok": False, "error": f"o download não é um instalador: {nome or url}"}
    if sys.platform != "win32":
        return open_url(url)
    import shutil
    import tempfile
    import urllib.request

    destino = Path(tempfile.gettempdir()) / "ativavid-update" / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".part")
    _PROGRESSO.update({"estado": "baixando", "baixado": 0, "total": 0,
                       "erro": "", "versao": str(info.get("latestVersion") or "")})
    try:
        # Pedaco a pedaco para a tela poder mostrar a barra: com
        # `copyfileobj` o app ficava mudo do clique ate o instalador abrir,
        # e o usuario nao tinha como saber se estava acontecendo algo.
        with urllib.request.urlopen(url, timeout=180) as resp, open(tmp, "wb") as f:
            _PROGRESSO["total"] = int(resp.headers.get("Content-Length") or 0)
            while True:
                pedaco = resp.read(256 * 1024)
                if not pedaco:
                    break
                f.write(pedaco)
                _PROGRESSO["baixado"] = int(_PROGRESSO["baixado"]) + len(pedaco)
        tmp.replace(destino)
    except OSError as e:
        _PROGRESSO.update({"estado": "erro", "erro": str(e)[:200]})
        return {"ok": False, "error": f"download falhou: {e}"}
    if destino.stat().st_size < 1_000_000:
        _PROGRESSO.update({"estado": "erro", "erro": "instalador pequeno demais"})
        return {"ok": False, "error": "o instalador baixado veio pequeno demais — tente pelo navegador"}
    # 5.0.41: o arquivo tem de ser O publicado. Ate aqui o app executava o
    # que quer que viesse da URL: um instalador trocado no GitHub (conta
    # invadida, release editada) rodaria em toda maquina de cliente no
    # proximo "Atualizar agora". O SHA-256 vem da politica do Supabase, que
    # o `publicar_versao.py` grava a partir do exe local; para trocar o
    # instalador o atacante precisaria dos dois lugares. Sem hash na
    # politica (versao antiga dela, ou caminho do GitHub) segue como antes.
    esperado = str(info.get("downloadSha256") or "").strip().lower()
    if esperado:
        achado = _sha256_do_arquivo(destino)
        if achado != esperado:
            try:
                destino.unlink()
            except OSError:
                pass
            _PROGRESSO.update({"estado": "erro",
                               "erro": "o instalador baixado não confere com o publicado"})
            return {"ok": False,
                    "error": ("o instalador baixado não confere com o publicado — "
                              "nada foi executado. Tente de novo mais tarde ou "
                              "baixe pelo site."),
                    "sha256": achado, "esperado": esperado}
    # SILENCIOSO: o usuario pediu "atualizar so dando o Ok, sem estas
    # etapas" (29/08, comparando com o CapCut). Com /VERYSILENT o unico
    # clique que sobra e o do Windows perguntando se autoriza — o resto
    # (idioma, pasta, avancar, concluir) some. O instalador derruba o app
    # e o reabre pelo [Run] (que perdeu o `skipifsilent` por isto).
    import subprocess

    # `/SILENT` (e nao `/VERYSILENT`): sem pergunta nenhuma, mas COM a
    # barra de progresso do instalador. O usuario pediu para "ver a barra
    # e o app sumir so quando terminar" — sem ela, entre o clique e o app
    # voltar havia um buraco de segundos sem nada na tela.
    flags = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             "/CLOSEAPPLICATIONS", "/NOCANCEL"]
    _PROGRESSO.update({"estado": "instalando"})
    try:
        subprocess.Popen([str(destino), *flags], close_fds=True)
    except OSError:
        # Se nem abrir der, ainda vale tentar do jeito antigo (com
        # assistente) antes de mandar o usuario para o navegador.
        try:
            os.startfile(str(destino))  # type: ignore[attr-defined]
        except OSError as e:
            return {"ok": False,
                    "error": f"não consegui abrir o instalador: {e}",
                    "path": str(destino)}
    return {"ok": True, "path": str(destino), "silencioso": True,
            "message": "Atualizando… o ATIVAVID fecha e reabre sozinho."}


def open_setup() -> dict[str, Any]:
    """Abre a pasta do instalador (usuário roda setup.ps1)."""
    setup = REPO / "installer" / "setup.ps1"
    folder = setup.parent
    try:
        if sys.platform == "win32":
            os.startfile(str(folder))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(folder)], check=False)
        return {
            "ok": True,
            "path": str(setup),
            "message": "Pasta do instalador aberta — rode setup.ps1 no PowerShell.",
        }
    except OSError as e:
        return {"ok": False, "error": str(e), "path": str(setup)}
