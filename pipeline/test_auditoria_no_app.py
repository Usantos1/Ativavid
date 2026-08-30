# -*- coding: utf-8 -*-
"""A auditoria dos vídeos entregues, agora dentro do app.

`tools/auditar_projetos.py` passa invariantes em TODOS os projetos e lista
o que saiu torto — trecho pedindo tempo que a fonte não tem, pausa morta
sobrando no corte, rótulo errado no EDL, vídeo sem trilha. Foi por ela que
os defeitos mais caros apareceram, e nenhum deles dava erro na hora.

Até 30/08 só quem tinha terminal conseguia rodar.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOL = (REPO / "tools" / "auditar_projetos.py").read_text(encoding="utf-8")
SRV = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_a_ferramenta_fala_json_e_texto():
    """O texto continua sendo o que se lê no terminal; o JSON é para o app.
    Parsear texto impresso seria frouxo demais para virar tela."""
    assert '_ap.add_argument("--json"' in TOOL
    assert "if _args.json:" in TOOL
    # e no modo JSON a saída tem de ser SÓ o JSON
    i = TOOL.index('print(f"projetos: {len(projs)}')
    assert "if not _args.json:" in TOOL[i - 120:i]


def test_o_servidor_expoe_a_auditoria():
    assert '"/api/auditoria"' in SRV
    assert "def rodar_auditoria(" in SRV
    i = SRV.index("def rodar_auditoria(")
    bloco = SRV[i:i + 1400]
    # tem de ter teto de tempo e caminho de erro — ela lê 187 projetos
    assert "timeout=180" in bloco
    assert "TimeoutExpired" in bloco
    assert '"ok": False' in bloco


def test_a_tela_tem_o_cartao_e_o_botao():
    assert 'id="auditoriaCard"' in HTML
    assert 'id="btnAuditoria"' in HTML
    assert "Conferir os vídeos entregues" in HTML
    assert "async function rodarAuditoria()" in JS
    assert '$("#btnAuditoria")' in JS


def test_a_conferencia_mora_em_projetos():
    """"isso nao quero em configuracoes" (30/08). Ela le os projetos e
    refaz video — e trabalho, nao ajuste de maquina. Configuracoes fica
    com a instalacao (Diagnostico, pastas, atualizacao)."""
    i = HTML.index('id="view-projetos"')
    j = HTML.index('id="view-estilo"')
    assert 'id="auditoriaCard"' in HTML[i:j], "saiu de Projetos"
    assert HTML.count('id="auditoriaCard"') == 1, "ficou em dois lugares"
    k = HTML.index('class="sys-grid"')
    assert 'id="auditoriaCard"' not in HTML[k:HTML.index('id="sysSupport"')]


def test_a_auditoria_nao_roda_sozinha():
    """O Diagnóstico roda ao abrir porque é barato e é a primeira pergunta
    de quem chega ali. Esta lê 187 projetos em ~11s — é uma pergunta que se
    faz de propósito."""
    i = JS.index('if (name === "sistema") {')
    bloco = JS[i:i + 500]
    assert "runDoutor()" in bloco
    assert "rodarAuditoria()" not in bloco


def test_a_auditoria_pode_consertar_e_nao_so_acusar():
    """Em 3.90 ela passou a acusar; o usuário ficava olhando a lista sem
    nada para fazer. As duas famílias mais comuns (15 rótulos errados, 4
    pausas) foram consertadas no pipeline em 29/08 — refazer o projeto com
    o pipeline de hoje resolve."""
    assert 'data-refazer=' in JS
    assert "async function refazerProjeto(" in JS
    i = JS.index("async function refazerProjeto(")
    bloco = JS[i:i + 1200]
    # reusa o endpoint que o editor já usa
    assert '"/api/jobs/requeue-folder"' in bloco
    # e pede confirmação: SUBSTITUI o vídeo entregue e ocupa a fila
    assert "pedirConfirmacao(" in bloco
    assert "é substituído" in bloco


def test_o_refazer_usa_funcoes_que_existem():
    """`loadJobs` não existe neste arquivo — eu inventei o nome na primeira
    versão e só o navegador teria contado, depois do clique."""
    i = JS.index("async function refazerProjeto(")
    bloco = JS[i:i + 1200]
    for chamada in ("pedirConfirmacao", "refreshJobs", "toast"):
        assert chamada in bloco, chamada
        assert (f"function {chamada}(" in JS
                or f"async function {chamada}(" in JS
                or f"const {chamada} =" in JS), f"{chamada} não existe"
