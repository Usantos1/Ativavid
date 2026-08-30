"""Cache global de node_modules do Remotion — um install, muitos jobs.

Cada job continua com seu edit/remotion/ (src + public).
As dependências ficam em %USERPROFILE%/ATIVAVID/remotion-cache/<track>-<hash>/.
O job recebe um junction (mklink /J), não um symlink /D.

Invalida quando package.json do template ou o pin do Remotion mudam.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

CACHE_ROOT = Path.home() / "ATIVAVID" / "remotion-cache"
REMOTION_PIN = "4.0.482"


def _log(msg: str) -> None:
    print(msg, flush=True)


def cache_fingerprint(track: str, package_json: Path) -> str:
    raw = package_json.read_bytes() if package_json.exists() else b""
    h = hashlib.sha256()
    h.update(track.encode("utf-8"))
    h.update(raw)
    h.update(REMOTION_PIN.encode("utf-8"))
    return f"{track}-{h.hexdigest()[:12]}"


def cache_dir(track: str, package_json: Path) -> Path:
    return CACHE_ROOT / cache_fingerprint(track, package_json)


def cli_ok(node_modules: Path) -> bool:
    return (node_modules / "@remotion" / "cli").is_dir() or (
        node_modules / "remotion"
    ).is_dir()


def _is_reparse(path: Path) -> bool:
    """Junction ou symlink — não apagar um node_modules real por engano."""
    try:
        if hasattr(path, "is_junction") and path.is_junction():
            return True
    except OSError:
        pass
    try:
        return path.is_symlink()
    except OSError:
        return False


def _junction(link: Path, target: Path) -> bool:
    """Cria junction Windows. Sem /D (precisa admin). Valida o CLI depois."""
    target = target.resolve()
    if not target.is_dir():
        return False
    if link.exists() or link.is_symlink():
        if cli_ok(link) and _same_target(link, target):
            return True
        if _is_reparse(link):
            try:
                link.unlink()
            except OSError:
                try:
                    os.rmdir(link)
                except OSError:
                    return False
        else:
            return False
    link.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if r.returncode != 0 or not cli_ok(link):
        _log(f"[remotion-cache] junction falhou: {(r.stderr or r.stdout or '')[-200:]}")
        return False
    _log(f"[remotion-cache] junction {link} → {target}")
    return True


def _same_target(link: Path, target: Path) -> bool:
    try:
        return Path(os.path.realpath(link)).resolve() == target.resolve()
    except OSError:
        return False


def _pin_package(pkg_path: Path) -> None:
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return
    deps = pkg.setdefault("dependencies", {})
    for k in list(deps):
        if k == "remotion" or k.startswith("@remotion/"):
            deps[k] = REMOTION_PIN
    pkg["overrides"] = {
        "remotion": REMOTION_PIN,
        "@remotion/cli": REMOTION_PIN,
        "@remotion/google-fonts": REMOTION_PIN,
        "@remotion/layout-utils": REMOTION_PIN,
    }
    pkg_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _npm_install(cwd: Path) -> None:
    from app.win_process import child_env, resolve_npm_argv

    npm_argv = resolve_npm_argv()
    env = child_env()
    _log(f"[remotion-cache] npm install em {cwd}")
    t0 = time.perf_counter()
    proc = subprocess.run(
        [*npm_argv, "install", "--no-fund", "--no-audit", "--save-exact"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    dt = time.perf_counter() - t0
    _log(f"TIMING REMOTION_NPM_INSTALL={dt:.2f}s")
    if proc.returncode != 0:
        raise RuntimeError(f"npm install (cache) failed:\n{(proc.stderr or proc.stdout or '')[-3000:]}")


def _seed_from_donor(cache_nm: Path) -> bool:
    """Copia node_modules de um projeto existente se o pin bater."""
    # A pasta de projetos CONFIGURADA vem primeiro. Aqui havia um caminho
    # fixo de uma maquina so (`E:\ATIVAVID\Projetos`): quem instalasse o
    # app com a pasta noutro lugar nao achava doador nenhum e pagava um
    # `npm install` inteiro — e o app e revendido.
    roots: list[Path] = []
    try:
        from app.settings_store import load_settings

        cfg = str((load_settings() or {}).get("projectsRoot") or "").strip()
        if cfg:
            roots.append(Path(cfg))
    except Exception:  # noqa: BLE001 — doador e atalho, nao requisito
        pass
    roots.append(Path.home() / "ATIVAVID" / "Projetos")
    for root in roots:
        if not root.is_dir():
            continue
        try:
            kids = list(root.iterdir())
        except OSError:
            continue
        for proj in kids:
            donor = proj / "edit" / "remotion" / "node_modules"
            if not cli_ok(donor):
                continue
            if _is_reparse(donor):
                continue
            _log(f"[remotion-cache] copiando node_modules de {donor}")
            t0 = time.perf_counter()
            if cache_nm.exists():
                shutil.rmtree(cache_nm, ignore_errors=True)
            try:
                shutil.copytree(donor, cache_nm, dirs_exist_ok=True)
            except OSError as e:
                _log(f"[remotion-cache] copy donor falhou: {e}")
                return False
            _log(f"TIMING REMOTION_CACHE_SEED={time.perf_counter() - t0:.2f}s")
            return cli_ok(cache_nm)
    return False


def ensure_cache(track: str, template_pkg: Path) -> Path:
    """Garante node_modules no cache. Retorna a pasta node_modules."""
    root = cache_dir(track, template_pkg)
    nm = root / "node_modules"
    if cli_ok(nm):
        return nm
    root.mkdir(parents=True, exist_ok=True)
    dest_pkg = root / "package.json"
    if template_pkg.exists():
        shutil.copy2(template_pkg, dest_pkg)
        _pin_package(dest_pkg)
    if not _seed_from_donor(nm):
        _npm_install(root)
    if not cli_ok(nm):
        raise RuntimeError(f"cache Remotion incompleto: {nm}")
    (root / "fingerprint.txt").write_text(
        cache_fingerprint(track, template_pkg), encoding="utf-8"
    )
    return nm


def attach_node_modules(dest: Path, track: str, template_pkg: Path) -> bool:
    """Liga dest/node_modules ao cache. False = caller deve instalar no job."""
    try:
        cached = ensure_cache(track, template_pkg)
    except Exception as e:
        _log(f"[remotion-cache] ensure falhou: {e}")
        return False
    return _junction(dest / "node_modules", cached)
