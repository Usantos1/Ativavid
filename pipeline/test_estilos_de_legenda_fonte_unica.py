# -*- coding: utf-8 -*-
"""A lista de estilos de legenda vive num lugar só — e a IA a conhece.

A mesma armadilha do `videoLayout`: o id vivia repetido em vários pontos e
quem esquecesse uma cópia não recebia erro, só não acontecia. Aqui era pior
num ponto — a IA não tinha lista NENHUMA. `set_captions_style` aceitava
qualquer texto, então "põe legenda metálica" virava `style="metalica"`, o
template caía no `else` (karaokê) e o job ainda perdia o motor rápido.
Dois prejuízos, nenhum aviso.
"""
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app import caption_styles                      # noqa: E402
from app.ai_actions import apply_actions_to_edits    # noqa: E402
from app.render_proprio import motivo_nao_suportado  # noqa: E402


def _public():
    p = Path(tempfile.mkdtemp()) / "public"
    p.mkdir(parents=True)
    (p / "captions.json").write_text("[]", encoding="utf-8")
    (p / "caption-cues.json").write_text("[]", encoding="utf-8")
    return p


def test_a_tela_e_a_lista_falam_dos_mesmos_estilos():
    """O catálogo do preview é o que o usuário vê; a lista é o que o
    pipeline aceita. Um estilo numa e não na outra é um estilo que aparece
    na tela e não sai no vídeo — ou o contrário."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("  captions: [")
    bloco = js[i:js.index("  elements: [", i)]
    na_tela = set()
    for linha in bloco.splitlines():
        if "{id: '" in linha:
            na_tela.add(linha.split("{id: '")[1].split("'")[0])
    na_tela.discard("nenhuma")     # desligar a legenda não é um estilo
    assert na_tela == set(caption_styles.TODOS), (
        f"só na tela: {na_tela - set(caption_styles.TODOS)} · "
        f"só na lista: {set(caption_styles.TODOS) - na_tela}")


def test_o_portao_do_motor_rapido_le_a_lista():
    pub = _public()
    base = {"hook": {"enabled": False}, "endCard": {"enabled": False},
            "transitions": [], "elements": {}}
    for estilo in caption_styles.TODOS:
        ed = dict(base, captions={"enabled": True, "style": estilo})
        assert motivo_nao_suportado(ed, pub) is None, estilo
    ed = dict(base, captions={"enabled": True, "style": "metalica"})
    assert "metalica" in (motivo_nao_suportado(ed, pub) or "")


def test_a_ia_recusa_estilo_que_nao_existe():
    """Antes passava — e o estrago era mudo."""
    r = apply_actions_to_edits(
        [{"action": "set_captions_style", "style": "metalica"}],
        style={"captions": "stacked"})
    assert r["style"]["captions"] == "stacked", "não pode ter trocado"
    assert not r["applied"]
    assert len(r["recusadas"]) == 1
    assert "metalica" in r["recusadas"][0]["motivo"]


def test_a_ia_aceita_o_id_e_o_nome_da_tela():
    """"põe legenda metálica" — o nome que o usuário tem na frente é o da
    tela, e é ele que a IA tende a devolver."""
    for pedido, esperado in (("metal", "metal"), ("Metálico", "metal"),
                             ("metalico", "metal"),
                             ("Contorno fino", "traco")):
        r = apply_actions_to_edits(
            [{"action": "set_captions_style", "style": pedido}],
            style={"captions": "stacked"})
        assert r["style"]["captions"] == esperado, pedido
        assert not r["recusadas"], pedido


def test_o_prompt_da_ia_traz_a_lista():
    """Sem a lista no texto, a IA chuta o nome — e chutar era o problema."""
    fonte = (REPO / 'app' / 'ai_actions.py').read_text(encoding='utf-8')
    assert '_ESTILOS_DE_LEGENDA = caption_styles.lista_para_ia()' in fonte
    # definido ANTES de ser usado no texto das ações
    definicao = fonte.index('_ESTILOS_DE_LEGENDA = ')
    uso = fonte.index('+ _ESTILOS_DE_LEGENDA')
    assert definicao < uso
    assert 'set_captions_style: style TEM de ser' in fonte
    texto = caption_styles.lista_para_ia()
    for estilo in caption_styles.TODOS:
        assert estilo in texto, estilo


def test_as_headlines_batem_nos_tres_motores():
    """Mesma guarda das legendas, para o outro catálogo.

    Um id que exista na tela e não no motor faz o job cair no caminho lento
    (o gate recusa); um que exista no motor e não na tela é código morto.
    Hoje são 15 dos dois lados — o teste é para quando alguém acrescentar o
    16º e esquecer uma das listas.
    """
    import re

    from app.render_proprio import Renderizador

    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("  headlines: [")
    bloco = js[i:js.index("  captions: [", i)]
    na_tela = set(re.findall(r"\{id: '([a-z0-9]+)'", bloco)) - {"nenhuma"}
    motor = set(Renderizador.HL_STYLES)
    assert na_tela == motor, (
        f"só na tela: {na_tela - motor} · só no motor: {motor - na_tela}")

    # e a união de tipos do template conhece todos
    tsx = (REPO / "assets" / "shortform" / "src"
           / "Main.tsx").read_text(encoding="utf-8")
    j = tsx.index("style?: 'outline'")
    uniao = set(re.findall(r"'([a-z]+)'", tsx[j:tsx.index(";", j)]))
    assert not (na_tela - uniao), f"o template não tipa: {na_tela - uniao}"
