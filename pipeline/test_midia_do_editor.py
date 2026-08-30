# -*- coding: utf-8 -*-
"""A mídia posta à mão no editor tem de chegar ao vídeo.

A tela sabia inserir imagem na agulha desde sempre e guardava o pedido em
`preview_edits.json` (`editData.newInserts`). O pipeline **nunca leu esse
campo**: `load_preview_edit_ranges` só pega `edl.ranges`, e o "refazer" só
recoloca o job na fila. O pedido era salvo e sumia no render — calado, do
mesmo jeito que o `videoLayout` sumia no motor rápido.

Ninguém tinha percebido porque, até a 3.58, o botão de mídia só funcionava
na aba Visual: 0 de 186 projetos entregues tinham uma imagem posta à mão.

Três regras que o teste segura:

* sobrevive ao estilo "limpa" — quadro cheio dispensa b-roll AUTOMÁTICO, e
  o que o usuário pediu na mão não é automático;
* arquivo que não está na pasta do projeto NÃO entra, e é apontado na
  ficha (sumir calado é o defeito que este caminho tinha);
* `..` no caminho é recusado — o campo vem da tela e aponta um arquivo.
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.run_fast import _RENDER_META, midia_do_editor


def _projeto(tmp_path: Path, editor: dict) -> tuple[Path, Path]:
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    (public / "sfx").mkdir(parents=True)
    (public / "biblioteca").mkdir()
    (public / "biblioteca" / "foto.jpg").write_bytes(b"x")
    (public / "sfx" / "risada.mp3").write_bytes(b"x")
    (edit / "preview_edits.json").write_text(
        json.dumps({"editData": editor}), encoding="utf-8")
    return edit, public


def test_a_imagem_posta_na_mao_entra_no_render(tmp_path):
    edit, public = _projeto(tmp_path, {"newInserts": [
        {"src": "biblioteca/foto.jpg", "start": 3.0, "end": 5.5, "credit": "eu"}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    assert len(ed["inserts"]) == 1
    it = ed["inserts"][0]
    assert it["src"] == "biblioteca/foto.jpg" and it["start"] == 3.0
    # marcada como do usuário: o corte não pode descartá-la como descarta o
    # b-roll automático do estilo limpa
    assert it["manual"] is True


def test_o_efeito_sonoro_posto_na_mao_entra(tmp_path):
    edit, public = _projeto(tmp_path, {"sfxManual": [
        {"src": "risada.mp3", "atSec": 4.2, "volume": 0.6}]})
    ed: dict = {}
    midia_do_editor(edit, public, ed)
    assert ed["sfxManual"] == [{"src": "risada.mp3", "atSec": 4.2, "volume": 0.6}]


def test_arquivo_que_nao_esta_na_pasta_e_apontado(tmp_path):
    _RENDER_META.pop("midiaDoEditorPerdida", None)
    edit, public = _projeto(tmp_path, {
        "newInserts": [{"src": "biblioteca/sumiu.jpg", "start": 8, "end": 9}],
        "sfxManual": [{"src": "nao-existe.mp3", "atSec": 5}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    assert not ed["inserts"] and "sfxManual" not in ed
    perdida = _RENDER_META.get("midiaDoEditorPerdida") or []
    assert len(perdida) == 2


def test_caminho_para_fora_da_pasta_e_recusado(tmp_path):
    edit, public = _projeto(tmp_path, {"newInserts": [
        {"src": "../fora.jpg", "start": 1, "end": 2}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    assert not ed["inserts"]


def test_duracao_absurda_vira_a_janela_padrao(tmp_path):
    edit, public = _projeto(tmp_path, {"newInserts": [
        {"src": "biblioteca/foto.jpg", "start": 3.0, "end": 3.01}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    assert ed["inserts"][0]["end"] == 5.5


def test_o_motor_rapido_toca_o_efeito_da_mao(tmp_path):
    """Contrato dos dois motores: mesmo arquivo, mesmo segundo."""
    from app.render_proprio import Renderizador

    public = tmp_path / "public"
    (public / "sfx").mkdir(parents=True)
    ed = {"width": 1080, "height": 1920, "fps": 30, "durationSec": 3,
          "hook": {"enabled": False}, "captions": {"enabled": False},
          "endCard": {"enabled": False}, "soundtrack": {"enabled": False},
          "transitions": [], "inserts": [], "behind": [],
          "camera": {"enabled": False, "zooms": [1]},
          "sfxManual": [{"src": "pop.mp3", "atSec": 1.5, "volume": 0.4},
                        {"src": "", "atSec": 2.0},
                        {"src": "x.mp3", "atSec": -1}]}
    r = Renderizador(public, ed, frames=90, fps=30)
    assert r.eventos_sfx == [("pop.mp3", 1.5, 0.4)]


def test_o_template_toca_o_mesmo():
    repo = Path(__file__).resolve().parent.parent
    tsx = (repo / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    assert "const SfxManual" in tsx and "<SfxManual />" in tsx
    i = tsx.index("const SfxManual")
    assert "sfxManual" in tsx[i:i + 400]


def test_aplicar_duas_vezes_nao_duplica(tmp_path):
    """Esta função roda no render completo E no "Aplicar alterações". Sem
    marca de "já apliquei", o segundo clique poria a mesma imagem duas
    vezes no vídeo — e o usuário veria a foto piscar repetida."""
    edit, public = _projeto(tmp_path, {
        "newInserts": [{"src": "biblioteca/foto.jpg", "start": 3.0, "end": 5.5}],
        "sfxManual": [{"src": "risada.mp3", "atSec": 4.2}],
        "emojis": [{"char": "🔥", "atSec": 2.0}]})
    ed: dict = {}
    for _ in range(3):
        midia_do_editor(edit, public, ed)
    assert len(ed["inserts"]) == 1
    assert len(ed["sfxManual"]) == 1
    assert len(ed["emojis"]) == 1


def test_o_aplicar_alteracoes_tambem_le_a_midia():
    """"Aplicar alterações" é o botão que o usuário usa depois de mexer na
    linha do tempo. Se só o render completo lesse a mídia, ele aplicaria e
    receberia o vídeo sem ela, calado."""
    fonte = (Path(__file__).resolve().parent.parent / "app"
             / "apply_execute.py").read_text(encoding="utf-8")
    assert "from pipeline.run_fast import midia_do_editor" in fonte
    i = fonte.index("midia_do_editor(edit, public, edit_data)")
    # e grava, senão o render (que lê o arquivo) não veria a mudança
    assert "_write_json(edit_data_path(edit), edit_data)" in fonte[i:i + 400]


def test_a_midia_sobrevive_ao_render_que_refaz_o_public(tmp_path):
    """O render refaz `remotion/public` do zero. A mídia que a tela copiou
    para lá sumia ANTES do pipeline olhar — a prova fim a fim de 29/08
    mostrou o emoji e o som entrando e a imagem não ("não achei em
    public/"). A cópia durável mora em `<edit>/midia/`."""
    edit = tmp_path / "edit"
    public = edit / "remotion" / "public"
    (public / "sfx").mkdir(parents=True)
    # nada em public/: e o estado depois do scaffold
    (edit / "midia" / "library").mkdir(parents=True)
    (edit / "midia" / "library" / "foto.jpg").write_bytes(b"x")
    (edit / "midia" / "sfx").mkdir(parents=True)
    (edit / "midia" / "sfx" / "risada.mp3").write_bytes(b"x")
    (edit / "preview_edits.json").write_text(json.dumps({"editData": {
        "newInserts": [{"src": "library/foto.jpg", "start": 3.0, "end": 5.0}],
        "sfxManual": [{"src": "sfx/risada.mp3", "atSec": 4.0}]}}),
        encoding="utf-8")

    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    assert len(ed["inserts"]) == 1 and len(ed["sfxManual"]) == 1
    # e os arquivos voltaram para public/, que é de onde o render lê
    assert (public / "library" / "foto.jpg").exists()
    assert (public / "sfx" / "risada.mp3").exists()


def test_a_biblioteca_guarda_a_copia_duravel(tmp_path):
    from app.broll_library import copy_into_public

    (tmp_path / "foto.jpg").write_bytes(b"x")
    public = tmp_path / "proj" / "edit" / "remotion" / "public"
    r = copy_into_public(tmp_path / "foto.jpg", public)
    assert r["src"] == "library/foto.jpg"
    # a cópia que sobrevive ao scaffold
    assert (tmp_path / "proj" / "edit" / "midia" / "library" / "foto.jpg").exists()


def test_a_imagem_leva_posicao_e_tamanho(tmp_path):
    """Pedido de 30/08: a foto entrava sempre no mesmo cartão fixo e tapava
    a cena. x/y são o CENTRO em fração do quadro e `size` a largura."""
    edit, public = _projeto(tmp_path, {"newInserts": [
        {"src": "biblioteca/foto.jpg", "start": 3.0, "end": 5.0,
         "x": 0.75, "y": 0.7, "size": 0.36}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    it = ed["inserts"][0]
    assert (it["x"], it["y"], it["size"]) == (0.75, 0.7, 0.36)


def test_geometria_absurda_e_aparada(tmp_path):
    edit, public = _projeto(tmp_path, {"newInserts": [
        {"src": "biblioteca/foto.jpg", "start": 1.0, "end": 3.0,
         "x": -5, "y": 9, "size": 40}]})
    ed: dict = {"inserts": []}
    midia_do_editor(edit, public, ed)
    it = ed["inserts"][0]
    assert 0.0 <= it["x"] <= 1.0 and 0.0 <= it["y"] <= 1.0
    assert 0.08 <= it["size"] <= 1.0


def test_sem_os_campos_o_cartao_e_o_de_sempre():
    """Projeto antigo não pode mudar de aparência: 780x500 a 90px do topo."""
    from app.render_proprio import geometria_do_insert

    assert geometria_do_insert({}, 1080, 1920) == (780, 500, 540.0, 340.0)


def test_o_cartao_nunca_deforma():
    """Um botão de tamanho só: a altura segue a proporção do cartão."""
    from app.render_proprio import geometria_do_insert

    for frac in (0.2, 0.5, 0.9):
        cw, ch, _, _ = geometria_do_insert({"size": frac}, 1080, 1920)
        assert abs(ch / cw - 500 / 780) < 0.01, (frac, cw, ch)


def test_os_dois_motores_calculam_igual():
    repo = Path(__file__).resolve().parent.parent
    tsx = (repo / "assets" / "shortform" / "src" / "Main.tsx").read_text(encoding="utf-8")
    i = tsx.index("const InsertCard")
    bloco = tsx[i:i + 2200]
    assert "(larg * CARD_H) / CARD_W" in bloco      # altura pela proporção
    assert "cx - larg / 2" in bloco                 # x/y são o centro
    assert "(CARD_TOP + CARD_H / 2) / 1920" in bloco  # mesmo padrão


def test_o_tamanho_tem_alca_e_nao_so_a_roda():
    """O usuário moveu a imagem e não conseguiu mudar o tamanho (30/08): a
    roda do mouse é gesto invisível. Quem olha um elemento selecionado
    procura a alça no canto."""
    repo = Path(__file__).resolve().parent.parent
    js = (repo / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "function alcaDeTamanho" in js
    i = js.index("function alcaDeTamanho")
    bloco = js[i:i + 1400]
    # a alça não pode virar arrasto do elemento
    assert "e.stopPropagation();" in bloco
    # a diagonal manda, e o limite vem de quem chamou
    assert "Math.max(minimo, Math.min(maximo" in bloco
    # e serve aos dois: cartão e emoji
    assert js.count("alcaDeTamanho(") == 3   # a definição + os dois usos
    css = (repo / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    j = css.index(".previa-alca")
    assert "cursor: nwse-resize" in css[j:j + 400]
