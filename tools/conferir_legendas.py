# -*- coding: utf-8 -*-
"""Confere as legendas dos projetos REAIS contra invariantes.

Os testes do repositório provam cada peça isolada. Isto prova o conjunto, nos
arquivos de verdade — que foi onde os defeitos desta sessão apareceram: a
palavra duplicada estava em 73% dos projetos e nenhum teste unitário a via,
porque o defeito nasce da combinação entre a transcrição real (que às vezes
junta uma fala inteira numa "palavra") e os cortes reais.

Não afirma versão nem compara "antes"; AFIRMA propriedades que a legenda
entregue tem de ter:

  1. nenhuma palavra da fonte sai duas vezes
  2. as palavras saem na ORDEM da fala
  3. nenhuma palavra com duração <= 0
  4. o texto entregue é subconjunto do que a fonte disse (nada inventado)
  5. nenhuma cue vazia sobrevive — o motor levanta nelas

Só CPU: não disputa GPU com um render em andamento.

Uso:  python tools/conferir_legendas.py [raiz-dos-projetos]
Sai com 1 se alguma invariante quebrar, para servir de porta num script.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for extra in (REPO, REPO / "helpers"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

PADRAO = Path.home() / "ATIVAVID" / "Projetos"


def _vocabulario(edit: Path) -> set[str]:
    from helpers.captions_for_remotion import _word_items

    vocab: set[str] = set()
    for tr in (edit / "transcripts").glob("*.json"):
        if tr.name == "cut.json":
            continue
        try:
            dados = json.loads(tr.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        vocab.update(str(w.get("text") or "").strip().lower() for w in _word_items(dados))
    return vocab


def conferir(raiz: Path) -> dict[str, list[str]]:
    from helpers.captions_for_remotion import build_captions_with_provenance

    falhas: dict[str, list[str]] = {k: [] for k in (
        "duplicada", "fora_de_ordem", "duracao", "texto_inventado",
        "cue_vazia", "erro")}
    projetos = palavras = 0

    for edit in sorted(raiz.glob("*/edit")):
        if not ((edit / "edl.json").is_file() and (edit / "transcripts").is_dir()):
            continue
        nome = edit.parent.name[:34]
        try:
            edl = json.loads((edit / "edl.json").read_text(encoding="utf-8-sig"))
            caps = build_captions_with_provenance(edl, edit, quiet=True)
        except Exception as e:  # noqa: BLE001
            falhas["erro"].append(f"{nome}: {type(e).__name__}: {e}")
            continue
        if not caps:
            continue
        projetos += 1
        palavras += len(caps)

        if any(b["startMs"] < a["startMs"] for a, b in zip(caps, caps[1:])):
            falhas["fora_de_ordem"].append(nome)
        if any(c["endMs"] <= c["startMs"] for c in caps):
            falhas["duracao"].append(nome)
        chaves = Counter((c.get("source"), round(c.get("sourceStart") or 0, 3), c["text"])
                         for c in caps)
        if any(v > 1 for v in chaves.values()):
            repetida = next(k for k, v in chaves.items() if v > 1)
            falhas["duplicada"].append(f"{nome}: {repetida[2]!r}")
        vocab = _vocabulario(edit)
        if vocab:
            inventadas = [c["text"] for c in caps
                          if str(c["text"]).strip().lower() not in vocab]
            if inventadas:
                falhas["texto_inventado"].append(f"{nome}: {inventadas[:3]}")

    for cues_p in raiz.glob("*/edit/remotion/public/caption-cues.json"):
        try:
            cues = json.loads(cues_p.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        lista = cues if isinstance(cues, list) else (cues or {}).get("cues") or []
        n = sum(1 for c in lista if isinstance(c, dict) and not any(c.get("lines") or []))
        if n:
            proj = cues_p.parents[3].name[:30]
            falhas["cue_vazia"].append(f"{proj}: {n} cue(s)")

    falhas["_resumo"] = [f"{projetos} projetos, {palavras} palavras"]
    return falhas


def main() -> int:
    raiz = Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO
    if not raiz.is_dir():
        print(f"raiz não encontrada: {raiz}")
        return 2
    falhas = conferir(raiz)
    print(falhas.pop("_resumo")[0])
    print()
    rotulos = {
        "duplicada": "1. palavra saindo duas vezes",
        "fora_de_ordem": "2. palavras fora da ordem da fala",
        "duracao": "3. palavra com duração <= 0",
        "texto_inventado": "4. texto que a fonte não disse",
        "cue_vazia": "5. cue vazia (o motor levanta nela)",
        "erro": "!. reconstrução levantou",
    }
    ruim = 0
    for chave, rotulo in rotulos.items():
        itens = falhas.get(chave) or []
        ruim += len(itens)
        print(f"  {'OK   ' if not itens else 'FALHA'} {rotulo}: {len(itens)}")
        for x in itens[:5]:
            print(f"           {x}")
    return 1 if ruim else 0


if __name__ == "__main__":
    raise SystemExit(main())
