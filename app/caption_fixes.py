"""Aplica correção de texto na legenda. Não remuxa nem renderiza."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


def _fold(s: str) -> str:
    raw = unicodedata.normalize("NFD", s or "")
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    return re.sub(r"[^\w]+", "", raw, flags=re.UNICODE).lower()


def _punct_suffix(s: str) -> str:
    m = re.search(r"([.,!?…:;]+)$", s or "")
    return m.group(1) if m else ""


def tokens_match(word: str, needle: str) -> bool:
    """Igualdade de palavra. Ignora maiúscula e pontuação final. Sem prefixo."""
    a, b = _fold(word), _fold(needle)
    return bool(a) and a == b


def _split_tokens(text: str) -> list[str]:
    return [t for t in re.split(r"\s+", str(text or "").strip()) if t]


def _item_span_s(item: dict) -> tuple[float, float]:
    if item.get("startMs") is not None or item.get("endMs") is not None:
        return float(item.get("startMs") or 0) / 1000.0, float(item.get("endMs") or 0) / 1000.0
    return float(item.get("start") or 0), float(item.get("end") or 0)


def _item_ids(item: dict) -> set[str]:
    out: set[str] = set()
    for key in ("id", "tokenId", "cueId", "wordId"):
        raw = item.get(key)
        if raw is not None and str(raw).strip() != "":
            out.add(str(raw))
    return out


def locate_replacement_windows(words: list[dict], src_toks: list[str]) -> list[int]:
    """Índices iniciais de janelas com match exato de cada token."""
    hits: list[int] = []
    n = len(src_toks)
    if n < 1 or not isinstance(words, list):
        return hits
    for i in range(0, len(words) - n + 1):
        window = words[i : i + n]
        if len(window) != n:
            continue
        if all(
            isinstance(window[k], dict)
            and window[k].get("text") is not None
            and tokens_match(str(window[k].get("text") or ""), src_toks[k])
            for k in range(n)
        ):
            hits.append(i)
    return hits


def _fix_time_range_s(fix: dict) -> tuple[float, float] | None:
    if fix.get("startMs") is not None or fix.get("endMs") is not None:
        a = float(fix.get("startMs") or 0) / 1000.0
        b = float(fix.get("endMs") or 0) / 1000.0
        return (a, b) if b > a else None
    for a_key, b_key in (("start", "end"), ("renderedStart", "renderedEnd")):
        if fix.get(a_key) is None and fix.get(b_key) is None:
            continue
        a = float(fix.get(a_key) or 0)
        b = float(fix.get(b_key) or 0)
        if b > a:
            return a, b
    return None


def resolve_replacement_index(
    words: list[dict], src_toks: list[str], fix: dict | None = None
) -> tuple[str, list[int]]:
    """Escolhe a janela. ('ok', [i]) | ('none', []) | ('ambiguous', [...]).

    Ordem: tokenId/cueId → índice → intervalo temporal → match exato único.
    Várias ocorrências sem alvo → ambíguo, não chuta.
    Cue clicado (id único) não passa pelo matcher textual.
    """
    fix = fix if isinstance(fix, dict) else {}
    n = len(src_toks)
    target_id = None
    for key in ("tokenId", "cueId", "id", "wordId"):
        if fix.get(key) is not None and str(fix.get(key)).strip() != "":
            target_id = str(fix.get(key))
            break
    if target_id is not None:
        id_hits = [
            i
            for i, w in enumerate(words)
            if isinstance(w, dict) and target_id in _item_ids(w)
        ]
        if len(id_hits) == 1:
            start = id_hits[0]
            if start + max(1, n) <= len(words):
                return "ok", [start]
            return "ok", id_hits

    hits = locate_replacement_windows(words, src_toks)
    if target_id is not None:
        hits = [
            i
            for i in hits
            if any(target_id in _item_ids(words[i + k]) for k in range(n) if isinstance(words[i + k], dict))
        ]

    if fix.get("index") is not None:
        try:
            idx = int(fix["index"])
        except (TypeError, ValueError):
            idx = None
        if idx is not None:
            hits = [i for i in hits if i == idx]

    span = _fix_time_range_s(fix)
    if span is not None:
        t0, t1 = span
        timed: list[int] = []
        for i in hits:
            ws, we = _item_span_s(words[i])
            we2 = _item_span_s(words[i + n - 1])[1]
            if ws < t1 and we2 > t0:
                timed.append(i)
        hits = timed

    if len(hits) == 1:
        return "ok", hits
    if len(hits) == 0:
        return "none", []
    return "ambiguous", hits


def _replace_word(word: str, new: str) -> str:
    suf = _punct_suffix(word)
    core = new.rstrip(".,!?…:;")
    return core + (suf if not _punct_suffix(new) else "")


def apply_replacements_to_words(
    words: list[dict],
    fixes: list[dict],
    *,
    splice: bool = True,
    all_occurrences: bool = False,
) -> int:
    """Troca o texto. Se o número de tokens muda, redistribui o intervalo do cue.

    O início/fim globais do trecho original se mantêm. Sem Whisper.
    splice=True (captions.json): a lista ganha/perde palavras.
    splice=False (cues aninhados): só altera o texto dos nós existentes.
    Sem alvo e com 2+ ocorrências: não altera (ambíguo), salvo all_occurrences.
    """
    return int(replace_caption_tokens(words, fixes, splice=splice, all_occurrences=all_occurrences)["changed"])


def replace_caption_tokens(
    words: list[dict],
    fixes: list[dict],
    *,
    splice: bool = True,
    all_occurrences: bool = False,
) -> dict[str, Any]:
    changed = 0
    ambiguous = False
    match_count = 0
    if not isinstance(words, list):
        return {"changed": 0, "ambiguous": False, "matches": 0}
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        src = str(fix.get("from") or "").strip()
        dst = str(fix.get("to") or "").strip()
        if not src or not dst:
            continue
        src_toks = _split_tokens(src)
        dst_toks = _split_tokens(dst)
        if not src_toks or not dst_toks:
            continue
        status, hits = resolve_replacement_index(words, src_toks, fix)
        if status == "none":
            continue
        if status == "ambiguous" and not all_occurrences:
            ambiguous = True
            match_count += len(hits)
            continue
        if status == "ok" or all_occurrences:
            match_count += len(hits)
            for i in sorted(hits, reverse=True):
                changed += _apply_window(words, i, src_toks, dst_toks, splice=splice)
    return {"changed": changed, "ambiguous": ambiguous, "matches": match_count}


def _apply_window(
    words: list[dict],
    i: int,
    src_toks: list[str],
    dst_toks: list[str],
    *,
    splice: bool,
) -> int:
    window = words[i : i + len(src_toks)]
    if len(window) != len(src_toks):
        return 0
    t0 = float(window[0].get("startMs") if window[0].get("startMs") is not None else window[0].get("start") or 0)
    t1 = float(window[-1].get("endMs") if window[-1].get("endMs") is not None else window[-1].get("end") or 0)
    use_ms = window[0].get("startMs") is not None or window[0].get("endMs") is not None
    if len(dst_toks) == len(src_toks):
        new_words = []
        for k, tok in enumerate(dst_toks):
            w = dict(window[k])
            w["text"] = _replace_word(str(window[k].get("text") or ""), tok)
            new_words.append(w)
    else:
        new_words = _redistribute_tokens(window[0], dst_toks, t0, t1, use_ms)
    if splice:
        words[i : i + len(src_toks)] = new_words
        return 1
    changed = 0
    if len(dst_toks) == len(src_toks):
        for k, tok in enumerate(dst_toks):
            nxt = _replace_word(str(window[k].get("text") or ""), tok)
            if window[k].get("text") != nxt:
                window[k]["text"] = nxt
                changed += 1
    else:
        joined = " ".join(dst_toks)
        if window[0].get("text") != joined:
            window[0]["text"] = joined
            changed += 1
        for extra in window[1:]:
            if extra.get("text"):
                extra["text"] = ""
                changed += 1
    return changed


def _redistribute_tokens(
    template: dict, dst_toks: list[str], t0: float, t1: float, use_ms: bool
) -> list[dict]:
    """Parte o intervalo [t0, t1] em N tokens iguais. O span global não muda."""
    n = max(1, len(dst_toks))
    span = max(0.0, t1 - t0)
    out: list[dict] = []
    for i, tok in enumerate(dst_toks):
        a = t0 + span * i / n
        b = t1 if i == n - 1 else t0 + span * (i + 1) / n
        w = dict(template)
        w["text"] = tok
        if use_ms:
            w["startMs"] = int(round(a))
            w["endMs"] = int(round(b))
        else:
            w["start"] = round(a, 3)
            w["end"] = round(b, 3)
        out.append(w)
    if out:
        if use_ms:
            out[0]["startMs"] = int(round(t0))
            out[-1]["endMs"] = int(round(t1))
        else:
            out[0]["start"] = round(t0, 3)
            out[-1]["end"] = round(t1, 3)
    return out


def _collect_text_nodes(node: Any, out: list[dict]) -> None:
    if isinstance(node, dict):
        if isinstance(node.get("text"), str):
            out.append(node)
        for v in node.values():
            _collect_text_nodes(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_text_nodes(v, out)


# Whisper ouve "cursinho/curseto" no CTA falado "ficar 1% mais feliz".
# Não troca "cursinho" solto (ex.: "você fez um cursinho?").
_CTA_ASR_GARBAGE = re.compile(
    r"(?i)\b(?:um\s+)?(?:cursinho|curseto|pisceta)\b(?=\s+mais\b)"
)


def normalize_cta_asr(text: str) -> str:
    """Corrige o CTA '1% mais feliz' sem mexer em 'cursinho' de verdade."""
    if not text:
        return text or ""
    return _CTA_ASR_GARBAGE.sub("1%", text)


def apply_replacements_to_text(text: str, fixes: list[dict] | None = None) -> str:
    out = normalize_cta_asr(str(text or ""))
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        src = str(fix.get("from") or "").strip()
        dst = str(fix.get("to") or "").strip()
        if not src or not dst:
            continue
        pattern = r"(?<!\w)" + re.escape(src) + r"(?!\w)"
        out = re.sub(pattern, dst, out, flags=re.I)
    return out


def patch_edit_data_text(edit_dir: Path, fixes: list[dict] | None = None) -> int:
    """Atualiza gancho/headline no edit-data. Sem render."""
    path = Path(edit_dir) / "remotion" / "public" / "edit-data.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return 0
    if not isinstance(data, dict):
        return 0
    changed = 0
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    lines = hook.get("lines")
    if isinstance(lines, list):
        nxt = [apply_replacements_to_text(str(x), fixes) for x in lines]
        if nxt != [str(x) for x in lines]:
            hook["lines"] = nxt
            data["hook"] = hook
            changed += 1
    for key in ("aiHeadline",):
        cur = data.get(key)
        if isinstance(cur, str) and cur:
            nxt = apply_replacements_to_text(cur, fixes)
            if nxt != cur:
                data[key] = nxt
                changed += 1
    if changed:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def _prune_empty_cue_words(node: Any) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _prune_empty_cue_words(v)
        for key, v in list(node.items()):
            if isinstance(v, list) and v and isinstance(v[0], dict) and "text" in v[0]:
                node[key] = [x for x in v if str(x.get("text") or "").strip()]
    elif isinstance(node, list):
        for v in node:
            _prune_empty_cue_words(v)


def apply_caption_fixes(edit_dir: Path, fixes: list[dict] | None) -> dict:
    """Atualiza legendas e o gancho na tela. Sem FFmpeg."""
    edit = Path(edit_dir)
    public = edit / "remotion" / "public"
    caps_p = public / "captions.json"
    cues_p = public / "caption-cues.json"
    if not fixes:
        return {"ok": True, "changed": patch_edit_data_text(edit, fixes)}

    applied = 0
    if caps_p.exists():
        words = json.loads(caps_p.read_text(encoding="utf-8-sig"))
        if isinstance(words, list):
            result = replace_caption_tokens(words, fixes)
            if result.get("ambiguous") and not result.get("changed"):
                return {
                    "ok": False,
                    "changed": 0,
                    "ambiguous": True,
                    "matches": int(result.get("matches") or 0),
                    "error": "Essa palavra aparece mais de uma vez. Clique na legenda certa no vídeo.",
                }
            applied += int(result.get("changed") or 0)
            words = [w for w in words if isinstance(w, dict) and str(w.get("text") or "").strip()]
            caps_p.write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ja_estava = _destino_ja_no_lugar(words if caps_p.exists() else None, fixes)
    applied += patch_edit_data_text(edit, fixes)

    if cues_p.exists():
        cues = json.loads(cues_p.read_text(encoding="utf-8-sig"))
        nodes: list[dict] = []
        _collect_text_nodes(cues, nodes)
        applied += apply_replacements_to_words(nodes, fixes, splice=False)
        _prune_empty_cue_words(cues)
        cues_p.write_text(json.dumps(cues, ensure_ascii=False) + "\n", encoding="utf-8")

    packed = edit / "takes_packed.md"
    if packed.exists():
        txt = packed.read_text(encoding="utf-8-sig")
        nxt = apply_replacements_to_text(txt, fixes)
        if nxt != txt:
            packed.write_text(nxt, encoding="utf-8")

    store = edit / "caption_fixes.json"
    try:
        prev = []
        if store.exists():
            prev = json.loads(store.read_text(encoding="utf-8-sig"))
            if not isinstance(prev, list):
                prev = []
        merged = list(prev)
        for fix in fixes:
            if not isinstance(fix, dict) or not fix.get("from"):
                continue
            merged = [x for x in merged if str(x.get("from") or "") != str(fix.get("from"))]
            merged.append({"from": fix["from"], "to": fix.get("to") or ""})
        store.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    if applied:
        return {"ok": True, "changed": applied}
    # Nada mudou. Isso tem DOIS significados opostos e tratar os dois igual foi
    # o defeito: no app o mesmo fix passa por aqui DUAS vezes (uma no clique,
    # via /api/corrections, e outra ao salvar), entao "0 trocas" e o caso
    # normal — o texto ja esta no lugar. Mas se o destino tambem nao esta la, a
    # correcao simplesmente NAO pegou, e dizer "ok" faz a tela apagar o pedido
    # do usuario e cantar "Legenda corrigida" com a palavra errada na tela.
    if ja_estava:
        return {"ok": True, "changed": 0, "alreadyApplied": True}
    return {
        "ok": False,
        "changed": 0,
        "notFound": True,
        "error": "não achei esse texto na legenda para corrigir",
    }


def _destino_ja_no_lugar(words: list[dict] | None, fixes: list[dict]) -> bool:
    """True se o texto de DESTINO de todo fix ja esta nas palavras.

    E o que separa "ja foi aplicado antes" de "nao pegou". Usa o mesmo
    localizador do apply, com a mesma janela de tempo do fix, para nao
    confundir com outra ocorrencia da mesma palavra noutro ponto do video.
    """
    if not isinstance(words, list) or not words:
        return False
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        dst = _split_tokens(str(fix.get("to") or ""))
        if not dst:
            continue
        status, _ = resolve_replacement_index(words, dst, fix)
        if status == "none":
            return False
    return True


def load_stored_fixes(edit_dir: Path) -> list[dict]:
    path = Path(edit_dir) / "caption_fixes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("from") and x.get("to")]
