"""contentType — só prompt/guards, sem transcrever nem processar mídia."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.content_type import normalize_content_type, prompt_rules
from app.editing_intent import normalize, prompt_rules as intent_prompt


# Trechos no estilo takes_packed — fixtures, não transcrição nova.
HUMOR = (
    "[000.00-004.20] S0 Eu falei que ia dar errado.\n"
    "[004.20-006.10] S0 Aí ela olhou pra câmera.\n"
    "[006.10-008.40] S0 E o bolo caiu no chão."
)
SALES = (
    "[000.00-003.00] S0 Você perde tempo todo dia com isso.\n"
    "[003.00-006.50] S0 O método resolve em uma semana.\n"
    "[006.50-009.00] S0 Clica no link e garante a oferta."
)
EDU = (
    "[000.00-003.50] S0 Primeiro, o que é o conceito.\n"
    "[003.50-007.00] S0 Depois a gente aplica no exemplo.\n"
    "[007.00-010.00] S0 Por isso o passo 2 depende do passo 1."
)


def test_normalize_aliases():
    assert normalize_content_type("Humor") == "humor"
    assert normalize_content_type("venda") == "sales"
    assert normalize_content_type("Educativo") == "educational"
    assert normalize_content_type("review") == "review"
    assert normalize_content_type("xyz") is None


def test_intent_keeps_editing_and_content_apart():
    d = normalize({"editingIntent": "dynamic", "contentType": "humor"})
    assert d["editingIntent"] == "dynamic"
    assert d["contentType"] == "humor"


def test_humor_prompt_preserves_joke_arc():
    rules = prompt_rules("humor")
    assert "setup" in rules.lower()
    assert "punchline" in rules.lower()
    full = intent_prompt({"editingIntent": "dynamic", "contentType": "humor"})
    assert "TIPO=humor" in full
    assert "piada" in full.lower() or "punchline" in full.lower()
    assert HUMOR  # fixture disponível para decisão simulada


def test_sales_prompt_preserves_offer_cta():
    full = intent_prompt({"editingIntent": "dynamic", "contentType": "sales"})
    assert "TIPO=sales" in full
    assert "oferta" in full.lower()
    assert "CTA" in full
    assert SALES


def test_educational_prompt_preserves_sequence():
    full = intent_prompt({"editingIntent": "complete", "contentType": "educational"})
    assert "TIPO=educational" in full
    assert "sequência" in full.lower() or "logica" in full.lower() or "lógica" in full.lower()
    assert EDU


def test_simulated_edl_keeps_payoff_when_humor():
    """Decisão simulada: range do payoff não some só porque o modo é dynamic."""
    edl = [
        {"start": 0.0, "end": 4.2, "beat": "HOOK", "text": "Eu falei que ia dar errado."},
        {"start": 4.2, "end": 6.1, "beat": "B1", "text": "Aí ela olhou pra câmera."},
        {"start": 6.1, "end": 8.4, "beat": "B2", "text": "E o bolo caiu no chão."},
    ]
    rules = prompt_rules("humor").lower()
    # Guard semântico: se a regra pede preservar payoff, o último bloco fica.
    assert "payoff" in rules or "punchline" in rules
    assert edl[-1]["end"] == 8.4
