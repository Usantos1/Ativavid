"""Emoji automático: casamento exato, cooldown e idempotência."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))
from app.caption_emoji import add_caption_emojis  # noqa: E402


def _w(text, ms):
    return {"text": text, "startMs": ms, "endMs": ms + 400}


def test_matches_normalized_word():
    words = [_w("Garantia!", 0), _w("boa", 600)]
    assert add_caption_emojis(words) == 1
    assert "✅" in words[0]["text"]
    assert words[1]["text"] == "boa"


def test_cooldown_limits_density():
    # três palavras com emoji em 3s — só a primeira ganha (cooldown 6s)
    words = [_w("celular", 0), _w("bateria", 1500), _w("carregador", 3000),
             _w("garantia", 8000)]
    assert add_caption_emojis(words) == 2
    assert "📱" in words[0]["text"]
    assert "🔋" not in words[1]["text"]
    assert "✅" in words[3]["text"]


def test_never_doubles_existing_emoji():
    words = [_w("celular 📱", 0)]
    assert add_caption_emojis(words) == 0
    assert words[0]["text"].count("📱") == 1


def test_ambiguous_word_never_gets_emoji():
    # "para" (preposição) está mapeada para None de propósito
    words = [_w("para", 0)]
    assert add_caption_emojis(words) == 0


def test_hook_duration_presets():
    from run_fast import _hook_end_sec

    # curta: fórmula clássica
    assert _hook_end_sec("realce", {}, 60) == 4.0
    # media: dobro com teto 8s
    assert _hook_end_sec("realce", {"headlineDuration": "media"}, 60) == 8.0
    # inteira: vídeo todo
    assert _hook_end_sec("realce", {"headlineDuration": "inteira"}, 60) == 60.0
    # pilula ignora a preferência — é sempre o vídeo todo
    assert _hook_end_sec("pilula", {"headlineDuration": "curta"}, 60) == 60.0
    # vídeo curto: media aplica o piso de 3s sem passar da duração
    assert _hook_end_sec("realce", {"headlineDuration": "media"}, 5) == 3.0
    assert _hook_end_sec("realce", {"headlineDuration": "media"}, 2.5) == 2.5
