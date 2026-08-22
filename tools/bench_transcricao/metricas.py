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

def manual_edits_per_100w(counts: EditCounts) -> float:
    """Correcoes humanas necessarias por 100 palavras.

    Definicao operacional do benchmark: cada substituicao, delecao ou insercao
    e uma acao de edicao que uma pessoa precisa fazer antes de publicar.
    Deliberadamente igual ao numerador do WER, so que por 100 palavras - o
    ponto e expressar a mesma verdade na unidade que o usuario do ATIVAVID
    sente (quantas vezes ele vai ter que parar e digitar).
    """
    n = counts.ref_len
    return 100.0 * (counts.sub + counts.dele + counts.ins) / n if n else 0.0


@dataclass
class TextReport:
    counts: EditCounts
    cer: float
    edits_100w: float
    entities: CategoryScore
    numbers: CategoryScore
    colloquial: CategoryScore


def evaluate_text(ref_text: str, hyp_text: str,
                  entities: list[str] | None = None) -> TextReport:
    ref = tokens(ref_text)
    hyp = tokens(hyp_text)
    counts, ops = levenshtein_ops(ref, hyp)
    return TextReport(
        counts=counts,
        cer=cer(ref_text, hyp_text),
        edits_100w=manual_edits_per_100w(counts),
        entities=score_entities(ref_text, hyp_text, entities),
        numbers=score_category(ref, ops, hyp, is_number_token),
        colloquial=score_category(ref, ops, hyp, is_colloquial_token),
    )
