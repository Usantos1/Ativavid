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
    # As palavras das CUES usam `fromMs`/`toMs` — nomes proprios delas. Sem
    # este ramo elas mediam (0,0) e o filtro de tempo do
    # `resolve_replacement_index` derrubava TODO candidato: a correcao nunca
    # entrava na cue, calada. Nao aparecia no video porque o pipeline
    # regenera as cues a partir do captions.json corrigido — mas o PREVIEW
    # desenha a partir das cues, entao a correcao so aparecia depois de
    # refazer o video.
    if item.get("fromMs") is not None or item.get("toMs") is not None:
        return float(item.get("fromMs") or 0) / 1000.0, float(item.get("toMs") or 0) / 1000.0
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
        # `delete` e o pedido de APAGAR a legenda, nao de troca-la por vazio.
        # Sem uma marca explicita nao daria para distinguir "apague isto" de
        # "o campo veio vazio por engano" — e trocar por vazio calado e
        # exatamente o tipo de coisa que apaga trabalho sem querer.
        apagar = bool(fix.get("delete"))
        if not src or (not dst and not apagar):
            continue
        src_toks = _split_tokens(src)
        dst_toks = [] if apagar else _split_tokens(dst)
        if not src_toks or (not dst_toks and not apagar):
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
    if not dst_toks:
        # APAGAR. Em captions.json as palavras saem da lista; nas cues elas
        # ficam com texto vazio e o `_prune_empty_cue_words` as remove depois
        # — os nos das cues carregam layout que nao da para recortar aqui.
        if splice:
            del words[i : i + len(src_toks)]
            return 1
        n = 0
        for w in window:
            if str(w.get("text") or "").strip():
                w["text"] = ""
                n += 1
        return n
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


def _e_lista_de_palavras(v: Any) -> bool:
    return isinstance(v, list) and bool(v) and isinstance(v[0], dict) and "text" in v[0]


def _drop_cues_vazias(cues: Any) -> Any:
    """Tira a cue que ficou sem NENHUMA linha.

    Apagar todas as palavras de uma cue deixava a cue no arquivo, vazia. O
    motor levanta nela (`_tempos_cue` faz `max()` sobre as palavras e a
    sequencia esta vazia), entao isto nao e arrumacao: e o que separa o
    apagar de quebrar o render. O campo `i` da cue e rotulo, nao indice do
    array — nada no motor procura cue por `i`.
    """
    if isinstance(cues, list):
        return [c for c in cues
                if not isinstance(c, dict) or any(c.get("lines") or [])]
    if isinstance(cues, dict) and isinstance(cues.get("cues"), list):
        cues["cues"] = _drop_cues_vazias(cues["cues"])
    return cues


# Arranjos que andam LADO A LADO com `lines` numa cue: o motor le
# `lineStyles[li]`, `lineEmph[li]` e `lineBoost[li]` pelo INDICE da linha
# (render_proprio.py:822-833). Tirar uma linha sem tirar a entrada
# correspondente desloca o estilo de todas as linhas de baixo — a legenda
# continua aparecendo, com o desenho errado, e nada acusa.
_ARRANJOS_DA_LINHA = ("lineStyles", "lineBoost", "lineEmph")


def _podar_cue(cue: dict) -> None:
    """Tira palavra vazia e linha vazia de UMA cue, sem desalinhar o estilo."""
    linhas = cue.get("lines")
    if not isinstance(linhas, list):
        return
    mantidas: list[int] = []
    novas: list[Any] = []
    for li, linha in enumerate(linhas):
        if _e_lista_de_palavras(linha):
            linha = [x for x in linha if str(x.get("text") or "").strip()]
            if not linha:
                continue
        elif isinstance(linha, list) and not linha:
            continue
        mantidas.append(li)
        novas.append(linha)
    if len(novas) == len(linhas):
        cue["lines"] = novas
        return
    cue["lines"] = novas
    for chave in _ARRANJOS_DA_LINHA:
        arr = cue.get(chave)
        if isinstance(arr, list):
            cue[chave] = [arr[i] for i in mantidas if i < len(arr)]


def _e_cue(node: Any) -> bool:
    return (isinstance(node, dict) and isinstance(node.get("lines"), list)
            and ("startMs" in node or "endMs" in node))


