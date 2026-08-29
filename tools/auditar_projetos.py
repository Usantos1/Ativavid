# -*- coding: utf-8 -*-
"""Passa invariantes em TODOS os projetos entregues e lista o que saiu torto.

Rodar de tempos em tempos, e SEMPRE depois de mexer no corte. Foi assim
que os defeitos mais caros apareceram — nenhum deles deu erro na hora:

* trecho pedindo tempo que a fonte NAO tem (video mudo e travado; 29/08,
  job de 3 partes) — hoje barrado por `_aparar_fora_da_fonte`;
* `edl.json` dizendo `multi_take_concat` num job de fonte unica (o bug de
  indentacao da 3.18, consertado na 3.24): o corte da IA era reprocessado
  e a manchete dela, trocada;
* pausa morta sobrando dentro do corte (3.32/3.33).

Uso:
    uv run python tools/auditar_projetos.py [--raiz E:/ATIVAVID/Projetos]

So leitura: json dos projetos + ffprobe das fontes. Nada e alterado.
Ultima varredura (29/08, noite, 186 projetos): 19 com alguma marca. As 15
de "rotulo errado" e a de "fora da fonte" sao anteriores as correcoes; a
de "trecho baixo" e um trecho de 0,9s cujo RMS cai porque a maior parte
dele e pausa, nao voz fraca (1 em 186 — nao virou conserto).
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import argparse

_ap = argparse.ArgumentParser(description=__doc__)
_ap.add_argument("--raiz", type=Path,
                 default=Path.home() / "ATIVAVID" / "Projetos")
RAIZ = _ap.parse_args().raiz
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}


def ler(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def duracao(p: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration", "-of",
             "default=nokey=1:noprint_wrappers=1", str(p)],
            capture_output=True, text=True, timeout=60)
        return float((r.stdout or "0").strip().splitlines()[0])
    except Exception:
        return 0.0


achados = Counter()
linhas = []
projs = sorted([p for p in RAIZ.glob("2026*") if p.is_dir()])
print(f"projetos: {len(projs)}\n")

for proj in projs:
    edit = proj / "edit"
    edl = ler(edit / "edl.json")
    if not edl:
        continue
    ranges = edl.get("ranges") or []
    if not ranges:
        continue
    fontes = {}
    for f in proj.iterdir():
        if f.is_file() and f.suffix.lower() in VIDEO_EXT:
            chave = "".join(c if c.isalnum() or c == "_" else "_"
                            for c in f.stem)[:28]
            fontes[chave] = f
    duracoes = {}
    problemas = []

    # 1) trecho pedindo tempo que a fonte nao tem
    fora = 0
    for r in ranges:
        k = str(r.get("source") or "")
        if k not in fontes:
            continue
        if k not in duracoes:
            duracoes[k] = duracao(fontes[k])
        d = duracoes[k]
        if d and float(r.get("end") or 0) > d + 0.2:
            fora += 1
    if fora:
        problemas.append(f"{fora} trecho(s) fora da fonte")
        achados["fora da fonte"] += 1

    # 2) rotulo do plano x plano salvo
    llm = edl.get("llm") or {}
    plano = ler(edit / "llm_cut_plan.json") or {}
    meta = plano.get("meta") or {}
    if (llm.get("backend") == "multi_take_concat"
            and int(llm.get("takes") or 0) <= 1 and meta.get("backend")):
        problemas.append(
            f"rotulo errado: edl diz multi_take_concat, plano diz "
            f"{meta.get('backend')}")
        achados["rotulo errado"] += 1

    # 3) o que a verificacao achou
    v = ler(edit / "verificacao.json") or {}
    sil = float(v.get("silencioTotalS") or 0)
    baixos = v.get("takesBaixos") or []
    # Em "Sem cortes" (intact) a pausa NAO e defeito: e o que o modo manda
    # manter — o proprio card do app ja se cala nesse caso (jobs_view). A
    # ferramenta nao sabia disso e acusou 4,5s num depoimento de 29/08 que
    # estava exatamente como pedido; gastei meia hora atras de um defeito
    # que nao existia. Aviso que nao se pode atender ensina a ignorar aviso.
    modo = str((ler(edit / "job_intent.json") or {}).get("editingIntent") or "").lower()
    if sil >= 1.0 and modo != "intact":
        problemas.append(f"{sil:.1f}s de pausa sobrando")
        achados["pausa sobrando >= 1s"] += 1
    if baixos:
        pior = min(float(b.get("quedaDb") or 0) for b in baixos)
        problemas.append(f"trecho {pior:.0f} dB abaixo")
        achados["trecho baixo"] += 1
    if int(v.get("emendasEstouradas") or 0):
        problemas.append(f"{v['emendasEstouradas']} emenda(s) estourada(s)")
        achados["emenda estourada"] += 1

    # 4) video final MUITO menor que o corte planejado
    res = ler(edit / "result.json") or {}
    total = sum(max(0.0, float(r.get("end") or 0) - float(r.get("start") or 0))
                for r in ranges)
    fim = float(res.get("durationSec") or 0)
    if total > 5 and fim and fim < total * 0.6:
        problemas.append(f"video {fim:.0f}s x corte planejado {total:.0f}s")
        achados["video bem menor que o corte"] += 1

    # 5) trilha
    t = ler(edit / "timing.json") or {}
    if str(t.get("musicaSkip") or "").strip():
        problemas.append(f"sem trilha: {str(t['musicaSkip'])[:40]}")
        achados["sem trilha"] += 1

    if problemas:
        linhas.append((proj.name[:38], problemas))

for nome, ps in linhas:
    print(f"{nome:<38} {' · '.join(ps)[:120]}")
print("\n--- resumo ---")
for k, n in achados.most_common():
    print(f"  {k:<28} {n} projeto(s)")
print(f"  projetos com algo               {len(linhas)} de {len(projs)}")
