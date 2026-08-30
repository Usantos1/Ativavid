# -*- coding: utf-8 -*-
"""O card diz por que o vídeo não saiu.

`friendly_error` devolvia a MESMA frase para tudo — "Não foi possível
concluir este vídeo." — em qualquer falha que não fosse cancelamento. A
causa ficava no `detail`, atrás de "Ver detalhe".

O que de fato falhou nos projetos do usuário (varrendo os `result.json`):

    56x  'viral'                        KeyError do planejador (corrigido)
     4x  Expecting ',' delimiter …      a IA devolveu JSON quebrado
     1x  Invalid control character …    idem
     1x  Sessão Gemini incompleta…      já tinha mensagem boa — e era
                                        substituída pela frase genérica
    m = friendly_error("cmd failed (1): python helpers/render.py edl.json")

O caso da sessão mostra o pior do desenho antigo: quando o pipeline se deu
ao trabalho de escrever uma mensagem para o usuário, a tela jogava fora.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import MOTIVOS_DO_RENDER, friendly_error  # noqa: E402


def test_json_quebrado_da_IA():
    for e in ("Expecting ',' delimiter: line 29 column 4 (char 1251)",
              "Expecting property name enclosed in double quotes: line 15",
              "Invalid control character at: line 13 column 14"):
        assert "formato que não deu para ler" in friendly_error(e), e


def test_o_keyerror_do_planejador():
    assert "planejamento" in friendly_error("KeyError: 'viral'")


def test_falta_de_disco():
    assert "espaço em disco" in friendly_error(
        "OSError: [Errno 28] No space left on device")


def test_falha_do_corte_aponta_o_log():
    m = friendly_error("cmd failed (1): python helpers/render.py edl.json")
    assert "log deste vídeo" in m


def test_a_mensagem_do_pipeline_passa_inteira():
    """Quando o pipeline escreveu para o usuário, ele sabe mais que esta
    função — e a frase genérica jogava fora."""
    m = "Sessão Gemini incompleta. Abra gemini.google.com já logado."
    assert friendly_error(m) == m


def test_traceback_com_a_palavra_sessao_nao_passa():
    """Passar um traceback inteiro para o card seria pior que a genérica."""
    m = friendly_error("Traceback (most recent call last): ... sessao ...")
    assert m.startswith("Não foi possível")


def test_cancelamento_continua_reconhecido():
    assert friendly_error("Cancelled by user") == "Cancelado pelo usuário"


def test_o_desconhecido_aponta_onde_olhar():
    m = friendly_error("coisa que nunca aconteceu antes")
    assert "log deste vídeo" in m


def test_vazio_nao_quebra():
    assert friendly_error("") and friendly_error(None)


def test_toda_familia_tem_frase():
    for chaves, frase in MOTIVOS_DO_RENDER:
        assert chaves and frase.strip()
