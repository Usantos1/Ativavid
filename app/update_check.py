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
                result["updateAvailable"] = bool(upd.get("updateAvailable") or upd.get("force"))
                result["downloadUrl"] = upd.get("downloadUrl") or None
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
