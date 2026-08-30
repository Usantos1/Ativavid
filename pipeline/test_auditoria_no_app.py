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


def test_a_auditoria_nao_roda_sozinha():
    """O Diagnóstico roda ao abrir porque é barato e é a primeira pergunta
    de quem chega ali. Esta lê 187 projetos em ~11s — é uma pergunta que se
    faz de propósito."""
    i = JS.index('if (name === "sistema") {')
    bloco = JS[i:i + 500]
    assert "runDoutor()" in bloco
    assert "rodarAuditoria()" not in bloco