def _prune_empty_cue_words(node: Any) -> None:
    if _e_cue(node):
        _podar_cue(node)
        return
    if isinstance(node, dict):
        for v in node.values():
            _prune_empty_cue_words(v)
        for key, v in list(node.items()):
            if _e_lista_de_palavras(v):
                node[key] = [x for x in v if str(x.get("text") or "").strip()]
            elif isinstance(v, list) and v and isinstance(v[0], list):
                # lista de LINHAS fora de uma cue: poda as palavras e as linhas
                # vazias, sem arranjo paralelo para acertar
                linhas = []
                for linha in v:
                    if _e_lista_de_palavras(linha):
                        linha = [x for x in linha if str(x.get("text") or "").strip()]
                        if not linha:
                            continue
                    linhas.append(linha)
                node[key] = linhas
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

    # Quem ja foi apagado ANTES. Para um apagar, "a palavra sumiu" nao prova
    # que fui eu: um alvo que nunca existiu tambem esta ausente, e ai dizer
    # "ja aplicado" e o mesmo silencio que este commit veio tirar. O que
    # distingue e o registro: se este apagar ja esta no caption_fixes.json, a
    # ausencia e obra dele.
    ja_apagados = {str(f.get("from") or "") for f in _fixes_guardados(edit)
                   if f.get("delete")}
    ja_estava = _destino_ja_no_lugar(
        words if caps_p.exists() else None, fixes, ja_apagados=ja_apagados)
    applied += patch_edit_data_text(edit, fixes)

    if cues_p.exists():
        cues = json.loads(cues_p.read_text(encoding="utf-8-sig"))
        nodes: list[dict] = []
        _collect_text_nodes(cues, nodes)
        applied += apply_replacements_to_words(nodes, fixes, splice=False)
        _prune_empty_cue_words(cues)
        cues = _drop_cues_vazias(cues)
        cues_p.write_text(json.dumps(cues, ensure_ascii=False) + "\n", encoding="utf-8")

    packed = edit / "takes_packed.md"
    if packed.exists():
        txt = packed.read_text(encoding="utf-8-sig")
        nxt = apply_replacements_to_text(txt, fixes)
        if nxt != txt:
            packed.write_text(nxt, encoding="utf-8")

    # A LEGENDA DO POST tambem. Ela cita a fala ("marca ai, chefe..."), entao a
    # palavra errada que o usuario corrigiu na tela pode estar la — e e esse
    # texto que ele copia para o Instagram pelo botao do card. Ficava congelada
    # com o erro; correcoes reais dele ("Prime Camps" -> "@lojaprimecamp")
    # eram exatamente desse tipo. O pack em publicar/ se atualiza sozinho no
    # proximo sync (copy-if-newer).
    for leg_p in (edit / "legenda.txt", edit / "post" / "legenda.txt"):
        if leg_p.is_file():
            try:
                txt = leg_p.read_text(encoding="utf-8-sig")
                nxt = apply_replacements_to_text(txt, fixes)
                if nxt != txt:
                    leg_p.write_text(nxt, encoding="utf-8")
            except OSError:
                pass

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
            guardado = {"from": fix["from"], "to": fix.get("to") or ""}
            # Os TEMPOS vao junto. Sem eles o fix guardado so da para localizar
            # por texto, e uma palavra que aparece duas vezes no video vira
            # "ambiguo" — foi por isso que, dos 35 projetos com correcao, 15
            # nao conseguiram ser localizados para a emenda parcial. Sao 4
            # numeros por correcao; o arquivo nao sente.
            for chave in ("startMs", "endMs", "renderedStart", "renderedEnd"):
                if fix.get(chave) is not None:
                    guardado[chave] = fix[chave]
            # A marca `delete` TEM de ser guardada. Sem ela o reprocesso relia
            # um fix com `to` vazio, que o proprio apply ignora — e a legenda
            # apagada voltava ao video. Apagar que volta sozinho e pior do que
            # apagar que nao funciona: o usuario ja conferiu e seguiu.
            if fix.get("delete"):
                guardado["delete"] = True
            merged.append(guardado)
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
    apagar = any(isinstance(f, dict) and f.get("delete") for f in fixes)
    return {
        "ok": False,
        "changed": 0,
        "notFound": True,
        "error": ("não achei essa legenda para apagar" if apagar
                  else "não achei esse texto na legenda para corrigir"),
    }


def _fixes_guardados(edit_dir: Path) -> list[dict]:
    p = Path(edit_dir) / "caption_fixes.json"
    if not p.exists():
        return []
    try:
        d = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return [x for x in d if isinstance(x, dict)]


def _destino_ja_no_lugar(
    words: list[dict] | None, fixes: list[dict],
    *, ja_apagados: set[str] | None = None,
) -> bool:
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
        if fix.get("delete"):
            alvo = str(fix.get("from") or "")
            if alvo not in (ja_apagados or set()):
                return False       # nunca apaguei isto: sumido = nao achei
            src = _split_tokens(alvo)
            if src and resolve_replacement_index(words, src, fix)[0] != "none":
                return False       # continua la: o apagar nao pegou
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
    # `x.get("to")` sozinho descartava todo APAGAR, que por definicao tem
    # destino vazio — era o segundo jeito de a legenda apagada voltar.
    return [x for x in data if isinstance(x, dict) and x.get("from")
            and (x.get("to") or x.get("delete"))]


# Emoji e pictogramas fora do texto de TELA. As fontes de marca (Sora,
# Integral, a que o usuario instalar) nao tem esses glifos: a headline
# "Foi Traído 2 Vezes" saiu com duas caixas no video dele (31/08). Os
# dois motores desenham o que esta em hook.lines — limpar o DADO cobre
# os dois; limpar so um desenhista deixaria o outro divergir.
# Nao entra no texto do post (legenda.txt): la emoji funciona e e bem-vindo.
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"   # emoji, simbolos, bandeiras
    "☀-➿"           # miscelanea + dingbats (☀✂✅…)
    "⬀-⯿"           # setas/estrelas (⭐…)
    "‍︎️⃣"  # emendas e seletores de variacao
    "]+"
)


def sem_emoji(text: str) -> str:
    """Tira emoji e recolhe os espacos que sobram no lugar."""
    limpo = _EMOJI_RE.sub("", str(text or ""))
    limpo = re.sub(r"[ \t]{2,}", " ", limpo)
    # "confere ✅!" nao pode virar "confere !"
    return re.sub(r" ([!?.,;:])", r"\1", limpo).strip()
