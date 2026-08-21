# -*- coding: utf-8 -*-
"""O aviso de atualização estava cego: toda release publicada era invisível.

O usuário, na v2.46, viu "Você está em 2.46 — sem atualização" com a v2.47 já
publicada. A causa: o ramo da política do Supabase tinha precedência e
**retornava ali**, sem nunca consultar o GitHub. Ele estava parado numa versão
antiga — `latestVersion: "0.1.24"` contra 2.47 instalada — então respondia
"sem atualização" para sempre.

Duas regras agora:

- a política do Supabase só manda quando tem novidade DE VERDADE (versão maior)
  ou quando é update obrigatório (`force`); fora disso, cai para o GitHub;
- "novidade" é comparação NUMÉRICA. O GitHub usava `tag != cur`, então uma tag
  mais velha também virava "atualização" — o app ofereceria um downgrade.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.mark.parametrize("nova,atual,esperado", [
    ("2.47", "2.46", True),
    ("2.46", "2.46", False),
    ("0.1.24", "2.47", False),      # a politica velha que causou o defeito
    ("2.5", "2.46", False),         # numerico: 5 < 46, nao texto
    ("2.46", "2.5", True),
    ("v2.47", "2.46", True),        # o "v" da tag nao atrapalha
    ("2.47.1", "2.47", True),
    ("", "2.46", False),
    ("abc", "2.46", False),         # lixo nunca vira atualizacao
])
def test_novidade_e_comparacao_numerica(nova, atual, esperado):
    from app.update_check import _e_mais_nova

    assert _e_mais_nova(nova, atual) is esperado


def _upd(monkeypatch, política: dict | None, tag_github: str | None):
    """Fixa as duas fontes: a política do Supabase e o release do GitHub."""
    import app.update_check as uc

    class _Lic:
        @staticmethod
        def configured():
            return política is not None

        @staticmethod
        def public_status():
            return {"update": política}

    # `from app import license` resolve pelo ATRIBUTO do pacote assim que o
    # submódulo é importado por qualquer outro teste — trocar só o sys.modules
    # deixava passar o módulo real e o stub era ignorado.
    import app as _app

    monkeypatch.setitem(sys.modules, "app.license", _Lic)
    monkeypatch.setattr(_app, "license", _Lic, raising=False)
    monkeypatch.setattr(uc, "configured_repo", lambda: "dono/repo")

    chamou = {"github": False}
    if tag_github is not None:
        import json as _json

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            @staticmethod
            def read():
                return _json.dumps({
                    "tag_name": f"v{tag_github}",
                    "html_url": "https://exemplo/rel",
                    "assets": [{"name": "Instalar.exe",
                                "browser_download_url": "https://exemplo/i.exe"}],
                }).encode()

        def _abrir(*a, **k):
            chamou["github"] = True
            return _Resp()

        monkeypatch.setattr(uc.urllib.request, "urlopen", _abrir)
    return uc, chamou


def test_politica_velha_nao_esconde_a_release_nova(monkeypatch):
    """O defeito exato: Supabase parado em 0.1.24 escondia a v2.47."""
    import app.update_check as uc

    uc, chamou = _upd(monkeypatch,
                      {"latestVersion": "0.1.24", "updateAvailable": False},
                      tag_github="2.47")
    monkeypatch.setattr(uc, "current_version", lambda: "2.46")
    r = uc.check_update()
    assert chamou["github"], "voltou a nao consultar o GitHub"
    assert r["source"] == "github"
    assert r["latestVersion"] == "2.47"
    assert r["updateAvailable"] is True


def test_update_obrigatorio_do_supabase_continua_mandando(monkeypatch):
    """`force` e o caso em que a politica TEM de vencer, mesmo sem versao
    maior — e o botao de emergencia."""
    import app.update_check as uc

    uc, _ = _upd(monkeypatch,
                 {"latestVersion": "0.1.24", "force": True},
                 tag_github="2.47")
    monkeypatch.setattr(uc, "current_version", lambda: "2.46")
    r = uc.check_update()
    assert r["source"] == "supabase"
    assert r["force"] is True


def test_politica_com_versao_maior_manda(monkeypatch):
    import app.update_check as uc

    uc, _ = _upd(monkeypatch,
                 {"latestVersion": "2.99", "updateAvailable": True},
                 tag_github="2.47")
    monkeypatch.setattr(uc, "current_version", lambda: "2.46")
    r = uc.check_update()
    assert r["source"] == "supabase"
    assert r["latestVersion"] == "2.99"


def test_github_nao_oferece_downgrade(monkeypatch):
    """`tag != cur` faria uma tag mais velha virar "atualizacao"."""
    import app.update_check as uc

    uc, _ = _upd(monkeypatch, None, tag_github="2.40")
    monkeypatch.setattr(uc, "current_version", lambda: "2.46")
    r = uc.check_update()
    assert r["updateAvailable"] is False, "ofereceu voltar para uma versao velha"


def test_o_botao_de_baixar_usa_o_verificador_e_nao_o_link_da_licenca():
    """O aviso dizia "Nova versão 2.50" e o botão baixava a **0.1.24**.

    Cada metade lia uma fonte diferente: o texto vinha do verificador e o botão
    usava `update.downloadUrl`, que chega junto da licença e apontava para uma
    política parada em v0.1.24 — o mesmo dado que já tinha cegado o aviso.

    O verificador resolve os dois casos: em update OBRIGATÓRIO ele devolve a URL
    da própria política, então usar só ele não perde nada.
    """
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("async function openUpdateDownload(")
    corpo = js[i:js.index("\nfunction ", i)]
    # As ATRIBUICOES, nao as mencoes: o comentario acima do codigo cita
    # `upd.downloadUrl` e faria o teste passar/falhar pelo texto errado.
    pos_check = corpo.index('url = (check.downloadUrl')
    pos_lic = corpo.index("url = (upd.downloadUrl")
    assert pos_check < pos_lic, (
        "o link da licença voltou a ter precedência sobre o verificador"
    )
    assert "if (!url) url = (upd.downloadUrl" in corpo, (
        "sem reserva: offline o botão ficaria sem nenhuma URL"
    )


def test_nenhum_caminho_de_download_ignora_o_verificador():
    """Os três botões que abrem download têm de sair da mesma fonte."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    for i, _ in enumerate(js.split('"/api/update/open"')[1:], start=1):
        pass
    aberturas = js.count('"/api/update/open"')
    assert aberturas >= 2, "a busca quebrou — nenhum caminho de download achado"
    # todo trecho que abre download precisa ter consultado o check antes
    for pedaco in js.split('"/api/update/open"')[:-1]:
        janela = pedaco[-1200:]
        assert "/api/update/check" in janela, (
            "um caminho de download não consulta o verificador"
        )
