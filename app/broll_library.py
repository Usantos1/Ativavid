"""Biblioteca local de B-roll (imagens/vídeos curtos do usuário)."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def library_root(projects_root: Path | None = None) -> Path:
    if projects_root:
        root = Path(projects_root).expanduser().resolve().parent / "Biblioteca"
    else:
        root = Path.home() / "ATIVAVID" / "Biblioteca"
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    (root / "clips").mkdir(exist_ok=True)
    return root


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", (name or "asset").lower())[:48].strip("-") or "asset"


def list_assets(projects_root: Path | None = None) -> dict[str, Any]:
    root = library_root(projects_root)
    items: list[dict[str, Any]] = []
    for kind, folder in (("image", root / "images"), ("clip", root / "clips")):
        for p in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}:
                continue
            items.append({
                "id": p.stem,
                "name": p.name,
                "kind": kind,
                "path": str(p),
                "rel": f"{folder.name}/{p.name}",
                "bytes": p.stat().st_size,
                "mtime": int(p.stat().st_mtime),
            })
    return {"root": str(root), "items": items}


def add_file(src: Path, *, kind: str = "image", projects_root: Path | None = None) -> dict[str, Any]:
    root = library_root(projects_root)
    src = Path(src)
    if not src.is_file():
        raise ValueError("arquivo não encontrado")
    folder = root / ("clips" if kind == "clip" else "images")
    dest = folder / f"{_slug(src.stem)}-{int(time.time())}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return {
        "ok": True,
        "id": dest.stem,
        "name": dest.name,
        "kind": "clip" if kind == "clip" else "image",
        "path": str(dest),
        "rel": f"{folder.name}/{dest.name}",
    }


def add_bytes(
    filename: str,
    data: bytes,
    *,
    kind: str | None = None,
    projects_root: Path | None = None,
) -> dict[str, Any]:
    if not data:
        raise ValueError("arquivo vazio")
    ext = Path(filename).suffix.lower() or ".jpg"
    if kind is None:
        kind = "clip" if ext in {".mp4", ".mov", ".webm"} else "image"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}:
        raise ValueError("formato não suportado")
    root = library_root(projects_root)
    folder = root / ("clips" if kind == "clip" else "images")
    dest = folder / f"{_slug(Path(filename).stem)}-{int(time.time())}{ext}"
    dest.write_bytes(data)
    return {
        "ok": True,
        "id": dest.stem,
        "name": dest.name,
        "kind": "clip" if kind == "clip" else "image",
        "path": str(dest),
        "rel": f"{folder.name}/{dest.name}",
    }


def pick_for_query(query: str, projects_root: Path | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """Heurística simples: nome do arquivo contém palavra da query."""
    q = (query or "").lower()
    words = [w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", q) if w]
    items = list_assets(projects_root)["items"]
    if not words:
        return items[:limit]
    scored = []
    for it in items:
        name = it["name"].lower()
        score = sum(1 for w in words if w in name)
        if score:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]] or items[:limit]


def copy_into_public(src: Path, public_dir: Path) -> dict[str, Any]:
    """Copia um asset da biblioteca (ou outro path local) para remotion/public/library/."""
    src = Path(src)
    if not src.is_file():
        raise ValueError("arquivo não encontrado")
    public_dir = Path(public_dir)
    dest_dir = public_dir / "library"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    kind = "clip" if dest.suffix.lower() in {".mp4", ".mov", ".webm"} else "image"
    return {
        "ok": True,
        "ref": f"library/{dest.name}",
        "src": f"library/{dest.name}",
        "kind": kind,
        "path": str(dest),
    }


def resolve_query_to_public(
    query: str,
    public_dir: Path,
    *,
    projects_root: Path | None = None,
    prefer_library: bool = True,
) -> dict[str, Any] | None:
    """Resolve query → arquivo em public/: biblioteca local primeiro, depois Pexels."""
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    q = (query or "").strip()
    if not q:
        return None

    if prefer_library:
        picks = pick_for_query(q, projects_root, limit=1)
        if picks:
            try:
                out = copy_into_public(Path(picks[0]["path"]), public_dir)
                out["query"] = q
                out["source"] = "library"
                out["credit"] = picks[0].get("name") or "biblioteca"
                return out
            except ValueError:
                pass

    # Pexels fallback
    try:
        import sys
        helpers = str(REPO / "helpers")
        if helpers not in sys.path:
            sys.path.insert(0, helpers)
        import pexels_search  # type: ignore

        key = pexels_search.load_api_key()
        photos = pexels_search.search(q, key, 3, "portrait")
        if not photos:
            return None
        photo = photos[0]
        src = photo.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            return None
        out_dir = public_dir / "pexels"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"{pexels_search.slugify(q)}-ai.jpg"
        dest = out_dir / name
        pexels_search.download(url, dest)
        photographer = (photo.get("photographer") or "Pexels").strip()
        return {
            "ok": True,
            "ref": f"pexels/{name}",
            "src": f"pexels/{name}",
            "kind": "image",
            "path": str(dest),
            "query": q,
            "source": "pexels",
            "credit": photographer,
        }
    except Exception:
        return None
