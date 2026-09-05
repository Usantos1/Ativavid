"""Busca pelo que foi DITO no vídeo (5.0.43).

A busca dos Concluídos e dos Projetos olhava título e nome de arquivo. Com
centenas de vídeos, o que a pessoa lembra é a frase — "aquele em que eu
falo do carregador" — e isso está na transcrição (`captions.json`) e na
legenda do post (`legenda.txt`), não no título.

O texto de cada projeto é lido uma vez e guardado por (mtime dos arquivos):
331 projetos custam ~1 s frio e nada quente. Acentos e maiúsculas não
contam ("VÍDEO" acha "video").
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

# edit_dir -> (mtimes das fontes, texto normalizado)
_CACHE: dict[str, tuple[tuple[float, ...], str]] = {}

MINIMO = 2  # letras; abaixo disso toda lista casa e a busca não diz nada


def normalizar(s: str) -> str:
    """Minúsculas, sem acento, espaços colapsados."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _fontes(edit: Path) -> list[Path]:
    return [edit / "legenda.txt",
            edit / "remotion" / "public" / "captions.json",
            edit / "transcripts" / "transcript.txt"]


def texto_do_projeto(edit: Path) -> str:
    """Tudo que foi dito/escrito no projeto, normalizado, com cache por mtime."""
    fontes = _fontes(edit)
    marcas: list[float] = []
    for f in fontes:
        try:
            marcas.append(f.stat().st_mtime)
        except OSError:
            marcas.append(0.0)
    chave = str(edit)
    guardado = _CACHE.get(chave)
    if guardado and guardado[0] == tuple(marcas):
        return guardado[1]
    partes: list[str] = []
    for f, m in zip(fontes, marcas):
        if not m:
            continue
        try:
            bruto = f.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        if f.suffix == ".json":
            try:
                dados = json.loads(bruto)
            except ValueError:
                continue
            if isinstance(dados, list):
                partes.append(" ".join(
                    str(c.get("text") or "") for c in dados if isinstance(c, dict)))
        else:
            partes.append(bruto)
    texto = normalizar(" ".join(partes))
    _CACHE[chave] = (tuple(marcas), texto)
    return texto


def buscar(jobs: list[dict], termo: str, limite: int = 500) -> list[str]:
    """Ids dos jobs em cujo texto o termo aparece (substring, sem acento)."""
    q = normalizar(termo)
    if len(q) < MINIMO:
        return []
    achados: list[str] = []
    for j in jobs:
        if not isinstance(j, dict):
            continue
        edit = str(j.get("editDir") or "")
        if not edit or not j.get("id"):
            continue
        if q in texto_do_projeto(Path(edit)):
            achados.append(str(j["id"]))
            if len(achados) >= limite:
                break
    return achados
