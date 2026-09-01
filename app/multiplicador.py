# -*- coding: utf-8 -*-
"""Multiplicador de criativos: ganchos x corpos x CTAs, todas as combinações.

O usuário grava variações de cada parte (ex.: 3 ganchos, 3 corpos, 3 CTAs) e
cada combinação vira UM vídeo na fila — 3x3x3 = 27 — todos com os mesmos
arquivos. É o fluxo de teste de criativo para tráfego pago: sobe tudo no
gerenciador de anúncios e deixa o algoritmo achar o vencedor.

Desenho (mesmo padrão dos Clipes de podcast, `materialize_clip_projects`):
- os arquivos originais moram UMA vez numa pasta-mãe `*_multiplicador-fontes_*`
  (que não é projeto nem job — só o cofre das fontes);
- cada combinação é um projeto próprio com HARDLINK das 3 fontes (custo zero
  de disco no mesmo volume; cai para cópia se o link falhar) e entra na fila
  como job multi-take comum, na ordem gancho → corpo → CTA — a ordem dos
  `sources` é a ordem da concatenação (`--also` preserva a lista);
- a transcrição de cada fonte é paga uma vez: o cache entre projetos serve
  as combinações seguintes por conteúdo.
"""
from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from itertools import product
from pathlib import Path

PAPEIS = ("gancho", "corpo", "cta")
_PREFIXO = {"gancho": "g", "corpo": "c", "cta": "cta"}
_ROTULO = {"gancho": "G", "corpo": "C", "cta": "CTA"}

# 4x4x3 = 48 já é uma tarde inteira de fila (~2-3 min por vídeo). Acima
# disso é quase sempre engano de seleção, não intenção.
TETO_COMBOS = 48


class MultiplicadorInvalido(ValueError):
    """Entrada que não dá para multiplicar — a mensagem é para a tela."""


def contar_combos(por_papel: dict) -> int:
    n = 1
    for papel in PAPEIS:
        n *= len(por_papel.get(papel) or [])
    return n


def validar(por_papel: dict) -> None:
    nomes = {"gancho": "gancho", "corpo": "corpo", "cta": "CTA"}
    for papel in PAPEIS:
        if not por_papel.get(papel):
            raise MultiplicadorInvalido(
                f"faltou pelo menos 1 vídeo de {nomes[papel]}")
    total = contar_combos(por_papel)
    if total > TETO_COMBOS:
        raise MultiplicadorInvalido(
            f"{total} combinações passam do teto de {TETO_COMBOS} — "
            "tire alguma variação")


def preparar_pasta_mae(
    projects_root: Path,
    arquivos: dict[str, list[tuple[str, Path, bool]]],
) -> tuple[Path, dict[str, list[Path]]]:
    """Guarda cada fonte UMA vez em `*_multiplicador-fontes_*`.

    `arquivos`: {papel: [(nome_original, caminho_atual, mover), ...]} na ordem
    em que o usuário pôs na caixa. `mover=True` para upload (o arquivo está
    num temporário); importação por caminho copia, como o import normal — o
    mesmo lote pode misturar os dois (escolher pelo app + arrastar).
    """
    validar(arquivos)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    mae = Path(projects_root) / f"{stamp}_multiplicador-fontes_{uuid.uuid4().hex[:8]}"
    mae.mkdir(parents=True, exist_ok=True)
    fontes: dict[str, list[Path]] = {}
    for papel in PAPEIS:
        fontes[papel] = []
        for i, (nome, origem, mover) in enumerate(arquivos[papel], start=1):
            origem = Path(origem)
            sufixo = Path(nome).suffix or origem.suffix or ".mp4"
            # O prefixo identifica papel e ordem no NOME (g1-, c2-, cta3-);
            # o resto do nome original fica, para o usuário reconhecer o take.
            dest = mae / f"{_PREFIXO[papel]}{i}-{Path(nome).stem}{sufixo}"
            if mover:
                shutil.move(str(origem), str(dest))
            else:
                shutil.copy2(origem, dest)
            fontes[papel].append(dest)
    return mae, fontes


def materializar_combos(
    projects_root: Path,
    fontes: dict[str, list[Path]],
    *,
    intent: dict | None = None,
) -> list[dict]:
    """Um projeto por combinação. Devolve [{id,name,source,sources,editDir,projectDir}]."""
    validar(fontes)
    projects_root = Path(projects_root)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out: list[dict] = []
    ordem = [list(enumerate(fontes[papel], start=1)) for papel in PAPEIS]
    for (ig, g), (ic, c), (ik, k) in product(*ordem):
        job_id = uuid.uuid4().hex[:10]
        rotulo = f"G{ig}C{ic}A{ik}"
        project = projects_root / f"{stamp}_{rotulo}_{job_id}"
        project.mkdir(parents=True, exist_ok=True)
        copiados: list[Path] = []
        for fonte in (g, c, k):
            dest = project / Path(fonte).name
            try:
                os.link(fonte, dest)
            except OSError:
                shutil.copy2(fonte, dest)
            copiados.append(dest)
        edit = project / "edit"
        edit.mkdir(parents=True, exist_ok=True)
        if intent:
            try:
                from app.editing_intent import save as save_intent

                save_intent(edit, dict(intent))
            except Exception:  # noqa: BLE001
                pass
        nome = f"G{ig} · C{ic} · CTA{ik}"
        out.append({
            "id": job_id,
            "name": nome,
            "source": str(copiados[0]),
            "sources": [str(p) for p in copiados],
            "editDir": str(edit),
            "projectDir": str(project),
        })
    return out
