# -*- coding: utf-8 -*-
"""5.0.64: o mapa de emoji passa a falar a língua dos vídeos dele.

O recurso existia desde 04/09 com 60 palavras — curadas de cabeça. Medido
contra o vocabulário REAL (86.679 palavras em 1.049 transcrições dos
projetos), ele casava 4,51% delas: numa fala de assistência técnica, onde
"aparelho", "película", "conserto" e "orçamento" são o assunto, quase nada
recebia emoji.

Com 180 palavras — escolhidas descendo a contagem de frequência real, e só
onde o emoji tem referente claro — a cobertura vai a 11,36%. O que chega
na tela continua contido pelo intervalo de 6 s: medido nos últimos 60
vídeos, mediana de 3 emoji por vídeo (máximo 8) em 68 palavras.

Palavra de ligação ("você", "aqui", "isso", "gente") não entra por
princípio: emoji em palavra vazia é o que faz legenda parecer spam.
"""
from __future__ import annotations

import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.caption_emoji import (  # noqa: E402
    COOLDOWN_MS, EMOJI_MAP, add_caption_emojis, _norm,
)

# As mais faladas do corpus real que NÃO podem ganhar emoji.
VAZIAS = ("voce", "aqui", "isso", "gente", "mais", "esse", "mesmo", "tudo",
          "entao", "tambem", "muito", "essa", "assim", "porque", "como",
          "quando", "depois", "sempre", "cada", "quem", "onde")


def test_o_mapa_cresceu_com_o_vocabulario_real():
    assert len(EMOJI_MAP) >= 180
    # o assunto dos vídeos dele — assistência e venda de celular
    for p in ("aparelho", "pelicula", "conserto", "orcamento", "carregar",
              "problema", "troca", "cliente", "agendamento", "whatsapp"):
        assert EMOJI_MAP.get(p), p


def test_palavra_de_ligacao_fica_de_fora():
    for p in VAZIAS:
        assert not EMOJI_MAP.get(p), f"`{p}` nao pode receber emoji"


def test_a_chave_e_sempre_a_forma_normalizada():
    """A busca é por `_norm(texto)`: chave com acento ou maiúscula nunca
    casaria — e o defeito seria mudo, só um emoji que não aparece."""
    for chave in EMOJI_MAP:
        assert chave == _norm(chave), f"`{chave}` nao esta normalizada"
        assert chave == chave.lower()
        assert not any(unicodedata.combining(c) for c in
                       unicodedata.normalize("NFD", chave)), chave


def test_o_valor_e_um_emoji_de_verdade():
    for chave, v in EMOJI_MAP.items():
        if v is None:          # "para" é ambíguo de propósito
            continue
        assert isinstance(v, str) and v, chave
        assert any(ord(c) >= 0x2190 for c in v), f"`{chave}`: {v!r} nao e emoji"
        assert len(v) <= 4, f"`{chave}`: {v!r} longo demais para caber na palavra"


def test_o_intervalo_segura_o_exagero():
    """Sem o intervalo, uma frase cheia de palavras do mapa viraria uma
    linha de emoji — que é exatamente o que faz a legenda parecer spam."""
    assert COOLDOWN_MS >= 4000
    palavras = [{"text": "conserto", "startMs": i * 500} for i in range(40)]
    n = add_caption_emojis(palavras)
    # 40 palavras em 20 s, com intervalo de 6 s: 4 no máximo
    assert 1 <= n <= 4, n
    postos = [w for w in palavras if any(ord(c) >= 0x2190 for c in w["text"])]
    assert len(postos) == n


def test_palavra_que_ja_tem_emoji_nao_ganha_outro():
    palavras = [{"text": "conserto 🔧", "startMs": 0},
                {"text": "problema", "startMs": 30000}]
    n = add_caption_emojis(palavras)
    assert n == 1
    assert palavras[0]["text"].count("🔧") == 1
    assert palavras[1]["text"] != "problema"


def test_casa_com_acento_e_pontuacao_como_a_fala_chega():
    """A transcrição entrega "orçamento," e "Película" — se o casamento
    fosse literal, o mapa nunca acertaria a fala de verdade."""
    for bruto in ("Orçamento,", "PELÍCULA", "conserto.", "Água!"):
        assert EMOJI_MAP.get(_norm(bruto)), bruto
