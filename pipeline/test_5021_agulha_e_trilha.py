# -*- coding: utf-8 -*-
"""5.0.21: a agulha só anda pela minutagem, e a trilha volta a ser clicável.

Ele (04/09, com print do editor):
  - "não dá pra clicar na trilha sonora pra adicionar outra trilha";
  - "se eu clicar em cima de um vídeo/áudio/imagem não é pra mover a
    agulha... a agulha deve ser movida só na linha da minutagem".

O botão da trilha existia desde a 4.101 e NUNCA pôde ser clicado: o CSS
do chip tinha `pointer-events: none`. O teste da 4.101 olhava só o JS —
por isso este arquivo checa o par (ouvinte no JS + clique permitido no
CSS), que é o que faltava.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
CSS_BRUTO = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
# sem comentarios: o proprio comentario que explica o defeito cita
# `pointer-events: none`, e ler isso como declaracao daria falso positivo
CSS = re.sub(r"/\*.*?\*/", "", CSS_BRUTO, flags=re.S)


def _declaracoes(seletor: str, prop: str) -> list[str]:
    """Todos os valores de `prop` nos blocos de `seletor`, na ordem do
    arquivo — o último é o que vale (mesma especificidade)."""
    achados = []
    for m in re.finditer(rf"(?m)^{re.escape(seletor)}\s*(?:,[^{{]*)?{{(.*?)}}", CSS, re.S):
        for d in re.finditer(rf"{re.escape(prop)}\s*:\s*([^;}}]+)", m.group(1)):
            achados.append(d.group(1).strip())
    return achados


def test_o_chip_da_trilha_aceita_clique():
    """O par que faltava: ouvinte no JS E clique permitido no CSS."""
    assert "chip.addEventListener('click', (e) => { e.stopPropagation(); abrirMenuTrilha(e.clientX, e.clientY); });" in JS
    valores = _declaracoes(".chip.music", "pointer-events")
    assert valores, "sem regra de pointer-events em .chip.music"
    assert valores[-1] == "auto", f"o clique da trilha continua desligado: {valores}"


def test_nenhum_chip_com_ouvinte_fica_sem_clique():
    """A mesma armadilha já tinha mordido a legenda (`.chip.caption` levou
    um `auto` depois do `none`). Qualquer chip que a timeline escute tem de
    terminar com `pointer-events: auto`."""
    for seletor in (".chip.caption", ".chip.music"):
        valores = _declaracoes(seletor, "pointer-events")
        assert valores and valores[-1] == "auto", f"{seletor}: {valores}"


def test_a_agulha_so_anda_pela_minutagem():
    i = JS.index("panel.addEventListener('pointerdown'")
    bloco = JS[i:JS.index("panel.addEventListener('pointermove'", i)]
    # o ramo final (o unico que inicia o arraste da agulha) sai antes de
    # qualquer coisa que nao seja a regua
    assert "if (!e.target.closest('.ruler-track')) return;" in bloco
    j = bloco.index("if (!e.target.closest('.ruler-track')) return;")
    resto = bloco[j:]
    assert "drag = { type: 'scrub' };" in resto and resto.count("seekDraft(") == 1, (
        "o scrub tem de ser o unico seek depois da guarda da regua")
    # e clicar num take nao leva mais a agulha junto
    k = bloco.index("if (clip && S.tab === 1) {")
    ramo = bloco[k:bloco.index("drag = { type: 'clip-range'", k)]
    assert "seekDraft(" not in ramo, "clicar no take voltou a mover a agulha"


def test_a_regua_ficou_mais_facil_de_acertar():
    i = CSS.index(".ruler-lane {")
    bloco = CSS[i:CSS.index("}", i)]
    assert "cursor: ew-resize" in bloco, "a regua precisa dizer que arrasta"
    alt = re.search(r"height:\s*(\d+)px", bloco)
    assert alt and int(alt.group(1)) >= 32, (
        f"a regua e a UNICA forma de mover a agulha; 26px era pouco (achei {alt and alt.group(1)})")
