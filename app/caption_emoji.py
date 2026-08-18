"""Emoji automático nas legendas — mapa curado PT, sem IA e sem rede.

Opt-in (elements.emojiCaptions). O emoji entra no TEXTO da palavra em
captions.json, então vale para todos os estilos de legenda — inclusive o
Empilhado, cujo caption_style.py já trata emoji (is_emoji_run) e nunca
descarta a palavra que o carrega.

Regras anti-poluição: no máximo 1 emoji a cada COOLDOWN_MS, nunca em
palavra que já tem emoji, e a palavra precisa casar inteira (normalizada,
sem acento) — "garantia" ganha ✅, "garantiA123" não.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

COOLDOWN_MS = 6000

# Palavra normalizada (minúscula, sem acento) → emoji. Curado para o
# vocabulário de Reels de venda/serviço em PT-BR; genérico por design —
# nada de marca ou nicho específico aqui.
EMOJI_MAP = {
    # dinheiro / oferta
    "gratis": "🆓", "gratuito": "🆓", "desconto": "💸", "promocao": "💸",
    "barato": "💰", "dinheiro": "💰", "preco": "💰", "reais": "💰",
    "oferta": "🔥", "imperdivel": "🔥",
    # urgência / atenção
    "hoje": "⏰", "agora": "⏰", "urgente": "🚨", "cuidado": "⚠️",
    "atencao": "⚠️", "perigo": "⚠️", "nunca": "🚫", "proibido": "🚫",
    "pare": "✋", "para": None,  # ambíguo demais ("para" preposição) — nunca
    # qualidade / confiança
    "garantia": "✅", "garantido": "✅", "aprovado": "✅", "certo": "✅",
    "original": "💎", "premium": "💎", "melhor": "🏆", "top": "🏆",
    "perfeito": "👌", "incrivel": "🤯", "surreal": "🤯", "chocante": "😱",
    # objetos comuns de loja/serviço
    "celular": "📱", "telefone": "📱", "iphone": "📱", "bateria": "🔋",
    "carregador": "🔌", "fone": "🎧", "fones": "🎧", "camera": "📷",
    "tela": "📱", "martelo": "🔨", "martelada": "🔨", "chave": "🔧",
    "carro": "🚗", "moto": "🏍️", "casa": "🏠", "loja": "🏪",
    # emoção / reação
    "amei": "😍", "amor": "❤️", "coracao": "❤️", "rindo": "😂",
    "segredo": "🤫", "presente": "🎁", "novidade": "✨", "novo": "✨",
    "rapido": "⚡", "veloz": "⚡", "forte": "💪", "quebrou": "💔",
}


def _norm(t: str) -> str:
    t = t.strip(" .,!?;:…\"'-").lower()
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def _has_emoji(t: str) -> bool:
    return any(ord(ch) >= 0x2190 for ch in t)


def add_caption_emojis(words: list[dict]) -> int:
    """Muta a lista de palavras (formato captions.json). Devolve nº aplicado."""
    applied = 0
    last_ms = -COOLDOWN_MS
    for w in words:
        text = str(w.get("text") or "")
        if not text or _has_emoji(text):
            continue
        emoji = EMOJI_MAP.get(_norm(text))
        if not emoji:
            continue
        start = w.get("startMs")
        if not isinstance(start, (int, float)):
            continue
        if start - last_ms < COOLDOWN_MS:
            continue
        w["text"] = f"{text} {emoji}"
        last_ms = start
        applied += 1
    return applied


def apply_to_captions_file(caps_path: Path) -> int:
    """Aplica in-place em public/captions.json. Erro nunca derruba o job."""
    try:
        p = Path(caps_path)
        words = json.loads(p.read_text(encoding="utf-8-sig"))
        if not isinstance(words, list):
            return 0
        n = add_caption_emojis(words)
        if n:
            p.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        return n
    except (OSError, json.JSONDecodeError, TypeError):
        return 0
