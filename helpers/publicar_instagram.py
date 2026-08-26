# -*- coding: utf-8 -*-
"""Publica um Reel no Instagram pela Graph API oficial da Meta.

Fluxo (v21.0, upload RESUMÁVEL — o vídeo local sobe direto, sem precisar de
URL pública):
  1. POST /{ig-user-id}/media  (media_type=REELS, upload_type=resumable)
     → devolve o id do "container" e a URI de upload (rupload.facebook.com)
  2. POST binário do mp4 na URI (Authorization: OAuth <token>, offset: 0)
  3. GET  /{container}?fields=status_code até FINISHED (a Meta processa)
  4. POST /{ig-user-id}/media_publish (creation_id=container) → media id
  5. GET  /{media}?fields=permalink → o link do post

Requisitos da conta (guia no chat/painel): conta Instagram PROFISSIONAL
vinculada a uma Página do Facebook, app na developers.facebook.com e um
token de acesso com instagram_basic + instagram_content_publish +
pages_show_list. IG_USER_ID é o id numérico da conta profissional.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

GRAPH = "https://graph.facebook.com/v21.0"
_POLL_S = 5
_POLL_MAX = 120          # 10 min de processamento na Meta
_CAPTION_MAX = 2200      # limite do Instagram


def _erro_meta(resp: Any) -> str:
    try:
        e = (resp.json() or {}).get("error") or {}
        msg = str(e.get("error_user_msg") or e.get("message") or "")
        if e.get("code") == 190:
            msg += " (token inválido ou vencido — gere um novo)"
        return msg or f"HTTP {resp.status_code}"
    except Exception:  # noqa: BLE001
        return f"HTTP {getattr(resp, 'status_code', '?')}"


def testar_conta(ig_user_id: str, token: str) -> dict[str, Any]:
    """Valida o par id+token sem publicar nada."""
    import requests

    r = requests.get(
        f"{GRAPH}/{ig_user_id}",
        params={"fields": "username,name", "access_token": token},
        timeout=20,
    )
    if r.status_code >= 400:
        return {"ok": False, "error": _erro_meta(r)}
    j = r.json() or {}
    return {"ok": True, "username": j.get("username") or j.get("name") or ""}


def publicar_reel(
    video: Path,
    caption: str,
    *,
    ig_user_id: str,
    token: str,
    progresso: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """(dict com ok/permalink ou ok=False/error). Nunca levanta."""
    import requests

    def _p(msg: str) -> None:
        if progresso:
            progresso(msg)

    try:
        video = Path(video)
        if not video.is_file() or video.stat().st_size < 100_000:
            return {"ok": False, "error": "vídeo final não encontrado"}

        _p("Criando o post no Instagram…")
        r = requests.post(
            f"{GRAPH}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": (caption or "").strip()[:_CAPTION_MAX],
                "access_token": token,
            },
            timeout=30,
        )
        if r.status_code >= 400:
            return {"ok": False, "error": _erro_meta(r)}
        j = r.json() or {}
        container = str(j.get("id") or "")
        upload_uri = str(j.get("uri") or "")
        if not container or not upload_uri:
            return {"ok": False, "error": f"resposta sem container/uri: {j}"}

        _p("Enviando o vídeo…")
        size = video.stat().st_size
        with open(video, "rb") as f:
            up = requests.post(
                upload_uri,
                headers={
                    "Authorization": f"OAuth {token}",
                    "offset": "0",
                    "file_size": str(size),
                },
                data=f,
                timeout=1800,
            )
        if up.status_code >= 400:
            return {"ok": False, "error": f"upload: {_erro_meta(up)}"}

        _p("Instagram processando o vídeo…")
        for _ in range(_POLL_MAX):
            st = requests.get(
                f"{GRAPH}/{container}",
                params={"fields": "status_code,status", "access_token": token},
                timeout=30,
            ).json() or {}
            code = str(st.get("status_code") or "")
            if code == "FINISHED":
                break
            if code == "ERROR":
                return {"ok": False,
                        "error": f"a Meta recusou o vídeo: {st.get('status')}"}
            time.sleep(_POLL_S)
        else:
            return {"ok": False,
                    "error": "a Meta não terminou de processar em 10 min"}

        _p("Publicando…")
        pub = requests.post(
            f"{GRAPH}/{ig_user_id}/media_publish",
            data={"creation_id": container, "access_token": token},
            timeout=60,
        )
        if pub.status_code >= 400:
            return {"ok": False, "error": f"publicar: {_erro_meta(pub)}"}
        media_id = str((pub.json() or {}).get("id") or "")

        permalink = ""
        try:
            perma = requests.get(
                f"{GRAPH}/{media_id}",
                params={"fields": "permalink", "access_token": token},
                timeout=30,
            ).json() or {}
            permalink = str(perma.get("permalink") or "")
        except Exception:  # noqa: BLE001
            pass
        return {"ok": True, "mediaId": media_id, "permalink": permalink}
    except Exception as e:  # noqa: BLE001 - o chamador grava o estado
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
