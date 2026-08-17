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
    a, b = _fold(word), _fold(needle)
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _replace_word(word: str, new: str) -> str:
    suf = _punct_suffix(word)
    core = new.rstrip(".,!?…:;")
    return core + (suf if not _punct_suffix(new) else "")


def apply_replacements_to_words(words: list[dict], fixes: list[dict]) -> int:
    """Troca o texto; preserva startMs/endMs. Devolve quantas palavras mudaram."""
    changed = 0
    items = [w for w in words if isinstance(w, dict) and w.get("text") is not None]
    for fix in fixes or []:
        if not isinstance(fix, dict):
            continue
        src = str(fix.get("from") or "").strip()
        dst = str(fix.get("to") or "").strip()
        if not src or not dst:
            continue
        src_toks = [t for t in re.split(r"\s+", src) if t]
        dst_toks = [t for t in re.split(r"\s+", dst) if t]
        if not src_toks:
            continue
        i = 0
        while i < len(items):
            window = items[i : i + len(src_toks)]
            if len(window) == len(src_toks) and all(
                tokens_match(window[k]["text"], src_toks[k]) for k in range(len(src_toks))
            ):
                if len(dst_toks) == 1:
                    new = _replace_word(window[0]["text"], dst_toks[0])
                    if window[0]["text"] != new:
                        window[0]["text"] = new
                        changed += 1
                    for extra in window[1:]:
                        if extra["text"]:
                            extra["text"] = ""
                            changed += 1
                elif len(dst_toks) == len(src_toks):
                    for k, tok in enumerate(dst_toks):
                        new = _replace_word(window[k]["text"], tok)
                        if window[k]["text"] != new:
                            window[k]["text"] = new
                            changed += 1
                else:
                    new = _replace_word(window[0]["text"], " ".join(dst_toks))
                    if window[0]["text"] != new:
                        window[0]["text"] = new
                        changed += 1
                    for extra in window[1:]:
                        if extra["text"]:
                            extra["text"] = ""
                            changed += 1
                i += len(src_toks)
                continue
            i += 1
    return changed


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
        out = re.sub(re.escape(src), dst, out, flags=re.I)
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
    applied = patch_edit_data_text(edit, fixes)
    if not fixes:
        return {"ok": True, "changed": applied}

    if caps_p.exists():
        words = json.loads(caps_p.read_text(encoding="utf-8-sig"))
        if isinstance(words, list):
            applied += apply_replacements_to_words(words, fixes)
            words = [w for w in words if isinstance(w, dict) and str(w.get("text") or "").strip()]
            caps_p.write_text(json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if cues_p.exists():
        cues = json.loads(cues_p.read_text(encoding="utf-8-sig"))
        nodes: list[dict] = []
        _collect_text_nodes(cues, nodes)
        applied += apply_replacements_to_words(nodes, fixes)
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
    return {"ok": True, "changed": applied}


def load_stored_fixes(edit_dir: Path) -> list[dict]:
    path = Path(edit_dir) / "caption_fixes.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [x for x in data if isinstance(x, dict) and x.get("from") and x.get("to")]
