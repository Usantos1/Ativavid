"""Legenda .srt do vídeo curto (5.0.43).

O vídeo sai com a legenda QUEIMADA. YouTube, LinkedIn e o leitor de tela
querem a legenda como arquivo (.srt) — e só o longform gerava um. Aqui o
.srt nasce do que foi desenhado: `caption-cues.json` (uma cue por bloco,
com as linhas e o tempo de cada palavra), o mesmo arquivo que o motor lê.
Sem ele, cai no `captions.json` (palavras soltas) agrupado em blocos.

O arquivo vai para a pasta de entrega (a que "Abrir pasta" abre) e para o
`edit/`; nunca sobrescreve um .srt que a pessoa tenha editado à mão fora
do app (compara o conteúdo antes).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

NOME = "legendas.srt"


def _tempo(ms: float) -> str:
    ms = max(0, int(round(ms)))
    h, resto = divmod(ms, 3_600_000)
    m, resto = divmod(resto, 60_000)
    s, mil = divmod(resto, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{mil:03d}"


def _blocos_das_cues(cues: list) -> list[tuple[int, int, str]]:
    fora: list[tuple[int, int, str]] = []
    for c in cues:
        if not isinstance(c, dict):
            continue
        linhas = c.get("lines") or []
        palavras: list[str] = []
        for ln in linhas:
            if isinstance(ln, list):
                palavras.extend(str(w.get("text") or "") for w in ln if isinstance(w, dict))
        texto = " ".join(p for p in palavras if p).strip()
        if not texto:
            continue
        fora.append((int(c.get("startMs") or 0), int(c.get("endMs") or 0), texto))
    return fora


def _blocos_das_palavras(palavras: list, max_palavras: int = 7,
                         max_ms: int = 2800) -> list[tuple[int, int, str]]:
    fora: list[tuple[int, int, str]] = []
    atual: list[str] = []
    ini = fim = 0
    for w in palavras:
        if not isinstance(w, dict) or not str(w.get("text") or "").strip():
            continue
        s, e = int(w.get("startMs") or 0), int(w.get("endMs") or 0)
        if atual and (len(atual) >= max_palavras or e - ini > max_ms):
            fora.append((ini, fim, " ".join(atual)))
            atual = []
        if not atual:
            ini = s
        atual.append(str(w["text"]).strip())
        fim = max(fim, e)
    if atual:
        fora.append((ini, fim, " ".join(atual)))
    return fora


def blocos_do_projeto(edit: Path) -> list[tuple[int, int, str]]:
    public = Path(edit) / "remotion" / "public"
    for nome, monta in (("caption-cues.json", _blocos_das_cues),
                        ("captions.json", _blocos_das_palavras)):
        p = public / nome
        if not p.is_file():
            continue
        try:
            dados = json.loads(p.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if isinstance(dados, list):
            blocos = monta(dados)
            if blocos:
                return blocos
    return []


def srt_do_projeto(edit: Path) -> str:
    linhas: list[str] = []
    for i, (ini, fim, texto) in enumerate(blocos_do_projeto(edit), start=1):
        if fim <= ini:
            fim = ini + 500
        linhas += [str(i), f"{_tempo(ini)} --> {_tempo(fim)}", texto, ""]
    return "\n".join(linhas)


def salvar_srt(edit: Path) -> dict:
    """Grava o .srt no edit/ e na pasta de entrega. Devolve {ok, path, blocos}."""
    edit = Path(edit)
    texto = srt_do_projeto(edit)
    if not texto.strip():
        return {"ok": False, "error": "este vídeo não tem legenda para exportar"}
    destino = edit / NOME
    if not (destino.is_file() and destino.read_text(encoding="utf-8", errors="replace") == texto):
        destino.write_text(texto, encoding="utf-8")
    final = destino
    try:
        # A MESMA pasta que "Abrir pasta" abre (o pacote de entrega dentro
        # do projeto; `read_pack_dir` sozinho recusa pasta fora dele).
        from app.delivery_pack import folder_to_open

        pasta = folder_to_open(edit)
        if pasta and pasta.is_dir() and pasta.resolve() != edit.resolve():
            alvo = pasta / NOME
            if not (alvo.is_file() and alvo.read_text(encoding="utf-8", errors="replace") == texto):
                shutil.copyfile(destino, alvo)
            final = alvo
    except Exception:  # noqa: BLE001 — sem pasta de entrega, fica o do edit/
        pass
    return {"ok": True, "path": str(final), "blocos": texto.count("-->")}
