# -*- coding: utf-8 -*-
"""Vídeo de humor usa os clipes de humor da Biblioteca.

Pedido de 30/08: "quando a gente escolher vídeo de humor usar estes takes
e partes engraçadas... incluir inserções destes e outros takes".

O app já tinha tudo menos a ponte:

  - a Biblioteca aceita vídeo e tem `humor`, `meme`, `reacao`, `viral`;
  - `_attach_auto_broll` sabe colar clipe num momento da fala;
  - o tipo `humor` já manda preservar setup → punchline.

Mas com o layout `limpa` — o dele em 114 de 114 vídeos — as inserções
ficavam desligadas por padrão e a checagem não olhava o TIPO. Com a
Biblioteca cheia de clipes de humor, nenhum entrava.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import broll_library as bl  # noqa: E402

RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _biblioteca(tmp_path, monkeypatch, arquivos: list[str]):
    raiz = tmp_path / "Biblioteca"
    # `clips` é o nome no DISCO (`list_assets`); a tela chama de "Vídeos".
    (raiz / "clips").mkdir(parents=True)
    for nome in arquivos:
        (raiz / "clips" / nome).write_bytes(b"\x00")
    monkeypatch.setattr(bl, "library_root", lambda *_a, **_k: raiz)
    return raiz


def test_acha_os_clipes_que_servem_ao_humor(tmp_path, monkeypatch):
    _biblioteca(tmp_path, monkeypatch, [
        "humor--cliente-rindo.mp4", "reacao--susto.mp4",
        "meme--gato.mp4", "viral--queda.mp4",
        "produto--iphone.mp4", "cta--segue.mp4", "abertura--loja.mp4",
    ])
    nomes = {c["name"] for c in bl.clipes_de_humor()}
    assert nomes == {"humor--cliente-rindo.mp4", "reacao--susto.mp4",
                     "meme--gato.mp4", "viral--queda.mp4"}, nomes


def test_foto_nao_conta_como_take_engracado(tmp_path, monkeypatch):
    """"takes e partes engracadas" — uma foto no meio da piada nao e
    reacao."""
    raiz = tmp_path / "Biblioteca"
    (raiz / "images").mkdir(parents=True)
    (raiz / "images" / "humor--placa.jpg").write_bytes(b"\x00")
    monkeypatch.setattr(bl, "library_root", lambda *_a, **_k: raiz)
    assert bl.clipes_de_humor() == []


def test_biblioteca_vazia_nao_inventa_nada(tmp_path, monkeypatch):
    _biblioteca(tmp_path, monkeypatch, [])
    assert bl.clipes_de_humor() == []


def test_biblioteca_ilegivel_nao_derruba_o_render(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "list_assets",
                        lambda *_a, **_k: (_ for _ in ()).throw(OSError("x")))
    assert bl.clipes_de_humor() == []


# ------------------------------------------------------------- a ponte

def test_o_layout_limpo_abre_excecao_para_humor_COM_acervo():
    i = RUN.index("humor_com_acervo = False")
    bloco = RUN[i:i + 1400]
    assert 'normalize_content_type(preset.get("contentType")) == "humor"' in bloco
    # 5.0.2: so os clipes da empresa do video (+ os comuns)
    assert 'clipes_de_humor(\n                    raiz_projetos, brand_id=' in bloco
    assert 'brand_id=str(preset.get("brandId") or ""))' in bloco
    assert "not humor_com_acervo" in bloco, (
        "a saida por layout limpo tem de olhar o tipo")


def test_sem_clipe_guardado_nada_muda():
    """`humor_com_acervo` so vira True com clipe NA Biblioteca — senao o
    video sai como sempre saiu."""
    i = RUN.index("humor_com_acervo = False")
    bloco = RUN[i:i + 1400]
    assert "humor_com_acervo = bool(clipes_de_humor(" in bloco


def test_a_busca_procura_pela_categoria_e_nao_pela_fala():
    """"reacao" nao aparece no texto falado — e e justamente o que entra."""
    i = RUN.index("if humor_com_acervo:", RUN.index("kws = keywords_from_text"))
    bloco = RUN[i:i + 400]
    assert "CATEGORIAS_HUMOR" in bloco


def test_falha_ao_ler_a_biblioteca_nao_derruba_o_render():
    i = RUN.index("humor_com_acervo = False")
    bloco = RUN[i:i + 1400]
    assert "except Exception" in bloco
    assert "b-roll nunca derruba render" in bloco


def test_a_raiz_e_a_dos_projetos_e_nao_a_do_home():
    """A Biblioteca do C: e uma pasta morta e vazia — ler dela ja custou a
    trilha (3.03) e o b-roll (29/08)."""
    i = RUN.index("raiz_projetos = public.parents[3]")
    assert RUN.count("raiz_projetos = public.parents[3]") == 1
    assert "public.parents[3] if len(public.parents) > 3 else None" in RUN[i:i + 120]
