"""Store de preferências do app (perfil, pasta, licença) — sem secrets de pagamento.

Grava em %USERPROFILE%/ATIVAVID/settings.json (Program Files é só leitura).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app import secret_store

REPO = Path(__file__).resolve().parent.parent
# Legacy (dev / builds antigos)
_LEGACY_SETTINGS = REPO / ".ativavid-settings.json"
# Produção: pasta do usuário (gravável sem admin)
USER_DIR = Path.home() / "ATIVAVID"
SETTINGS_PATH = USER_DIR / "settings.json"
# Config de licença embutida na build do cliente (somente leitura, ao lado do app).
# O instalador grava este arquivo; ele vence o settings.json do usuário para que
# apagar a URL do Supabase não vire "modo aberto".
BUNDLED_LICENSE_PATH = REPO / "license_config.json"
# Campos que a build embutida trava contra edição do cliente.
# `checkoutUrlMensal` entra aqui junto com o anual: sao os dois planos do
# mesmo produto, vem empacotados na build e o cliente nao edita nenhum.
_MANAGED_KEYS = ("supabaseUrl", "supabaseAnonKey", "checkoutUrl",
                 "checkoutUrlMensal")

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
    # Motor de música: auto = nuvem (ElevenLabs) primeiro; local = IA local
    # (MusicGen na GPU) primeiro, nuvem de reserva — não gasta créditos;
    # nuvem = só ElevenLabs. Em qualquer caso a biblioteca de trilhas
    # fecha a fila.
    "musicEngine": "auto",  # auto | local | nuvem
    "llmFallback": True,  # Gemini → ChatGPT se explícito no gateway
    "oneClickDefault": True,
    # Trocar os efeitos do app pelos da Biblioteca do usuario. DESLIGADO:
    # a troca nasceu na 4.10 por iniciativa nossa, nunca foi pedida, e
    # rendeu duas queixas em dois dias ("apito de galinha", "efeitos
    # sonoros nada a ver"). A Biblioteca serve para ele ESCOLHER.
    "sfxDoUsuario": False,
    "updateChannel": "stable",
    "updateCheckEnabled": True,
    "githubRepo": "",  # ex.: "sua-org/ativa-vid" — releases para auto-check
    # Licença (Supabase). Vazio = modo aberto (dev).
    "supabaseUrl": "",
    "supabaseAnonKey": "",
    "checkoutUrl": "",  # link Stripe Checkout / Mercado Pago (R$ 399/ano)
    "checkoutUrlMensal": "",  # o mesmo produto no plano mensal (R$ 59/mes)
    # Só no PC do admin — nunca embutir no instalador do cliente.
    "supabaseServiceRoleKey": "",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def bundled_raw() -> dict[str, Any]:
    """Arquivo embutido inteiro — inclui campos que não são settings da UI
    (ex.: cacheSecret, usado para assinar o cache de licença)."""
    if not BUNDLED_LICENSE_PATH.exists():
        return {}
    return _read_json(BUNDLED_LICENSE_PATH)


def bundled_license_config() -> dict[str, Any]:
    """Só os campos que viram settings do app (vazio em dev/checkout do repo)."""
    raw = bundled_raw()
    return {k: raw[k] for k in _MANAGED_KEYS if str(raw.get(k) or "").strip()}


def license_managed() -> bool:
    """True quando a build traz a config de licença — cliente não pode alterá-la."""
    return bool(bundled_license_config())


def is_dev_install() -> bool:
    """Checkout de desenvolvimento (tem .git) — o instalador não empacota .git."""
    return (REPO / ".git").exists()


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
    # Service role é cifrada em repouso (DPAPI). Valor sem prefixo é legado em
    # texto plano e continua valendo até a próxima gravação.
    srv = str(data.get("supabaseServiceRoleKey") or "")
    if srv:
        data["supabaseServiceRoleKey"] = secret_store.unprotect(srv)
    # A config embutida vence a do usuário: apagar supabaseUrl no settings.json
    # não pode destravar o app.
    data.update(bundled_license_config())
    return data


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    data = load_settings()
    managed = bundled_license_config()
    for k, v in patch.items():
        if k not in DEFAULTS:
            continue
        # Build com config embutida: a origem da licença não se edita pelo app.
        if k in managed:
            continue
        # Campos secretos: string vazia no form = manter o valor já salvo.
        # supabaseUrl entra aqui porque esvaziá-la desligava o gate de licença.
        if k in ("supabaseUrl", "supabaseAnonKey", "supabaseServiceRoleKey") and not str(v or "").strip():
            continue
        data[k] = v
    USER_DIR.mkdir(parents=True, exist_ok=True)
    on_disk = dict(data)
    srv = str(on_disk.get("supabaseServiceRoleKey") or "")
    if srv:
        on_disk["supabaseServiceRoleKey"] = secret_store.protect(srv)
    try:
        # Escrita atomica: write_text direto trunca antes de escrever, e um
        # processo morto nesse meio deixa settings.json VAZIO — na abertura
        # seguinte load_settings devolve defaults e o projectsRoot do
        # usuario "some" em silencio (a fila junto).
        tmp = SETTINGS_PATH.with_name(SETTINGS_PATH.name + ".tmp")
        tmp.write_text(json.dumps(on_disk, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, SETTINGS_PATH)
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
    out["licenseManaged"] = license_managed()
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
