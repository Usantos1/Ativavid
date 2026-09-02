# -*- coding: utf-8 -*-
"""Emoji posto à mão, solto no quadro.

Pedido do usuário em 29/08 ("emojis etc"). A decisão que muda tudo: **não**
entra como imagem. Um insert vira CARTÃO (780x500 a 90px do topo), e o
emoji apareceria enquadrado no meio da tela — o que ele quer é o emoji
solto, grande, num canto.

Por isso tem contrato próprio, `edit-data.emojis`, com x/y sendo o CENTRO
em fração do quadro e `size` a altura em fração da LARGURA. Fração e não
pixel porque o mesmo estilo serve qualquer tamanho de export.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline.run_fast import midia_do_editor

REPO = Path(__file__).resolve().parent.parent


def _pedido(tmp_path: Path, emojis: list[dict]) -> tuple[Path, Path]:
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    (public / "sfx").mkdir(parents=True)
    (edit / "preview_edits.json").write_text(
        json.dumps({"editData": {"emojis": emojis}}), encoding="utf-8")
    return edit, public


def test_o_emoji_do_editor_chega_ao_render(tmp_path):
    edit, public = _pedido(tmp_path, [
        {"char": "🔥", "atSec": 2.0, "durSec": 1.6, "x": 0.5, "y": 0.34,
         "size": 0.22}])
    ed: dict = {}
    midia_do_editor(edit, public, ed)
    assert ed["emojis"] == [{"char": "🔥", "atSec": 2.0, "durSec": 1.6,
                             "x": 0.5, "y": 0.34, "size": 0.22}]


def test_valor_absurdo_e_aparado(tmp_path):
    """O campo vem da tela: tamanho 9 (900% do quadro) ou y negativo põem o
    emoji fora do vídeo, e o render não avisaria."""
    edit, public = _pedido(tmp_path, [
        {"char": "😱", "atSec": 5.0, "size": 9.0, "y": -3}])
    ed: dict = {}
    midia_do_editor(edit, public, ed)
    e = ed["emojis"][0]
    assert e["size"] == 0.8 and e["y"] == 0.0 and e["durSec"] == 1.6


def test_emoji_vazio_nao_vira_camada(tmp_path):
    edit, public = _pedido(tmp_path, [{"char": "  ", "atSec": 1.0}])
    ed: dict = {}
    midia_do_editor(edit, public, ed)
    assert "emojis" not in ed


def test_o_motor_rapido_desenha_o_emoji(tmp_path):
    from app.render_proprio import EMOJI_FONT, Renderizador

    if not EMOJI_FONT.exists():
        import pytest
        pytest.skip("sem Segoe UI Emoji nesta máquina")
    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True)
    ed = {"width": 1080, "height": 1920, "fps": 30, "durationSec": 4,
          "hook": {"enabled": False}, "captions": {"enabled": False},
          "endCard": {"enabled": False}, "soundtrack": {"enabled": False},
          "transitions": [], "inserts": [], "behind": [],
          "camera": {"enabled": False, "zooms": [1]},
          "emojis": [{"char": "🔥", "atSec": 1.0, "durSec": 1.5,
                      "x": 0.5, "y": 0.3, "size": 0.25}]}
    r = Renderizador(public, ed, frames=120, fps=30)
    assert len(r.camadas) == 1
    cam = r.camadas[0]
    assert cam.inicio_f == 30 and cam.fim_f == 75
    p = cam.palavras[0]
    # colorido de verdade (o emoji não aceita a tinta do texto) e no lugar
    assert float(p.alpha.max()) > 0.9
    assert p.rgb.max() > 0
    centro_x = p.x0 + p.alpha.shape[1] / 2
    assert abs(centro_x - 0.5 * 1080) < 12


def test_os_dois_motores_usam_as_mesmas_contas():
    """x/y como CENTRO e `size` sobre a LARGURA — se um dos lados mudar a
    conta, o emoji sai num lugar no motor rápido e noutro no Remotion."""
    tsx = (REPO / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    i = tsx.index("const EmojisManuais")
    bloco = tsx[i:i + 1400]
    assert "translate(-50%, -50%)" in bloco          # x/y = centro
    assert "(e.size ?? 0.22) * width" in bloco       # size sobre a largura
    py = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    j = py.index("def _montar_emojis")
    corpo = py[j:j + 2200]
    assert "tam_frac * self.w" in corpo
    assert "x * self.w - img.width / 2" in corpo


def test_a_tela_manda_comeco_e_duracao():
    """Diferente do efeito sonoro (só o instante): o emoji fica na tela
    enquanto o bloco durar."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("emojis: S.insertsDraft")
    bloco = js[i:i + 320]
    assert "atSec: +c.start.toFixed(3)" in bloco
    assert "durSec" in bloco and "char: c.char" in bloco


