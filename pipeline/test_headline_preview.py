# -*- coding: utf-8 -*-
"""O overlay da headline no editor tem de dar o MESMO layout que o motor.

O overlay existe para o usuário arrastar a headline até onde ele quer. Se a
caixa que ele arrasta tem outra altura que a desenhada, a posição escolhida
está errada — e mais ainda na `manchete`, que se ancora pela BASE, onde a
altura da caixa entra direto na conta.

Aqui a largura do texto é substituída, dos DOIS lados, por uma métrica
sintética idêntica. O que sobra a comparar é só o algoritmo: onde quebra a
linha e que tamanho de fonte sai. É essa transcrição que pode sair errada —
as métricas reais vêm do mesmo arquivo de fonte nos dois motores.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.render_proprio import Renderizador, ancoras_de_headline  # noqa: E402

NOWIN = {"creationflags": subprocess.CREATE_NO_WINDOW} if hasattr(subprocess, "CREATE_NO_WINDOW") else {}

# Métrica sintética: larguras diferentes por caractere e sensíveis ao peso,
# para que a escolha da quebra não seja trivialmente "no meio".
LARG_JS = """
function larg(txt, tam, peso) {
  let soma = 0;
  for (const c of txt) soma += (c.codePointAt(0) % 7) + 3;
  return soma * 10 * (tam / 100) * (1 + (peso - 800) / 2000);
}
"""


def _larg_py(txt: str, tam: float, peso: int) -> float:
    soma = sum((ord(c) % 7) + 3 for c in txt)
    return soma * 10 * (tam / 100) * (1 + (peso - 800) / 2000)


TEXTOS = [
    "ola",
    "ola mundo",
    "o segredo que ninguem te conta sobre isso",
    "tres passos para dobrar seu faturamento hoje",
    "por que voce ainda nao consegue",
    "a b c d e f g h i j k l m n o p",
]


def _js_layouts() -> list[dict]:
    """Roda hlEstilo/hlLayout do app.js no node, com a métrica trocada."""
    src = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    trechos = []
    for nome in ("function hlLayout(", "function hlEstilo("):
        i = src.index(nome)
        # a função vai até a linha que fecha na coluna 0
        fim = src.index("\n}\n", i) + 3
        trechos.append(src[i:fim])
    prog = "\n".join([
        LARG_JS,
        "const hlLargura = larg;",
        # hlEstilo lê o estado da página; aqui o estilo entra pronto
        trechos[0],
        f"const ANCORAS = {json.dumps(ancoras_de_headline())};",
        f"const TEXTOS = {json.dumps(TEXTOS, ensure_ascii=False)};",
        """
const out = [];
for (const [nome, a] of Object.entries(ANCORAS)) {
  const e = {maiuscula: !!a.maiuscula, pesos: a.pesos, cap: a.cap,
             safeWidth: a.safeWidth, lineHeight: a.lineHeight, minimo: a.minimo};
  for (const t of TEXTOS) {
    const texto = e.maiuscula ? t.toUpperCase() : t;
    out.push({estilo: nome, texto: t, ...hlLayout(texto, e)});
  }
}
console.log(JSON.stringify(out));
""",
    ])
    r = subprocess.run([("node.exe" if sys.platform == "win32" else "node"), "-e", prog],
                       capture_output=True, text=True, **NOWIN)
    if r.returncode != 0:
        pytest.fail(f"node falhou: {r.stderr[-600:]}")
    return json.loads(r.stdout)


def test_o_overlay_quebra_e_dimensiona_como_o_motor(monkeypatch):
    monkeypatch.setattr(Renderizador, "_larg_hl",
                        lambda self, t, tam, peso=900: _larg_py(t, tam, peso))
    r = Renderizador.__new__(Renderizador)
    r.marca_hook = None
    divergencias = []
    for caso in _js_layouts():
        e = ancoras_de_headline()[caso["estilo"]]
        texto = caso["texto"].upper() if e["maiuscula"] else caso["texto"]
        linhas, tam = r._hl_linhas(texto, e["pesos"], e["cap"], e["safeWidth"])
        if linhas != caso["linhas"] or tam != caso["tam"]:
            divergencias.append(
                f'{caso["estilo"]}/{caso["texto"][:24]!r}: '
                f'motor {linhas} {tam}px vs editor {caso["linhas"]} {caso["tam"]}px')
    assert not divergencias, "\n".join(divergencias)


def test_o_editor_nao_guarda_copia_da_tipografia():
    """A tabela de estilos mora no motor. Uma segunda cópia no JavaScript
    sairia de sincronia calada — foi o que aconteceu com as âncoras antes."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function hlEstilo(")
    bloco = js[i:js.index("\n}\n", i)]
    assert "HL_ANCORAS[" in bloco, "a tipografia tem de vir do endpoint"
    # nenhum dos tetos de fonte do motor pode estar escrito no JS como tabela
    tetos = sorted({str(v["cap"]) for v in ancoras_de_headline().values()})
    achados = [t for t in tetos if len(re.findall(rf"\b{t}\b", bloco)) > 0]
    assert len(achados) <= 1, f"parece tabela copiada: {achados}"


def test_o_endpoint_entrega_a_tipografia():
    for nome, v in ancoras_de_headline().items():
        for k in ("base", "px", "maiuscula", "pesos", "cap", "safeWidth",
                  "lineHeight", "minimo"):
            assert k in v, f"{nome} sem {k}"
        assert len(v["pesos"]) == 2
    assert ancoras_de_headline()["manchete"]["base"] == "bottom"
    assert {n for n, v in ancoras_de_headline().items() if v["maiuscula"]} == \
        set(Renderizador.HL_MAIUSCULA)
