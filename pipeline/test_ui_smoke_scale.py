"""Smoke de UI: IDs e textos existem. Sem servidor, sem mídia."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_editor_has_protect_and_versions():
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    assert 'id="btnProtect"' in html
    assert 'id="protectMenu"' in html
    assert "Proteger seleção" in html
    assert "Proteger gancho" in html
    assert "Proteger CTA" in html
    assert "Desproteger" in html
    assert 'id="btnVersions"' in html
    assert "Restaurar versão" in html
    assert 'id="autoContentType"' in html
    assert 'id="presetSelect"' in html
    assert 'id="dlgAutosave"' in html
    assert '<dialog id="dlgAutosave"' in html
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "toUpperCase() === 'DIALOG'" in js
    assert "const firstLoad = !S.lastSig" in js
    assert "isQuickEditing()" not in js.split("async function poll")[1].split("async function applyState")[0]
    assert "Continuar de onde parou?" in html
    assert 'id="btnApply"' in html
    assert "Aplicar alterações" in html
    assert "Ver final" in html
    assert "Abrir pasta" in html
    assert "Alterações pendentes" in html
    assert "•••" in html
    assert 'id="btnHeadMore"' in html
    assert 'id="btnZoom100"' in html
    assert 'id="btnZoomIn"' in html
    assert 'id="btnZoomOut"' in html
    assert ">100%<" in html
    assert 'id="hlOverlay"' in html
    assert 'id="pendingPill"' in html
    assert 'id="quickFixes"' in html
    assert 'id="hlChip"' in html
    assert 'id="applyStage"' in html
    assert "Cortar" in html
    assert "Excluir" in html
    assert "Restaurar versão" in html
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "persistCorrection" in js
    assert "commitHeadline" in js
    assert "op: 'apply'" in js
    assert "Aplicando alterações" in js
    assert "setZoom100" in js
    assert "bumpZoom" in js
    assert "CLIP_TIGHT_PX" in js
    assert "clip-body-hit" in js
    assert "e.ctrlKey" in js
    assert "isTypingContext" in js
    assert "tokenId: c.tokenId" in js or "tokenId: c.tokenId || undefined" in js
    assert "Final anterior" in js
    assert "Vídeo atualizado" in js


def test_studio_has_content_type_and_simple_system():
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert 'id="importContentType"' in html
    assert "Tipo de conteúdo" in html
    assert 'id="importPresetHint"' in html
    assert "Status do ATIVAVID" in html
    assert "Tudo funcionando corretamente" in html or 'id="sysStatusLine"' in html
    assert "Avançado" in html
    assert 'id="hwAccelDetail"' in html
    assert 'id="btnHwBench"' in html
    # Menu lateral: as quatro seções pedidas, na ordem, e cada item com uma
    # tela de verdade por trás. O guarda antigo travava o menu em 6 itens —
    # virou o contrário: fixa a estrutura para ninguém encolher sem querer.
    for secao in ("Trabalho", "Criação", "Automação", "Aplicativo"):
        assert f'<p class="sb-label">{secao}</p>' in html, secao
    itens = (
        "import", "fila", "done", "projetos",           # trabalho
        "estilo", "marca", "biblioteca", "presets",     # criação
        "ia", "integracoes",                            # automação
        "sistema",                                      # aplicativo
    )
    for v in itens:
        assert f'data-view="{v}"' in html, v
        assert f'data-view-panel="{v}"' in html, f"{v} sem tela"
    # Saíram do menu principal (licença foi para o menu do workspace, chaves
    # viraram IA/Integrações, sistema virou Configurações).
    assert 'data-view="licenca"' not in html
    assert 'data-view="keys"' not in html
    assert 'data-view="historico"' not in html
    assert "Chaves &amp; IA" not in html
    # Rodapé é o workspace, não um painel de conta.
    assert 'id="btnWorkspace"' in html and 'id="wsMenu"' in html
    assert 'id="btnSbAccount"' not in html
    assert 'class="sb-acc-dot"' not in html
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function jobInFila" in js
    assert 'badge: "ATUALIZANDO"' in js
    assert "Não foi possível atualizar o vídeo." in js
    assert "Vídeo atualizado" in js
    assert "maybeToastApply" in js
    assert "justFinished" in js
    assert "ativavid-apply-ack:" in js
    assert "45000" not in js
    assert "Ver anterior" in js
    assert "Ver detalhe" in js
    assert "Lixeira" in html
    assert "data-act=\"detail\"" in js
    # `?view=keys` é link antigo salvo por aí — tem de continuar abrindo IA.
    assert 'if (name === "keys") name = "ia";' in js
    assert "workspacePlanMeta" in js and "renderWorkspaceCard" in js
    shell = (REPO / "assets" / "studio" / "shell.js").read_text(encoding="utf-8")
    assert "quickApply" in shell
    # A página do editor usa o MESMO menu (mesmo CSS, mesmos itens).
    prev = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    for v in itens:
        assert f'data-hub-view="{v}"' in prev, v


def test_score_labels_from_real_numbers():
    import sys

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from helpers.video_score import present_score

    out = present_score({"overall": 87, "hook": 90, "clarity": 80, "rhythm": 78, "cta": 88, "tips": []})
    labels = {i["id"]: i["text"] for i in out["items"]}
    assert labels["hook"] == "forte"
    assert labels["clarity"] == "boa"
    assert present_score({}) == {}



def test_grades_das_telas_novas_nao_estouram_em_tela_estreita():
    """`minmax(320px, 1fr)` reserva 320px mesmo quando sobra menos que
    isso — medido: 44px de estouro na Marca a 390px de janela. O
    `min(Npx, 100%)` deixa o track encolher junto."""
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    for grade in (".pane-grid", ".ident-grid", ".lib-grid"):
        i = css.index(grade + " {")
        bloco = css[i:css.index("}", i)]
        assert "minmax(min(" in bloco, f"{grade} precisa de minmax(min(...))"
    # o filtro de Projetos tem 4 botões: em tela estreita quebra, não corta
    i = css.index(".seg {")
    assert "flex-wrap: wrap" in css[i:css.index("}", i)]
    # empilhado, a busca não pode carregar o flex-basis da versão em linha
    # (200px viravam ALTURA e abriam um buraco de 145px — medido)
    assert ".proj-search { flex: 0 0 auto; max-width: none; }" in css
    # caminho longo do Windows precisa poder quebrar
    assert "overflow-wrap: anywhere" in css


def test_telas_avisam_quando_a_leitura_falha():
    """Servidor fora do ar deixava Biblioteca, Presets e Estilos mudos —
    Estilos ficava totalmente em branco, sem nem dizer o que houve."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert "function falhaDaTela" in js
    assert js.count('falhaDaTela("') >= 2, "biblioteca e presets"
    # o iframe do editor de estilo nao avisa sozinho: `load` dispara ate na
    # pagina de erro do Chrome, entao quem decide e o CONTEUDO
    assert "function estiloCarregou" in js
    assert "contentDocument" in js and "body.children.length" in js
    assert 'id="estiloFalha"' in html and 'id="btnEstiloRetry"' in html
    # e o retry precisa recriar o iframe: trocar o src deixa o frame preso
    # na pagina de erro (contentDocument segue nulo, medido)
    i = js.index("btn.onclick")
    assert "createElement(\"iframe\")" in js[i:i + 1200]

