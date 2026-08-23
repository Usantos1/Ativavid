# -*- coding: utf-8 -*-
"""A extensão entra pela porta dela — e só por ela.

Este arquivo existe por causa de um prejuízo concreto: por dois dias a guarda
de origem recusou a extensão do navegador em silêncio, a sessão do Gemini nunca
chegou ao app, a IA parou de planejar o corte, e a headline dos vídeos passou a
ser um pedaço cru da transcrição. Em 20 e 21/08, 50 de 51 vídeos saíram assim.

A correção abre `chrome-extension://` numa lista fechada de rotas. O risco de
abrir demais é o motivo original da guarda existir, então o que estes testes
travam não é só "a extensão passa": é que ela continua barrada em todo o resto,
e que nenhum site consegue se passar por ela.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import http_guard as guard  # noqa: E402

EXT = "chrome-extension://kmpnbfclkhmklekkonoiiibgcbmghgpo"


class _H(dict):
    def get(self, k, default=None):
        for chave, valor in self.items():
            if chave.lower() == str(k).lower():
                return valor
        return default


def _pede(caminho, origin=EXT, site="cross-site"):
    return guard.origin_allowed(
        _H({"Host": "127.0.0.1:4850", "Origin": origin, "Sec-Fetch-Site": site}),
        path=caminho)


@pytest.mark.parametrize("rota", sorted(guard.ROTAS_DA_EXTENSAO))
def test_extensao_alcanca_as_rotas_dela(rota):
    assert _pede(rota) is True


def test_barra_no_fim_e_query_nao_driblam_nem_quebram():
    # A rota é comparada por caminho; `?t=1` e a barra final são a mesma rota.
    assert _pede("/api/llm-proxy/capture/") is True
    assert _pede("/api/llm-proxy/capture?t=1") is True


@pytest.mark.parametrize("rota", [
    "/api/settings",            # trocaria o Supabase e capturaria a senha
    "/api/admin/access",        # liberaria dias com o JWT de admin
    "/api/jobs",
    "/api/llm-proxy",           # prefixo não basta
    "/api/llm-proxy/capture/../../settings",
])
def test_extensao_nao_alcanca_o_resto_do_app(rota):
    assert _pede(rota) is False


@pytest.mark.parametrize("origin", [
    "https://site-malicioso.com",
    "http://chrome-extension.evil.com",
    "https://evil.com/chrome-extension://x",
])
def test_site_nao_se_passa_por_extensao(origin):
    """Nenhum site consegue forjar `chrome-extension://` — mas se a checagem
    fosse por 'contém' em vez de 'começa com', estas três passariam."""
    assert _pede("/api/llm-proxy/capture", origin=origin) is False


def test_sem_caminho_a_regra_antiga_continua_valendo():
    """Quem chama sem `path` (o cors_origin, por exemplo) não ganha a exceção."""
    h = _H({"Host": "127.0.0.1:4850", "Origin": EXT})
    assert guard.origin_allowed(h) is False


def test_cors_nao_devolve_a_origem_da_extensao():
    h = _H({"Host": "127.0.0.1:4850", "Origin": EXT})
    assert guard.cors_origin(h) == "http://127.0.0.1:4850"
