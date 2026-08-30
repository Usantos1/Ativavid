# -*- coding: utf-8 -*-
"""Os efeitos importados entram no vídeo — e a tela diz quais.

O usuário tem **234 efeitos** na Biblioteca. O app troca o som do vídeo
pelo dele casando a categoria do arquivo com a vaga:

    vagas do vídeo:  clique · risco · whoosh · pop · corte
    categorias dele: impacto 87 · swoosh 70 · clique 30 ·
                     transicao 19 · impacto-grave 18 · riser 8 · sino 1

Só `clique` batia — os **70 `swoosh` nunca tocaram**, embora a própria
tabela de famílias do app declare `swoosh` como sinônimo de `whoosh`. O
casamento usava o prefixo literal e não passava por ela.

O whoosh toca na manchete de todo vídeo (menos no estilo pílula) e em
cada insert: trocar esse som é audível em cada vídeo que ele faz.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.broll_library import SFX_VAGAS, vaga_do_efeito  # noqa: E402

JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
BL = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")


def test_swoosh_ocupa_a_vaga_do_whoosh():
    """A tabela de famílias do app já dizia que são a mesma coisa."""
    assert vaga_do_efeito("swoosh--001.mp3") == "whoosh"
    assert vaga_do_efeito("swipe--007.mp3") == "whoosh"


def test_a_categoria_certa_continua_valendo():
    for nome, vaga in (("clique--001.mp3", "clique"),
                       ("whoosh--meu.mp3", "whoosh"),
                       ("pop--x.mp3", "pop"),
                       ("corte--x.mp3", "corte"),
                       ("risco--x.mp3", "risco")):
        assert vaga_do_efeito(nome) == vaga, nome


def test_categoria_sem_vaga_nao_toca():
    """Inventar onde um "impacto" entraria mudaria o vídeo no palpite."""
    for nome in ("impacto--001.mp3", "impacto-grave--002.mp3",
                 "transicao--003.mp3", "riser--004.mp3", "sino--005.mp3"):
        assert vaga_do_efeito(nome) == "", nome


def test_arquivo_sem_categoria_cai_na_heuristica():
    assert vaga_do_efeito("meu-whoosh-legal.mp3") == "whoosh"
    assert vaga_do_efeito("cut-click.mp3") == "corte"
    assert vaga_do_efeito("som qualquer.mp3") == ""


def test_a_troca_usa_a_vaga_e_nao_o_prefixo():
    i = BL.index("def aplicar_sfx_do_usuario(")
    # A funcao inteira: por janela fixa, o teto de duracao (4.19) ficou de
    # fora e o teste acusou o que nao havia.
    corpo = BL[i:BL.index("\ndef ", i + 10)]
    assert "vaga_do_efeito(f.name) == vaga" in corpo
    assert "categoria_de(f.name) == vaga" not in corpo


def test_a_listagem_diz_se_toca():
    i = BL.index("def list_assets(")
    corpo = BL[i:i + 2200]
    assert '"vaga": vaga' in corpo and '"tocaNoVideo"' in corpo


def test_a_tela_marca_os_dois_casos():
    assert "function selosDoEfeito(" in JS
    assert "lib-selo--toca" in JS and "lib-selo--guardado" in JS
    assert "selosDoEfeito(it)" in JS, "o selo existe e não é usado"
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    assert ".lib-selo--toca" in css and ".lib-selo--guardado" in css


def test_todo_rotulo_de_vaga_existe():
    """Vaga nova sem rótulo apareceria como o id cru na tela."""
    i = JS.index("const VAGA_ROTULO = {")
    bloco = JS[i:JS.index("\n};", i)]
    for vaga in SFX_VAGAS:
        assert f"{vaga}:" in bloco, vaga


def test_efeito_novo_ganha_a_vaga_pelo_nome(tmp_path):
    """`meu-whoosh.mp3` entrava como "sem categoria" e nunca tocava — o
    botão "Adicionar efeitos" guardava arquivo sem mudar vídeo nenhum."""
    from app import broll_library as bl

    r = bl.add_bytes("meu-whoosh-legal.mp3", b"x" * 2000, kind="sfx",
                     projects_root=tmp_path)
    assert r["categoria"] == "whoosh"
    assert bl.vaga_do_efeito(r["name"]) == "whoosh"


def test_nome_sem_pista_continua_sem_categoria(tmp_path):
    """Palpite que não cai numa vaga de verdade seria pior que nenhum."""
    from app import broll_library as bl

    r = bl.add_bytes("som qualquer.mp3", b"x" * 2000, kind="sfx",
                     projects_root=tmp_path)
    assert r["categoria"] == ""


def test_a_categoria_pedida_ganha_do_palpite(tmp_path):
    from app import broll_library as bl

    r = bl.add_bytes("meu-whoosh.mp3", b"x" * 2000, kind="sfx",
                     categoria="pop", projects_root=tmp_path)
    assert r["categoria"] == "pop"


def test_trilha_nao_ganha_vaga_de_efeito(tmp_path):
    """As vagas são só de efeito; trilha tem outro vocabulário."""
    from app import broll_library as bl

    r = bl.add_bytes("whoosh-da-musica.mp3", b"x" * 2000, kind="track",
                     projects_root=tmp_path)
    assert r["categoria"] == ""


def test_o_cabecalho_do_grupo_concorda_com_o_selo():
    """O grupo `swoosh` dizia "só guardado" com os itens dizendo "toca" —
    duas etiquetas discordando na mesma tela."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("const vagaDaCategoria = new Map();")
    trecho = js[i:i + 700]
    assert "it.vaga" in trecho
    assert "vagaDaCategoria.has(k)" in trecho
