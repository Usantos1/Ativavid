"""Store de preferências do app (perfil, pasta, licença) — sem secrets de pagamento.

Grava em %USERPROFILE%/ATIVAVID/settings.json (Program Files é só leitura).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
# Legacy (dev / builds antigos)
_LEGACY_SETTINGS = REPO / ".ativavid-settings.json"
# Produção: pasta do usuário (gravável sem admin)
USER_DIR = Path.home() / "ATIVAVID"
SETTINGS_PATH = USER_DIR / "settings.json"

DEFAULTS: dict[str, Any] = {
    "performanceProfile": "auto",
    "renderMode": "auto",  # auto | turbo | quality — motor de render
    # Interno. O cliente só vê "Motor de render: Automático".
    # default = OVERLAY se elegível; off = sempre FULL (desliga rápido).
    "overlayRollout": "default",  # default | off  (canary só em validação)
    "canaryAttempt": 0,  # tentativas OVERLAY no canary (persiste)
    "canaryLimit": 5,  # teto rígido do canary
    "experimentalOverlay": False,  # força OVERLAY (dev). Preferir overlayRollout.
    "experimentalFfmpegZoom": False,  # zoomCuts+pushIn no extract — off em produção
    "projectsRoot": None,  # None → %USERPROFILE%/ATIVAVID/Projetos
    "llmFallback": True,  # Gemini → ChatGPT se explícito no gateway
    "oneClickDefault": True,
    "updateChannel": "stable",
    "updateCheckEnabled": True,
    "githubRepo": "",  # ex.: "sua-org/ativa-vid" — releases para auto-check
    # Licença (Supabase). Vazio = modo aberto (dev).
    "supabaseUrl": "",
    "supabaseAnonKey": "",
    "checkoutUrl": "",  # link Stripe Checkout / Mercado Pago (R$ 399/ano)
    # Só no PC do admin — nunca embutir no instalador do cliente.
    "supabaseServiceRoleKey": "",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_settings() -> dict[str, Any]:
    data = dict(DEFAULTS)
    # Preferência: settings do usuário; senão legado no repo/install
    if SETTINGS_PATH.exists():
        raw = _read_json(SETTINGS_PATH)
    elif _LEGACY_SETTINGS.exists():
        raw = _read_json(_LEGACY_SETTINGS)
    else:
        raw = {}
    data.update({k: raw[k] for k in DEFAULTS if k in raw})
    return data


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    for k, v in patch.items():
        if k not in DEFAULTS:
            continue
        # Campos secretos: string vazia no form = manter o valor já salvo
        if k in ("supabaseAnonKey", "supabaseServiceRoleKey") and not str(v or "").strip():
            continue
        data[k] = v
    USER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        SETTINGS_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        raise OSError(
            f"Não foi possível gravar settings em {SETTINGS_PATH}: {e}"
        ) from e
    return data


def public_settings() -> dict[str, Any]:
    """Settings para a UI — mascara service role (não vaza no GET)."""
    data = load_settings()
    out = dict(data)
    srv = str(out.get("supabaseServiceRoleKey") or "").strip()
    out["supabaseServiceRoleKey"] = ""
    out["hasServiceRole"] = bool(srv)
    return out


def resolve_projects_root(fallback: Path) -> Path:
    s = load_settings()
    custom = s.get("projectsRoot")
    if custom:
        p = Path(str(custom)).expanduser()
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p.resolve()
        except OSError:
            pass
    return fallback.expanduser().resolve()
