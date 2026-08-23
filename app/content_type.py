"""Tipo de conteúdo — separado de editingIntent (como editar)."""
from __future__ import annotations

CONTENT_TYPES = (
    "educational",
    "humor",
    "sales",
    "ad",
    "viral",
    "review",
    "institutional",
    "informational",
)

LABELS = {
    "educational": "Educativo",
    "humor": "Humor",
    "sales": "Venda",
    "ad": "Anúncio (AIDA)",
    "viral": "Viral",
    "review": "Review",
    "institutional": "Institucional",
    "informational": "Informativo",
}

_RULES = {
    "educational": (
        "TIPO=educational (Educativo).\n"
        "Preserve explicação, contexto e a sequência lógica. "
        "Não pule um passo só para acelerar. "
        "Pode limpar silêncio, erro e repetição, mas a aula precisa continuar fazendo sentido."
    ),
    "humor": (
        "TIPO=humor.\n"
        "Preserve semanticamente o bloco da piada: setup → reação → payoff → punchline. "
        "Não remova o contexto que a punchline precisa. "
        "Punchline não é CTA. Na dúvida se a frase seguinte ainda é engraçada sem isto: PRESERVAR."
    ),
    "sales": (
        "TIPO=sales (Venda).\n"
        "Preserve o arco: problema → argumento → oferta → CTA. "
        "Não corte a objeção nem a prova que sustenta a oferta. "
        "O CTA do fim é parte da venda, não um extra."
    ),
    "ad": (
        "TIPO=ad (Anúncio, estrutura AIDA).\n"
        "Monte o corte na ordem AIDA: Atenção (gancho forte nos primeiros 2s) → "
        "Interesse (o problema/desejo) → Desejo (benefício ou prova concreta) → "
        "Ação (CTA claro no fim). "
        "O primeiro range DEVE ser beat=HOOK com a frase mais forte do vídeo; "
        "o último DEVE ser beat=CTA. Corte tudo que não sustenta um dos 4 blocos. "
        "Nunca termine sem o CTA — sem ação explícita não é anúncio."
    ),
    "viral": (
        "TIPO=viral.\n"
        "O video inteiro serve ao comeco: a frase mais forte vai no primeiro "
        "range (beat=HOOK), e ela precisa fazer sentido sozinha, sem nada antes. "
        "Corte pausa, rodeio e preambulo -- 'oi gente', 'entao', 'deixa eu "
        "explicar'. Mas NAO corte o que da sentido a frase forte: promessa sem "
        "a entrega vira clickbait e o espectador sai nos primeiros segundos. "
        "Prefira terminar num fecho seco a alongar ate esvaziar."
    ),
    "review": (
        "TIPO=review.\n"
        "Preserve: produto → teste/opinião → conclusão. "
        "Não remova o veredito nem o critério que o justifica."
    ),
    "institutional": (
        "TIPO=institutional (Institucional).\n"
        "Edição conservadora: só limpe silêncio, erro e repetição. "
        "Não reordene a mensagem da marca nem corte tom/credibilidade."
    ),
    "informational": (
        "TIPO=informational (Informativo).\n"
        "Ritmo equilibrado sem sacrificar clareza. "
        "Pode enxugar pausa, mas cada fato precisa continuar compreensível sozinho."
    ),
}


def normalize_content_type(raw: str | None) -> str | None:
    val = str(raw or "").strip().lower()
    aliases = {
        "educativo": "educational",
        "educacao": "educational",
        "piada": "humor",
        "venda": "sales",
        "comercial": "sales",
        "anuncio": "ad",
        "trend": "viral",
        "trending": "viral",
        "anúncio": "ad",
        "aida": "ad",
        "ads": "ad",
        "analise": "review",
        "institucional": "institutional",
        "informativo": "informational",
        "info": "informational",
    }
    val = aliases.get(val, val)
    if val in CONTENT_TYPES:
        return val
    return None


def label(raw: str | None) -> str:
    key = normalize_content_type(raw)
    return LABELS.get(key or "", "")


def prompt_rules(raw: str | None) -> str:
    """Regra de prompt do tipo, ou "" se nao houver.

    O acesso era direto (`_RULES[key]`) e um tipo sem regra derrubava o
    planejamento inteiro. Foi o que aconteceu com "viral": ele estava na lista
    oferecida na tela e nos rotulos, mas ficou sem regra. Como o pipeline
    engole a excecao e cai na heuristica, o sintoma nao foi um erro na tela --
    foi o titulo do video saindo torto. 65 videos entre 18 e 22/08.

    Sem regra o corte fica generico, o que e ruim; com a excecao ele ficava
    generico E calado, que e pior. O teste `todos_os_tipos_tem_regra` impede
    que a lacuna volte.
    """
    key = normalize_content_type(raw)
    if not key:
        return ""
    return _RULES.get(key, "")


def choices() -> list[dict[str, str]]:
    return [{"id": k, "label": LABELS[k]} for k in CONTENT_TYPES]
