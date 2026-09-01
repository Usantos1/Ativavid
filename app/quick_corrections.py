"""Correções rápidas do operador — persistência + EDL manual, sem pipeline.

Fontes de verdade (preview e render futuro leem as mesmas):

- HEADLINE  remotion/public/edit-data.json → hook.lines
- CAPTIONS  remotion/public/captions.json  (texto corrigido > Whisper)
- EDL       edl.json → ranges
- ESTADO    corrections.json → dirty / finalStale / captionsTimedTo (nunca o texto)
- AUDITORIA caption_fixes.json → histórico; nunca fonte do render

Não transcreve, não chama IA, não renderiza.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.apply_plan import DIRTY_KEYS, empty_dirty, normalize_dirty, plan_apply_changes

FILE_NAME = "corrections.json"
MIN_SEG = 0.2


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, TypeError):
        return default


def _ranges_snapshot(raw: Any) -> list[dict] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        if end <= start:
            continue
        item = {
            "source": r.get("source") or "SRC",
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if r.get("beat"):
            item["beat"] = r["beat"]
        out.append(item)
    return out or None


def _jcut_snapshot(raw: Any) -> list[dict] | None:
    if not isinstance(raw, list) or not raw:
        return None
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(dict(item))
    return out or None


def empty_corrections() -> dict[str, Any]:
    return {
        "version": 1,
        "dirty": empty_dirty(),
        "finalStale": False,
        "pending": {k: 0 for k in DIRTY_KEYS},
        "revertVersionId": None,
        "appliedAt": None,
        "captionsTimedTo": None,
        "captionsTimedToJcut": None,
        "captionsTimedToFps": None,
    }


def load(edit_dir: Path) -> dict[str, Any]:
    data = _read_json(Path(edit_dir) / FILE_NAME, None)
    if not isinstance(data, dict):
        return empty_corrections()
    out = empty_corrections()
    out["dirty"] = normalize_dirty(data.get("dirty"))
    pending = data.get("pending") if isinstance(data.get("pending"), dict) else {}
    out["pending"] = {k: int(pending.get(k) or 0) for k in DIRTY_KEYS}
    out["revertVersionId"] = data.get("revertVersionId")
    out["appliedAt"] = data.get("appliedAt")
    out["version"] = int(data.get("version") or 1)
    out["finalStale"] = bool(data.get("finalStale")) or any(out["dirty"].values())
    out["captionsTimedTo"] = _ranges_snapshot(data.get("captionsTimedTo"))
    out["captionsTimedToJcut"] = _jcut_snapshot(data.get("captionsTimedToJcut"))
    try:
        fps = float(data.get("captionsTimedToFps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    out["captionsTimedToFps"] = fps if fps > 0 else None
    return out


def save(edit_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    body = empty_corrections()
    body["dirty"] = normalize_dirty((data or {}).get("dirty"))
    pending = (data or {}).get("pending") if isinstance((data or {}).get("pending"), dict) else {}
    body["pending"] = {k: int(pending.get(k) or 0) for k in DIRTY_KEYS}
    body["revertVersionId"] = (data or {}).get("revertVersionId")
    body["appliedAt"] = (data or {}).get("appliedAt")
    body["finalStale"] = bool((data or {}).get("finalStale")) or any(body["dirty"].values())
    body["captionsTimedTo"] = _ranges_snapshot((data or {}).get("captionsTimedTo"))
    body["captionsTimedToJcut"] = _jcut_snapshot((data or {}).get("captionsTimedToJcut"))
    try:
        fps = float((data or {}).get("captionsTimedToFps") or 0)
    except (TypeError, ValueError):
        fps = 0.0
    body["captionsTimedToFps"] = fps if fps > 0 else None
    # Nunca gravar headline/captions aqui — isso duplicaria a fonte de verdade.
    _write_json(Path(edit_dir) / FILE_NAME, body)
    return body


def edit_data_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "remotion" / "public" / "edit-data.json"


def captions_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "remotion" / "public" / "captions.json"


def edl_path(edit_dir: Path) -> Path:
    return Path(edit_dir) / "edl.json"


def _ensure_revert_snapshot(edit_dir: Path, data: dict[str, Any]) -> dict[str, Any]:
    if data.get("revertVersionId"):
        return data
    try:
        from app.project_versions import snapshot

        item = snapshot(
            Path(edit_dir),
            origin="corrections",
            description="Antes das correções rápidas",
        )
        data["revertVersionId"] = item.get("id")
    except Exception:
        pass
    return data


def prepare_correction(edit_dir: Path) -> dict[str, Any]:
    """Snapshot do estado atual ANTES de gravar a correção."""
    data = load(edit_dir)
    if data.get("revertVersionId"):
        return data
    data = _ensure_revert_snapshot(edit_dir, data)
    return save(edit_dir, data)


def mark_dirty(edit_dir: Path, *keys: str) -> dict[str, Any]:
    data = load(edit_dir)
    dirty = normalize_dirty(data.get("dirty"))
    pending = dict(data.get("pending") or {})
    for key in keys:
        if key not in DIRTY_KEYS:
            continue
        dirty[key] = True
        pending[key] = int(pending.get(key) or 0) + 1
    data["dirty"] = dirty
    data["pending"] = pending
    data["finalStale"] = True
    return save(edit_dir, data)


def as_headline_lines(text_or_lines: Any) -> list[str]:
    if isinstance(text_or_lines, list):
        lines = [str(x).strip() for x in text_or_lines]
    else:
        raw = str(text_or_lines or "").replace("\r\n", "\n").replace("\r", "\n")
        lines = [ln.strip() for ln in raw.split("\n")]
    return [ln for ln in lines if ln]


def read_headline_lines(edit_dir: Path) -> list[str]:
    data = _read_json(edit_data_path(edit_dir), {})
    if not isinstance(data, dict):
        return []
    hook = data.get("hook") if isinstance(data.get("hook"), dict) else {}
    lines = hook.get("lines") or hook.get("text") or []
    if isinstance(lines, str):
        return as_headline_lines(lines)
    if isinstance(lines, list):
        return [str(x).strip() for x in lines if str(x).strip()]
    return []


def set_headline(edit_dir: Path, text_or_lines: Any) -> dict[str, Any]:
    """Grava a headline neste projeto. Não toca preset da marca."""
    lines = as_headline_lines(text_or_lines)
    if not lines:
        return {"ok": False, "error": "headline vazia"}
    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    hook = dict(data.get("hook") or {}) if isinstance(data.get("hook"), dict) else {}
    hook["enabled"] = True
    hook["lines"] = lines
    data["hook"] = hook
    _write_json(path, data)
    corr = mark_dirty(edit_dir, "headline")
    return {"ok": True, "headline": lines, "corrections": corr}


def set_headline_answer(edit_dir: Path, text_or_lines: Any) -> dict[str, Any]:
    """Grava a RESPOSTA do estilo pergunta (hook.answerLines) neste projeto."""
    lines = as_headline_lines(text_or_lines)
    if not lines:
        return {"ok": False, "error": "resposta vazia"}
    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    hook = dict(data.get("hook") or {}) if isinstance(data.get("hook"), dict) else {}
    hook["answerLines"] = lines
    data["hook"] = hook
    _write_json(path, data)
    corr = mark_dirty(edit_dir, "headline")
    return {"ok": True, "answer": lines, "corrections": corr}


def limpar_headline_pos(edit_dir: Path) -> dict[str, Any]:
    """Volta a headline para a altura padrao do estilo (campo ausente)."""
    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    hook = dict(data.get("hook") or {}) if isinstance(data.get("hook"), dict) else {}
    hook.pop("paddingTop", None)
    hook.pop("paddingBottom", None)
    data["hook"] = hook
    _write_json(path, data)
    return {"ok": True, "padrao": True, "corrections": mark_dirty(edit_dir, "headline")}


def limpar_caption_pos(edit_dir: Path) -> dict[str, Any]:
    """Volta a legenda para a altura padrao do estilo (campo ausente)."""
    from app.render_proprio import LEGENDA_ANCORAS

    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    caps = dict(data.get("captions") or {}) if isinstance(data.get("captions"), dict) else {}
    # SO o botao do estilo em uso. `paddingBottom` e o botao do impacto, mas
    # tambem e a posicao generica que o karaoke le — apagar sempre tirava um
    # ajuste que este estilo nem usa (visto num projeto `stacked`: o 420 foi
    # embora sem ninguem pedir).
    estilo = str(caps.get("style") or "stacked")
    a = LEGENDA_ANCORAS.get(estilo)
    if a:
        caps.pop(a["chave"], None)
    data["captions"] = caps
    _write_json(path, data)
    return {"ok": True, "padrao": True, "corrections": mark_dirty(edit_dir, "style")}


def set_headline_pos(edit_dir: Path, valor: Any, *, base: str = "top") -> dict[str, Any]:
    """Altura da headline, em pixels do quadro de 1920.

    `base="top"` grava paddingTop (a maioria dos estilos); `base="bottom"`
    grava paddingBottom, que e como a manchete se ancora. Os dois campos ja
    sao lidos pelo template e pelo render_proprio.
    """
    try:
        px = float(valor)
    except (TypeError, ValueError):
        return {"ok": False, "error": "posicao invalida"}
    if px != px or px in (float("inf"), float("-inf")):
        return {"ok": False, "error": "posicao invalida"}
    # Fora da tela a headline some sem aviso; o limite deixa sempre uma
    # faixa visivel, com folga para o texto que cresce para baixo.
    px = max(0.0, min(1560.0, px))
    campo = "paddingBottom" if str(base).lower() == "bottom" else "paddingTop"
    prepare_correction(edit_dir)
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    hook = dict(data.get("hook") or {}) if isinstance(data.get("hook"), dict) else {}
    hook[campo] = round(px)
    data["hook"] = hook
    _write_json(path, data)
    corr = mark_dirty(edit_dir, "headline")
    return {"ok": True, campo: hook[campo], "corrections": corr}


def set_caption_pos(edit_dir: Path, y_px: Any, altura: int = 1920) -> dict[str, Any]:
    """Altura da legenda, pela ancora do estilo que o projeto usa.

    Recebe PIXEL do quadro e grava o botao certo — a conversao mora no
    render_proprio (`legenda_y_para_valor`), que e quem desenha.
    """
    from app.render_proprio import legenda_y_para_valor

    try:
        y = float(y_px)
    except (TypeError, ValueError):
        return {"ok": False, "error": "posicao invalida"}
    if y != y or y in (float("inf"), float("-inf")):
        return {"ok": False, "error": "posicao invalida"}
    y = max(0.0, min(float(altura), y))
    path = edit_data_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    caps = dict(data.get("captions") or {}) if isinstance(data.get("captions"), dict) else {}
    estilo = str(caps.get("style") or "stacked")
    par = legenda_y_para_valor(estilo, y, altura)
    if par is None:
        return {"ok": False, "error": f"estilo '{estilo}' nao tem altura livre"}
    chave, valor = par
    prepare_correction(edit_dir)
    caps[chave] = valor
    data["captions"] = caps
    _write_json(path, data)
    corr = mark_dirty(edit_dir, "style")
    return {"ok": True, "style": estilo, chave: valor, "corrections": corr}


def fix_caption(
    edit_dir: Path, *, src: str, dst: str, apagar: bool = False, **target: Any,
) -> dict[str, Any]:
    """Aplica o texto corrigido na fonte real da legenda. Preserva timings.

    `apagar=True` REMOVE a legenda em vez de trocar o texto. E um pedido
    explicito: salvar com o campo vazio nunca apaga sozinho, senao um campo
    limpo por engano levaria a legenda junto.
    """
    from app.caption_fixes import apply_caption_fixes

    src = str(src or "").strip()
    dst = "" if apagar else str(dst or "").strip()
    if not src or (not apagar and (not dst or src == dst)):
        return {"ok": True, "changed": 0, "corrections": load(edit_dir)}
    fix: dict[str, Any] = {"from": src, "to": dst}
    if apagar:
        fix["delete"] = True
    for key in (
        "index", "cueId", "tokenId", "id", "wordId",
        "start", "end", "startMs", "endMs", "cueIndex",
        "renderedStart", "renderedEnd",
    ):
        if target.get(key) is not None:
            fix[key] = target[key]
    prepare_correction(edit_dir)
    out = apply_caption_fixes(Path(edit_dir), [fix])
    if not out.get("ok"):
        return {**out, "captionWords": _read_json(captions_path(edit_dir), []) or [], "corrections": load(edit_dir)}
    changed = int((out or {}).get("changed") or 0)
    corr = mark_dirty(edit_dir, "captions") if changed else load(edit_dir)
    words = _read_json(captions_path(edit_dir), [])
    return {
        "ok": True,
        "changed": changed,
        "captionWords": words if isinstance(words, list) else [],
        "corrections": corr,
    }


# Espaco minimo para uma legenda caber sem virar piscada.
_MIN_LEGENDA_S = 0.30
# Quanto tempo cada palavra ocupa quando ninguem a falou.
_SEG_POR_PALAVRA = 0.38


def add_caption(
    edit_dir: Path, *, texto: str, inicio_s: Any, dur_s: Any = None,
) -> dict[str, Any]:
    """Cria uma legenda ONDE NAO HAVIA — o resto do editor so corrige.

    Grava PALAVRAS em captions.json, nao uma cue pronta: o apply reconstroi
    as cues a partir das palavras, entao a legenda escrita na mao sai com o
    mesmo desenho e as mesmas quebras das outras. Uma cue inventada aqui
    apareceria com estilo diferente das vizinhas.

    Nao encosta em legenda existente: o fim e aparado ate a proxima palavra.
    Sem espaco livre (>= 0,30s) o pedido volta com o motivo — sobrescrever a
    fala transcrita para caber um texto novo seria pior que recusar.
    """
    palavras = [w for w in str(texto or "").split() if w]
    if not palavras:
        return {"ok": False, "erro": "Escreva o texto da legenda."}
    try:
        ini = max(0.0, float(inicio_s))
    except (TypeError, ValueError):
        return {"ok": False, "erro": "Momento inválido."}

    atual = _read_json(captions_path(edit_dir), []) or []
    if not isinstance(atual, list):
        atual = []
    ini_ms = int(round(ini * 1000))
    try:
        dur = float(dur_s) if dur_s is not None else 0.0
    except (TypeError, ValueError):
        dur = 0.0
    if dur <= 0:
        dur = min(4.0, max(1.2, _SEG_POR_PALAVRA * len(palavras)))
    fim_ms = ini_ms + int(round(dur * 1000))

    # nao passar por cima do que ja existe
    for w in atual:
        try:
            w0, w1 = int(w.get("startMs") or 0), int(w.get("endMs") or 0)
        except (TypeError, ValueError):
            continue
        if w1 <= ini_ms:
            continue
        if w0 < fim_ms:
            fim_ms = min(fim_ms, w0)
    if fim_ms - ini_ms < _MIN_LEGENDA_S * 1000:
        return {"ok": False,
                "erro": "Já existe legenda neste trecho — leve a agulha "
                        "para um espaço livre."}

    passo = (fim_ms - ini_ms) / len(palavras)
    novas = []
    for k, w in enumerate(palavras):
        a0 = int(round(ini_ms + k * passo))
        a1 = int(round(ini_ms + (k + 1) * passo))
        novas.append({"text": w, "startMs": a0, "endMs": a1,
                      "timestampMs": (a0 + a1) // 2, "confidence": None,
                      # marca de origem: quem le o arquivo depois sabe que
                      # esta palavra nao veio da transcricao
                      "manual": True})
    prepare_correction(edit_dir)
    juntas = list(atual) + novas
    juntas.sort(key=lambda w: (int(w.get("startMs") or 0),
                               int(w.get("endMs") or 0)))
    _write_json(captions_path(edit_dir), juntas)
    corr = mark_dirty(edit_dir, "captions")
    return {"ok": True, "changed": len(novas), "captionWords": juntas,
            "corrections": corr,
            "janela": {"inicioMs": ini_ms, "fimMs": fim_ms}}


def read_edl_ranges(edit_dir: Path) -> list[dict]:
    data = _read_json(edl_path(edit_dir), {})
    if not isinstance(data, dict):
        return []
    ranges = data.get("ranges") or []
    return [r for r in ranges if isinstance(r, dict)]


def _norm_range(r: dict) -> tuple:
    return (
        str(r.get("source") or "SRC"),
        round(float(r.get("start") or 0), 3),
        round(float(r.get("end") or 0), 3),
        str(r.get("beat") or ""),
    )


def _same_ranges(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    return all(_norm_range(x) == _norm_range(y) for x, y in zip(a, b) if isinstance(x, dict) and isinstance(y, dict))


# O que o planejador escreve em cada trecho e que a tela nao tem como
# devolver. `quote` e a fala daquele trecho: a nota de clareza conta
# trechos com fala, e o texto do post e montado a partir dela.
_HERDAVEIS = ("quote", "reason", "beat", "gain_db")


def _herdar_do_anterior(novo: dict, antigos: list[dict]) -> dict:
    """Completa `novo` com o que o trecho antigo do mesmo lugar sabia.

    Medido nos projetos do usuario: 100% dos que passaram por um apply
    ficaram SEM NENHUMA `quote` no EDL, contra 11% dos que nunca
    passaram — o salvamento da linha do tempo montava cada trecho do zero.

    O casamento e por sobreposicao de tempo, e exige que a maior parte do
    trecho novo esteja dentro do antigo: encostar de raspao numa fala
    vizinha herdaria a fala errada, que e pior que herdar nada.
    """
    a0, a1 = float(novo["start"]), float(novo["end"])
    dur = a1 - a0
    if dur <= 0:
        return novo
    melhor, melhor_cob = None, 0.0
    for velho in antigos:
        try:
            b0, b1 = float(velho.get("start")), float(velho.get("end"))
        except (TypeError, ValueError):
            continue
        if (velho.get("source") or "SRC") != novo.get("source"):
            continue
        cob = max(0.0, min(a1, b1) - max(a0, b0)) / dur
        if cob > melhor_cob:
            melhor, melhor_cob = velho, cob
    if melhor is None or melhor_cob < 0.6:
        return novo
    for campo in _HERDAVEIS:
        if campo not in novo and melhor.get(campo) not in (None, ""):
            novo[campo] = melhor[campo]
    return novo


def write_edl_ranges(edit_dir: Path, ranges: list[dict], *, mark: bool = True) -> dict[str, Any]:
    path = edl_path(edit_dir)
    data = _read_json(path, {})
    if not isinstance(data, dict):
        data = {}
    clean: list[dict] = []
    for r in ranges or []:
        if not isinstance(r, dict):
            continue
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        if end <= start:
            continue
        item = {
            "source": r.get("source") or "SRC",
            "start": round(start, 3),
            "end": round(end, 3),
        }
        if r.get("beat"):
            item["beat"] = r["beat"]
        for campo in _HERDAVEIS:
            if r.get(campo) not in (None, ""):
                item.setdefault(campo, r[campo])
        clean.append(item)
    old = [r for r in (data.get("ranges") or []) if isinstance(r, dict)]
    # O que a tela nao devolve, o EDL anterior devolve.
    clean = [_herdar_do_anterior(item, old) for item in clean]
    if _same_ranges(old, clean):
        return {"ok": True, "ranges": clean, "corrections": load(edit_dir), "changed": False}
    old_jcut = data.get("jcut_timeline")
    if mark:
        prepare_correction(edit_dir)
        data = _read_json(path, {}) or data
        if not isinstance(data, dict):
            data = {}
        old_jcut = data.get("jcut_timeline") if old_jcut is None else old_jcut
    data["ranges"] = clean
    # Ranges mudaram: a timeline gravada descreve o cut antigo, não este EDL.
    data.pop("jcut_timeline", None)
    _write_json(path, data)
    if mark:
        # Não reescrever captions.json: o cut.mp4 ainda é o antigo até o Apply.
        # O remapeamento temporal fica derivado (captionsTimedTo → EDL atual).
        corr = load(edit_dir)
        if not corr.get("captionsTimedTo"):
            snap = _ranges_snapshot(old)
            if snap:
                corr["captionsTimedTo"] = snap
                corr["captionsTimedToJcut"] = _jcut_snapshot(old_jcut)
                try:
                    fps = float(data.get("fps") or 0)
                except (TypeError, ValueError):
                    fps = 0.0
                corr["captionsTimedToFps"] = fps if fps > 0 else None
                save(edit_dir, corr)
    corr = mark_dirty(edit_dir, "edl") if mark else load(edit_dir)
    return {"ok": True, "ranges": clean, "corrections": corr, "changed": True}


def range_at_timeline(
    ranges: list[dict], playhead_sec: float
) -> tuple[int, float] | None:
    """Devolve (índice, tempo na fonte) do take que contém a agulha na timeline."""
    acc = 0.0
    t = float(playhead_sec)
    for i, r in enumerate(ranges):
        start = float(r.get("start") or 0)
        end = float(r.get("end") or 0)
        dur = end - start
        if dur <= 0:
            continue
        if t < acc + dur - 1e-9:
            return i, start + (t - acc)
        acc += dur
    return None


def split_at_playhead(
    ranges: list[dict], playhead_sec: float, *, min_seg: float = MIN_SEG
) -> list[dict]:
    """Corta o take da agulha em dois. Sem FFmpeg. Timeline fecha o espaço sozinha."""
    hit = range_at_timeline(ranges, playhead_sec)
    if hit is None:
        return [dict(r) for r in ranges]
    i, source_t = hit
    r = dict(ranges[i])
    start = float(r.get("start") or 0)
    end = float(r.get("end") or 0)
    if source_t - start < min_seg or end - source_t < min_seg:
        return [dict(x) for x in ranges]
    left = dict(r)
    left["end"] = round(source_t, 3)
    right = dict(r)
    right["start"] = round(source_t, 3)
    return [dict(x) for x in ranges[:i]] + [left, right] + [dict(x) for x in ranges[i + 1 :]]


def delete_range_index(ranges: list[dict], index: int) -> list[dict]:
    """Remove o take e fecha o buraco (ripple). Sem IA."""
    if index < 0 or index >= len(ranges):
        return [dict(r) for r in ranges]
    return [dict(r) for j, r in enumerate(ranges) if j != index]


def split_project_at(edit_dir: Path, playhead_sec: float) -> dict[str, Any]:
    ranges = read_edl_ranges(edit_dir)
    nxt = split_at_playhead(ranges, playhead_sec)
    if nxt == ranges:
        return {"ok": True, "ranges": ranges, "changed": False, "corrections": load(edit_dir)}
    out = write_edl_ranges(edit_dir, nxt)
    out["changed"] = True
    return out


def delete_project_range(edit_dir: Path, index: int) -> dict[str, Any]:
    ranges = read_edl_ranges(edit_dir)
    nxt = delete_range_index(ranges, index)
    if nxt == ranges:
        return {"ok": True, "ranges": ranges, "changed": False, "corrections": load(edit_dir)}
    out = write_edl_ranges(edit_dir, nxt)
    out["changed"] = True
    return out


def mark_style(edit_dir: Path) -> dict[str, Any]:
    prepare_correction(edit_dir)
    return {"ok": True, "corrections": mark_dirty(edit_dir, "style")}


def plan_for_edit(edit_dir: Path) -> dict[str, Any]:
    return plan_apply_changes(load(edit_dir))


def discard(edit_dir: Path) -> dict[str, Any]:
    """Restaura o snapshot feito antes das correções. Não apaga o final.mp4."""
    data = load(edit_dir)
    vid = data.get("revertVersionId")
    restored = None
    if vid:
        try:
            from app.project_versions import restore

            restored = restore(Path(edit_dir), str(vid))
        except Exception as e:
            return {"ok": False, "error": str(e)}
    save(edit_dir, empty_corrections())
    return {"ok": True, "restored": restored, "corrections": empty_corrections()}


def _busy_if_applying(edit_dir: Path) -> dict[str, Any] | None:
    try:
        from app.apply_execute import is_apply_running
    except Exception:
        return None
    if not is_apply_running(edit_dir):
        return None
    return {
        "ok": False,
        "busy": True,
        "error": "Estou aplicando as alterações. Espere terminar para editar.",
        "corrections": load(edit_dir),
    }


def handle(
    edit_dir: Path,
    body: dict[str, Any],
    *,
    hooks: Any = None,
    fallback_full: Any = None,
) -> dict[str, Any]:
    """API do editor. Apply dispara o executor; o planner continua puro."""
    op = str((body or {}).get("op") or (body or {}).get("action") or "").strip().lower()
    edit = Path(edit_dir)
    if op in ("plan", "apply-plan"):
        plan = plan_for_edit(edit)
        return {
            "ok": True,
            "plan": plan,
            "execute": False,
            "corrections": load(edit),
        }
    if op == "apply":
        from app.apply_execute import execute_apply_plan, start_apply

        if body.get("sync") or hooks is not None:
            plan = plan_for_edit(edit)
            return execute_apply_plan(edit, plan, hooks=hooks)
        return start_apply(edit, fallback_full=fallback_full)
    busy = _busy_if_applying(edit)
    if busy and op not in ("load", "get", "plan", "apply-plan", ""):
        return busy
    if op in ("set_headline", "headline"):
        return set_headline(edit, body.get("lines") or body.get("text") or body.get("headline"))
    if op in ("set_headline_answer", "headline_answer"):
        return set_headline_answer(edit, body.get("lines") or body.get("text") or body.get("answer"))
    if op in ("set_caption_pos", "caption_pos"):
        if body.get("reset"):
            return limpar_caption_pos(edit)
        return set_caption_pos(edit, body.get("y"))
    if op in ("set_headline_pos", "headline_pos"):
        if body.get("reset"):
            return limpar_headline_pos(edit)
        return set_headline_pos(
            edit,
            body.get("paddingTop") if body.get("paddingTop") is not None
            else body.get("paddingBottom"),
            base="bottom" if body.get("paddingBottom") is not None else "top",
        )
    if op in ("add_caption", "nova_legenda"):
        return add_caption(
            edit,
            texto=str(body.get("text") or body.get("texto") or ""),
            inicio_s=body.get("start") if body.get("start") is not None
            else body.get("inicio"),
            dur_s=body.get("dur") if body.get("dur") is not None
            else body.get("duracao"),
        )
    if op in ("fix_caption", "caption", "captions"):
        return fix_caption(
            edit,
            src=str(body.get("from") or body.get("src") or ""),
            dst=str(body.get("to") or body.get("dst") or body.get("text") or ""),
            apagar=bool(body.get("delete") or body.get("apagar")),
            index=body.get("index"),
            cueIndex=body.get("cueIndex"),
            cueId=body.get("cueId"),
            tokenId=body.get("tokenId") or body.get("id") or body.get("wordId"),
            start=body.get("start"),
            end=body.get("end"),
            startMs=body.get("startMs"),
            endMs=body.get("endMs"),
            renderedStart=body.get("renderedStart"),
            renderedEnd=body.get("renderedEnd"),
        )
    if op in ("set_edl", "edl"):
        ranges = body.get("ranges")
        if not isinstance(ranges, list):
            return {"ok": False, "error": "ranges ausentes"}
        return write_edl_ranges(edit, ranges)
    if op in ("split", "cut"):
        return split_project_at(edit, float(body.get("playhead") or body.get("t") or 0))
    if op in ("delete_range", "delete"):
        return delete_project_range(edit, int(body.get("index") if body.get("index") is not None else -1))
    if op in ("mark_style", "style"):
        return mark_style(edit)
    if op in ("discard", "revert"):
        return discard(edit)
    if op in ("load", "get", ""):
        return {"ok": True, "corrections": load(edit), "plan": plan_for_edit(edit)}
    return {"ok": False, "error": f"op desconhecida: {op}"}
