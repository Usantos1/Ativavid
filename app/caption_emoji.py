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
    "rapido": "\u26a1", "veloz": "\u26a1", "forte": "\U0001f4aa", "quebrou": "\U0001f494",
    # --- 5.0.64: lido do vocabulario REAL dos videos dele ---------------
    # 86.679 palavras em 1.049 transcricoes: o mapa antigo casava 4,5%
    # delas. As entradas abaixo saem dessa contagem, das mais faladas para
    # baixo, e so onde o emoji tem referente claro — palavra de ligacao
    # ("voce", "aqui", "isso") nunca entra, porque emoji em palavra vazia e
    # o que faz legenda parecer spam.
    # assistencia / conserto (o negocio dele, e o de boa parte dos clientes)
    "aparelho": "\U0001f4f1", "capinha": "\U0001f6e1\ufe0f", "capinhas": "\U0001f6e1\ufe0f",
    "capa": "\U0001f6e1\ufe0f", "pelicula": "\U0001f6e1\ufe0f", "tampa": "\U0001f4f1",
    "traseira": "\U0001f4f1", "conector": "\U0001f50c", "fonte": "\U0001f50c",
    "carga": "\U0001f50b", "carregar": "\U0001f50b", "carrega": "\U0001f50b",
    "conserto": "\U0001f527", "consertar": "\U0001f527", "reparo": "\U0001f527",
    "assistencia": "\U0001f527", "tecnica": "\U0001f527", "ferramenta": "\U0001f527",
    "parafuso": "\U0001f529", "placa": "\U0001f9e0",
    # o que deu errado
    "problema": "\u26a0\ufe0f", "defeito": "\u26a0\ufe0f", "falha": "\u26a0\ufe0f",
    "quebrado": "\U0001f494", "quebrada": "\U0001f494", "quebra": "\U0001f494",
    "umidade": "\U0001f4a7", "agua": "\U0001f4a7", "molhou": "\U0001f4a7",
    "risco": "\u26a0\ufe0f", "erro": "\u274c",
    # o que resolve
    "troca": "\U0001f504", "trocar": "\U0001f504", "substituicao": "\U0001f504",
    "resolver": "\u2705", "resolva": "\u2705", "pronto": "\u2705",
    "funciona": "\u2705", "funcionando": "\u2705", "funcionar": "\u2705",
    "testar": "\U0001f9ea", "testa": "\U0001f9ea", "teste": "\U0001f9ea",
    "verificar": "\U0001f50e", "verifica": "\U0001f50e", "identificar": "\U0001f50e",
    "conferir": "\U0001f50e", "limpar": "\U0001f9fc", "limpa": "\U0001f9fc",
    "proteger": "\U0001f6e1\ufe0f", "protege": "\U0001f6e1\ufe0f",
    # dinheiro e compra
    "orcamento": "\U0001f4b0", "valor": "\U0001f4b0", "pagar": "\U0001f4b3",
    "credito": "\U0001f4b3", "debito": "\U0001f4b3", "pix": "\U0001f4b3",
    "compra": "\U0001f6d2", "comprar": "\U0001f6d2", "comprei": "\U0001f6d2",
    "venda": "\U0001f6d2", "vendas": "\U0001f4c8", "gastar": "\U0001f4b8",
    "gastando": "\U0001f4b8", "economia": "\U0001f4b0", "parcelado": "\U0001f4b3",
    # combinar hora
    "whatsapp": "\U0001f4ac", "agendamento": "\U0001f4c5", "agende": "\U0001f4c5",
    "agendar": "\U0001f4c5", "horario": "\U0001f552", "horas": "\U0001f552",
    "hora": "\U0001f552", "manha": "\U0001f305", "minutos": "\u23f1\ufe0f",
    "amanha": "\U0001f4c5", "segunda": "\U0001f4c5",
    # gente
    "cliente": "\U0001f91d", "clientes": "\U0001f91d", "atendimento": "\U0001f91d",
    "ajudar": "\U0001f91d", "ajuda": "\U0001f91d", "obrigado": "\U0001f64f",
    "deus": "\U0001f64f", "equipe": "\U0001f465", "seguidores": "\U0001f465",
    # conteudo e reacao
    "video": "\U0001f3ac", "videos": "\U0001f3ac", "edicao": "\U0001f3ac",
    "foto": "\U0001f4f8", "link": "\U0001f517", "comenta": "\U0001f4ac",
    "compartilha": "\U0001f501", "salva": "\U0001f516", "inscreva": "\U0001f514",
    "dica": "\U0001f4a1", "ideia": "\U0001f4a1", "aprender": "\U0001f393",
    "aula": "\U0001f393", "curso": "\U0001f393", "resultado": "\U0001f4c8",
    "crescer": "\U0001f4c8", "qualidade": "\U0001f3c6",
    "feliz": "\U0001f604", "gostei": "\U0001f60d", "caraca": "\U0001f632",
    "calma": "\U0001f9d8", "sorte": "\U0001f340",
    # objetos e lugares que aparecem no dia a dia
    "som": "\U0001f50a", "toque": "\U0001f514", "ouvido": "\U0001f442",
    "sinal": "\U0001f4f6", "sistema": "\u2699\ufe0f", "academia": "\U0001f4aa",
    "trabalho": "\U0001f4bc", "chefe": "\U0001f4bc", "caixa": "\U0001f4e6",
    "entrega": "\U0001f69a", "viagem": "\u2708\ufe0f", "comida": "\U0001f37d\ufe0f",
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
