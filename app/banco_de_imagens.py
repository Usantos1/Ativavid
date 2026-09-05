"""Banco de imagens (Freepik/Magnific e Pexels) para a BIBLIOTECA (5.0.55).

Ate aqui so o editor buscava foto/video de banco, e o arquivo caia dentro do
projeto (`remotion/public/pexels|freepik/`) — servia uma vez e sumia com o
projeto. "O cliente montar a propria biblioteca baixando do banco de
imagens" (05/09): a mesma busca sai na tela da Biblioteca e o arquivo entra
no acervo, com empresa e categoria, para todos os videos seguintes.

O download NUNCA aceita URL do cliente para a Freepik (e por ID, que e o que
a API conta como download) e, para a Pexels, so aceita host
`images.pexels.com` / `videos.pexels.com` — a mesma regra do editor: sem
isso a rota vira proxy aberto gravando arquivo remoto na maquina.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
if str(HELPERS) not in sys.path:
    sys.path.insert(0, str(HELPERS))

FONTES = ("pexels", "freepik")
KINDS = ("image", "video")
PEXELS_OK = ("https://images.pexels.com/", "https://videos.pexels.com/",
             "https://player.vimeo.com/external/")


class BancoIndisponivel(RuntimeError):
    """Helper ausente ou sem chave — a tela mostra o motivo."""


def _pexels():
    try:
        import pexels_search  # type: ignore
    except ImportError as e:  # noqa: BLE001
        raise BancoIndisponivel("helper da Pexels indisponivel") from e
    try:
        return pexels_search, pexels_search.load_api_key()
    except SystemExit as e:
        raise BancoIndisponivel(str(e) or "sem chave da Pexels") from e


def _freepik():
    try:
        import freepik_search  # type: ignore
    except ImportError as e:  # noqa: BLE001
        raise BancoIndisponivel("helper da Freepik indisponivel") from e
    try:
        return freepik_search, freepik_search.load_api_key()
    except SystemExit as e:
        raise BancoIndisponivel(str(e) or "sem chave da Freepik") from e


def fontes_disponiveis() -> list[dict[str, Any]]:
    """Quais bancos dao para usar agora (a tela nao oferece o que nao ha)."""
    fora = []
    for nome, fn in (("pexels", _pexels), ("freepik", _freepik)):
        try:
            fn()
            fora.append({"id": nome, "ok": True, "motivo": ""})
        except BancoIndisponivel as e:
            fora.append({"id": nome, "ok": False, "motivo": str(e)})
    return fora


def buscar(query: str, fonte: str = "pexels", kind: str = "image",
           quantos: int = 24) -> list[dict[str, Any]]:
    """Resultados normalizados: {id, thumb, full, credit, creditUrl, kind}."""
    q = str(query or "").strip()
    if not q:
        raise ValueError("busca vazia")
    fonte = fonte if fonte in FONTES else "pexels"
    kind = kind if kind in KINDS else "image"
    quantos = max(1, min(40, int(quantos or 24)))
    if fonte == "freepik":
        fp, key = _freepik()
        itens = (fp.search_videos(q, key, quantos, "portrait") if kind == "video"
                 else fp.search(q, key, quantos, "portrait"))
        fora = []
        for it in itens or []:
            rid = str(it.get("id") or "").strip()
            if not rid.isdigit():
                continue
            fora.append({
                "id": rid, "fonte": "freepik", "kind": kind,
                "thumb": it.get("thumb") or it.get("preview") or it.get("url") or "",
                "full": "", "credit": it.get("credit") or it.get("author") or "Freepik",
                "creditUrl": it.get("creditUrl") or it.get("page") or "",
            })
        return fora
    px, key = _pexels()
    if kind == "video":
        raise BancoIndisponivel("video so na Freepik por enquanto")
    fotos = px.search(q, key, quantos, "portrait")
    fora = []
    for p in fotos or []:
        src = p.get("src") or {}
        cheia = src.get("large2x") or src.get("large") or src.get("original")
        if not (src.get("medium") and cheia):
            continue
        fora.append({
            "id": str(p.get("id") or ""), "fonte": "pexels", "kind": "image",
            "thumb": src["medium"], "full": cheia,
            "credit": p.get("photographer") or "?", "creditUrl": p.get("url") or "",
        })
    return fora


def salvar_na_biblioteca(*, fonte: str, kind: str = "image", rid: str = "",
                         url: str = "", query: str = "", credit: str = "",
                         empresa: str | None = None,
                         projects_root: Path | None = None) -> dict[str, Any]:
    """Baixa e guarda no acervo. Devolve o item como a Biblioteca o lista."""
    import tempfile

    from app.broll_library import add_file

    fonte = fonte if fonte in FONTES else "pexels"
    kind = kind if kind in KINDS else "image"
    alvo_kind = "clip" if kind == "video" else "image"
    slug_fn = None
    with tempfile.TemporaryDirectory(prefix="ativavid-banco-") as tmp:
        pasta = Path(tmp)
        if fonte == "freepik":
            fp, key = _freepik()
            slug_fn = fp.slugify
            rid = str(rid or "").strip()
            if not rid.isdigit():
                raise ValueError("id invalido")
            ext = ".mp4" if kind == "video" else ".jpg"
            dest = pasta / f"{slug_fn(query or 'banco')}-{rid}{ext}"
            if kind == "video":
                fp.download_video(rid, key, dest)
            else:
                fp.download(rid, key, dest, image_size="large")
        else:
            px, key = _pexels()
            slug_fn = px.slugify
            url = str(url or "").strip()
            if not url.startswith(PEXELS_OK):
                raise ValueError("url nao permitida")
            dest = pasta / f"{slug_fn(query or 'banco')}-{str(rid or 'x')}.jpg"
            px.download(url, dest)
        if not dest.is_file() or dest.stat().st_size < 1024:
            raise RuntimeError("o download veio vazio")
        item = add_file(dest, kind=alvo_kind, projects_root=projects_root,
                        empresa=empresa)
    item["fonte"] = fonte
    item["credit"] = str(credit or "")
    return item
