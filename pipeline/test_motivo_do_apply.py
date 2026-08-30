# -*- coding: utf-8 -*-
"""Aplicar que falha tem de dizer o que houve e o que fazer.

No histórico do usuário: **14 de 99 aplicações falharam** (14%), e em todas
ele leu a mesma frase — "Não foi possível preparar este corte. O vídeo
anterior foi mantido." O motivo técnico ia para um campo que a tela nem
mostra, então a falha era um beco sem saída.

As famílias, lidas uma a uma no histórico:

    OLD map Nf vs cut.mp4 Mf           6x   (a tolerância era de 1 quadro e
    cut temporário tem N frames…       5x    recusava 64%; corrigido 21/08)
    ordem das palavras invertida       2x
    token duplicado sem justificativa  1x

As guardas em si NÃO foram mexidas: elas protegem a legenda, e a condição
das duas últimas não reproduz (no estado atual daquele projeto a validação
passa). O que mudou é o beco sem saída.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.apply_execute import (          # noqa: E402
    PREPARE_FAIL_MSG,
    motivo_do_apply,
)

FONTE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")


def test_cada_familia_de_falha_tem_frase_e_proximo_passo():
    """Todas as quatro famílias que apareceram no histórico dele."""
    casos = {
        "ordem das palavras invertida": "Salvar e refazer a Fase 2",
        "token duplicado sem justificativa": "Salvar e refazer a Fase 2",
        "OLD map 1132f vs cut.mp4 1126f": "Recarregue o projeto",
        "cut temporário tem 203 frames, o mapa previa 205": "Tente de novo",
        "fila cheia": "fila esvaziar",
    }
    for erro, pedaco in casos.items():
        frase = motivo_do_apply(erro)
        assert frase, erro
        assert pedaco in frase, f"{erro}: {frase}"


def test_erro_desconhecido_cai_na_frase_generica():
    """Inventar explicação para o que não se conhece é pior que a genérica."""
    assert motivo_do_apply("um erro que ninguém previu") is None
    assert motivo_do_apply("") is None
    assert motivo_do_apply(None) is None


def test_o_motivo_vence_a_frase_generica_na_origem():
    """O `user_message` era decidido no ponto do `raise`, e uma frase
    explícita ali venceria o mapa lá embaixo — foi o que aconteceu na
    primeira versão deste conserto."""
    i = FONTE.index("user = (PROVENANCE_FAIL_MSG if err == OVERLAP_FAIL")
    bloco = FONTE[i:i + 200]
    assert "motivo_do_apply(err) or PREPARE_FAIL_MSG" in bloco
    # e o caminho da exceção também consulta o mapa
    j = FONTE.index('msg = (getattr(e, "user_message", None)')
    assert "motivo_do_apply(str(e))" in FONTE[j:j + 260]


def test_a_frase_generica_continua_dizendo_que_nada_se_perdeu():
    """É a única coisa que a genérica precisa garantir."""
    assert "vídeo anterior foi mantido" in PREPARE_FAIL_MSG


def test_a_espera_diz_o_que_esta_acontecendo():
    """80,7% do tempo de aplicar é o redesenho (mediana 52,4s), e o que se
    lia nesse minuto era "Aplicando edição..." — uma frase que não muda e
    não diz nada."""
    i = FONTE.index('hooks.progress("visual"')
    bloco = FONTE[i:i + 220]
    assert "Redesenhando o vídeo com as suas correções" in bloco


def test_nao_se_promete_tempo_de_espera():
    """Tentei em 30/08 e o dado reprovou: a faixa acertava 21 de 45 (47%).
    Dizer "cerca de 2 minutos" e levar 40s é pior que não dizer nada.

    Este teste existe para a tentação não voltar sem dado novo.
    """
    assert "espera_do_redesenho" not in FONTE
    assert "NAO PROMETER TEMPO AQUI" in FONTE
    assert "47%" in FONTE      # o número que reprovou
