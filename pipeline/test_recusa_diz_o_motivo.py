# -*- coding: utf-8 -*-
"""Importar num PC bloqueado tem de dizer LICENÇA, não "falha no upload".

Print dele em 31/08, no computador que ele mesmo bloqueou: o bloqueio
funcionou (o rodape ja dizia "Licença bloqueada"), mas a tentativa de
importar virou um card vermelho com "falha no upload" e um botao "Tentar
novamente" — nada sobre licenca, e um caminho que nunca vai dar certo.

A recusa por licenca podia chegar a tela de varias formas: 403 com corpo,
403 sem corpo, resposta vazia, conexao caindo no meio do envio. So a
primeira era tratada; as outras caiam no texto generico.

Nota do que NAO era: eu suspeitei do teto de 8 MB da drenagem do corpo
(o servidor recusa cedo e o navegador ainda esta enviando). Testei com
60 MB nos dois tetos e o 403 chegou inteiro nos dois — a hipotese morreu.
O teto subiu por higiene do socket, sem a promessa.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
DS = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")


def _upload() -> str:
    i = JS.index("async function uploadFiles(")
    return JS[i:JS.index("\nfunction wireDrop", i)]


def test_qualquer_falha_pergunta_o_motivo():
    b = _upload()
    i = b.index("} catch (err) {")
    depois = b[i:]
    assert 'await api("/api/license")' in depois, "o card vermelho sai sem perguntar"
    assert "lic.entitled === false" in depois
    assert "openLicenseDialog(lic)" in depois


def test_a_pergunta_so_acontece_quando_algo_deu_errado():
    """Um GET a cada importacao boa seria peso a toa."""
    b = _upload()
    i = b.index("} catch (err) {")
    assert 'await api("/api/license").catch' in b[i:]
    antes = b[:i]
    # a checagem PREVIA continua existindo (evita subir 150 MB a toa)
    assert antes.count('api("/api/license")') == 1


def test_erro_de_rede_nao_se_chama_upload():
    i = JS.index("xhr.onerror = () => {")
    bloco = JS[i:i + 700]
    assert "a conexão caiu no meio do envio" in bloco
    assert "L.entitled === false" in bloco, "app que ja sabe do bloqueio tem de dizer"


def test_o_corpo_recusado_e_lido_ate_o_fim():
    """Sobra no socket faz a requisicao SEGUINTE ser lida a partir do lixo."""
    i = DS.index("def _drenar_corpo")
    bloco = DS[i:i + 1400]
    assert "self._CORPO_MAX_AO_RECUSAR" in bloco
    assert "8 * 1024 * 1024" not in bloco
