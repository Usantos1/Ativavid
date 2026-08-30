# -*- coding: utf-8 -*-
"""A tela de Presets grava na marca que ela está MOSTRANDO.

O servidor lista os presets da marca ATIVA do disco. A tela, porém, montava o
`brandId` das mutações a partir de `state.brandActive` — que só é preenchido
por `loadBrandsUi()`. Abrir Presets direto, sem passar pela tela de Marca,
deixava isso em `"padrao"`.

Resultado: você via os presets do "Prime Camp" (`loja-teste`) e criar, renomear
ou apagar ia para a marca `padrao`. A lista na sua frente nem se mexia, então
parecia que o botão não funcionou — enquanto o preset de outra marca mudava.

Conferido no navegador com `state.brandActive = null`, que é o cenário exato:
o servidor lista `loja-teste`, a versão antiga gravaria em `padrao`, a nova
grava em `loja-teste`.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

JS = REPO / "assets" / "studio" / "studio.js"
PY = REPO / "app" / "local_server.py"


def test_a_tela_usa_a_marca_que_o_servidor_listou():
    js = JS.read_text(encoding="utf-8")
    i = js.index("state.presetBrandId =")
    linha = js[i:js.index("\n", i)]
    assert "pack.brandId" in linha, (
        "a tela voltou a adivinhar a marca em vez de usar a que foi listada"
    )
    assert linha.index("pack.brandId") < linha.index("state.brandActive"), (
        "`state.brandActive` tem precedência de novo — ele é nulo quando a tela "
        "de Marca não foi aberta, e aí a mutação vai para 'padrao'"
    )


def test_a_tela_pega_a_marca_do_servidor_e_nao_do_proprio_estado():
    """O rótulo nomeava a marca listada — ele saiu na 4.19, junto com a
    palavra "marca" na tela. O que ele protegia continua de pé, e é a parte
    que importa: quem manda é a marca que o SERVIDOR listou. Pelo estado da
    tela, abrir Presets direto deixava isto em "padrao", e criar, renomear e
    apagar iam todos para a marca errada."""
    js = JS.read_text(encoding="utf-8")
    base = js.index("async function loadPresetsUi(")
    i = js.index("state.presetBrandId = ", base)
    linha = js[i:js.index("\n", i)]
    assert "pack.brandId" in linha, linha


def test_o_servidor_diz_qual_marca_listou():
    py = PY.read_text(encoding="utf-8")
    i = py.index('if path == "/api/brand-presets":')
    bloco = py[i:i + 1600]
    assert '"brandName": nome' in bloco, "a resposta não nomeia a marca listada"
    # `brandId` ja vem do pack (brand_presets.load/_empty); o teste abaixo prova
    assert "**pack" in bloco


def test_o_pack_sempre_carrega_o_brand_id(tmp_path):
    """Os DOIS caminhos — marca com presets e marca vazia — precisam devolver
    `brandId`, senão a tela cai na adivinhação de novo."""
    from app.brand_presets import load as load_presets

    cheio = load_presets("loja-teste", root=tmp_path)
    assert cheio["brandId"] == "loja-teste", "marca sem arquivo perdeu o brandId"
    assert cheio["presets"], "o caminho vazio deveria criar o preset padrão"

    (tmp_path / "loja-teste.json").write_text(
        '{"activeId": "a", "presets": [{"id": "a", "name": "A"}]}', encoding="utf-8")
    com = load_presets("loja-teste", root=tmp_path)
    assert com["brandId"] == "loja-teste"
    assert [p["id"] for p in com["presets"]] == ["a"]
