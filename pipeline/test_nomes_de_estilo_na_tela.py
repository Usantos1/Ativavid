# -*- coding: utf-8 -*-
"""A tela de Presets mostra nome, não id interno.

O cartão do preset dizia `LAYOUT limpa · LEGENDA stacked · MANCHETE realce
· RITMO dinamico` e, embaixo, `informational` — numa tela que existe
justamente para o usuário entender o que o preset decide. Os nomes já
existiam em quatro lugares; só esta tela não os usava.

O mapa mora no `studio.js` porque é rótulo de tela. Este teste é o que
impede a cópia de apodrecer: estilo novo sem nome aqui quebra aqui, e não
volta calado para a tela como id cru.
"""
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import caption_styles, content_type, video_layouts  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
PREVIEW = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def _mapa(eixo: str) -> dict:
    """Lê um eixo do NOME_DO_ESTILO sem executar JavaScript."""
    i = JS.index("const NOME_DO_ESTILO = {")
    j = JS.index("\n};", i)
    bloco = JS[i:j]
    k = bloco.index(f"  {eixo}: {{")
    fim = bloco.index("\n  },", k)
    corpo = bloco[bloco.index("{", k) + 1:fim]
    out = {}
    for chave, valor in re.findall(r'([A-Za-z_][\w]*)\s*:\s*"([^"]*)"', corpo):
        out[chave] = valor
    assert out, eixo
    return out


def test_todo_estilo_de_legenda_tem_nome_na_tela():
    faltam = sorted(set(caption_styles.NOMES) - set(_mapa("legenda")))
    assert not faltam, f"sem nome na tela de Presets: {faltam}"


def test_o_nome_da_legenda_e_o_mesmo_do_resto_do_app():
    tela = _mapa("legenda")
    difere = {k: (v, tela[k]) for k, v in caption_styles.NOMES.items()
              if tela.get(k) != v}
    assert not difere, f"nome divergente: {difere}"


def test_todo_layout_tem_nome_na_tela():
    tela = _mapa("layout")
    faltam = sorted(set(video_layouts.TODOS) - set(tela))
    assert not faltam, f"sem nome na tela de Presets: {faltam}"
    difere = {k: (v, tela[k]) for k, v in video_layouts.TODOS.items()
              if tela.get(k) != v}
    assert not difere, f"nome divergente: {difere}"


def test_todo_tipo_de_conteudo_tem_nome_na_tela():
    fonte = dict(content_type.LABELS)
    tela = _mapa("tipo")
    difere = {k: (v, tela.get(k)) for k, v in fonte.items() if tela.get(k) != v}
    assert not difere, f"nome divergente ou faltando: {difere}"


def test_toda_manchete_do_catalogo_tem_nome_na_tela():
    """O catálogo de manchetes vive no preview — é a fonte de verdade."""
    i = PREVIEW.index("  headlines: [")
    bloco = PREVIEW[i:PREVIEW.index("\n  captions: [", i)]
    fonte = dict(re.findall(r"\{id:\s*'([^']+)',\s*name:\s*'([^']+)'", bloco))
    assert len(fonte) > 10, f"achei so {len(fonte)} manchetes — mudou o padrao?"
    tela = _mapa("manchete")
    difere = {k: (v, tela.get(k)) for k, v in fonte.items() if tela.get(k) != v}
    assert not difere, f"nome divergente ou faltando: {difere}"


def test_todo_ritmo_do_preview_tem_nome_na_tela():
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    ids = re.findall(r'class="rhythm-preset[^"]*"\s+data-preset="([^"]+)"', html)
    assert ids, "não achei os ritmos no preview"
    tela = _mapa("ritmo")
    faltam = [i for i in ids if i not in tela]
    assert not faltam, f"ritmo sem nome na tela: {faltam}"


def test_id_desconhecido_aparece_como_veio():
    """Versão mais nova pode trazer id que este mapa não conhece: mostrar o
    id é feio, esconder o valor seria pior."""
    i = JS.index("function nomeDoEstilo(")
    corpo = JS[i:i + 400]
    assert "|| v;" in corpo


def test_a_tela_usa_o_mapa():
    assert 'nomeDoEstilo("tipo", p.contentType)' in JS
    for eixo, campo in (("layout", "st.edit"), ("legenda", "st.captions"),
                        ("manchete", "st.headline"), ("ritmo", "st.rhythm")):
        assert f'nomeDoEstilo("{eixo}", {campo})' in JS, eixo
