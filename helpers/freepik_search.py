"""Banco de imagens e vídeos da Freepik (hoje "Magnific API").

Pedido de 03/09: "implementar com o Magnific, antigo Freepik, pra banco de
imagens como o Pexels". Mesma forma do `pexels_search.py`: busca primeiro,
baixa só o que foi escolhido, guarda em `remotion/public/freepik/`.

Diferenças que importam:
- a chave vai no cabeçalho `x-magnific-api-key` (a Freepik virou Magnific em
  2026; a API antiga em api.freepik.com com `x-freepik-api-key` continua no
  ar — este módulo tenta a nova e cai para a antiga se ela não responder);
- a busca NÃO devolve o arquivo grande: devolve uma prévia (`image.source.url`)
  e o download é outra chamada, por id (`/v1/resources/{id}/download`), que
  devolve a URL assinada. É essa chamada que a Freepik cobra e que vale como
  "download" no contrato — por isso só acontece quando a pessoa escolhe;
- tem VÍDEO de banco (`/v1/videos`), coisa que o Pexels do app não usa.

Precisa de FREEPIK_API_KEY (Integrações → B-roll, ou `.env`). Chave em
https://www.freepik.com/api (plano com franquia gratuita mensal).
"""
from __future__ import annotations

import _utf8  # noqa: F401  — UTF-8 no stdout antes de qualquer print

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

# (host, cabeçalho) — a ordem é a de tentativa. Depois que um responde, fica.
HOSTS: list[tuple[str, str]] = [
    ("https://api.magnific.com", "x-magnific-api-key"),
    ("https://api.freepik.com", "x-freepik-api-key"),
]
_HOST_OK: tuple[str, str] | None = None
TIMEOUT = 60


def load_api_key() -> str:
    """Mesma ordem do app: `%USERPROFILE%/ATIVAVID/.env` primeiro."""
    for candidate in [Path.home() / "ATIVAVID" / ".env",
                      Path(__file__).resolve().parent.parent / ".env",
                      Path(".env")]:
        if candidate.exists():
            try:
                for line in candidate.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == "FREEPIK_API_KEY":
                        val = v.strip().strip('"').strip("'")
                        if val:
                            return val
            except OSError:
                pass
    v = os.environ.get("FREEPIK_API_KEY", "")
    if not v:
        sys.exit("FREEPIK_API_KEY não encontrada — cole a chave em Integrações "
                 "(ou no .env). Chave em https://www.freepik.com/api")
    return v


def slugify(s: str) -> str:
    return "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")[:40]


def _get(path: str, api_key: str, params: dict[str, Any] | None = None) -> dict:
    """GET com fallback de host. Erro de rede/404 no host novo → tenta o antigo."""
    global _HOST_OK
    ordem = [_HOST_OK] + [h for h in HOSTS if h != _HOST_OK] if _HOST_OK else list(HOSTS)
    ultimo: Exception | None = None
    for host, header in ordem:
        try:
            r = requests.get(f"{host}{path}", params=params or {},
                             headers={header: api_key, "Accept-Language": "pt-BR"},
                             timeout=TIMEOUT)
        except requests.RequestException as e:   # DNS/conexão: próximo host
            ultimo = e
            continue
        if r.status_code == 404 and host != ordem[-1][0]:
            ultimo = RuntimeError(f"{host} respondeu 404")
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Freepik respondeu {r.status_code}: {r.text[:300]}")
        _HOST_OK = (host, header)
        return r.json() if r.content else {}
    raise RuntimeError(f"Freepik indisponível: {ultimo}")


# ------------------------------------------------------------------ fotos
def search(query: str, api_key: str, count: int = 12,
           orientation: str | None = "portrait") -> list[dict]:
    """Fotos (não vetor/PSD). Devolve itens já no formato do picker:
    {id, title, thumb, credit, creditUrl, premium, kind:"image"}."""
    params: dict[str, Any] = {
        "term": query, "limit": max(1, min(int(count), 100)), "page": 1,
        "order": "relevance", "filters[content_type][photo]": 1,
    }
    if orientation:
        params[f"filters[orientation][{orientation}]"] = 1
    data = _get("/v1/resources", api_key, params)
    out: list[dict] = []
    for it in data.get("data") or []:
        img = it.get("image") or {}
        src = (img.get("source") or {}).get("url")
        if not src:
            continue
        lic = [str(x.get("type") or "") for x in (it.get("licenses") or [])]
        out.append({
            "id": it.get("id"),
            "title": it.get("title") or "",
            "thumb": src,
            "credit": ((it.get("author") or {}).get("name") or "Freepik").strip(),
            "creditUrl": it.get("url") or "",
            "premium": "premium" in lic and "freemium" not in lic,
            "kind": "image",
        })
    return out


def download(resource_id: int | str, api_key: str, dest: Path,
             image_size: str = "large") -> Path:
    """Baixa a foto pelo id (é esta chamada que conta como download)."""
    data = _get(f"/v1/resources/{resource_id}/download", api_key,
                {"image_size": image_size})
    info = data.get("data") or {}
    url = info.get("signed_url") or info.get("url")
    if not url:
        raise RuntimeError("Freepik não devolveu a URL do arquivo")
    return _baixar(url, dest)


