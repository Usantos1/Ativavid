# -*- coding: utf-8 -*-
"""A guarda que impede o Whisper de entregar texto que ninguém falou.

O caso: num vídeo só com música o motor devolveu `"Legendas pela comunidade
Amara.org"`. Alucinação conhecida do Whisper em áudio sem fala.

**Por que a solução não é a óbvia.** Medido antes de escolher:

- *Só região acústica não basta*: o `silencedetect` mede NÍVEL, e a música de
  teste (máx −17,6 dB) virou uma "região de fala" de 12s inteiros — o texto
  inventado caiu dentro dela.
- *Nenhum sinal do Whisper serve sozinho*: em 177 segmentos de fala real do
  usuário, o pior chega a `no_speech_prob` 0,939 e `avg_logprob` −0,691,
  ambos **piores** que o material inventado (0,857 / −0,613). Foram testadas
  8 combinações de limiar: todas derrubam o mesmo segmento legítimo
  (`"Eu vou rapidinho, se eu conser…"`).
- *Filtrar palavra por região é pior ainda*: 3,4% das palavras REAIS já caem
  fora das regiões acústicas (a pior desvia 1,63s).

**O que separa** não está em nenhum segmento isolado, está no conjunto: na
música o único segmento é ruim; no vídeo real, 41 dos 42 são bons. Por isso a
regra é global.

**Validado no material de verdade**: 1.055 palavras de fala real em 8 vídeos,
**0 descartadas**; e 5 de 5 palavras inventadas descartadas. Nos casos
construídos — ruído puro 0 palavras, pausa de 6s mantém os dois lados, fala
logo após silêncio começa em 3,14s sem corte, fala a −26 dB mantém as 49.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.transcricao import Palavra, ResultadoDeTranscricao, Segmento  # noqa: E402
from app.transcricao import guarda  # noqa: E402


def _seg(texto: str, ini: float, fim: float, logprob: float,
         n: int = 3) -> Segmento:
    passo = (fim - ini) / max(n, 1)
    return Segmento(texto, ini, fim, logprob, tuple(
        Palavra(f"p{i}", ini + i * passo, ini + (i + 1) * passo, 0.9)
        for i in range(n)))


def _res(*segs: Segmento) -> ResultadoDeTranscricao:
    return ResultadoDeTranscricao(" ".join(s.texto for s in segs), list(segs),
                                  "pt", 30.0)


# --- o caso que motivou tudo ----------------------------------------------

def test_musica_sem_voz_nao_entrega_palavra_nenhuma():
    """Os números são os medidos no arquivo real de música."""
    r = _res(_seg("Legendas pela comunidade Amara.org", 0.0, 12.0, -0.613, 5))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.857},
                              regioes=[(0.0, 12.0)])   # a música VIRA região
    assert limpo.palavras() == []
    assert v.entrou == 5 and v.saiu == 0
    assert v.descartou_tudo


def test_silencio_nao_produz_nada():
    limpo, v = guarda.aplicar(_res(), no_speech={}, regioes=[])
    assert limpo.palavras() == [] and v.entrou == 0


# --- e o que ela NÃO pode fazer -------------------------------------------

def test_um_segmento_ruim_no_meio_de_fala_boa_nao_derruba_o_video():
    """O par real medido (`ns=0,94`, `lp=-0,69`) existe em gravação legítima.
    Se cada segmento fosse julgado sozinho, esse vídeo perderia texto."""
    r = _res(_seg("olá pessoal", 0.0, 3.0, -0.30),
             _seg("eu vou rapidinho", 3.0, 6.0, -0.69),   # o suspeito real
             _seg("até logo", 6.0, 9.0, -0.25))
    limpo, v = guarda.aplicar(
        r, no_speech={0: 0.20, 1: 0.94, 2: 0.15},
        regioes=[(0.0, 9.0)])
    assert v.entrou == v.saiu == 9, "descartou fala real"
    assert len(limpo.segmentos) == 3


def test_fala_muito_baixa_sem_regiao_acustica_e_mantida():
    """A −26 dB o detector pode não achar região. Sem sinal acústico, a guarda
    não pode inventar motivo para descartar."""
    r = _res(_seg("fala baixinha", 0.0, 4.0, -0.35))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.30}, regioes=[])
    assert v.entrou == v.saiu == 3


def test_palavra_atravessando_a_borda_da_regiao_nao_e_cortada():
    """Nenhuma palavra é descartada por conta própria — só segmento inteiro,
    e só quando ele é suspeito E está fora do som."""
    r = ResultadoDeTranscricao("beira", [Segmento("beira", 4.5, 6.5, -0.30, (
        Palavra("antes", 4.5, 5.2, 0.9),     # começa fora da região
        Palavra("dentro", 5.2, 5.8, 0.9),
        Palavra("depois", 5.8, 6.5, 0.9),    # termina fora
    ))], "pt", 10.0)
    limpo, v = guarda.aplicar(r, no_speech={0: 0.2}, regioes=[(5.0, 6.0)])
    assert [p.texto for p in limpo.palavras()] == ["antes", "dentro", "depois"]
    assert v.entrou == v.saiu == 3


def test_pausa_longa_nao_separa_o_video_em_dois():
    r = _res(_seg("primeira parte", 0.0, 6.0, -0.28),
             _seg("segunda parte", 12.0, 18.0, -0.31))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.2, 1: 0.25},
                              regioes=[(0.0, 6.0), (12.0, 18.0)])
    assert v.entrou == v.saiu == 6
    assert len(limpo.segmentos) == 2


# --- a regra 2: alucinação grudada no fim de gravação boa ------------------

def test_alucinacao_no_silencio_final_sai_sozinha():
    """O caso comum: a fala acaba e o Whisper acrescenta uma frase no
    silêncio. O segmento é suspeito E não tem som nenhum embaixo."""
    r = _res(_seg("conteúdo de verdade", 0.0, 8.0, -0.30),
             _seg("Legendas pela comunidade Amara.org", 9.0, 12.0, -0.62))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.2, 1: 0.86},
                              regioes=[(0.0, 8.0)])   # silêncio depois de 8s
    assert v.saiu == 3, "a alucinação final ficou"
    assert [s.texto for s in limpo.segmentos] == ["conteúdo de verdade"]
    assert v.segmentos_descartados == 1


def test_segmento_suspeito_mas_com_som_embaixo_fica():
    """Na dúvida, mantém: descartar fala real é pior que deixar passar."""
    r = _res(_seg("boa", 0.0, 4.0, -0.28),
             _seg("suspeita mas soante", 4.0, 8.0, -0.62))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.2, 1: 0.86},
                              regioes=[(0.0, 8.0)])
    assert v.entrou == v.saiu == 6


def test_no_speech_alto_sozinho_nao_condena_o_segmento():
    """O caso que exige os DOIS sinais.

    Existe fala real com `no_speech_prob` 0,939 — pior que o material
    inventado (0,857). Se a guarda olhasse só esse sinal, um trecho legítimo
    que por azar caísse num vão da detecção acústica seria apagado. A
    confiança (`avg_logprob` −0,30 aqui, contra −0,613 do inventado) é o que
    diz que ali tem fala de verdade.

    Sem este teste, trocar a regra por `no_speech` sozinho passa despercebido:
    conferido injetando exatamente essa mudança.
    """
    r = _res(_seg("boa", 0.0, 4.0, -0.28),
             _seg("fala real que o detector não marcou", 9.0, 12.0, -0.30))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.20, 1: 0.94},
                              regioes=[(0.0, 8.0)])   # o 2º cai no "silêncio"
    assert v.entrou == v.saiu == 6, (
        "descartou fala real por olhar só o no_speech_prob")
    assert len(limpo.segmentos) == 2


def test_logprob_baixo_sozinho_tambem_nao_condena():
    """O outro lado do mesmo argumento, com o contraexemplo real medido.

    Em `cta_cta_mais_feliz.mp4` um segmento legítimo tem `avg_logprob` −0,453
    — abaixo do limiar — com `no_speech_prob` de apenas 0,01. Ou seja, o
    modelo tem certeza de que ali tem fala; a confiança baixa vem da
    dificuldade do áudio, não de ausência de voz.

    Conferido injetando a regra só-logprob: sem este teste ela passa.
    """
    r = _res(_seg("boa", 0.0, 4.0, -0.28),
             _seg("segue a gente pra ficar", 9.0, 12.0, -0.453))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.20, 1: 0.01},
                              regioes=[(0.0, 8.0)])
    assert v.entrou == v.saiu == 6, (
        "descartou fala real por olhar só o avg_logprob")
    assert len(limpo.segmentos) == 2


def test_sem_regioes_a_regra_2_nao_dispara():
    """Sem verdade acústica não dá para dizer que o segmento está no vazio."""
    r = _res(_seg("boa", 0.0, 4.0, -0.28),
             _seg("suspeita", 4.0, 8.0, -0.62))
    limpo, v = guarda.aplicar(r, no_speech={0: 0.2, 1: 0.86}, regioes=[])
    assert v.entrou == v.saiu == 6


# --- os limiares -----------------------------------------------------------

def test_os_limiares_ficam_entre_a_fala_real_e_o_inventado():
    """Ancorado nos extremos MEDIDOS. Se alguém apertar o limiar, o teste
    mostra qual lado passa a ser violado."""
    PIOR_FALA_REAL_NS, PIOR_FALA_REAL_LP = 0.939, -0.691
    INVENTADO_NS, INVENTADO_LP = 0.857, -0.613

    # o limiar tem de deixar o inventado do lado suspeito...
    assert INVENTADO_NS > guarda.NAO_PARECE_FALA_NS
    assert INVENTADO_LP < guarda.NAO_PARECE_FALA_LP
    # ...e cada sinal SOZINHO nao pode ser usado: a fala real e pior nos dois
    assert PIOR_FALA_REAL_NS > INVENTADO_NS
    assert PIOR_FALA_REAL_LP < INVENTADO_LP


def test_a_regra_1_exige_que_TODOS_sejam_suspeitos():
    """Um único segmento bom salva o vídeo — é o que separa música de fala."""
    r = _res(_seg("ruim", 0.0, 4.0, -0.62), _seg("boa", 4.0, 8.0, -0.20))
    _limpo, v = guarda.aplicar(r, no_speech={0: 0.86, 1: 0.20},
                               regioes=[(0.0, 8.0)])
    assert v.saiu == 6, "a regra global disparou com um segmento bom presente"


def test_sem_sinal_do_whisper_nada_e_descartado():
    """Backend futuro que não exponha `no_speech_prob` não pode ter o
    transcript esvaziado por falta de dado."""
    r = _res(_seg("a", 0.0, 4.0, -0.62))
    _limpo, v = guarda.aplicar(r, no_speech={}, regioes=[])
    assert v.entrou == v.saiu == 3
