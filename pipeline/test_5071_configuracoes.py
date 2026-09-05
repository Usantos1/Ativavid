# -*- coding: utf-8 -*-
"""5.0.71: três pedidos dele na tela de Configurações (print de 05/09).

1. "Esta linha está estourando" — o rótulo do interruptor "Copiar cada
   vídeo pronto para a pasta de entregas (dobra o espaço em disco)" saía
   para fora do card Projetos e cache. Dois motivos: `.lib-switch` tem
   `white-space: nowrap`, e a grade (`auto-fill`) deixava uma quarta coluna
   VAZIA à direita do card. O card passa a ir até a última coluna e o
   rótulo quebra linha.
2. "Mostrar isso dentro dele" — os itens de hardware da checagem (perfil
   automático, jobs paralelos, encoder, cada GPU com a VRAM) aparecem no
   card Desempenho. Mesma fonte do Diagnóstico: os dados reais do PC de
   cada cliente.
3. "Ao lado de Tudo funcionando corretamente, o e-mail do usuário e o ID do
   dispositivo pra ele poder copiar" — dois botões-pílula; o ID mostra o
   código curto da tela de máquinas e copia o ID inteiro.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_card_de_projetos_vai_ate_a_ultima_coluna():
    assert re.search(r'<div class="sys-card sys-card--largo">\s*<h4>Projetos e cache</h4>', HTML)
    assert HTML.count("sys-card--largo") == 1, "so o ultimo card estica"
    assert ".sys-grid > .sys-card--largo { grid-column-end: -1; }" in CSS


def test_o_rotulo_do_interruptor_quebra_linha_dentro_do_card():
    """`.lib-switch` continua `nowrap` na Biblioteca; no card ele quebra."""
    assert "white-space: nowrap;" in CSS.split(".lib-switch {", 1)[1][:200]
    bloco = CSS.split(".sys-card .lib-switch {", 1)[1][:200]
    assert "white-space: normal;" in bloco
    assert "align-items: flex-start;" in bloco, "a caixa fica no alto da 1a linha"
    assert ".sys-card .lib-switch > span { min-width: 0; }" in CSS


def test_o_hardware_aparece_dentro_do_card_desempenho():
    assert 'id="perfDados"' in HTML
    i = HTML.index('id="sysPerfHint"')
    assert HTML.index('id="perfDados"') > i, "logo abaixo do 'Motor de render'"
    fn = JS.split("function pintarDadosDeHardware(itens)", 1)[1][:900]
    assert 't.startsWith("Perfil automático") || t.startsWith("GPU:")' in fn, (
        "os MESMOS itens do Diagnostico — a checagem e a fonte")
    assert "escapeHtml(it.titulo" in fn and "escapeHtml(it.detalhe)" in fn
    assert 'it.nivel === "aviso" || it.nivel === "bloqueio"' in fn, "o ponto muda de cor"
    # chamado quando a checagem roda (ao abrir Configuracoes e no botao)
    corpo = JS.split("async function runDoutor()", 1)[1][:1200]
    assert "pintarDadosDeHardware(itens);" in corpo
    assert ".perf-dado.aviso::before" in CSS and ".perf-dado.bloqueio::before" in CSS


def test_email_e_id_do_dispositivo_copiaveis():
    assert 'id="sysQuem"' in HTML
    assert HTML.index('id="sysQuem"') > HTML.index('id="sysStatusLine"'), "ao lado do status"
    fn = JS.split("function renderQuemSou()", 1)[1][:1600]
    assert "state.auth && state.auth.email" in fn
    assert "state.license && state.license.deviceId" in fn
    assert 'pill("Conta", email, email,' in fn
    assert 'pill("ID do dispositivo", codigoDoPc(id) || id, id,' in fn, (
        "mostra o codigo curto da tela de maquinas e copia o ID INTEIRO")
    assert "await copiarTexto(copia)" in fn, "o mesmo copiar da tela"
    assert 'b.type = "button"' in fn
    assert "escapeHtml(valor)" in fn and "escapeHtml(rotulo)" in fn
    # sem conta e sem ID, nada aparece (instalacao aberta, antes do login)
    assert 'if (!email && !id) { box.classList.add("hidden"); return; }' in fn


def test_o_quem_sou_acompanha_licenca_e_checagem():
    """A licenca chega depois do login e a checagem roda ao abrir a tela:
    nos dois momentos o par e-mail/ID e repintado."""
    lic = JS.split("function renderLicense(lic)", 1)[1][:600]
    assert "state.license = lic;\n  renderQuemSou();" in lic
    corpo = JS.split("async function runDoutor()", 1)[1][:1200]
    assert "renderQuemSou();" in corpo
