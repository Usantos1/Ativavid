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
    # O maior item da pasta de um projeto: 636 MB de `node_modules`. Nos
    # projetos do usuario sao 16 copias de verdade (10,7 GB) e 168
    # junctions para uma instalacao compartilhada — por isso a guarda de
    # atalho abaixo nao e opcional.
    "edit/remotion/node_modules",
)

_DIAS_PADRAO = 7


def _e_atalho(p: Path) -> bool:
    """Junction ou symlink de pasta — um ATALHO, nao a pasta.

    O Windows do usuario tem 168 projetos cujo `node_modules` e junction
    para uma instalacao compartilhada. `rglob` e `rmtree` atravessam
    junction: sem esta pergunta, medir contaria o mesmo conteudo 168 vezes
    e limpar apagaria a instalacao que os outros 167 usam.
    """
    try:
        if p.is_symlink():
            return True
        st = os.stat(p, follow_symlinks=False)
    except OSError:
        return False
    # FILE_ATTRIBUTE_REPARSE_POINT. So existe no Windows; noutros sistemas
    # o `is_symlink` acima ja respondeu.
    return bool(getattr(st, "st_file_attributes", 0) & 0x400)


def _tamanho(p: Path) -> int:
    """Bytes que somem se `p` for embora. Atalho nao ocupa disco: zero."""
    if _e_atalho(p):
        return 0
    if p.is_file():
        try:
            return p.stat().st_size
        except OSError:
            return 0
    total = 0
    for raiz, dirs, arquivos in os.walk(p):
        # nao descer por atalho: o conteudo do outro lado nao e deste projeto
        dirs[:] = [d for d in dirs if not _e_atalho(Path(raiz) / d)]
        for f in arquivos:
            try:
                total += os.path.getsize(os.path.join(raiz, f))
            except OSError:
                pass
    return total


def _apagar(p: Path) -> None:
    """Apaga `p`. Atalho e desfeito COMO atalho — o alvo fica de pe."""
    if _e_atalho(p):
        # `rmtree` num junction do Windows entra e apaga o conteudo do
        # outro lado. Aqui so o atalho sai.
        try:
            p.unlink()
        except OSError:
            os.rmdir(p)
        return
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()


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


# Cache da medida dos intermediarios.
#
# Sem ele a tela de Configuracoes demora 6,64s em vez de 0,41s: a conta e
# dominada pelos 16 `node_modules` de verdade (636 MB e ~30 mil arquivos
# cada), e o preco e o `stat` de cada arquivo.
#
# So entra na conta projeto ENTREGUE e PARADO ha uma semana — e o que esta
# parado nao muda de tamanho. A chave e o `mtime` do `result.json`: mexeu
# no projeto, a medida e refeita.
_CACHE_REL = ".ativavid/espaco-cache.json"


def _cache_ler(root: Path) -> dict[str, Any]:
    try:
        d = json.loads((root / _CACHE_REL).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def _cache_gravar(root: Path, dados: dict[str, Any]) -> None:
    alvo = root / _CACHE_REL
    try:
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text(json.dumps(dados), encoding="utf-8")
    except OSError:
        pass    # cache e conforto, nao resultado: falhar aqui nao e erro


def _cache_limpar(root: Path) -> None:
    """Depois de apagar, a medida velha vira mentira."""
    try:
        (root / _CACHE_REL).unlink(missing_ok=True)
    except OSError:
        pass


def _intermediarios(proj: Path) -> int:
    total = 0
    for rel in _REGENERAVEIS:
        p = proj / Path(rel)
        if p.exists():
            total += _tamanho(p)
    for prep in proj.glob("*.prep.mp4"):
        total += _tamanho(prep)
    return total


def medir(projects_root: Path) -> dict[str, Any]:
    dup = 0
    inter = 0
    projetos = 0
    raiz = Path(projects_root)
    cache = _cache_ler(raiz)
    mudou = False
    for proj in sorted(raiz.iterdir()) if raiz.exists() else []:
        if not proj.is_dir() or proj.name.startswith((".", "_")):
            continue
        projetos += 1
        for orig, copia in _duplicatas(proj):
            if _linkavel(orig, copia):
                dup += copia.stat().st_size
        entregue, idade = _e_entregue(proj)
        if entregue and idade >= _DIAS_PADRAO:
            try:
                chave = str((proj / "edit" / "result.json").stat().st_mtime_ns)
            except OSError:
                chave = ""
            guardado = cache.get(proj.name)
            if chave and isinstance(guardado, list) and guardado[:1] == [chave]:
                inter += int(guardado[1])
            else:
                bytes_ = _intermediarios(proj)
                inter += bytes_
                if chave:
                    cache[proj.name] = [chave, bytes_]
                    mudou = True
    if mudou:
        _cache_gravar(raiz, cache)
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
                _apagar(p)
                removido += sz
            except OSError:
                erros += 1
    _cache_limpar(Path(projects_root))
    return {
        "ok": True,
        "deduplicadoGb": round(dedup / (1024 ** 3), 2),
        "removidoGb": round(removido / (1024 ** 3), 2),
        "totalGb": round((dedup + removido) / (1024 ** 3), 2),
        "erros": erros,
    }
