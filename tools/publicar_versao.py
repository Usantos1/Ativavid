"""Sincroniza a política de versão do Supabase com a release publicada.

    py tools/publicar_versao.py              # anuncia a versão do VERSION
    py tools/publicar_versao.py --forcar     # TAMBÉM sobe min_version (trava builds antigas)
    py tools/publicar_versao.py --conferir   # só mostra o que faria

Por que existe: a `app_config` ficou parada em 0.1.24 enquanto o app chegava
na 2.50 — ninguém atualiza a mão a cada release. Com a tabela velha, o
`download_url` do force-update apontava para uma build de meses atrás, então
forçar atualização mandaria o cliente instalar a versão errada.

Rode no fim do processo de release, depois de publicar o .exe no GitHub.
Só sobe min_version com --forcar: isso BLOQUEIA quem está em versão anterior
até atualizar.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import settings_store as ss  # noqa: E402
from app.update_check import configured_repo  # noqa: E402


def _get(url: str, headers: dict, timeout: int = 25):
    req = request.Request(url, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def _release(tag: str, repo: str) -> dict | None:
    """Release publicada com o .exe — a fonte da verdade do que existe."""
    code, data = _get(
        f"https://api.github.com/repos/{repo}/releases/tags/{tag}",
        {"User-Agent": "ativavid", "Accept": "application/vnd.github+json"},
    )
    if code != 200 or not isinstance(data, dict):
        return None
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--forcar", action="store_true",
                    help="sobe min_version: BLOQUEIA quem está em versão anterior")
    ap.add_argument("--conferir", action="store_true", help="não grava nada")
    ap.add_argument("--versao", default=None, help="padrão: o conteúdo de VERSION")
    args = ap.parse_args()

    versao = (args.versao or (REPO / "VERSION").read_text(encoding="utf-8")).strip().lstrip("vV")
    repo = configured_repo() or "Usantos1/Ativavid"
    print(f"versão: {versao} · repo: {repo}")

    rel = _release(f"v{versao}", repo)
    if not rel:
        print(f"ERRO: release v{versao} não existe em {repo}. Publique o .exe primeiro.")
        return 1
    assets = rel.get("assets") or []
    exe = next((a for a in assets if str(a.get("name", "")).lower().endswith(".exe")), None)
    if not exe:
        print(f"ERRO: release v{versao} não tem .exe anexado.")
        return 1
    download = exe["browser_download_url"]
    print(f"instalador: {exe['name']}")

    s = ss.load_settings()
    url = str(s.get("supabaseUrl") or "").strip().rstrip("/")
    service = str(s.get("supabaseServiceRoleKey") or "").strip()
    if not url or not service:
        print("ERRO: precisa de supabaseUrl + service role para gravar a política.")
        return 1

    h = {
        "apikey": service,
        "Authorization": f"Bearer {service}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    code, atual = _get(f"{url}/rest/v1/app_config?select=*", h)
    if code != 200 or not isinstance(atual, list) or not atual:
        print(f"ERRO: não li app_config (HTTP {code}).")
        return 1
    antes = atual[0]
    print(f"antes : min={antes.get('min_version')} latest={antes.get('latest_version')}")

    patch = {
        "latest_version": versao,
        "download_url": download,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if args.forcar:
        patch["min_version"] = versao
        patch["update_message"] = (
            f"Esta versão não é mais suportada. Atualize para a {versao} para continuar."
        )

    if args.conferir:
        print("depois : " + json.dumps(patch, ensure_ascii=False))
        print("(--conferir: nada foi gravado)")
        return 0

    if args.forcar:
        print(f"\nATENÇÃO: min_version={versao} BLOQUEIA todo cliente em versão anterior")
        print("até que ele atualize. Confirme que o instalador está no ar.")

    req = request.Request(
        f"{url}/rest/v1/app_config?id=eq.1",
        data=json.dumps(patch).encode("utf-8"),
        headers=h,
        method="PATCH",
    )
    try:
        with request.urlopen(req, timeout=25) as r:
            depois = json.loads(r.read().decode("utf-8"))[0]
    except error.HTTPError as e:
        print("ERRO ao gravar:", e.code, e.read().decode("utf-8", errors="replace")[:300])
        return 1

    print(f"depois: min={depois.get('min_version')} latest={depois.get('latest_version')}")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
