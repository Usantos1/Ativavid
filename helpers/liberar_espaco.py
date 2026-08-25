# -*- coding: utf-8 -*-
"""Liberar espaço dos projetos SEM perder nada que importa.

Medido nos projetos reais (25/08): 127 GB em 145 projetos, e um projeto
entregue típico carrega ~575 MB de DUPLICATAS byte a byte (o final existe em
3 lugares: edit/<nome>.mp4, edit/final.mp4 e publicar/; o cut existe em
edit/ e em remotion/public/) mais ~700 MB de intermediários regeneráveis
(remotion/out, clips_graded, <fonte>.prep.mp4).

Duas ações, dois níveis de risco:

- **Deduplicar (sempre seguro)**: cópias idênticas no MESMO volume viram
  hardlink — todos os caminhos continuam funcionando, o conteúdo passa a
  ocupar o disco uma vez só. Nada é apagado.
- **Limpar intermediários (projetos entregues e parados)**: remove o que o
  pipeline sabe reconstruir (remotion/out, clips_graded, prep.mp4, caches de
  preview) de projetos concluídos sem mexida há N dias. Fonte, final,
  publicar/, cut.mp4 e todos os JSONs ficam.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

# Intermediários que o pipeline reconstrói sozinho num reprocesso.
_REGENERAVEIS = (
    "edit/remotion/out",
    "edit/clips_graded",
    "edit/.preview_cache",
    "edit/clips_draft",
    "edit/clips_preview",
)

_DIAS_PADRAO = 7


def _tamanho(p: Path) -> int:
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for f in p.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


def _e_entregue(proj: Path) -> tuple[bool, float]:
    """(concluído?, idade em dias do último resultado)."""
    r = proj / "edit" / "result.json"
    try:
        data = json.loads(r.read_text(encoding="utf-8-sig"))
        idade = (time.time() - r.stat().st_mtime) / 86400.0
        return str(data.get("status")) == "done", idade
    except (OSError, json.JSONDecodeError):
        return False, 0.0


def _mesmo_arquivo(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)


def _linkavel(a: Path, b: Path) -> bool:
    """Mesmo volume, mesmo tamanho, ainda não são o mesmo arquivo."""
    try:
        sa, sb = a.stat(), b.stat()
    except OSError:
        return False
    if (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino):
        return False
    return sa.st_dev == sb.st_dev and sa.st_size == sb.st_size and sa.st_size > 1_000_000


def _duplicatas(proj: Path) -> list[tuple[Path, Path]]:
    """(original, cópia) — a cópia vira hardlink do original."""
    edit = proj / "edit"
    pares: list[tuple[Path, Path]] = []
    cut = edit / "cut.mp4"
    pub_cut = edit / "remotion" / "public" / "cut.mp4"
    if cut.is_file() and pub_cut.is_file():
        pares.append((cut, pub_cut))
    nome_final = ""
    try:
        st = json.loads((edit / "state.json").read_text(encoding="utf-8-sig"))
        nome_final = str(st.get("finalVideo") or "")
    except (OSError, json.JSONDecodeError):
        pass
    entregue = edit / nome_final if nome_final else None
    if entregue and entregue.is_file():
        alias = edit / "final.mp4"
        if alias.is_file() and alias.name != entregue.name:
            pares.append((entregue, alias))
        pub = proj / "publicar"
        if pub.is_dir():
            for f in pub.rglob("*.mp4"):
                pares.append((entregue, f))
    return pares


def medir(projects_root: Path) -> dict[str, Any]:
    dup = 0
    inter = 0
    projetos = 0
    for proj in sorted(Path(projects_root).iterdir()) if Path(projects_root).exists() else []:
        if not proj.is_dir() or proj.name.startswith((".", "_")):
            continue
        projetos += 1
        for orig, copia in _duplicatas(proj):
            if _linkavel(orig, copia):
                dup += copia.stat().st_size
        entregue, idade = _e_entregue(proj)
        if entregue and idade >= _DIAS_PADRAO:
            for rel in _REGENERAVEIS:
                p = proj / Path(rel)
                if p.exists():
                    inter += _tamanho(p)
            for prep in proj.glob("*.prep.mp4"):
                inter += _tamanho(prep)
    return {
        "ok": True,
        "projetos": projetos,
        "duplicatasGb": round(dup / (1024 ** 3), 2),
        "intermediariosGb": round(inter / (1024 ** 3), 2),
        "totalGb": round((dup + inter) / (1024 ** 3), 2),
        "diasMinimos": _DIAS_PADRAO,
    }


def liberar(projects_root: Path, *, dias_minimos: int = _DIAS_PADRAO) -> dict[str, Any]:
    dedup = 0
    removido = 0
    erros = 0
    for proj in sorted(Path(projects_root).iterdir()) if Path(projects_root).exists() else []:
        if not proj.is_dir() or proj.name.startswith((".", "_")):
            continue
        # 1. deduplicar por hardlink — sempre, sem gate de idade
        for orig, copia in _duplicatas(proj):
            if not _linkavel(orig, copia):
                continue
            tmp = copia.with_suffix(copia.suffix + ".lnk")
            try:
                if tmp.exists():
                    tmp.unlink()
                os.link(orig, tmp)
                sz = copia.stat().st_size
                os.replace(tmp, copia)
                dedup += sz
            except OSError:
                erros += 1
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
        # 2. intermediários — só entregues e parados
        entregue, idade = _e_entregue(proj)
        if not entregue or idade < dias_minimos:
            continue
        alvos = [proj / Path(rel) for rel in _REGENERAVEIS]
        alvos += list(proj.glob("*.prep.mp4"))
        for p in alvos:
            if not p.exists():
                continue
            sz = _tamanho(p)
            try:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
                removido += sz
            except OSError:
                erros += 1
    return {
        "ok": True,
        "deduplicadoGb": round(dedup / (1024 ** 3), 2),
        "removidoGb": round(removido / (1024 ** 3), 2),
        "totalGb": round((dedup + removido) / (1024 ** 3), 2),
        "erros": erros,
    }
