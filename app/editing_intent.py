"""Intenção de edição por job — o que fazer com ESTE vídeo.

Não é estilo de marca. Não mexe em motor de render.
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

INTENTS = ("complete", "dynamic", "shorts", "clips", "light", "intact")
INTENT_FILE = "job_intent.json"

# Vídeo ≥ isto (segundos) recomenda "Editar vídeo completo"
LONG_VIDEO_SEC = 90.0
# Dynamic em clipes curtos: só limpa silêncio/erro — não corta fala de contexto
SHORT_DYNAMIC_SEC = 15.0

CTA_HINTS = (
    "me segue", "segue a gente", "segue o", "comenta", "compartilha",
    "salva esse", "salva este", "manda para", "manda pra", "chama no direct",
    "chama no zap", "chama no whats", "clica no link", "link na bio",
    "fale conosco", "chama no whatsapp", "até o próximo", "te vejo no próximo",
    "se você gostou", "se voce gostou", "se fez sentido", "agora você já sabe",
    "agora voce ja sabe", "entre em contato", "fala comigo", "me chama",
)

DEFAULTS = {
    "complete": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    "dynamic": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    "shorts": {
        "preserveHook": False,
        "preserveCTA": False,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    # "light": edição leve — corte heurístico local (só silêncio/erro),
    # SEM IA reescrevendo o corte. Tudo preservado por padrão.
    "light": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    # "intact": SEM CORTES — o vídeo inteiro, zero tesoura. Só legendas,
    # título, cor e trilha. Nasceu de pedido direto do usuário (24-25/08):
    # "quero o mais original possível" — e o mínimo que existia (Vídeo
    # completo) ainda tira silêncio e repetição.
    "intact": {
        "preserveHook": True,
        "preserveCTA": True,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
    # "clips": o job mãe só analisa e divide — cada clipe filho roda como
    # "dynamic". As flags valem para os filhos.
    "clips": {
        "preserveHook": False,
        "preserveCTA": False,
        "preserveCompleteSentences": True,
        "preserveContext": True,
    },
}


def suggest_intent(duration_s: float | None) -> str:
    if duration_s is not None and float(duration_s) >= LONG_VIDEO_SEC:
        return "complete"
    return "dynamic"


def normalize(raw: dict | None, *, duration_s: float | None = None) -> dict:
    src = dict(raw or {})
    mode = str(src.get("editingIntent") or src.get("intent") or "").strip().lower()
    if mode not in INTENTS:
        mode = suggest_intent(duration_s)
    flags = dict(DEFAULTS[mode])
    for key in flags:
        if key in src:
            flags[key] = bool(src[key])
    ranges = _parse_ranges(src.get("protectedRanges"))
    brand = str(src.get("brandStyleSource") or "default").strip().lower()
    if brand not in ("default", "custom"):
        brand = "default"
    from app.content_type import normalize_content_type

    content = normalize_content_type(src.get("contentType") or src.get("tipoConteudo"))
    preset_id = str(src.get("brandPresetId") or "").strip() or None
    brand_id = str(src.get("brandId") or "").strip() or None
    # Knobs do corte escolhidos NA IMPORTACAO (25/08, "mais opcoes de
    # edicao"). Vazio/invalido = None = o preset do estilo decide. Os dois
    # sao _CUT_STYLE_KEYS: mudar num refazer replaneja o corte.
    ritmo = str(src.get("rhythm") or "").strip().lower() or None
    if ritmo not in ("natural", "calmo", "dinamico", "viral", "rapido",
                     "muito_rapido", "cirurgico", "narrativa"):
        ritmo = None
    limpeza = str(src.get("speechClean") or "").strip().lower() or None
    if limpeza not in ("desativado", "leve", "medio", "forte"):
        limpeza = None
    return {
        "rhythm": ritmo,
        "speechClean": limpeza,
        "editingIntent": mode,
        "contentType": content,
        "preserveHook": flags["preserveHook"],
        "preserveCTA": flags["preserveCTA"],
        "preserveCompleteSentences": flags["preserveCompleteSentences"],
        "preserveContext": flags["preserveContext"],
        "protectedRanges": ranges,
        "brandStyleSource": brand,
        "brandId": brand_id,
        "brandPresetId": preset_id,
        "suggestedIntent": suggest_intent(duration_s) if duration_s is not None else None,
        "sourceDurationSec": round(float(duration_s), 2) if duration_s else None,
    }


def _parse_ranges(raw: Any) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            start = float(item.get("start"))
            end = float(item.get("end"))
        except (TypeError, ValueError):
            continue
        if end > start >= 0:
            item_out = {"start": round(start, 3), "end": round(end, 3)}
            for key in ("source", "reason", "label"):
                if item.get(key):
                    item_out[key] = str(item[key])[:80]
            for key in ("draftStart", "draftEnd"):
                if item.get(key) is None:
                    continue
                try:
                    item_out[key] = round(float(item[key]), 3)
                except (TypeError, ValueError):
                    pass
            out.append(item_out)
    return out


def save(edit_dir: Path, intent: dict) -> dict:
    data = normalize(intent)
    path = Path(edit_dir) / INTENT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def load(edit_dir: Path) -> dict | None:
    path = Path(edit_dir) / INTENT_FILE
    if not path.exists():
        return None
    try:
        return normalize(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def merge_into_preset(preset: dict, intent: dict | None) -> dict:
    """Copia a intenção para o preset usado no plano de corte. Sem alterar visual."""
    out = dict(preset or {})
    if not intent:
        return out
    data = normalize(intent)
    out["editingIntent"] = data["editingIntent"]
    out["preserveHook"] = data["preserveHook"]
    out["preserveCTA"] = data["preserveCTA"]
    out["preserveCompleteSentences"] = data["preserveCompleteSentences"]
    out["preserveContext"] = data["preserveContext"]
    out["protectedRanges"] = data["protectedRanges"]
    out["brandStyleSource"] = data["brandStyleSource"]
    if data.get("contentType"):
        out["contentType"] = data["contentType"]
    if data.get("brandId"):
        out["brandId"] = data["brandId"]
    if data.get("brandPresetId"):
        out["brandPresetId"] = data["brandPresetId"]
    if data.get("sourceDurationSec") is not None:
        out["sourceDurationSec"] = data["sourceDurationSec"]
    if data.get("rhythm"):
        out["rhythm"] = data["rhythm"]
    if data.get("speechClean"):
        out["speechClean"] = data["speechClean"]
    return out


def prompt_rules(preset: dict | None) -> str:
    """Bloco extra para o system prompt da IA de corte."""
    p = preset or {}
    mode = str(p.get("editingIntent") or "dynamic").lower()
    if mode not in INTENTS:
        mode = "dynamic"
    hook = bool(p.get("preserveHook", DEFAULTS[mode]["preserveHook"]))
    cta = bool(p.get("preserveCTA", DEFAULTS[mode]["preserveCTA"]))
    sentences = bool(p.get("preserveCompleteSentences", True))
    context = bool(p.get("preserveContext", True))
    ranges = p.get("protectedRanges") or []

    if mode == "complete":
        intent_txt = (
            "INTENÇÃO=complete (Editar vídeo completo).\n"
            "O objetivo NÃO é encurtar. É manter o conteúdo completo e só limpar "
            "o que claramente não deveria estar no vídeo.\n"
            "PODE remover somente: silêncio excessivo; erro evidente + recomeço; "
            "frase abandonada e refeita; repetição literal/quase literal; "
            "ruído/trecho sem fala útil; preparação de gravação descartável.\n"
            "PROIBIDO remover fala por: ritmo, punchline, retenção, deixar mais rápido, "
            "achar a frase menos interessante, preferir outra parte mais forte.\n"
            "Na dúvida (contexto, humor, argumento, reação, continuidade): PRESERVAR.\n"
            "O primeiro bloco semântico da transcrição deve permanecer INTEIRO "
            "(só silêncio interno excessivo ou erro/recomeço evidente).\n"
            "Classifique cada remoção com um destes rótulos e só estes: "
            "silence | false_start | repetition | abandoned_take | non_content.\n"
        )
    elif mode == "shorts":
        intent_txt = (
            "INTENÇÃO=shorts (Criar Reels / Shorts).\n"
            "Prioridade: selecionar trechos independentes e fortes (cerca de 20–60s cada).\n"
            "Pode ignorar partes grandes do original — o objetivo é um conteúdo curto novo.\n"
            "Cada trecho precisa de começo e fim próprios (gancho + conclusão naturais).\n"
            "Nunca termine um short no meio de uma frase ou CTA.\n"
        )
    else:
        intent_txt = (
            "INTENÇÃO=dynamic (Deixar mais dinâmico).\n"
            "Significa: deixe mais rápido SEM destruir a estrutura narrativa.\n"
            "NÃO significa: remova qualquer coisa que deixe o vídeo mais curto.\n"
            "PODE remover: silêncio; pausa excessiva; erro; falso começo; "
            "repetição real; hesitação sem função; trecho morto entre frases.\n"
            "PROIBIDO remover fala só porque: é mais lenta; não é a frase principal; "
            "parece contexto; outra frase tem mais punch; quer melhorar retenção; "
            "quer chegar mais rápido na punchline.\n"
            "Antes de remover conteúdo falado, pergunte: "
            "'A frase seguinte ainda faz sentido e continua engraçada sem isto?' "
            "Se a resposta for incerta: PRESERVAR.\n"
            "HUMOR: identifique setup, contexto, pergunta, resposta, reação, "
            "escalada, contraste, callback, punchline, quebra de expectativa. "
            "Essas partes dependem umas das outras — preserve o bloco inteiro "
            "(setup + resposta + payoff). Punchline ≠ CTA.\n"
            "Dynamic NÃO é obrigado a cortar. Se o bloco inteiro for necessário, mantenha.\n"
        )
        dur = p.get("sourceDurationSec")
        try:
            dur_f = float(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur_f = None
        if dur_f is not None and dur_f <= SHORT_DYNAMIC_SEC:
            intent_txt += (
                f"VÍDEO CURTO (≈{dur_f:.1f}s): já está no tamanho de uma peça final. "
                "Seja ainda mais conservador. Remova só silêncio evidente, erro, "
                "falso começo ou pausa morta. Conteúdo falado deve ser preservado "
                "quase integralmente. Não corte 1–2s de contexto para 'ganhar ritmo'.\n"
            )

    guards = [
        "CORTES POR UNIDADE SEMÂNTICA (não só por silêncio/timestamp):",
        "- Só corte se a frase e o pensamento terminaram.",
        "- Se existe complemento logo depois, ou a fala explica a próxima, MANTENHA.",
        "- Prefira: fim de frase, pausa natural, mudança de assunto, erro+recomeço, repetição, silêncio inútil.",
        "- Evite: meio de oração, meio de raciocínio, entre pergunta e resposta, antes da conclusão, começo de CTA.",
    ]
    if sentences:
        guards.append("- NUNCA corte frase pela metade. Se duvidar, mantenha até o ponto final da ideia.")
    if context:
        guards.append("- Preserve o contexto: pergunta+resposta, setup+punchline, premissa+conclusão.")
    if hook:
        if mode == "complete":
            guards.append(
                "- GANCHO/COMPLETE: preserve o PRIMEIRO bloco packed inteiro. "
                "Não corte falas internas da abertura (ex.: 'Não é, pai?' / 'Aham, é sim, filha')."
            )
        else:
            guards.append(
                "- GANCHO: o primeiro bloco falado é protegido. Pode limpar respiração/falso começo minúsculo, "
                "mas NÃO troque a abertura por outra frase 'mais forte' nem apague os primeiros segundos sem motivo semântico."
            )
    if cta:
        guards.append(
            "- CTA/CONCLUSÃO: quando a finalização começar, preserve o bloco INTEIRO até a conclusão natural. "
            "Sinais (não exclusivos): me segue, comenta, compartilha, salva, link na bio, chama no direct/WhatsApp, "
            "se você gostou, se fez sentido, até o próximo, entre em contato. "
            "PROIBIDO terminar em 'me segue para…' ou qualquer CTA cortado."
        )
    if ranges:
        bits = ", ".join(f"{r['start']:.2f}–{r['end']:.2f}s" for r in ranges[:12])
        guards.append(f"- TRECHOS PROTEGIDOS (obrigatório manter): {bits}.")

    from app.content_type import prompt_rules as content_rules

    extra = content_rules(p.get("contentType"))
    body = intent_txt + "\n".join(guards) + "\n"
    if extra:
        body += extra + "\n"
    return body


def first_hook_region(regions: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not regions:
        return None
    for a, b in regions:
        if b - a >= 0.35:
            return (a, b)
    return regions[0]


def last_cta_region(regions: list[tuple[float, float]]) -> tuple[float, float] | None:
    if not regions:
        return None
    return regions[-1]


def _covers(ranges: list[dict], start: float, end: float, *, min_overlap: float = 0.35) -> bool:
    need = max(0.2, min(min_overlap, (end - start) * 0.5))
    for r in ranges:
        try:
            a, b = float(r["start"]), float(r["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if min(b, end) - max(a, start) >= need:
            return True
    return False


def _insert_range(ranges: list[dict], start: float, end: float, beat: str, reason: str) -> list[dict]:
    """Insere um trecho e funde vizinhos — DENTRO DA MESMA FONTE.

    Os tempos de cada take sao LOCAIS do arquivo dele: o take 2 comeca em 0,0
    de novo. Ordenar e fundir a lista inteira por `start`, ignorando `source`,
    intercalava os arquivos e engolia os ranges do take curto dentro de um
    range longo do take 1.

    Medido nos projetos do usuario: **5 projetos multi-take onde uma fonte
    inteira sumiu do EDL** — tres deles o take de CTA que ele gravou e anexou
    (`cta_IMG_0098`, `cta_cta_mais_feliz`, `IMG_4048`) e dois a `Parte_2` de
    uma gravacao em duas partes. Nenhum erro, o take simplesmente nao aparece
    no video.

    A guarda so trabalha na fonte de onde vieram as `regions` (a de indice 0
    em run_fast), que e a mesma do primeiro range. As outras passam intactas,
    e a ordem relativa da lista e preservada — ela e a ordem do corte.
    """
    alvo = (ranges[0].get("source") if ranges else "SRC")
    item = {
        "source": alvo,
        "start": round(start, 3),
        "end": round(end, 3),
        "beat": beat,
        "quote": "",
        "reason": reason,
        "gain_db": 0.0,
    }

    def _e_alvo(r: dict) -> bool:
        return (r.get("source") or alvo) == alvo

    do_alvo = [r for r in ranges if _e_alvo(r)] + [item]
    do_alvo.sort(key=lambda r: float(r.get("start") or 0))
    merged: list[dict] = []
    for r in do_alvo:
        if merged and float(r["start"]) <= float(merged[-1]["end"]) + 0.08:
            merged[-1]["end"] = round(max(float(merged[-1]["end"]), float(r["end"])), 3)
            if r.get("beat") == "HOOK":
                merged[-1]["beat"] = "HOOK"
            if r.get("beat") == "CTA":
                merged[-1]["beat"] = "CTA"
        else:
            merged.append(dict(r))

    # Recompoe: o bloco da fonte alvo entra onde estava o primeiro range dela;
    # os das outras fontes ficam onde estavam.
    saida: list[dict] = []
    posto = False
    for r in ranges:
        if _e_alvo(r):
            if not posto:
                saida.extend(merged)
                posto = True
            continue
        saida.append(r)
    if not posto:
        saida.extend(merged)
    return saida


def looks_like_cta(text: str) -> bool:
    low = re.sub(r"\s+", " ", (text or "").lower())
    return any(h in low for h in CTA_HINTS)


# `\d+`, nao `\d{3}`: o escritor usa `f"{seconds:06.2f}"`, que preenche
# com zeros ate 3 digitos mas NAO trunca — a partir de 1000,00s (16min40s)
# ele emite 4. Com `{3}` a linha deixava de casar e a frase sumia da lista;
# como a lista alimenta a guarda que RESTAURA fala cortada pela IA, a
# protecao simplesmente parava de valer no resto de todo video longo.
PHRASE_RE = re.compile(r"\[(\d+\.\d{2})-(\d+\.\d{2})\]\s+S\d+\s+(.*)")
COMPLETE_ALLOWED_CLASSES = (
    "silence", "false_start", "repetition", "abandoned_take", "non_content",
)
COMPLETE_ALLOWED = (
    "silence", "silencio", "silêncio", "false_start", "falso comeco", "falso começo",
    "repetition", "repeticao", "repetição", "abandoned_take", "abandonad", "refeit",
    "non_content", "sem fala", "ruido", "ruído", "preparacao", "preparação",
)
COMPLETE_REJECTED = (
    "pace", "rhythm", "ritmo", "punchline", "retention", "retencao", "retenção",
    "boring", "encurtar", "highlight", "viral", "mais rapido", "mais rápido",
    "mais forte", "energia", "dinamico", "dinâmico",
)
_PREP_HINTS = (
    "ta gravando", "tá gravando", "espera ai", "espera aí", "perai", "peraí",
    "um dois tres", "um dois três", "testando", "mic test",
)
_FILLERS = {"ah", "eh", "uhm", "hum", "hmm", "tipo", "ne", "né", "ta", "tá", "ok", "e"}
_HUMOR_HINTS = (
    "piada", "engraçad", "risad", "hahaha", "kkkk", "punchline",
)


def load_packed_phrases(edit_dir: Path, stem: str | None = None) -> list[dict]:
    """Lê takes_packed.md (não transcripts/*.json)."""
    path = Path(edit_dir) / "takes_packed.md"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    sections: dict[str, list[dict]] = {}
    current = ""
    for line in text.splitlines():
        if line.startswith("## "):
            current = line[3:].split()[0].strip()
            sections.setdefault(current, [])
            continue
        m = PHRASE_RE.search(line)
        if not m or not current:
            continue
        sections[current].append({
            "start": float(m.group(1)),
            "end": float(m.group(2)),
            "text": m.group(3).strip(),
        })
    if stem and stem in sections and sections[stem]:
        return sections[stem]
    usable = [(k, v) for k, v in sections.items() if k.lower() not in ("cut", "base") and v]
    if not usable:
        return []
    return max(usable, key=lambda kv: kv[1][-1]["end"] - kv[1][0]["start"])[1]


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _coverage(start: float, end: float, ranges: list[dict]) -> float:
    return sum(
        _overlap(start, end, float(r.get("start") or 0), float(r.get("end") or 0))
        for r in ranges
    )


# Ao restaurar uma frase, pedacos de fala separados por MENOS que isto
# entram juntos (a pausa fica no video). Era 0,80s, e isso brigava com o
# resto do app: o corte remove pausa a partir de 0,40s (MIN_SILENCE_DROP em
# run_fast) e a ficha ACUSA pausa a partir de 0,40s (_SILENCIO_MIN_S) — ou
# seja, a restauracao devolvia silencio que o proprio corte tiraria e
# depois o app avisava o usuario sobre ele. Medido no projeto C014 (o plano
# da IA pedia dois blocos longos): com 0,80 sobravam 5 pausas somando 2,74s
# num corte de 40,7s; com 0,40 sobra ZERO e o corte cai para 38,2s, ao
# preco de 5 pontos de corte a mais (estilo dinamico ja e assim).
COLA_PAUSA_S = 0.40


def _speech_inside(
    start: float, end: float, regions: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    bits = []
    for a, b in regions or []:
        s, e = max(float(a), start), min(float(b), end)
        if e - s >= 0.12:
            bits.append((s, e))
    if not bits:
        return [(start, end)] if end - start >= 0.12 else []
    bits.sort()
    merged = [list(bits[0])]
    for a, b in bits[1:]:
        if a <= merged[-1][1] + COLA_PAUSA_S:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def _norm_txt(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", (text or "").lower())).strip()


def _class_from_blob(blob: str) -> str | None:
    low = (blob or "").lower().replace("-", "_")
    if any(k in low for k in COMPLETE_REJECTED):
        return None
    for cls in COMPLETE_ALLOWED_CLASSES:
        if cls in low:
            return cls
    if any(k in low for k in COMPLETE_ALLOWED):
        if "repet" in low:
            return "repetition"
        if "abandon" in low or "refeit" in low:
            return "abandoned_take"
        if "false" in low or "falso" in low or "recomec" in low or "recomeç" in low:
            return "false_start"
        if "silen" in low:
            return "silence"
        return "non_content"
    return None


def _near_dup(a: str, b: str, *, thresh: float = 0.86) -> bool:
    """`a` é (quase toda) repetição de `b` — DIRECIONAL de propósito.

    O `nb in na` (b contido em a) foi removido: uma frase que CONTÉM um
    refrão repetido não é ela mesma uma repetição. Caso real (24/08): "A sua
    mão que me sustenta. Você tá feliz hoje, hein?" era marcada como
    repetição porque continha a cantoria — e a fala única morria junto no
    modo Vídeo completo. Repetição removível é a frase cujo texto INTEIRO
    já existe em outro lugar.
    """
    na, nb = _norm_txt(a), _norm_txt(b)
    if not na or not nb or min(len(na), len(nb)) < 10:
        return False
    if na == nb or na in nb:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= thresh


def _dup_removivel(a: str, b: str, *, thresh: float = 0.86) -> bool:
    """Dup que PODE sair: mesma coisa dita do mesmo jeito. Um eco de diálogo
    — a pergunta que repete a afirmação do outro ("…porque tem um negócio
    dentro." → "Tem um negócio dentro?") — tem o mesmo texto mas é outra
    fala de outra pessoa, e cortá-lo deixa a resposta seguinte no vácuo
    (caso real, 25/08). Pergunta de um lado e afirmação do outro: preserva.
    """
    if not _near_dup(a, b, thresh=thresh):
        return False
    # Só a direção que importa: a frase avaliada é a PERGUNTA e o par não é.
    # Comparar os dois lados por igual descartava o refrão puro quando o par
    # era uma frase mista que por acaso terminava em "?".
    return not (a.rstrip().endswith("?")
                and not str(b or "").rstrip().endswith("?"))


def _drop_class_for(start: float, end: float, drops: list[dict] | None) -> str | None:
    span = max(0.01, end - start)
    best = None
    best_ov = 0.0
    for d in drops or []:
        try:
            a, b = float(d.get("start")), float(d.get("end"))
        except (TypeError, ValueError):
            continue
        ov = _overlap(start, end, a, b)
        if ov < 0.25 * span and ov < 0.35:
            continue
        cls = _class_from_blob(str(d.get("class") or d.get("reason") or ""))
        if ov > best_ov:
            best_ov = ov
            best = cls
    return best


def classify_complete_removal(
    phrase: dict,
    phrases: list[dict],
    *,
    drops: list[dict] | None = None,
) -> str | None:
    """Classe permitida ou None (restaurar). Sem teto de duração."""
    text = str(phrase.get("text") or "")
    low = _norm_txt(text)
    if not low:
        return "non_content"
    if any(h in low for h in _PREP_HINTS):
        return "non_content"
    words = low.split()
    if words and all(w in _FILLERS for w in words) and len(words) <= 2:
        return "non_content"
    later = [p for p in phrases if float(p["start"]) > float(phrase["end"]) - 0.05]
    earlier = [p for p in phrases if float(p["end"]) < float(phrase["start"]) + 0.05]
    if any(_dup_removivel(text, p.get("text") or "") for p in later + earlier):
        return "repetition"
    abandoned = text.rstrip().endswith(("...", "…")) or (
        len(words) <= 4 and not text.rstrip().endswith((".", "!", "?"))
    )
    if abandoned:
        head = " ".join(words[:4])
        for p in later:
            other = _norm_txt(str(p.get("text") or ""))
            if head and other.startswith(head[:12]):
                return "abandoned_take" if text.rstrip().endswith(("...", "…")) else "false_start"
    # O rótulo do modelo entra por ÚLTIMO e só com evidência na PRÓPRIA frase.
    # Antes ele vinha primeiro e valia sozinho: um único drop de 25s rotulado
    # "repetition" carimbou como repetição quatro falas únicas da piada
    # ("Vou esperar o cafezinho ali sentada, tá bom?") junto com a cantoria
    # de fato repetida — e o Vídeo completo, cujo contrato é preservar,
    # entregou 56s de um vídeo de 2:01, menos que a Edição leve (caso real,
    # 24/08). Rotular a janela inteira custa nada para o modelo; restaurar
    # é o comportamento seguro do modo.
    labeled = _drop_class_for(float(phrase["start"]), float(phrase["end"]), drops)
    if labeled == "repetition":
        # corroboração relaxada: o dup precisa existir, ainda que imperfeito
        if any(_dup_removivel(text, p.get("text") or "", thresh=0.72)
               for p in later + earlier):
            return "repetition"
        return None
    if labeled in ("false_start", "abandoned_take"):
        # só se a frase realmente parecer inacabada
        if len(words) <= 6 or not text.rstrip().endswith((".", "!", "?", "…")):
            return labeled
        return None
    # "silence"/"non_content" numa frase com palavras reais é contradição:
    # as heurísticas acima já teriam pego silêncio e muleta de verdade.
    return None


def load_complete_drops(edit_dir: Path | None) -> list[dict]:
    if not edit_dir:
        return []
    path = Path(edit_dir) / "llm_cut_plan.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    raw = data.get("drops")
    if raw is None and isinstance(data.get("raw"), str):
        try:
            parsed = json.loads(data["raw"])
            raw = parsed.get("drops") if isinstance(parsed, dict) else None
        except (json.JSONDecodeError, TypeError):
            raw = None
    return raw if isinstance(raw, list) else []


def _looks_like_humor(phrases: list[dict]) -> bool:
    texts = [str(p.get("text") or "") for p in phrases]
    blob = " ".join(texts).lower()
    if any(h in blob for h in _HUMOR_HINTS):
        return True
    if any(t.strip().endswith("?") for t in texts) and len(phrases) >= 2:
        return True
    words: list[str] = []
    for t in texts:
        words.extend(w for w in _norm_txt(t).split() if len(w) >= 5)
    if not words:
        return False
    counts: dict[str, int] = {}
    for w in words:
        counts[w] = counts.get(w, 0) + 1
    return any(c >= 3 for c in counts.values())


def assign_joke_roles(phrases: list[dict]) -> list[str]:
    roles = ["context"] * len(phrases)
    if not phrases:
        return roles
    roles[0] = "setup"
    last_words = _norm_txt(str(phrases[-1].get("text") or "")).split()
    if len(last_words) <= 8:
        roles[-1] = "punchline"
    for i, p in enumerate(phrases):
        text = str(p.get("text") or "")
        low = text.lower()
        if text.strip().endswith("?"):
            roles[i] = "question"
            if i + 1 < len(phrases) and roles[i + 1] == "context":
                roles[i + 1] = "response"
        if "pode deixar" in low or "tranquila" in low or "tranquilo" in low:
            if roles[i] in ("context", "setup"):
                roles[i] = "response" if i else "setup"
    return roles


def detect_semantic_units(
    phrases: list[dict],
    *,
    duration_s: float | None = None,
) -> list[dict]:
    """Unidades que não podem ser julgadas isoladamente (setup+payoff)."""
    if not phrases:
        return []
    short = duration_s is not None and float(duration_s) <= SHORT_DYNAMIC_SEC
    humor = _looks_like_humor(phrases)
    if short or humor:
        kind = "joke" if humor else "short_clip"
        return [{
            "semanticUnit": kind,
            "segments": list(range(len(phrases))),
            "roles": assign_joke_roles(phrases),
            "preserveTogether": True,
        }]
    units: list[dict] = []
    i = 0
    while i < len(phrases):
        text = str(phrases[i].get("text") or "")
        if text.strip().endswith("?") and i + 1 < len(phrases):
            units.append({
                "semanticUnit": "qa",
                "segments": [i, i + 1],
                "roles": ["question", "response"],
                "preserveTogether": True,
            })
            i += 2
            continue
        i += 1
    return units


def enforce_dynamic_edl(
    ranges: list[dict],
    *,
    phrases: list[dict],
    regions: list[tuple[float, float]],
    drops: list[dict] | None = None,
    duration_s: float | None = None,
) -> list[dict]:
    """Restaura fala de humor/contexto que o dynamic não pode cortar."""
    out = [dict(r) for r in (ranges or [])]
    if not phrases:
        return out
    units = detect_semantic_units(phrases, duration_s=duration_s)
    short = duration_s is not None and float(duration_s) <= SHORT_DYNAMIC_SEC
    roles_by_idx: dict[int, str] = {}
    must_keep: set[int] = set()
    for unit in units:
        if not unit.get("preserveTogether"):
            continue
        idxs = [int(x) for x in unit.get("segments") or []]
        unit_roles = unit.get("roles") or []
        for j, idx in enumerate(idxs):
            if j < len(unit_roles):
                roles_by_idx[idx] = str(unit_roles[j])
        any_kept = any(
            _coverage(float(phrases[i]["start"]), float(phrases[i]["end"]), out) >= 0.20
            for i in idxs if 0 <= i < len(phrases)
        )
        if any_kept or short:
            must_keep.update(i for i in idxs if 0 <= i < len(phrases))
    if short:
        must_keep.update(range(len(phrases)))

    for i, phrase in enumerate(phrases):
        ps, pe = float(phrase["start"]), float(phrase["end"])
        span = max(0.01, pe - ps)
        cov = _coverage(ps, pe, out)
        spoken = _speech_inside(ps, pe, regions)
        role = roles_by_idx.get(i, "context")
        need = 0.95 if (short or i in must_keep) else 0.88
        if 0.12 <= cov < need * span:
            for a, b in spoken:
                if _coverage(a, b, out) < need * (b - a):
                    out = _insert_range(out, a, b, "KEEP", f"restore-dynamic-sentence:{role}")
            continue
        if i not in must_keep:
            continue
        cls = classify_complete_removal(phrase, phrases, drops=drops)
        # Unidade de piada: repetição costuma ser callback/escalada — preservar.
        if cls in ("silence", "false_start", "abandoned_take", "non_content"):
            continue
        for a, b in spoken:
            if _coverage(a, b, out) < need * (b - a):
                reason = (
                    f"restore-dynamic-short:{role}"
                    if short
                    else f"restore-dynamic-joke:{role}"
                )
                out = _insert_range(out, a, b, "KEEP", reason)
    return out


def enforce_complete_edl(
    ranges: list[dict],
    *,
    phrases: list[dict],
    regions: list[tuple[float, float]],
    drops: list[dict] | None = None,
) -> list[dict]:
    """Restaura fala removida sem classe permitida. Só complete."""
    out = [dict(r) for r in (ranges or [])]
    if not phrases:
        return out
    for i, phrase in enumerate(phrases):
        ps, pe = float(phrase["start"]), float(phrase["end"])
        spoken = _speech_inside(ps, pe, regions)
        first = i == 0
        for a, b in spoken:
            cov = _coverage(a, b, out)
            need = 0.95 if first else 0.88
            if cov >= need * (b - a):
                continue
            if first:
                out = _insert_range(out, a, b, "HOOK", "restore-complete-first-block")
                continue
            cls = classify_complete_removal(phrase, phrases, drops=drops)
            if cls:
                continue
            out = _insert_range(out, a, b, "KEEP", "restore-complete: no allowed class")
    return out


def _load_transcript_words(edit_dir: Path | None, stem: str | None) -> list[dict]:
    if not edit_dir or not stem:
        return []
    path = Path(edit_dir) / "transcripts" / f"{stem}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return []
    out = []
    for w in data.get("words") or []:
        if w.get("type", "word") != "word":
            continue
        try:
            s, e = float(w["start"]), float(w["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if e - s < 0.05:  # timestamps zero-width são artefato do alinhador
            continue
        out.append({"start": s, "end": e, "text": str(w.get("text") or "")})
    return out


def cover_all_words(
    ranges: list[dict],
    *,
    edit_dir: Path | None,
    stem: str | None,
    phrases: list[dict],
    drops: list[dict] | None = None,
) -> list[dict]:
    """Complete: nenhuma PALAVRA fica de fora sem remoção sancionada.

    O fiscal por frases depende do takes_packed.md, e os tempos de lá
    desalinham dos tempos reais das palavras (caso real, 24/08: 4,7s de
    diálogo central fora do corte, "não vai levar." decepado no meio, "Tem
    lá." reduzido a 0,3s). A régua final é a transcrição palavra a palavra:
    o que não estiver coberto volta, a menos que caia dentro de uma frase
    cuja remoção o fiscal classificou (repetição/recomeço/muleta) — a
    cantoria repetida continua fora, mas fala única nunca.
    """
    words = _load_transcript_words(edit_dir, stem)
    if not words:
        return ranges
    sancionadas: list[tuple[float, float]] = []
    # phrases[1:]: o GANCHO nunca é remoção sancionada. A primeira frase pode
    # ser quase-dup de uma fala posterior (a piada volta ao bordão) e virava
    # "repetição" — o vídeo abria com o "Oi," decepado (caso real, 25/08).
    for p in phrases[1:]:
        if classify_complete_removal(p, phrases, drops=drops):
            sancionadas.append((float(p["start"]), float(p["end"])))
    if not phrases:
        # sem takes_packed só sobra o rótulo do modelo — melhor que restaurar
        # a cantoria inteira, pior que a corroboração por frase
        for d in drops or []:
            if _class_from_blob(str(d.get("class") or d.get("reason") or "")):
                try:
                    sancionadas.append((float(d["start"]), float(d["end"])))
                except (KeyError, TypeError, ValueError):
                    continue
    out = [dict(r) for r in (ranges or [])]
    for w in words:
        dur = w["end"] - w["start"]
        if _coverage(w["start"], w["end"], out) >= 0.6 * dur:
            continue
        if sum(_overlap(w["start"], w["end"], a, b)
               for a, b in sancionadas) >= 0.5 * dur:
            continue
        # folga assimétrica: fim de palavra carrega a cauda da consoante
        out = _insert_range(out, max(0.0, w["start"] - 0.05), w["end"] + 0.15,
                            "KEEP", "restore-complete-word")
    return out


def guard_ranges(
    ranges: list[dict],
    *,
    preset: dict | None,
    regions: list[tuple[float, float]],
    duration_s: float | None = None,
    edit_dir: Path | None = None,
    source_stem: str | None = None,
    drops: list[dict] | None = None,
) -> list[dict]:
    """Garante gancho, CTA e trechos protegidos no EDL. Não mexe em render."""
    p = preset or {}
    mode = str(p.get("editingIntent") or "dynamic").lower()
    if mode not in INTENTS:
        mode = "dynamic"
    out = [dict(r) for r in (ranges or [])]
    if mode == "intact":
        # Sem cortes: o EDL ja e o video inteiro, nao ha o que guardar.
        return out
    if not out and not regions:
        return out

    if mode == "complete":
        phrases = load_packed_phrases(edit_dir, source_stem) if edit_dir else []
        drop_list = list(drops or []) or load_complete_drops(edit_dir)
        if phrases:
            first = phrases[0]
            if bool(p.get("preserveHook", True)):
                for a, b in _speech_inside(first["start"], first["end"], regions):
                    if _coverage(a, b, out) < 0.95 * (b - a):
                        out = _insert_range(out, a, b, "HOOK", "preserve-hook-complete")
            out = enforce_complete_edl(out, phrases=phrases, regions=regions, drops=drop_list)
        if edit_dir:
            out = cover_all_words(out, edit_dir=edit_dir, stem=source_stem,
                                  phrases=phrases, drops=drop_list)
        if not phrases and bool(p.get("preserveHook", True)):
            hook = first_hook_region(regions)
            if hook and not _covers(out, hook[0], hook[1]):
                out = _insert_range(out, hook[0], hook[1], "HOOK", "preserve-hook")
    elif bool(p.get("preserveHook", DEFAULTS[mode]["preserveHook"])):
        hook = first_hook_region(regions)
        if hook and not _covers(out, hook[0], hook[1]):
            out = _insert_range(out, hook[0], hook[1], "HOOK", "preserve-hook")

    if mode == "dynamic":
        phrases = load_packed_phrases(edit_dir, source_stem) if edit_dir else []
        drop_list = list(drops or []) or load_complete_drops(edit_dir)
        dur = duration_s if duration_s is not None else p.get("sourceDurationSec")
        try:
            dur_f = float(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur_f = None
        if phrases:
            out = enforce_dynamic_edl(
                out,
                phrases=phrases,
                regions=regions,
                drops=drop_list,
                duration_s=dur_f,
            )
        elif dur_f is not None and dur_f <= SHORT_DYNAMIC_SEC:
            for a, b in regions or []:
                if b - a < 0.20:
                    continue
                if _coverage(a, b, out) < 0.88 * (b - a):
                    out = _insert_range(out, a, b, "KEEP", "restore-dynamic-short")

    if bool(p.get("preserveCTA", DEFAULTS[mode]["preserveCTA"])):
        cta = last_cta_region(regions)
        if cta:
            # `regions` e `duration_s` sao da fonte de indice 0 (run_fast so
            # guarda os do primeiro arquivo). Esticar o ULTIMO range da lista
            # com um instante desse relogio so faz sentido se ele for dessa
            # mesma fonte — senao pede um trecho que nao existe: medido num
            # projeto real, `cta_IMG_0098 0.41-0.90` virava `0.41-84.2`, ou
            # seja, 84s de um arquivo de 7s.
            alvo = (out[0].get("source") if out else None)
            ultimo = out[-1] if out else None
            mesma_fonte = (ultimo is not None
                           and (ultimo.get("source") or alvo) == alvo)
            fim = round(cta[1], 3)
            if duration_s:
                fim = min(fim, round(float(duration_s), 3))
            if ultimo is not None and mesma_fonte:
                if float(ultimo.get("end") or 0) < fim - 0.15:
                    ultimo["end"] = fim
                    ultimo["beat"] = "CTA"
                    ultimo["reason"] = (str(ultimo.get("reason") or "")
                                        + " · preserve-cta").strip(" ·")
            elif ultimo is not None:
                # O corte ja termina noutro take (tipicamente o CTA gravado a
                # parte). Ele E o CTA — nao ha o que esticar.
                pass
            else:
                out = _insert_range(out, cta[0], min(cta[1], fim), "CTA", "preserve-cta")

    for pr in p.get("protectedRanges") or []:
        try:
            a, b = float(pr["start"]), float(pr["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if b <= a:
            continue
        if duration_s:
            b = min(b, float(duration_s))
        if not _covers(out, a, b, min_overlap=0.2):
            out = _insert_range(out, a, b, "KEEP", "protected-range")

    return tirar_pausa_morta(out, regions, mode)


def tirar_pausa_morta(
    ranges: list[dict],
    regions: list[tuple[float, float]],
    mode: str,
) -> list[dict]:
    """Divide qualquer trecho na pausa morta que sobrou dentro dele.

    A 3.32 acertou a RESTAURACAO de frase (ela colava pausa de ate 0,80s),
    mas sobrava um segundo caminho: o trecho que a IA pediu e que passa
    inteiro pelo `_normalize_ranges` nunca era dividido — e as pausas de
    dentro dele ficavam no video. Medido em 6 projetos reais depois da
    3.32: sobravam 2,14s em dois deles (pausas de 0,40 a 0,45s), e a ficha
    seguia avisando sobre elas.

    A regra vale para QUEM QUER QUE tenha feito o trecho, e por isso mora
    no fim da guarda: em modo que corta, silencio de 0,40s ou mais nao
    sobrevive. Nenhuma palavra e perdida — o corte cai no silencio, entre
    as falas, e as bordas do trecho original ficam de pe (o lead/trail que
    protege a primeira e a ultima silaba).

    `intact` (Sem cortes) sai fora: la o video inteiro e o produto.
    """
    if mode == "intact" or not regions or not ranges:
        return ranges
    out: list[dict] = []
    for rg in ranges:
        try:
            a0, b0 = float(rg["start"]), float(rg["end"])
        except (KeyError, TypeError, ValueError):
            out.append(rg)
            continue
        falas = [(max(x, a0), min(y, b0)) for x, y in regions
                 if min(y, b0) - max(x, a0) > 0.05]
        if len(falas) < 2:
            out.append(rg)
            continue
        pedacos: list[list[float]] = [[falas[0][0], falas[0][1]]]
        for ini, fim in falas[1:]:
            if ini - pedacos[-1][1] >= COLA_PAUSA_S:
                pedacos.append([ini, fim])
            else:
                pedacos[-1][1] = fim
        if len(pedacos) < 2:
            out.append(rg)
            continue
        # as pontas do trecho original ficam: elas ja carregam a folga que
        # protege a primeira e a ultima silaba
        pedacos[0][0], pedacos[-1][1] = a0, b0
        for i, (ini, fim) in enumerate(pedacos):
            if fim - ini < 0.20:
                continue
            novo = dict(rg, start=round(ini, 3), end=round(fim, 3))
            if i:
                novo["reason"] = (str(rg.get("reason") or "")
                                  + " · sem-pausa-morta").strip(" ·")[:200]
            out.append(novo)
    return out
