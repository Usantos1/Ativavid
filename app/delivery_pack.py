"""Pasta para postar: vídeo + capa + legenda. Só copia arquivos, sem render."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

_WIN_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_SKIP_MP4 = {"cut.mp4", "base.mp4", "cut_proxy.mp4", "final_proxy.mp4"}
PACK_PARENT = "publicar"


def safe_pack_stem(text: str) -> str:
    s = _WIN_BAD.sub("", text or "")
    s = re.sub(r"\s+", " ", s).strip(" .")
    if s.lower().endswith(".mp4"):
        s = s[:-4].rstrip(" .")
    if not s or s.upper() in _WIN_RESERVED:
        return "video"
    return s[:80].rstrip(" .")


def project_dir(edit_dir: Path) -> Path:
    edit = Path(edit_dir)
    return edit.parent if edit.name.lower() == "edit" else edit


def _copy_if_needed(src: Path, dest: Path, *, force: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and src.exists() and not force:
        try:
            if src.stat().st_mtime <= dest.stat().st_mtime and src.stat().st_size == dest.stat().st_size:
                return
        except OSError:
            pass
    shutil.copy2(src, dest)


def resolve_final_mp4(edit_dir: Path, final: Path | None = None) -> Path | None:
    if final and Path(final).is_file() and Path(final).name not in _SKIP_MP4:
        return Path(final)
    edit = Path(edit_dir)
    state_p = edit / "state.json"
    if state_p.exists():
        try:
            rel = str(json.loads(state_p.read_text(encoding="utf-8-sig")).get("finalVideo") or "").strip()
        except (OSError, json.JSONDecodeError, TypeError):
            rel = ""
        if rel and rel not in _SKIP_MP4 and ".." not in Path(rel).parts:
            cand = edit / rel
            if cand.is_file():
                return cand
    hard = edit / "final.mp4"
    if hard.is_file():
        return hard
    cands = [
        p for p in edit.glob("*.mp4")
        if p.name not in _SKIP_MP4 and not p.name.endswith(".prenorm.mp4")
    ]
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def pack_dir_for(edit_dir: Path, stem: str) -> Path:
    return project_dir(edit_dir) / PACK_PARENT / stem


def _inside_project(path: Path, edit_dir: Path) -> bool:
    try:
        resolved = path.resolve()
        root = project_dir(edit_dir).resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def read_pack_dir(edit_dir: Path) -> Path | None:
    state_p = Path(edit_dir) / "state.json"
    if not state_p.exists():
        return None
    try:
        rel = str(json.loads(state_p.read_text(encoding="utf-8-sig")).get("deliveryPack") or "").strip()
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not rel:
        return None
    cand = (Path(edit_dir) / rel).resolve()
    if not _inside_project(cand, edit_dir):
        return None
    return cand if cand.is_dir() else None


def ensure_delivery_pack(
    edit_dir: Path,
    final: Path | None = None,
    *,
    force_cover: bool = False,
) -> Path | None:
    """Monta publicar/<nome>/ com o mp4, capa.jpg e legenda.txt."""
    edit = Path(edit_dir)
    video = resolve_final_mp4(edit, final)
    if video is None:
        return None
    stem = safe_pack_stem(video.stem)
    dest = pack_dir_for(edit, stem).resolve()
    # O pacote se chama pela MANCHETE, e a manchete muda quando o usuario
    # corrige o texto. Sem mover o pacote anterior, cada correcao deixava uma
    # pasta inteira para tras com uma copia do video: medido na maquina do
    # usuario, 11 projetos com pasta duplicada e 1,19 GB de sobra — um deles
    # com QUATRO pastas do mesmo video. E, ao abrir `publicar/`, ele nao tinha
    # como saber qual era a boa.
    #
    # Mover, nao apagar: o conteudo e o mesmo pacote, so mudou de nome.
    anterior = read_pack_dir(edit)
    movido = False
    if anterior is not None and anterior != dest and not dest.exists():
        try:
            anterior.rename(dest)
            movido = True
            print(f"[pack] renomeado: {anterior.name!r} -> {dest.name!r}", flush=True)
        except OSError as e:
            print(f"[warn] pack rename: {e}", flush=True)
    dest.mkdir(parents=True, exist_ok=True)
    _copy_if_needed(video, dest / f"{stem}.mp4")
    # Sobrou dentro do pacote a copia com o nome da manchete velha. Removo SO
    # ela — o nome exato do pacote que acabei de renomear.
    #
    # Nao um `glob("*.mp4")`: `publicar/<nome>/` e uma pasta que o usuario
    # ABRE, e ele pode ter posto video dele ali. Apagar por padrao de nome
    # apagaria junto.
    if movido and anterior is not None:
        obsoleto = dest / f"{anterior.name}.mp4"
        if obsoleto.is_file() and obsoleto.name != f"{stem}.mp4":
            try:
                obsoleto.unlink()
                print(f"[pack] removido video antigo: {obsoleto.name!r}", flush=True)
            except OSError:
                pass

    cover = edit / "cover.jpg"
    if not cover.is_file() and edit.parent.joinpath("cover.jpg").is_file():
        cover = edit.parent / "cover.jpg"
    if cover.is_file() and cover.stat().st_size > 400:
        _copy_if_needed(cover, dest / "capa.jpg", force=force_cover)

    legenda = edit / "legenda.txt"
    if not legenda.is_file() and (edit / "post" / "legenda.txt").is_file():
        legenda = edit / "post" / "legenda.txt"
    if legenda.is_file():
        _copy_if_needed(legenda, dest / "legenda.txt")

    state_p = edit / "state.json"
    if state_p.exists():
        try:
            state = json.loads(state_p.read_text(encoding="utf-8-sig"))
            if isinstance(state, dict):
                state["deliveryPack"] = f"../{PACK_PARENT}/{stem}"
                state_p.write_text(
                    json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return dest


def folder_to_open(edit_dir: Path) -> Path:
    """Pasta limpa para o Drive; se ainda não existir, monta agora."""
    pack = read_pack_dir(edit_dir) or ensure_delivery_pack(edit_dir)
    return pack if pack is not None else Path(edit_dir)
