# -*- coding: utf-8 -*-
"""O que saiu do corte, e por quê — escrito para o dono do vídeo ler.

Toda a investigação de 24-25/08 foi o usuário desconfiando do corte
("cortou falas sim") e a resposta vindo de abrir EDL + transcrição na mão.
Este módulo faz essa auditoria a cada render e grava `corte_relatorio.json`
no edit dir; o card do vídeo mostra o resumo ("Saiu: 32s silêncio · 9s
repetição") e o detalhe fica no JSON para inspeção.
"""
from __future__ import annotations

import json
from pathlib import Path

ROTULOS = {
    "silence": "silêncio",
    "repetition": "repetição",
    "false_start": "recomeço",
    "abandoned_take": "recomeço",
    "non_content": "sem fala útil",
    "estilo": "ritmo/estilo (IA)",
    "outro": "outros",
}

ARQUIVO = "corte_relatorio.json"

# Buraco menor que isto entre dois takes é respiro de edição, não remoção.
GAP_MINIMO_S = 0.25


def gerar(
    edit_dir: Path,
    *,
    duration_s: float | None,
    ranges: list[dict],
    stem: str | None,
    mode: str,
    backend: str | None = None,
) -> dict | None:
    """Escreve o relatório. Fonte única apenas — multi-take tem tempos locais
    por arquivo e um "gap" entre fontes não significa remoção."""
    fontes = {str(r.get("source") or "") for r in (ranges or [])}
    if len(fontes) != 1 or not duration_s:
        return None
    from app.editing_intent import (
        _load_transcript_words,
        classify_complete_removal,
        load_complete_drops,
        load_packed_phrases,
    )

    kept = sorted((float(r["start"]), float(r["end"])) for r in ranges)
    gaps: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in kept:
        if a - cursor >= GAP_MINIMO_S:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if float(duration_s) - cursor >= GAP_MINIMO_S:
        gaps.append((cursor, float(duration_s)))

    words = _load_transcript_words(edit_dir, stem)
    phrases = load_packed_phrases(edit_dir, stem)
    drops = load_complete_drops(edit_dir)
    sancionadas: list[tuple[float, float, str]] = []
    for p in phrases:
        cls = classify_complete_removal(p, phrases, drops=drops)
        if cls:
            sancionadas.append((float(p["start"]), float(p["end"]), cls))

    itens: list[dict] = []
    for a, b in gaps:
        ws = [w for w in words
              if min(b, w["end"]) - max(a, w["start"]) > 0.05]
        if not ws:
            classe, texto = "silence", ""
        else:
            classe = ""
            for ps, pe, cls in sancionadas:
                if min(b, pe) - max(a, ps) > 0.3:
                    classe = cls
                    break
            if not classe:
                # fala removida sem sanção do fiscal: nos modos que encurtam
                # é decisão editorial da IA; nos outros seria defeito — e o
                # relatório existe justamente para isso aparecer.
                classe = "estilo" if mode in ("dynamic", "shorts") else "outro"
            texto = " ".join(w["text"] for w in ws).strip()[:120]
        itens.append({
            "start": round(a, 2), "end": round(b, 2),
            "dur": round(b - a, 2), "classe": classe, "texto": texto,
        })

    tot: dict[str, float] = {}
    for it in itens:
        tot[it["classe"]] = tot.get(it["classe"], 0.0) + it["dur"]
    partes = [f"{max(1, round(secs))}s {ROTULOS.get(cls, cls)}"
              for cls, secs in sorted(tot.items(), key=lambda kv: -kv[1])
              if secs >= 0.5]
    data = {
        "mode": mode,
        "backend": backend,
        "sourceDurationSec": round(float(duration_s), 2),
        "removedSec": round(sum(it["dur"] for it in itens), 2),
        "resumo": " · ".join(partes),
        "itens": itens,
    }
    out = Path(edit_dir) / ARQUIVO
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    return data