# ----------------------------------------------------------------- vídeos
def search_videos(query: str, api_key: str, count: int = 12,
                  orientation: str | None = "vertical") -> list[dict]:
    """Vídeos de banco. {id, title, thumb, preview, duration, credit, kind:"video"}."""
    params: dict[str, Any] = {
        "term": query, "limit": max(1, min(int(count), 100)), "page": 1,
        "order": "relevance",
        # O download so existe no ORIGINAL 4K (um .mov de 8 s levou 5,5 min
        # para baixar em 03/09). Um insert dura 2-3 s: clipes curtos bastam
        # e baixam em tempo de gente esperar.
        "filters[duration][to]": 20,
    }
    if orientation:
        # o Pexels fala portrait/landscape; a Freepik, vertical/horizontal
        mapa = {"portrait": "vertical", "landscape": "horizontal"}
        params[f"filters[orientation][{mapa.get(orientation, orientation)}]"] = 1
    data = _get("/v1/videos", api_key, params)
    out: list[dict] = []
    for it in data.get("data") or []:
        thumbs = it.get("thumbnails") or []
        previews = it.get("previews") or []
        thumb = (thumbs[0] if thumbs else {}).get("url") if isinstance(thumbs, list) else None
        prev = (previews[0] if previews else {}).get("url") if isinstance(previews, list) else None
        if not thumb and not prev:
            continue
        out.append({
            "id": it.get("id"),
            "title": it.get("name") or it.get("title") or "",
            "thumb": thumb or prev,
            "preview": prev,
            "duration": it.get("duration") or "",
            "credit": ((it.get("author") or {}).get("name") or "Freepik").strip(),
            "creditUrl": it.get("url") or "",
            "premium": bool(it.get("premium")),
            "kind": "video",
        })
    return out


def download_video(video_id: int | str, api_key: str, dest: Path) -> Path:
    """Baixa o vídeo pelo id e CONVERTE para 1080p mp4.

    A API só entrega o ORIGINAL (conferido em 03/09: um .mov 4K de 328 MB
    para 34 s, e nenhum parâmetro de qualidade). Um insert de 3 s não
    precisa disso e a linha do tempo não aguenta: o original é baixado ao
    lado, vira `dest` em H.264 1080p e é apagado.
    """
    data = _get(f"/v1/videos/{video_id}/download", api_key)
    info = data.get("data") or {}
    url = info.get("signed_url") or info.get("url")
    if not url:
        raise RuntimeError("Freepik não devolveu a URL do vídeo")
    dest = Path(dest)
    ext = Path(str(info.get("filename") or "")).suffix.lower() or ".mov"
    if ext not in (".mov", ".mp4", ".m4v", ".mkv", ".webm", ".avi"):
        ext = ".mov"
    original = dest.with_name(dest.stem + "-original" + ext)
    _baixar(url, original)
    try:
        _converter_1080p(original, dest)
    finally:
        try:
            original.unlink()
        except OSError:
            pass
    return dest


def _ffmpeg() -> str:
    try:
        from app.ffmpeg_tools import ffmpeg_bin  # type: ignore

        return ffmpeg_bin()
    except Exception:  # noqa: BLE001 — helper solto, fora do app
        return shutil.which("ffmpeg") or "ffmpeg"


def _converter_1080p(origem: Path, destino: Path) -> None:
    """H.264 1080p (lado maior 1920, o menor cabe em 1080), AAC, mp4."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".conv.mp4")
    cmd = [
        _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(origem),
        "-vf", "scale='min(1080,iw)':'min(1920,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        str(tmp),
    ]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not tmp.exists():
        raise RuntimeError("ffmpeg não converteu o vídeo: "
                           + (r.stderr or b"").decode("utf-8", "replace")[-300:])
    tmp.replace(destino)


def _baixar(url: str, dest: Path) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, timeout=300, stream=True) as r:
        r.raise_for_status()
        # o servidor pode mandar .zip para vetor/PSD; foto e vídeo vêm crus.
        ctype = (r.headers.get("Content-Type") or "").lower()
        if "zip" in ctype:
            raise RuntimeError("o recurso veio como .zip (vetor/PSD) — escolha uma foto")
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    fh.write(chunk)
        tmp.replace(dest)
    return dest


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Busca e baixa fotos/vídeos da Freepik (Magnific)")
    ap.add_argument("query")
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--video", action="store_true", help="vídeos em vez de fotos")
    ap.add_argument("--orientation", default="portrait")
    args = ap.parse_args()
    key = load_api_key()
    itens = (search_videos if args.video else search)(args.query, key, args.count, args.orientation)
    if not itens:
        sys.exit(f"nada para: {args.query}")
    slug = slugify(args.query)
    for i, it in enumerate(itens[: args.count], start=1):
        ext = ".mp4" if args.video else ".jpg"
        dest = args.out_dir / f"{slug}-{it['id']}{ext}"
        try:
            (download_video if args.video else download)(it["id"], key, dest)
            print(f"  + {dest}  ({it['credit']}, {it['creditUrl']})")
        except Exception as e:  # noqa: BLE001
            print(f"  x {it['id']}: {e}")


if __name__ == "__main__":
    main()
