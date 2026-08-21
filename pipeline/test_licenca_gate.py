"""Gate de licença: as regressões que deixavam o app rodar sem assinatura.

Cada teste aqui corresponde a um bypass real que já existiu:
não pagar apagando a URL, editar o cache local, cair numa rota sem gate,
ou mandar POST a partir de um site aberto no navegador.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import http_guard as guard  # noqa: E402
from app import license as lic  # noqa: E402


def _utc(delta_h: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_h)).isoformat()


@pytest.fixture
def blob(tmp_path: Path, monkeypatch):
    """Aponta o license.json para tmp — nunca mexer no do usuário."""
    monkeypatch.setattr(lic, "LICENSE_DIR", tmp_path)
    monkeypatch.setattr(lic, "LICENSE_PATH", tmp_path / "license.json")

    def write(cached: dict, cached_at: str):
        lic._save_blob({"deviceId": "dev-test", "cached": cached, "cachedAt": cached_at})

    return write


# --- gate por exclusão ----------------------------------------------------


@pytest.mark.parametrize("path", [
    "/api/auth/login",
    "/api/auth/signup",
    "/api/license/activate",
    "/api/license/refresh",
    "/api/settings",
    "/api/admin/access",
    "/api/jobs/open-folder",
    "/api/jobs/delete",
    "/api/settings?x=1",
])
def test_rotas_para_sair_do_bloqueio_ficam_livres(path):
    assert lic.gate_free(path) is True


@pytest.mark.parametrize("path", [
    "/api/jobs",
    "/api/jobs/retry",
    "/api/jobs/append-cta",
    "/api/jobs/requeue-folder",
    "/api/ai-edit",       # escapava: edição por IA sem gate
    "/api/corrections",   # escapava: re-render do final pelo editor
    "/api/save",
    "/api/proxy/rebuild",
    "/api/rota-nova-que-ainda-nao-existe",
])
def test_rotas_que_produzem_video_exigem_licenca(path):
    assert lic.gate_free(path) is False


# --- fail-closed ----------------------------------------------------------


def test_dev_sem_config_fica_aberto(monkeypatch):
    monkeypatch.setattr(lic.ss, "is_dev_install", lambda: True)
    st = lic._unconfigured_status()
    assert st["entitled"] is True
    assert st["mode"] == "open"


def test_build_de_cliente_sem_config_bloqueia(monkeypatch):
    """Antes, instalação sem Supabase liberava tudo — e era o padrão de fábrica."""
    monkeypatch.setattr(lic.ss, "is_dev_install", lambda: False)
    st = lic._unconfigured_status()
    assert st["entitled"] is False
    assert st["mode"] == "blocked"


# --- cache local ----------------------------------------------------------


def test_offline_libera_dentro_da_janela(blob):
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-40))
    out = lic._offline_fallback("sem rede")
    assert out["entitled"] is True
    assert out["offline"] is True


def test_offline_nao_renova_a_janela(blob):
    """Cada checagem sem rede regravava cachedAt: 72h viravam para sempre."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-40))
    antes = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))["cachedAt"]
    lic._cache(lic._offline_fallback("sem rede"))
    depois = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))["cachedAt"]
    assert depois == antes


def test_erro_transitorio_nao_apaga_cache_bom(blob):
    """Um 503 do Supabase apagava a licença guardada e bloqueava quem pagou."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(-1))
    lic._cache({"entitled": False, "mode": "error", "error": "http_503"})
    salvo = json.loads(lic.LICENSE_PATH.read_text(encoding="utf-8"))
    assert salvo["cached"]["entitled"] is True


def test_cached_at_no_futuro_nao_libera(blob):
    """Editar cachedAt para 2900 dava idade negativa, que passava no <= 72h."""
    blob({"entitled": True, "mode": "account", "validUntil": _utc(24 * 30)}, _utc(24 * 365 * 900))
    assert lic._offline_fallback("sem rede")["entitled"] is False


def test_valid_until_vencido_nao_libera_offline(blob):
    blob({"entitled": True, "mode": "account", "validUntil": _utc(-24)}, _utc(-1))
    assert lic._offline_fallback("sem rede")["entitled"] is False


@pytest.mark.parametrize("valor,esperado", [
    (None, False),
    ("", False),
    (_utc(24), False),
    (_utc(-24), True),
])
def test_expired(valor, esperado):
    assert lic._expired(valor) is esperado


# --- CSRF do servidor local ----------------------------------------------


class _H(dict):
    """Stand-in para self.headers (case-insensitive o bastante para o guard)."""

    def get(self, k, default=None):  # noqa: D102
        for key, v in self.items():
            if key.lower() == k.lower():
                return v
        return default


def test_sem_origin_passa():
    """O próprio app e ferramentas locais não mandam Origin."""
    assert guard.origin_allowed(_H({"Host": "127.0.0.1:4850"})) is True


def test_origin_do_proprio_app_passa():
    h = _H({"Host": "127.0.0.1:4850", "Origin": "http://127.0.0.1:4850"})
    assert guard.origin_allowed(h) is True


@pytest.mark.parametrize("origin", [
    "https://site-malicioso.com",
    "http://evil.example",
    "https://127.0.0.1.evil.com",
])
def test_site_externo_e_recusado(origin):
    h = _H({"Host": "127.0.0.1:4850", "Origin": origin})
    assert guard.origin_allowed(h) is False


def test_sec_fetch_site_cross_site_e_recusado():
    h = _H({"Host": "127.0.0.1:4850", "Sec-Fetch-Site": "cross-site"})
    assert guard.origin_allowed(h) is False


def test_cors_nunca_devolve_wildcard():
    h = _H({"Host": "127.0.0.1:4850", "Origin": "https://site-malicioso.com"})
    assert guard.cors_origin(h) != "*"
    assert "site-malicioso" not in guard.cors_origin(h)
