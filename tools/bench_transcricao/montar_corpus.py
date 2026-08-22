# -*- coding: utf-8 -*-
"""Descobre os vídeos reais do ATIVAVID e monta o esqueleto do corpus.

NÃO faz parte do caminho de medição — não toca em motor, métrica nem relatório.
É só preparação de entrada: varre os seus projetos, mede a duração de cada
fonte e escreve um `corpus.json` com os caminhos já preenchidos, para você não
ter de digitar oito caminhos à mão.

    python tools\\bench_transcricao\\montar_corpus.py
    python tools\\bench_transcricao\\montar_corpus.py --saida corpus.json --min 8

O que ele NÃO preenche, de propósito:

  **tags** — dizer se um vídeo tem duas pessoas, ruído ou fala rápida exige
  conhecer o material. Um script chutando isso estragaria a cobertura, que é
  justamente o que o corpus precisa garantir.

  **entidades** — marcas, pessoas e lugares só entram se você confirmar. Nome
  próprio inventado vira métrica errada, e métrica errada decide arquitetura
  pelo motivo errado.

Para ajudar a escolher sem reabrir cada vídeo, ele mostra um trecho do
transcript que o ATIVAVID já gerou (quando existe) e sinaliza o que aquele
texto contém — dígitos, marcadores coloquiais, palavras capitalizadas no meio
da frase. São PISTAS para você decidir, não anotação.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parent.parent.parent
if str(RAIZ_REPO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPO))

# Derivados do pipeline. A fonte fica na raiz do projeto; `edit\` é saída.
DERIVADOS = {"cut.mp4", "base.mp4", "cut_proxy.mp4", "final.mp4"}
# O ATIVAVID grava um preparado ao lado da fonte, com o nome dela mais
# `.prep.mp4` (`IMG_4007.MOV.prep.mp4`). É derivado: entra no corpus como se
# fosse fonte, duplica o vídeo e mede o mesmo material duas vezes.
SUFIXO_PREPARADO = ".prep.mp4"
EXTENSOES = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}

COLOQUIAIS = re.compile(
    r"\b(c[eê]|t[aá]|t[oô]|n[eé]|pra|pro|num|tipo|mano|cara|vamo|tamo|bora|"
    r"a[ií]|sacou|beleza|valeu)\b", re.IGNORECASE)
CAPITALIZADA_NO_MEIO = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-ZÁÉÍÓÚÂÊÔÃÕÇ]\w{2,}")


def raiz_dos_projetos() -> Path:
    return Path(os.environ.get("ATIVAVID_PROJECTS")
                or (Path.home() / "ATIVAVID" / "Projetos"))


def duracao(video: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(video)],
            capture_output=True, text=True, timeout=60).stdout.strip()
        return float(out or 0.0)
    except (ValueError, OSError, subprocess.SubprocessError):
        return 0.0


def transcript_existente(projeto: Path, video: Path) -> str:
    """Texto que o ATIVAVID já transcreveu para esta fonte, se houver."""
    p = projeto / "edit" / "transcripts" / f"{video.stem}.json"
    if not p.is_file():
        return ""
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    texto = d.get("text") or " ".join(
        (w.get("text") or "") for w in (d.get("words") or [])
        if w.get("type", "word") == "word")
    return " ".join(texto.split())


def pistas(texto: str) -> list[str]:
    """Sinais que ajudam a escolher. Não são tags nem entidades."""
    if not texto:
        return []
    out = []
    # Dígito OU número por extenso: "quinze mil" não tem dígito nenhum e é
    # exatamente o caso que a tag `numeros` precisa cobrir.
    from tools.bench_transcricao.lexico import NUMBER_WORDS

    palavras = {w.strip(".,!?;:").casefold() for w in texto.split()}
    if re.search(r"\d", texto) or (palavras & NUMBER_WORDS):
        out.append("números?")
    if len(COLOQUIAIS.findall(texto)) >= 3:
        out.append("coloquial?")
    nomes = set(CAPITALIZADA_NO_MEIO.findall(texto))
    if nomes:
        out.append(f"maiúsculas: {', '.join(sorted(nomes)[:4])}")
    return out


def descobrir(raiz: Path) -> list[dict]:
    achados: list[dict] = []
    if not raiz.is_dir():
        return achados
    for projeto in sorted(p for p in raiz.iterdir() if p.is_dir()):
        for arq in sorted(projeto.iterdir()):
            if (not arq.is_file() or arq.suffix.lower() not in EXTENSOES
                    or arq.name.lower() in DERIVADOS
                    or arq.name.lower().endswith(SUFIXO_PREPARADO)):
                continue
            texto = transcript_existente(projeto, arq)
            achados.append({
                "projeto": projeto.name,
                "video": str(arq.resolve()),
                "duracao_s": duracao(arq),
                "trecho": texto[:160],
                "pistas": pistas(texto),
            })
    return achados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raiz", type=Path, default=None)
    ap.add_argument("--saida", type=Path, default=Path("corpus.json"))
    ap.add_argument("--min", type=int, default=8)
    ap.add_argument("--min-s", type=float, default=8.0,
                    help="ignorar fontes mais curtas que isto")
    ap.add_argument("--forcar", action="store_true")
    a = ap.parse_args()

    raiz = a.raiz or raiz_dos_projetos()
    print(f"procurando em {raiz}\n")
    achados = [x for x in descobrir(raiz) if x["duracao_s"] >= a.min_s]

    if not achados:
        print(f"nenhuma fonte encontrada em {raiz}.\n"
              f"Se seus projetos estão em outro lugar, use --raiz ou defina "
              f"ATIVAVID_PROJECTS.", file=sys.stderr)
        return 2

    larg = max(len(x["projeto"]) for x in achados)
    total = 0.0
    for i, x in enumerate(achados, 1):
        total += x["duracao_s"]
        print(f"{i:3d}. {x['projeto'].ljust(larg)}  "
              f"{x['duracao_s'] / 60:5.1f} min  {Path(x['video']).name}")
        if x["pistas"]:
            print(f"     pistas: {' · '.join(x['pistas'])}")
        if x["trecho"]:
            print(f"     \"{x['trecho']}…\"")
    print(f"\n{len(achados)} fontes, {total / 60:.1f} min no total.")

    if a.saida.exists() and not a.forcar:
        print(f"\n{a.saida} já existe — use --forcar para sobrescrever.",
              file=sys.stderr)
        return 1

    videos = [{
        "id": f"v{i:02d}",
        "video": x["video"],
        "projeto": x["projeto"],
        "duracao_s": round(x["duracao_s"], 2),
        "tags": [],
        "entidades": {"marcas": [], "pessoas": [], "lugares": []},
        "notas": x["trecho"][:120],
    } for i, x in enumerate(achados, 1)]

    a.saida.write_text(json.dumps({
        "_leia": "APAGUE as linhas que não quiser e PREENCHA tags e "
                 "entidades. tags e entidades ficam vazias de propósito: "
                 "exigem conhecer o material, e um chute estragaria a "
                 "cobertura e a métrica de nome próprio.",
        "_tags_possiveis": [
            "uma_pessoa", "duas_ou_mais", "conversa_rapida", "interrupcoes",
            "girias", "nomes_proprios", "marcas", "numeros", "ruido",
            "musica_fundo", "fala_baixa", "fala_rapida", "pausas",
            "coloquial_br"],
        "videos": videos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nescrito {a.saida} com {len(videos)} candidatos.")
    print(f"Agora: apague o que não quiser (deixe ≥ {a.min}), preencha "
          f"`tags` e `entidades`, e rode o preflight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