def test_a_previa_usa_a_geometria_do_render():
    """Prévia que mente é pior que prévia nenhuma: o emoji apareceria num
    lugar na tela e noutro no vídeo. `size` é fração da LARGURA, e x/y são
    o centro — as três contas do render."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    # a função inteira, não janela fixa — ela cresce a cada versão (lição
    # repetida do dia 02/09)
    i = js.index("function desenharMidiaNoPreview")
    bloco = js[i:js.index("function removerBlocoDaMao", i)]
    assert "(c.size ?? 0.22) * box.clientWidth" in bloco
    assert "(c.x ?? 0.5) * 100" in bloco and "(c.y ?? 0.34) * 100" in bloco
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    j = css.index(".midia-previa-emoji")
    assert "translate(-50%, -50%)" in css[j:j + 240]


def test_o_cartao_da_previa_tem_o_tamanho_do_cartao_do_render():
    """O InsertCard é 780x500 a 90px do topo num quadro de 1080x1920."""
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    i = css.index(".midia-previa-card")
    bloco = css[i:i + 400]
    for esperado in (f"{780 / 1080 * 100:.1f}%", f"{500 / 1920 * 100:.1f}%",
                     f"{90 / 1920 * 100:.1f}%"):
        assert esperado in bloco, (esperado, bloco[:200])


def test_a_previa_so_mostra_o_que_foi_posto_na_mao():
    """O insert da IA está no relógio do vídeo FINAL — aqui ele apareceria
    fora de hora."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function desenharMidiaNoPreview")
    bloco = js[i:i + 900]
    assert "c.isNew" in bloco
    # som não tem o que mostrar
    assert "'sfx'" not in bloco


def test_o_emoji_se_arrasta_e_a_roda_muda_o_tamanho():
    """Ele nascia no centro-alto e ficava lá: tirar do rosto de quem fala
    exigia mexer no arquivo. O gesto é o mesmo da manchete e da legenda."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    i = js.index("function emojiArrastavel")
    bloco = js[i:i + 2600]
    # guarda de tremor: clique não pode virar arrasto de 1px
    assert "Math.abs(dx) < 4 && Math.abs(dy) < 4" in bloco
    # preso ao quadro
    assert "Math.max(0.02, Math.min(0.98" in bloco
    # a roda é multiplicativa: o passo tem de valer igual em emoji pequeno
    # e grande
    assert "* fator" in bloco and "1.08" in bloco
    assert "Math.max(0.06, Math.min(0.7" in bloco
    # e o resultado vai para o bloco, que é o que viaja no salvar
    assert "c.x =" in bloco and "c.y =" in bloco and "c.size =" in bloco


def test_a_camada_deixa_pegar_so_o_emoji():
    """A camada inteira é transparente ao ponteiro (senão come o clique do
    vídeo); só o emoji recebe."""
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    i = css.index(".midia-overlay {")
    assert "pointer-events: none" in css[i:i + 260]
    j = css.index(".midia-previa-emoji {")
    assert "pointer-events: auto" in css[j:j + 400]
