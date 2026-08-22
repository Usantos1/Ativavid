# -*- coding: utf-8 -*-
"""Léxico PT-BR das métricas específicas do ATIVAVID.

Serve a uma decisão de produto: transcrever "você" onde a pessoa falou
"cê" é ERRO, não melhoria. Um motor que formaliza a fala obriga o usuário
a desfazer a "correção" — que é exatamente o retrabalho que este
benchmark mede."""

from __future__ import annotations

import re

# Coloquialismo -> formas "formais" equivalentes. Se o motor devolveu a forma
# formal, ele NORMALIZOU a fala - o que o benchmark conta como erro de
# preservacao, nao como acerto.
COLLOQUIAL: dict[str, set[str]] = {
    "ce": {"voce"}, "oce": {"voce"}, "voce": set(),
    "ta": {"esta"}, "to": {"estou"}, "tamo": {"estamos"}, "tao": {"estao"},
    "tava": {"estava"}, "tavam": {"estavam"}, "tinha": set(),
    "ne": {"nao e"}, "num": {"nao"}, "nao": set(),
    "pra": {"para"}, "pro": {"para o"}, "pras": {"para as"}, "pros": {"para os"},
    "vamo": {"vamos"}, "vo": {"vou"}, "cade": {"onde esta"},
    "bora": {"vamos embora"}, "peraí": {"espera ai"}, "perai": {"espera ai"},
    "aí": set(), "tipo": set(), "mano": set(), "cara": set(),
    "massa": set(), "bagulho": set(), "sacou": {"entendeu"},
    "beleza": set(), "valeu": {"obrigado"},
    "uai": set(), "oxe": set(), "eita": set(),
}

# Marcadores puramente coloquiais (sem par formal) que tambem contam como
# "preservacao de linguagem falada" quando aparecem no ground truth.
DISCOURSE_MARKERS = {
    "ne", "ta", "to", "ce", "pra", "pro", "tipo", "mano", "cara", "aí",
    "entao", "assim", "sabe", "olha", "ó", "bora", "eita", "uai", "oxe",
    "massa", "beleza", "valeu", "num", "vamo", "tamo", "sacou",
}

NUMBER_WORDS = {
    "zero", "um", "uma", "dois", "duas", "tres", "quatro", "cinco", "seis",
    "sete", "oito", "nove", "dez", "onze", "doze", "treze", "catorze",
    "quatorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove",
    "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta",
    "oitenta", "noventa", "cem", "cento", "duzentos", "trezentos",
    "quatrocentos", "quinhentos", "seiscentos", "setecentos", "oitocentos",
    "novecentos", "mil", "milhao", "milhoes", "bilhao", "bilhoes",
    "primeiro", "segundo", "terceiro", "meia", "meio",
}

# Digitos, moeda, percentual, ano, hora: "R$3.500", "15%", "2026", "10h30".
NUMERIC_RE = re.compile(r"\d")

# Marcas/produtos conhecidos do dominio ATIVAVID. O ground truth humano pode
# (e deve) estender esta lista por video; ela existe so como pre-tagger.
DOMAIN_ENTITIES = {
    "ativavid", "primecamp", "prime camp", "ativacrm", "ativadash",
    "ativafix", "elevenlabs", "scribe", "whisper", "gemini", "groq",
    "remotion", "youtube", "instagram", "tiktok", "reels", "shorts",
}
