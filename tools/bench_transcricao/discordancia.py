# -*- coding: utf-8 -*-
"""Onde os motores discordam — os únicos trechos que valem ouvido humano.

Transcrever 8 vídeos à mão para servir de referência é caro e desnecessário.
Onde os quatro motores dizem a mesma coisa, a chance de estarem todos errados
do mesmo jeito é desprezível — e, mesmo se estiverem, o erro é invisível na
comparação, porque afeta os quatro igualmente. O que decide o benchmark são os
pontos de divergência.

Então a referência humana é construída só neles:

    00:32.450   Scribe  "PrimeCamp"
                Whisper "praimcamp"
                Gemini  "Prime Camp"

A pessoa ouve 3 segundos e marca o certo. O resto do transcript é preenchido
pelo consenso dos motores, e cada palavra fica marcada com a sua procedência
(`consenso` ou `humano`) para o relatório poder dizer quanto da referência foi
efetivamente verificado por ouvido.

A ESPINHA é o transcript do Whisper local, por dois motivos: é o motor cujos
tempos o produto usa hoje, e é a fonte temporal do cenário D. Cada outro motor
é alinhado contra ela; um trecho onde algum discorda vira um `Ponto`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.transcricao import Palavra
from tools.bench_transcricao.alinhar import chave
from tools.bench_transcricao.metricas import levenshtein_ops

# Divergências separadas por menos que isto viram um ponto só: pedir para a
# pessoa ouvir duas vezes o mesmo trecho de 1s é desperdício de atenção.
JUNTAR_ATE_S = 0.30

# Teto de palavras por ponto. Sem ele, uma fala rápida com várias divergências
# seguidas vira uma pergunta longa — e aí a pessoa transcreve a frase inteira,
# que é exatamente o trabalho manual que este módulo existe para evitar.
# MEDIDO no caso que motivou o limite: sem teto, uma marca mal transcrita e
# duas contrações a 0,1s de distância viravam um único bloco de 3 palavras com
# candidatos que misturavam dois problemas diferentes.
MAXIMO_DE_PALAVRAS_POR_PONTO = 4

# Folga em volta do trecho no player, para a palavra não começar cortada.
FOLGA_S = 1.20

OMITIDO = "—"


@dataclass
class Ponto:
    """Um trecho onde os motores não concordam."""

    inicio: float
    fim: float
    # indices da espinha cobertos por este ponto. Guardados, e nao
    # redescobertos por tempo la na frente: `pal.inicio <= p.fim` incluiria a
    # palavra seguinte quando ela comeca exatamente onde esta termina.
    indices: list[int] = field(default_factory=list)
    # motor -> o que ele disse ali ("—" quando omitiu a palavra)
    propostas: dict[str, str] = field(default_factory=dict)
    contexto_antes: str = ""
    contexto_depois: str = ""

    @property
    def candidatos(self) -> list[str]:
        """Respostas distintas, da mais votada para a menos votada."""
        contagem: dict[str, int] = {}
        for texto in self.propostas.values():
            contagem[texto] = contagem.get(texto, 0) + 1
        return [t for t, _ in sorted(contagem.items(),
                                     key=lambda kv: (-kv[1], kv[0]))]

    def carimbo(self) -> str:
        m, s = divmod(self.inicio, 60)
        return f"{int(m):02d}:{s:06.3f}"


def _sobreposicao(a: Palavra, b: Palavra) -> float:
    return max(0.0, min(a.fim, b.fim) - max(a.inicio, b.inicio))


def _mapear(espinha: list[Palavra], outro: list[Palavra]) -> dict[int, str]:
    """Para cada índice da espinha, o que `outro` disse naquela posição.

    Palavras do outro motor sem contrapartida na espinha (o "Camp" de
    "Prime Camp", quando a espinha tem só "praimcamp") precisam grudar em
    ALGUM índice, e o alinhamento por edição não diz em qual: inserção e
    substituição custam o mesmo, então o backtrace às vezes põe a inserção
    ANTES da troca e "Prime" acabaria colado na palavra anterior — poluindo
    um ponto de divergência com uma palavra que ninguém contesta.

    Quem desempata é o TEMPO, que os dois lados têm: a palavra órfã vai para
    o índice da espinha com quem ela mais se sobrepõe. Sem sobreposição
    nenhuma (motores com deslocamento grande), vai para o centro mais próximo.
    """
    a = [chave(p.texto) for p in espinha]
    b = [chave(p.texto) for p in outro]
    _, ops = levenshtein_ops(a, b)

    # Por indice da espinha, as partes que cairam ali com o tempo de cada
    # uma. Juntar so no fim, ordenado, e o que garante "Prime Camp" e nao
    # "Camp Prime" quando a orfa chega antes da palavra que o diff casou.
    partes: dict[int, list[tuple[float, str]]] = {}
    orfas: list[int] = []
    for op, i, j in ops:
        if i is not None:
            if j is None:
                partes.setdefault(i, [])
            else:
                partes.setdefault(i, []).append((outro[j].inicio, outro[j].texto))
        elif j is not None:
            orfas.append(j)

    for j in orfas:
        alvo, melhor = 0, -1.0
        for i, pal in enumerate(espinha):
            sobr = _sobreposicao(pal, outro[j])
            if sobr > melhor:
                alvo, melhor = i, sobr
        if melhor <= 0:
            centro = (outro[j].inicio + outro[j].fim) / 2
            alvo = min(range(len(espinha)),
                       key=lambda i: abs((espinha[i].inicio + espinha[i].fim) / 2
                                         - centro))
        partes.setdefault(alvo, []).append((outro[j].inicio, outro[j].texto))

    return {i: (" ".join(t for _, t in sorted(v)) if v else OMITIDO)
            for i, v in partes.items()}


def encontrar(motores: dict[str, list[Palavra]], espinha: str = "whisper_local",
              juntar_ate: float = JUNTAR_ATE_S) -> list[Ponto]:
    """Lista os trechos em que algum motor diverge da espinha."""
    base = motores.get(espinha) or []
    if not base:
        return []
    outros = {nome: _mapear(base, pal)
              for nome, pal in motores.items() if nome != espinha and pal}

    # Índices da espinha onde alguém discorda.
    divergentes: list[int] = []
    for i, pal in enumerate(base):
        dito = {chave(pal.texto)}
        for m in outros.values():
            dito.add(chave(m.get(i, OMITIDO)))
        if len(dito) > 1:
            divergentes.append(i)

    # Agrupa índices próximos no tempo num ponto só.
    grupos: list[list[int]] = []
    for i in divergentes:
        perto = (grupos
                 and base[i].inicio - base[grupos[-1][-1]].fim <= juntar_ate
                 and len(grupos[-1]) < MAXIMO_DE_PALAVRAS_POR_PONTO)
        if perto:
            grupos[-1].append(i)
        else:
            grupos.append([i])

    pontos: list[Ponto] = []
    for g in grupos:
        ini, fim = g[0], g[-1]
        propostas = {espinha: " ".join(base[i].texto for i in g)}
        for nome, m in outros.items():
            trecho = " ".join(m.get(i, OMITIDO) for i in g)
            trecho = " ".join(t for t in trecho.split() if t != OMITIDO)
            propostas[nome] = trecho or OMITIDO
        pontos.append(Ponto(
            inicio=base[ini].inicio, fim=base[fim].fim, indices=list(g),
            propostas=propostas,
            contexto_antes=" ".join(p.texto for p in base[max(0, ini - 6):ini]),
            contexto_depois=" ".join(p.texto for p in base[fim + 1:fim + 7]),
        ))
    return pontos


def referencia_por_consenso(motores: dict[str, list[Palavra]],
                            decisoes: dict[str, str],
                            espinha: str = "whisper_local"
                            ) -> tuple[list[str], dict[str, int]]:
    """Monta a referência: consenso onde todos concordam, humano onde não.

    `decisoes` mapeia o carimbo de tempo do ponto para o texto que a pessoa
    marcou como correto. Ponto sem decisão fica com o texto da espinha e é
    contado em `pendentes` — o relatório precisa saber que aquela palavra
    NÃO foi verificada por ninguém.
    """
    base = motores.get(espinha) or []
    pontos = encontrar(motores, espinha)
    por_indice: dict[int, str] = {}
    contagem = {"consenso": len(base), "humano": 0, "pendentes": 0}

    idx = 0
    for p in pontos:
        cobertos = p.indices
        if not cobertos:
            continue
        escolha = decisoes.get(p.carimbo())
        if escolha is None:
            contagem["pendentes"] += len(cobertos)
        else:
            contagem["humano"] += len(cobertos)
        contagem["consenso"] -= len(cobertos)
        por_indice[cobertos[0]] = escolha if escolha is not None else \
            " ".join(base[i].texto for i in cobertos)
        for i in cobertos[1:]:
            por_indice[i] = ""
        idx += 1

    texto = []
    for i, pal in enumerate(base):
        t = por_indice.get(i, pal.texto)
        if t:
            texto.append(t)
    return texto, contagem
