# -*- coding: utf-8 -*-
"""A revisão da transcrição sabe o nome da loja.

Medido nas transcrições dos projetos do usuário: `Prime Camp` sai errado
30 vezes — `Prêmio Camp` (4), `Prime Cup` (6), `Prime Camps` (3),
`Prêmio Campo` (3), `PremiCamp` (3), `Prêmica` (3)… — e vai assim para a
legenda, queimada no vídeo.

O revisor já tinha "marcas e nomes próprios" no escopo (o exemplo do
próprio prompt é `praimcamp → PrimeCamp`), mas nunca soube QUAIS marcas.
O app sabe: estão no kit de marca.

Troca automática por semelhança foi medida e recusada: `Prêmio Camp` fica
a 0,737 do alvo e a palavra inocente `prime` a 0,714 — 0,02 de margem.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.transcricao import revisao  # noqa: E402


def test_o_bloco_lista_as_marcas():
    b = revisao._bloco_de_vocabulario(["Prime Camp", "Ativa CRM"])
    assert "Prime Camp" in b and "Ativa CRM" in b


def test_o_bloco_freia_a_troca_por_parecenca():
    """Sem este freio o modelo passa a "corrigir" fala que estava certa."""
    b = revisao._bloco_de_vocabulario(["Prime Camp"])
    baixo = b.lower()
    assert "primeira" in baixo and "prêmio" in baixo
    assert "não troque" in baixo or "nao troque" in baixo


def test_sem_marca_o_prompt_nao_muda():
    assert revisao._bloco_de_vocabulario([]) == ""


def test_o_vocabulario_nunca_levanta(monkeypatch):
    """Kit ilegível não pode derrubar a transcrição do vídeo."""
    import app.brand_kits as bk

    def explode():
        raise OSError("kit ilegível")

    monkeypatch.setattr(bk, "list_brands", explode)
    assert revisao.vocabulario() == []


def test_o_bloco_entra_no_pedido():
    """Sem isto o vocabulário existe e nunca chega ao modelo."""
    fonte = (REPO / "app" / "transcricao" / "revisao.py").read_text(
        encoding="utf-8")
    i = fonte.index("def pedir_correcoes(")
    corpo = fonte[i:i + 1200]
    assert "_bloco_de_vocabulario(vocabulario())" in corpo


def test_a_versao_subiu_junto_com_o_prompt():
    """A versão é a chave do cache: mantendo `rev1`, vídeo já revisado
    nunca veria o nome certo da loja."""
    assert revisao.VERSAO == "rev2"
