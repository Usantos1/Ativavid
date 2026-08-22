# -*- coding: utf-8 -*-
"""WER, CER, inserções/omissões/trocas e as métricas de produto do ATIVAVID.

O projeto não tinha nada disto — `app/editing_intent.py` usa
`SequenceMatcher` para outra finalidade. É a única peça de medição que o
benchmark precisa acrescentar.

A normalização é deliberadamente fraca: tira pontuação e caixa, e mais
nada. "cê" continua diferente de "você" e "tá" de "está", porque o
benchmark tem de penalizar quem normaliza a fala do usuário."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from tools.bench_transcricao.lexico import (
    COLLOQUIAL, DISCOURSE_MARKERS, DOMAIN_ENTITIES, NUMBER_WORDS,
    NUMERIC_RE)

_PUNCT = re.compile(r"[^\wÀ-ɏ'%$]+", re.UNICODE)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").casefold()


def norm_token(tok: str, *, fold_accents: bool = False) -> str:
    """Normaliza para comparacao de WER.

    NAO normaliza fala: "ce" continua diferente de "voce". Isso e proposital -
    o benchmark precisa penalizar quem formaliza o que a pessoa falou.
    """
    t = _PUNCT.sub("", tok).casefold()
    return _fold(t) if fold_accents else t


def tokens(text: str, *, fold_accents: bool = False) -> list[str]:
    out = [norm_token(t, fold_accents=fold_accents) for t in text.split()]
    return [t for t in out if t]


@dataclass
class EditCounts:
    hits: int = 0
    sub: int = 0
    dele: int = 0
    ins: int = 0

    @property
    def ref_len(self) -> int:
        return self.hits + self.sub + self.dele

    @property
    def wer(self) -> float:
        n = self.ref_len
        return (self.sub + self.dele + self.ins) / n if n else 0.0

    @property
    def accuracy(self) -> float:
        """Percentual de palavras exatamente corretas."""
        n = self.ref_len
        return self.hits / n if n else 0.0


def levenshtein_ops(ref: list[str], hyp: list[str]) -> tuple[EditCounts, list[tuple]]:
    """DP classico de WER. Retorna contagens e a trilha de operacoes.

    Trilha: lista de (op, i_ref, j_hyp) com op em {eq, sub, del, ins}.
    """
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if ref[i - 1] == hyp[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1,        # delecao
                          d[i][j - 1] + 1,        # insercao
                          d[i - 1][j - 1] + cost)  # sub / acerto

    ops: list[tuple] = []
    c = EditCounts()
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            if ref[i - 1] == hyp[j - 1]:
                ops.append(("eq", i - 1, j - 1)); c.hits += 1
            else:
                ops.append(("sub", i - 1, j - 1)); c.sub += 1
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, None)); c.dele += 1
            i -= 1
        else:
            ops.append(("ins", None, j - 1)); c.ins += 1
            j -= 1
    ops.reverse()
    return c, ops


def wer(ref_text: str, hyp_text: str, *, fold_accents: bool = False) -> EditCounts:
    return levenshtein_ops(tokens(ref_text, fold_accents=fold_accents),
                           tokens(hyp_text, fold_accents=fold_accents))[0]


def cer(ref_text: str, hyp_text: str) -> float:
    r = list(_PUNCT.sub(" ", ref_text).casefold().strip())
    h = list(_PUNCT.sub(" ", hyp_text).casefold().strip())
    return levenshtein_ops(r, h)[0].wer


# ---------------------------------------------------------------- categorias

def is_number_token(tok: str) -> bool:
    t = norm_token(tok, fold_accents=True)
    return bool(NUMERIC_RE.search(tok)) or t in NUMBER_WORDS


def is_colloquial_token(tok: str) -> bool:
    t = norm_token(tok, fold_accents=True)
    return t in DISCOURSE_MARKERS or t in COLLOQUIAL


@dataclass
class CategoryScore:
    total: int = 0
    correct: int = 0
    misses: list[tuple[str, str]] = field(default_factory=list)

    @property
    def rate(self) -> float:
        return self.correct / self.total if self.total else float("nan")


def score_category(ref_toks: list[str], ops: list[tuple], hyp_toks: list[str],
                   predicate) -> CategoryScore:
    """Acerto por categoria, usando o alinhamento de WER ja calculado."""
    sc = CategoryScore()
    for op, i, j in ops:
        if i is None:
            continue
        if not predicate(ref_toks[i]):
            continue
        sc.total += 1
        if op == "eq":
            sc.correct += 1
        else:
            sc.misses.append((ref_toks[i], hyp_toks[j] if j is not None else "<omitido>"))
    return sc


def score_entities(ref_text: str, hyp_text: str,
                   entities: list[str] | None = None) -> CategoryScore:
    """Nomes proprios / marcas / produtos.

    `entities` vem do ground truth humano (campo `entities`). Sem anotacao,
    cai no pre-tagger de dominio - que e so um apoio, nao substitui anotacao.
    """
    ents = [e.casefold() for e in (entities or [])] or sorted(DOMAIN_ENTITIES)
    hay = " ".join(tokens(hyp_text, fold_accents=True))
    ref_hay = " ".join(tokens(ref_text, fold_accents=True))
    sc = CategoryScore()
    for e in ents:
        needle = " ".join(tokens(e, fold_accents=True))
        if not needle or needle not in ref_hay:
            continue
        n_ref = ref_hay.count(needle)
        n_hyp = hay.count(needle)
        sc.total += n_ref
        sc.correct += min(n_ref, n_hyp)
        if n_hyp < n_ref:
            sc.misses.append((e, f"encontrado {n_hyp}x de {n_ref}x"))
    return sc


# --------------------------------------------------------- retrabalho manual

def operacoes_100w(counts: EditCounts) -> float:
    """Operações de edição por 100 palavras — o numerador do WER na unidade
    do produto. Sobe junto com o WER por construção; existe para comparar."""
    n = counts.ref_len
    return 100.0 * (counts.sub + counts.dele + counts.ins) / n if n else 0.0


def correcoes_humanas(ops: list[tuple], ref_len: int) -> tuple[int, float]:
    """Quantas vezes uma pessoa precisa PARAR E DIGITAR, por 100 palavras.

    Não é o WER em outra unidade — e a diferença importa. Quem conserta
    "na praimcamp ontem" seleciona o trecho e digita UMA vez; o WER conta três
    operações. Um motor que erra três palavras seguidas incomoda menos que um
    que erra três palavras espalhadas pelo vídeo, porque o segundo obriga a
    parar três vezes e a achar cada ponto.

    Então a conta é por CORRIDA de erro: sequências vizinhas de troca, omissão
    ou invenção viram uma correção só. É esta a métrica que responde a
    pergunta do produto — quanto trabalho manual cada motor gera.

    Devolve (número de correções, correções por 100 palavras).
    """
    corridas = 0
    dentro = False
    for op, _i, _j in ops:
        if op == "eq":
            dentro = False
        elif not dentro:
            corridas += 1
            dentro = True
    return corridas, (100.0 * corridas / ref_len if ref_len else 0.0)


# Nome antigo, mantido para não quebrar quem já importava.
manual_edits_per_100w = operacoes_100w


@dataclass
class TextReport:
    counts: EditCounts
    cer: float
    edits_100w: float        # operações por 100 palavras (segue o WER)
    correcoes: int           # vezes que a pessoa para e digita
    correcoes_100w: float    # o mesmo, por 100 palavras
    entities: CategoryScore
    numbers: CategoryScore
    colloquial: CategoryScore


def evaluate_text(ref_text: str, hyp_text: str,
                  entities: list[str] | None = None) -> TextReport:
    ref = tokens(ref_text)
    hyp = tokens(hyp_text)
    counts, ops = levenshtein_ops(ref, hyp)
    n_corr, corr_100 = correcoes_humanas(ops, counts.ref_len)
    return TextReport(
        counts=counts,
        cer=cer(ref_text, hyp_text),
        edits_100w=operacoes_100w(counts),
        correcoes=n_corr,
        correcoes_100w=corr_100,
        entities=score_entities(ref_text, hyp_text, entities),
        numbers=score_category(ref, ops, hyp, is_number_token),
        colloquial=score_category(ref, ops, hyp, is_colloquial_token),
    )
