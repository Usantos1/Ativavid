# -*- coding: utf-8 -*-
"""Criar marca nova nao pode apagar a marca ativa.

O botao "Criar com o estilo atual" mandava `...preset` para /api/brands, e o
preset carrega o `brandId` da marca ATIVA. Como `save_brand` lia `brandId`
antes do nome, o arquivo gravado era o da marca ativa: o nome digitado apenas
a renomeava, ela sumia e nenhuma marca nova aparecia — com o toast dizendo
"Marca salva e ativada".

Nao e hipotese. Nesta maquina as DUAS marcas do usuario tem o nome de exibicao
discordando do arquivo (`brands/loja-teste.json` chamando "Prime Camp" e
`brands/padrao.json` chamando "Uander"), que e exatamente a marca do atropelo.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture()
def marcas(tmp_path, monkeypatch):
    from app import brand_kits

    d = tmp_path / "brands"
    d.mkdir()
    monkeypatch.setattr(brand_kits, "BRANDS_DIR", d)
    monkeypatch.setattr(brand_kits, "ensure_brands_dir", lambda: d.mkdir(exist_ok=True))
    return d


def _ler(d: Path) -> dict[str, str]:
    return {
        p.stem: json.loads(p.read_text(encoding="utf-8"))["brandName"]
        for p in d.glob("*.json")
    }


def test_nome_diferente_com_mesmo_slug_nao_atropela(marcas):
    """A guarda do servidor. Dois nomes DISTINTOS podem virar o mesmo slug —
    e ai a gravacao caia em cima da marca que ja estava la.

    Com nomes que dao slugs diferentes o defeito nao aparece: o arquivo novo
    nasce ao lado e o teste passa igual, com ou sem a correcao. Por isso aqui
    os nomes colidem de proposito.
    """
    from app.brand_kits import save_brand

    save_brand({"brandName": "Prime Camp", "accent": "#ff5200"})
    assert _ler(marcas) == {"prime-camp": "Prime Camp"}

    save_brand({"brandName": "Prime  camp!", "accent": "#00aaff"})
    depois = _ler(marcas)
    assert depois.get("prime-camp") == "Prime Camp", "a marca antiga foi atropelada"
    assert "Prime  camp!" in depois.values(), "a marca nova nao nasceu"
    assert len(depois) == 2


def test_criar_marca_nova_preserva_a_anterior(marcas):
    from app.brand_kits import save_brand

    save_brand({"brandName": "Prime Camp", "accent": "#ff5200"})
    save_brand({"brandName": "Cliente X", "accent": "#ff5200"})
    depois = _ler(marcas)
    assert depois["prime-camp"] == "Prime Camp"
    assert "Cliente X" in depois.values()
    assert len(depois) == 2


def test_mesmo_nome_e_atualizacao_e_nao_duplica(marcas):
    from app.brand_kits import save_brand

    save_brand({"brandName": "Prime Camp", "accent": "#ff5200"})
    save_brand({"brandName": "Prime Camp", "accent": "#00aaff"})
    arquivos = _ler(marcas)
    assert arquivos == {"prime-camp": "Prime Camp"}
    j = json.loads((marcas / "prime-camp.json").read_text(encoding="utf-8"))
    assert j["accent"] == "#00aaff", "atualizar a mesma marca deve valer"


def test_brand_id_explicito_ainda_atualiza_aquela_marca(marcas):
    """Renomear uma marca EXISTENTE continua funcionando: quem manda brandId
    esta dizendo qual marca quer, e essa e a intencao da tela de editar."""
    from app.brand_kits import save_brand

    save_brand({"brandName": "Prime Camp"})
    save_brand({"brandId": "prime-camp", "brandName": "Prime Camp Oficial"})
    assert _ler(marcas) == {"prime-camp": "Prime Camp Oficial"}


def test_o_botao_de_criar_nao_manda_a_identidade_da_ativa():
    """A metade do cliente. Sem isto o servidor recebe o brandId da ativa e a
    guarda acima nem chega a ser consultada (brandId explicito = atualizar)."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index('$("#brandNewName")')
    trecho = js[i:i + 2000]
    assert "brandId: _bid" in trecho, "o brandId da marca ativa ainda vai no corpo"
    assert not re.search(r"\.\.\.preset,\s*\n\s*brandName", trecho), (
        "ainda espalha o preset inteiro, que carrega brandId"
    )
