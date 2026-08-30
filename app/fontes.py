# -*- coding: utf-8 -*-
"""As fontes que o usuario poe em ~/ATIVAVID/Fontes, pelo NOME delas.

"cade a fonte Integral que pedi pra voce instalar?" (30/08). Estava
instalada desde 29/08 — `Fontspring-DEMO-integralcf-bold.otf`, na pasta
certa, funcionando. O que faltava era a lista dizer o nome: a unica opcao
do seletor se chamava "Sua fonte (pasta Fontes)", e nenhuma tela do app
mostrava QUAL fonte era essa.

E havia um limite calado atras disso: o pipeline pegava o PRIMEIRO
arquivo em ordem alfabetica. Com duas fontes na pasta, a segunda nunca
tocava e nada dizia por que.

O nome sai do proprio arquivo (o Pillow le a tabela `name`), nao do nome
do arquivo: `Fontspring-DEMO-integralcf-bold.otf` vira **"FONTSPRING DEMO
- Integral CF Bold"**, que e onde a palavra "Integral" aparece.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

EXTS = (".ttf", ".otf", ".woff2", ".woff")

ACENTOS_PT = "ÁÃÂÀÉÊÍÓÔÕÚÇáãâàéêíóôõúç!?"


def acentos_que_faltam(arquivo: Path) -> str:
    """Letras do portugues que a fonte nao desenha DE VERDADE.

    Fonte de demonstracao nao deixa a letra faltando: ela MAPEIA o acento
    para um carimbo ("DEMO"). Por isso comparar com o glifo de ausente
    (.notdef) nao acha nada — a assinatura e outra: varios caracteres
    DIFERENTES saem com o desenho identico.

    Caso real (29/08): a Integral CF demo escrevia "N[DEMO]O MORRE[DEMO]"
    onde devia sair "NAO MORRE!" — e isso so aparecia no video pronto.

    (Nasceu no `run_fast`, que avisava DEPOIS do render. Mudou de casa em
    4.25 para a lista de fontes avisar na hora de escolher.)
    """
    try:
        from PIL import ImageFont

        f = ImageFont.truetype(str(arquivo), 64)

        def _desenho(ch: str) -> tuple:
            # `bytes(mask)`, nao `mask.tobytes()`: o objeto do Pillow nao
            # tem esse metodo, e o try/except engolia o AttributeError —
            # a checagem dizia "nenhum acento faltando" justamente para a
            # fonte que carimbava DEMO em todos eles.
            m = f.getmask(ch)
            return (m.size, bytes(m))

        ausente = _desenho("")
        grupos: dict[tuple, list[str]] = {}
        for c in ACENTOS_PT:
            grupos.setdefault(_desenho(c), []).append(c)
        faltam: list[str] = []
        for desenho, chars in grupos.items():
            # o proprio .notdef, ou um carimbo que serve a varias letras
            if desenho == ausente or len(chars) >= 3:
                faltam.extend(chars)
        return "".join(c for c in ACENTOS_PT if c in faltam)
    except Exception:  # noqa: BLE001 - checagem nunca derruba o render
        return ""


def pasta() -> Path:
    """~/ATIVAVID/Fontes — a mesma que o `run_fast` copia para o projeto."""
    return Path.home() / "ATIVAVID" / "Fontes"


def _nome_do_arquivo(f: Path) -> str:
    """O nome que a FONTE diz ter. Cai no nome do arquivo se nao der."""
    try:
        from PIL import ImageFont

        fam, estilo = ImageFont.truetype(str(f), 20).getname()
        fam = (fam or "").strip()
        estilo = (estilo or "").strip()
        if fam:
            return f"{fam} {estilo}".strip() if estilo.lower() not in (
                "", "regular", "normal") else fam
    except Exception:  # noqa: BLE001 — arquivo quebrado nao pode sumir da lista
        pass
    return f.stem


def listar() -> list[dict[str, Any]]:
    """As fontes da pasta, em ordem, com nome legivel.

    A ordem e a MESMA que o `_attach_brand_font_file` usa (nome do arquivo
    em minuscula), porque a primeira delas e a que responde pelo id antigo
    `arquivo` — o que estiver salvo nos estilos de antes continua caindo
    exatamente na mesma fonte.
    """
    p = pasta()
    if not p.is_dir():
        return []
    achados = sorted(
        (f for f in p.iterdir()
         if f.is_file() and f.suffix.lower() in EXTS),
        key=lambda f: f.name.lower())
    return [{"arquivo": f.name, "nome": _nome_do_arquivo(f),
             "faltam": acentos_que_faltam(f)} for f in achados]


def escolher(ident: str) -> Path | None:
    """O arquivo por tras de `arquivo` ou `arquivo:<nome do arquivo>`.

    `arquivo` puro = a primeira da pasta, que e o que sempre foi. Nome que
    nao existe mais (fonte apagada) tambem cai na primeira: o render nao
    para por causa de fonte.
    """
    ident = (ident or "").strip()
    if not ident.lower().startswith("arquivo"):
        return None
    p = pasta()
    if not p.is_dir():
        return None
    achados = sorted(
        (f for f in p.iterdir()
         if f.is_file() and f.suffix.lower() in EXTS),
        key=lambda f: f.name.lower())
    if not achados:
        return None
    _, _, alvo = ident.partition(":")
    alvo = alvo.strip().lower()
    if alvo:
        for f in achados:
            if f.name.lower() == alvo:
                return f
    return achados[0]