def test_menu_vira_gaveta_em_tela_de_celular():
    """Ate 620px o trilho de 72px comia 15% da largura e os rotulos so
    existiam como tooltip — inutil no toque."""
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    i = css.index("@media (max-width: 620px) {\n  .tb-burger")
    bloco = css[i:i + 1400]
    assert "position: fixed" in bloco and "translateX(-104%)" in bloco
    # a gaveta sai do grid: declarar duas colunas jogava o conteudo na de
    # 0px e a tela ficava PRETA (medido)
    assert "grid-template-columns: minmax(0, 1fr)" in bloco
    # o trilho e do desktop — dentro da gaveta o menu e o completo
    assert "@media (min-width: 621px) {" in css
    assert "@media (min-width: 621px) and (max-width: 900px) {" in css
    for arq, sb in (("studio", "sidebar"), ("preview", "hubSidebar")):
        pasta = "studio" if arq == "studio" else "preview"
        html = (REPO / "assets" / pasta / "index.html").read_text(encoding="utf-8")
        assert 'id="btnBurger"' in html and f'aria-controls="{sb}"' in html, arq
        assert 'id="sbScrim"' in html, arq
    for js in ("studio.js", "shell.js"):
        txt = (REPO / "assets" / "studio" / js).read_text(encoding="utf-8")
        assert "function wireGaveta" in txt, js
        assert "sb-open" in txt, js

def test_ia_e_integracoes_usam_a_largura_do_monitor():
    """Num monitor de 1920 sobravam ~680px de vazio: ao separar IA de
    Integracoes eu travei a grade em 900px e a tela ficou colada na
    esquerda. Em tela larga cada uma se divide em duas colunas."""
    css = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
    i = css.index(".keys-grid--single {")
    assert "max-width" not in css[i:css.index("}", i)], "sem teto arbitrario"
    i = css.index("@media (min-width: 1180px) {")
    bloco = css[i:]
    # IA: passo a passo de um lado, o que se opera do outro
    assert '"steps form"' in bloco
    assert ".keys-block--session > .keys-form" in bloco
    # Integracoes: os servicos lado a lado
    assert ".keys-block--apis .keys-form" in bloco
    assert "minmax(min(360px, 100%), 1fr)" in bloco


if __name__ == "__main__":
    test_editor_has_protect_and_versions()
    test_studio_has_content_type_and_simple_system()
    test_score_labels_from_real_numbers()
    print("ok")


def test_headline_arrastavel_no_editor():
    """A camada era um `padding-top: 22px` fixo: mostrava a headline num
    lugar que o render não usava, e não dava para mover."""
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    css = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")
    for fn in ("function hlAncora", "function hlMetrica",
               "function hlPosicionar", "function hlArrastavel"):
        assert fn in js, fn
    assert "set_headline_pos" in js
    # a altura padrão vem do MOTOR, não de uma terceira cópia da tabela
    assert "/api/headline-anchors" in js
    # o preview ancora no VÍDEO, não na moldura: com caixa-postal os dois
    # divergem e a headline apareceria onde o render não desenha
    assert "video.getBoundingClientRect()" in js
    # clique (editar texto) e arrasto (mover) convivem
    assert "acabouDeArrastar" in js
    assert "Math.abs(dy) < 4" in js
    # sem comentarios: o proprio comentario da mudanca cita o valor antigo
    limpo = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    i = limpo.index(".hl-overlay {")
    assert "padding-top" not in limpo[i:limpo.index("}", i)]
    assert ".hl-overlay-line.dragging" in css
