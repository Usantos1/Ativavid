# -*- coding: utf-8 -*-
"""Função de dentro que ESCREVE numa variável de fora, sem `nonlocal`.

Achado nos dados do usuário (30/08), no `timing.json` de 3 dos 174
projetos:

    overlayUmaPassadaFalhou: UnboundLocalError: cannot access local
    variable 'progresso' where it is not associated with a value

`render_final_uma_passada` recebe `progresso`; a função interna
`_passada` LÊ essa variável a cada quadro e, quando quem escuta quebra,
faz `progresso = None`. Essa atribuição torna o nome local da `_passada`
— e a leitura, no primeiro quadro, estoura. Efeito: com barra de
progresso ligada, a passada única levantava SEMPRE e o render caía no
caminho de duas etapas, que escreve um `overlay.mov` de ~150 MB e o lê de
volta. Ficava só no timing.json, calado.

O teste varre o código à procura da MESMA forma: função aninhada que lê
um nome do escopo de fora e também o atribui, sem declarar `nonlocal`.
Não é lint genérico — é este defeito, que já custou o caminho rápido.
"""
import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

PASTAS = ("app", "pipeline", "helpers", "tools")


def _nomes_atribuidos(fn: ast.FunctionDef) -> set[str]:
    """Nomes que ESTA função atribui, sem entrar nas funções de dentro."""
    out: set[str] = set()
    for no in ast.walk(fn):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no is not fn:
            continue
        if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
            out.add(no.id)
    return out


def _nomes_lidos(fn: ast.FunctionDef) -> set[str]:
    out: set[str] = set()
    for no in ast.walk(fn):
        if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load):
            out.add(no.id)
    return out


def _declarados(fn: ast.FunctionDef) -> set[str]:
    out: set[str] = set()
    for no in ast.walk(fn):
        if isinstance(no, (ast.Nonlocal, ast.Global)):
            out.update(no.names)
    return out


def _params(fn) -> set[str]:
    a = fn.args
    todos = [*a.posonlyargs, *a.args, *a.kwonlyargs]
    if a.vararg:
        todos.append(a.vararg)
    if a.kwarg:
        todos.append(a.kwarg)
    return {x.arg for x in todos}


def _amarrados_por_for(fn) -> set[str]:
    """Nomes que a propria funcao amarra em `for` ou comprehension."""
    out: set[str] = set()
    for no in ast.walk(fn):
        if isinstance(no, (ast.For, ast.AsyncFor)):
            alvo = no.target
            for x in ast.walk(alvo):
                if isinstance(x, ast.Name):
                    out.add(x.id)
        if isinstance(no, (ast.ListComp, ast.SetComp, ast.DictComp,
                           ast.GeneratorExp)):
            for g in no.generators:
                for x in ast.walk(g.target):
                    if isinstance(x, ast.Name):
                        out.add(x.id)
    return out


def _le_antes_de_escrever(fn, nome: str) -> bool:
    """A primeira aparicao do nome nesta funcao e uma LEITURA?

    E o que separa o defeito da sombra legitima: `progresso` era lido no
    primeiro quadro e atribuido so no `except`, entao a leitura acontecia
    com o nome ja local e ainda sem valor.
    """
    pontos = []
    for no in ast.walk(fn):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no is not fn:
            continue
        if isinstance(no, ast.Name) and no.id == nome:
            pontos.append((no.lineno, no.col_offset,
                           isinstance(no.ctx, ast.Load)))
    if not pontos:
        return False
    pontos.sort()
    return pontos[0][2]


def _suspeitas(caminho: Path) -> list[str]:
    try:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    achados: list[str] = []

    def _ver(fn, de_fora: set[str]) -> None:
        meus = _params(fn) | _nomes_atribuidos(fn)
        for filho in ast.walk(fn):
            if filho is fn or not isinstance(filho, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # só o primeiro nível de aninhamento desta função
            if getattr(filho, "_visto", False):
                continue
            filho._visto = True
            # So PARAMETROS da funcao de fora, e so nomes que a de dentro
            # nao amarra em `for`/comprehension. Sem esses dois filtros a
            # varredura acusa dezenas de sombras legitimas (`for x in ...`
            # dentro de uma comprehension aparece como escrita no mesmo
            # escopo para o `ast`), e um teste cheio de excecao apodrece.
            escritos = (_nomes_atribuidos(filho) - _params(filho)
                        - _amarrados_por_for(filho))
            meus = _params(fn)
            # So conta quando a LEITURA vem antes da escrita. `x = calc();
            # usa(x)` dentro da funcao interna e sombra legitima e aparece
            # em dezenas de lugares; o defeito e ler primeiro (e ai o nome
            # ja e local e ainda nao tem valor) e atribuir depois.
            perigo = {n for n in (escritos & meus & _nomes_lidos(filho))
                      if _le_antes_de_escrever(filho, n)} - _declarados(filho)
            for nome in sorted(perigo):
                achados.append(
                    f"{caminho.relative_to(REPO)}:{filho.lineno} "
                    f"{fn.name}() → {filho.name}() escreve e lê '{nome}' sem nonlocal")
            _ver(filho, de_fora | meus)

    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _ver(no, set())
        elif isinstance(no, ast.ClassDef):
            for m in no.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _ver(m, set())
    return achados


def test_nenhuma_funcao_de_dentro_escreve_sem_nonlocal():
    achados: list[str] = []
    for pasta in PASTAS:
        base = REPO / pasta
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*.py")):
            if "node_modules" in str(f):
                continue
            achados.extend(_suspeitas(f))
    assert not achados, "\n".join(achados)


def test_o_teste_pega_o_defeito_que_aconteceu(tmp_path):
    """Sem o caso positivo, o de cima passaria com a varredura quebrada."""
    ruim = tmp_path / "ruim.py"
    ruim.write_text(
        "def fora(progresso=None):\n"
        "    def dentro():\n"
        "        if progresso is not None:\n"
        "            progresso = None\n"
        "    return dentro\n", encoding="utf-8")
    # a varredura mede caminhos relativos ao REPO; aqui basta o parse
    achados = []
    arvore = ast.parse(ruim.read_text(encoding="utf-8"))
    fn = arvore.body[0]
    interna = fn.body[0]
    perigo = {n for n in ((_nomes_atribuidos(interna) - _params(interna))
                          & (_params(fn) | _nomes_atribuidos(fn))
                          & _nomes_lidos(interna))
              if _le_antes_de_escrever(interna, n)} - _declarados(interna)
    achados.extend(sorted(perigo))
    assert achados == ["progresso"], achados


def test_a_passada_unica_declara_nonlocal():
    src = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    i = src.index("def _passada(enc: str, extra: list[str]) -> bool:")
    assert "nonlocal progresso" in src[i:i + 900]
