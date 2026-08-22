# -*- coding: utf-8 -*-
"""Aplica correções de texto do Gemini sem tocar nos tempos do Whisper.

A regra que este módulo existe para garantir: o Whisper é a ÚNICA fonte de
verdade temporal, e o Gemini só corrige conteúdo textual. Como a legenda
karaokê lê `Palavra.inicio`/`fim` direto (ver `app/transcricao/__init__.py`),
qualquer tempo inventado aqui aparece na tela.

Nasceu no harness do benchmark (`tools/bench_transcricao/`) e foi promovido
para cá inteiro, sem uma linha reescrita, quando o cenário E virou produção.
O harness passou a importar deste arquivo: uma implementação só, e o
benchmark continua reproduzível medindo exatamente o código que roda.

Trabalha com `Palavra` do projeto — não há tipo novo.

A ESTRATÉGIA, bloco a bloco. `difflib` compara as duas sequências por uma
chave (minúscula, sem pontuação, acentos preservados — trocar "voce" por
"você" é correção de verdade) e cada tipo de bloco tem política própria:

    igual n:n     tempos intactos; adota a grafia do Gemini, que pode
                  consertar a caixa de um nome próprio. Custo temporal: zero.

    troca 1:1     cada palavra herda `inicio`/`fim` EXATOS da correspondente.

    divisão 1→m   "PrimeCamp" → "Prime Camp". Reparte [i, f] proporcional ao
                  número de caracteres, com `novo[0].inicio == i` e
                  `novo[-1].fim == f` CRAVADOS.

    fusão n→1     "Prime Camp" → "PrimeCamp". `inicio` da primeira, `fim` da
                  última. Exato, nada inventado.

    troca n:m     divisão proporcional sobre o span do bloco, bordas cravadas.

    remoção       o tempo órfão é ABSORVIDO pelo vizinho — deixar buraco faria
                  o realce do karaokê parar no meio da fala.

    inserção      RECUSADA por padrão. Revisor não inventa palavra; se o
                  Gemini quer acrescentar, ele está retranscrevendo.

Como a união dos intervalos de um bloco nunca escapa do span original, as
fronteiras de segmento e de frase ficam intactas. É daí que vem a garantia de
que a revisão não quebra o karaokê.

O peso da divisão é o número de caracteres do token, de propósito: qualquer
modelo mais esperto seria um timestamp inventado com outro nome.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field, replace

from . import Palavra

_PONTUACAO = re.compile(r"[^\wÀ-ɏ']+", re.UNICODE)

# Um microssegundo. Abaixo disso é ruído de ponto flutuante, não deslocamento.
EPS = 1e-6

# Duração mínima de uma palavra dividida. Abaixo disso o realce pisca sem ser
# lido — o `conferir_legendas.py` já reprova cue de duração <= 0.
DURACAO_MINIMA = 0.02

# Acima desta fração de palavras alteradas a revisão inteira é descartada: o
# Gemini retranscreveu em vez de revisar. Só vale com amostra suficiente —
# num segmento de 3 palavras, uma correção legítima já dá 33%.
FRACAO_MAXIMA_ALTERADA = 0.35
AMOSTRA_MINIMA_PARA_FREIO = 20


def chave(token: str) -> str:
    """Chave de comparação: minúscula, sem pontuação, acentos preservados."""
    return _PONTUACAO.sub("", token).casefold()


def tokenizar(texto: str) -> list[str]:
    return [t for t in texto.split() if t.strip()]


@dataclass
class Alteracao:
    """Uma mudança aplicada, para auditoria no relatório."""

    tipo: str          # grafia | troca | divisao | fusao | remocao | insercao_recusada
    antes: list[str]
    depois: list[str]
    inicio: float
    fim: float


@dataclass
class Resultado:
    palavras: list[Palavra]
    alteracoes: list[Alteracao] = field(default_factory=list)
    recusadas: list[Alteracao] = field(default_factory=list)
    revisao_descartada: bool = False
    motivo: str = ""

    @property
    def palavras_alteradas(self) -> int:
        return sum(len(a.antes) for a in self.alteracoes if a.tipo != "grafia")


def _pesos(tokens: list[str]) -> list[float]:
    return [float(max(len(_PONTUACAO.sub("", t)), 1)) for t in tokens]


def repartir(inicio: float, fim: float, tokens: list[str],
             duracao_minima: float = DURACAO_MINIMA) -> list[tuple[float, float]]:
    """Divide [inicio, fim] entre `tokens`, proporcional ao tamanho de cada um.

    `inicio` e `fim` são pontos fixos. É isso que impede o karaokê de quebrar.
    """
    n = len(tokens)
    if n == 0:
        return []
    if n == 1:
        return [(inicio, fim)]

    span = fim - inicio
    if span <= 0:
        # Intervalo degenerado já no Whisper: não há o que repartir.
        return [(inicio, fim) for _ in tokens]

    p = _pesos(tokens)
    total = sum(p)
    pontos = [inicio]
    acumulado = 0.0
    for x in p[:-1]:
        acumulado += x
        pontos.append(inicio + span * acumulado / total)
    pontos.append(fim)

    # Não cabe duração mínima para todos: reparte igual e aceita.
    if span < n * duracao_minima:
        pontos = [inicio + span * i / n for i in range(n + 1)]
        pontos[0], pontos[-1] = inicio, fim
        return list(zip(pontos[:-1], pontos[1:]))

    # Empurra da esquerda, depois da direita, sem soltar as bordas.
    for i in range(1, n):
        if pontos[i] - pontos[i - 1] < duracao_minima:
            pontos[i] = pontos[i - 1] + duracao_minima
    for i in range(n - 1, 0, -1):
        if pontos[i + 1] - pontos[i] < duracao_minima:
            pontos[i] = pontos[i + 1] - duracao_minima
    pontos[0], pontos[-1] = inicio, fim
    for i in range(1, n):
        pontos[i] = min(max(pontos[i], pontos[i - 1]), fim)
    return list(zip(pontos[:-1], pontos[1:]))


def aplicar(whisper: list[Palavra], corrigido: list[str], *,
            aceitar_insercoes: bool = False,
            fracao_maxima: float = FRACAO_MAXIMA_ALTERADA) -> Resultado:
    """Aplica `corrigido` sobre `whisper` preservando a linha do tempo."""
    if not whisper:
        return Resultado(palavras=[], motivo="sem palavras do Whisper")
    if not corrigido:
        return Resultado(palavras=list(whisper), revisao_descartada=True,
                         motivo="revisão vazia")

    a = [chave(p.texto) for p in whisper]
    b = [chave(t) for t in corrigido]
    blocos = difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes()

    saida: list[Palavra] = []
    alteracoes: list[Alteracao] = []
    recusadas: list[Alteracao] = []
    remocao_pendente: float | None = None

    def emitir(p: Palavra) -> None:
        nonlocal remocao_pendente
        if remocao_pendente is not None:
            p = replace(p, inicio=min(p.inicio, remocao_pendente))
            remocao_pendente = None
        saida.append(p)

    for tipo, i, j, k, l in blocos:
        origem = whisper[i:j]
        novo = corrigido[k:l]

        if tipo == "equal":
            for pal, tok in zip(origem, novo):
                if pal.texto != tok:
                    alteracoes.append(Alteracao("grafia", [pal.texto], [tok],
                                                pal.inicio, pal.fim))
                emitir(replace(pal, texto=tok))

        elif tipo == "replace":
            n, m = len(origem), len(novo)
            ini, f = origem[0].inicio, origem[-1].fim
            conf = min((p.confianca if p.confianca is not None else 1.0)
                       for p in origem)
            if n == m:
                for pal, tok in zip(origem, novo):
                    alteracoes.append(Alteracao("troca", [pal.texto], [tok],
                                                pal.inicio, pal.fim))
                    emitir(replace(pal, texto=tok))
            elif m == 1:
                alteracoes.append(Alteracao("fusao", [p.texto for p in origem],
                                            list(novo), ini, f))
                emitir(Palavra(texto=novo[0], inicio=ini, fim=f, confianca=conf))
            else:
                alteracoes.append(Alteracao(
                    "divisao" if n == 1 else "troca",
                    [p.texto for p in origem], list(novo), ini, f))
                for tok, (ws, we) in zip(novo, repartir(ini, f, novo)):
                    emitir(Palavra(texto=tok, inicio=ws, fim=we, confianca=conf))

        elif tipo == "delete":
            alteracoes.append(Alteracao("remocao", [p.texto for p in origem], [],
                                        origem[0].inicio, origem[-1].fim))
            if saida:
                saida[-1] = replace(saida[-1],
                                    fim=max(saida[-1].fim, origem[-1].fim))
            else:
                remocao_pendente = origem[0].inicio

        elif tipo == "insert":
            ini = whisper[i - 1].fim if i > 0 else whisper[0].inicio
            f = whisper[i].inicio if i < len(whisper) else whisper[-1].fim
            reg = Alteracao("insercao_recusada", [], list(novo), ini, f)
            # Aceitar só faz sentido se existir pausa real onde encaixar.
            if aceitar_insercoes and f - ini > DURACAO_MINIMA * len(novo):
                alteracoes.append(replace(reg, tipo="insercao"))
                for tok, (ws, we) in zip(novo, repartir(ini, f, novo)):
                    emitir(Palavra(texto=tok, inicio=ws, fim=we, confianca=None))
            else:
                recusadas.append(reg)

    if remocao_pendente is not None and saida:
        saida[0] = replace(saida[0], inicio=min(saida[0].inicio, remocao_pendente))

    r = Resultado(palavras=saida, alteracoes=alteracoes, recusadas=recusadas)

    fracao = r.palavras_alteradas / max(len(whisper), 1)
    if len(whisper) >= AMOSTRA_MINIMA_PARA_FREIO and fracao > fracao_maxima:
        return Resultado(
            palavras=list(whisper), alteracoes=alteracoes, recusadas=recusadas,
            revisao_descartada=True,
            motivo=f"revisão alterou {fracao:.1%} das palavras "
                   f"(limite {fracao_maxima:.0%}); tratada como retranscrição")

    conferir(whisper, r.palavras)
    return r


def conferir(original: list[Palavra], revisado: list[Palavra]) -> None:
    """Derruba a execução se a revisão tiver mexido na linha do tempo."""
    if not revisado:
        return
    oi, of = original[0].inicio, original[-1].fim
    if abs(revisado[0].inicio - oi) > EPS:
        raise AssertionError(f"início do bloco mudou: {oi} -> {revisado[0].inicio}")
    if abs(revisado[-1].fim - of) > EPS:
        raise AssertionError(f"fim do bloco mudou: {of} -> {revisado[-1].fim}")
    for p, q in zip(revisado[:-1], revisado[1:]):
        if q.inicio < p.inicio - EPS:
            raise AssertionError(f"tempos fora de ordem: {p} -> {q}")
    for p in revisado:
        if p.fim < p.inicio - EPS:
            raise AssertionError(f"duração negativa: {p}")
        if p.inicio < oi - EPS or p.fim > of + EPS:
            raise AssertionError(f"palavra fora do span original: {p}")


def linha_do_tempo_preservada(original: list[Palavra],
                              revisado: list[Palavra]) -> bool:
    """Versão que responde em vez de levantar — para o relatório."""
    try:
        conferir(original, revisado)
        return True
    except AssertionError:
        return False


def retencao_de_fronteiras(original: list[Palavra],
                           revisado: list[Palavra]) -> float:
    """Fração das fronteiras originais que sobreviveram.

    1.0 = o Gemini só mexeu na grafia. Divisão e fusão são legítimas e baixam
    este número; o relatório mostra quanto ocorreu em vez de esconder.
    """
    if not original:
        return float("nan")
    orig = {round(p.inicio, 6) for p in original} | {round(p.fim, 6) for p in original}
    novo = {round(p.inicio, 6) for p in revisado} | {round(p.fim, 6) for p in revisado}
    return len(orig & novo) / len(orig)
