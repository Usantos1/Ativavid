# -*- coding: utf-8 -*-
"""Roteiro de gravacao (4.97): a IA escreve o que gravar.

Ele em 03/09: "um criador de roteiro de gravacao, tipo uma conversa com a
IA, abaixo de Presets, botoes prontos, manda pra LLM os dados da empresa e
regras de como devolver o roteiro limpo, salvar a memoria dos chats local,
copiar as respostas, escolher o estilo do video, ganchos que param scroll".
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import roteiro as rt  # noqa: E402

SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
DESKTOP = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
JS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
CSS = (REPO / "assets" / "studio" / "studio.css").read_text(encoding="utf-8")


def _casa(monkeypatch, tmp_path, empresa=""):
    """Marca 'prime-camp' num diretorio de teste, roteiros ao lado."""
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "prime-camp.json").write_text(json.dumps({
        "brandId": "prime-camp", "brandName": "Prime Camp",
        "endCardCopy": {"line1": "Segue @lojaprimecamp", "line2": "ou me chama no direct"},
        "empresa": empresa,
    }), encoding="utf-8")
    monkeypatch.setattr(rt, "BRANDS_DIR", brands)
    monkeypatch.setattr(rt, "ROTEIROS_DIR", tmp_path / "roteiros")
    monkeypatch.setattr(rt, "ensure_brands_dir", lambda: None)
    from app import brand_kits as bk
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(bk, "ensure_brands_dir", lambda: None)
    monkeypatch.setattr(bk, "get_active_id", lambda: "prime-camp")


# ---------------------------------------------------------------- prompt
def test_o_prompt_leva_a_empresa_o_cartao_e_o_formato(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, empresa="Assistência de celulares em Campinas, troca de tela em 40 min")
    p = rt.perfil_empresa("prime-camp")
    s = rt.montar_system(p, {"estilo": "viral", "duracao": 45, "objetivo": "alcance", "tom": "provocador"})
    assert "EMPRESA: Prime Camp" in s
    assert "troca de tela em 40 min" in s
    assert "Segue @lojaprimecamp / ou me chama no direct" in s
    assert "Viral / curiosidade" in s and "45 segundos" in s
    assert "alcance máximo" in s and "provocador" in s
    for secao in ("GANCHOS", "ROTEIRO PARA GRAVAR (45s)", "CTA", "TEXTO NA TELA", "LEGENDA DO POST"):
        assert secao in s, secao
    assert "sem markdown" in s and "sem emoji" in s
    assert "TAREFA DE TEXTO" in s, "o Gemini web recusa 'tarefa de video' (4.76)"


def test_sem_dados_da_empresa_o_prompt_diz_isso(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    s = rt.montar_system(rt.perfil_empresa("prime-camp"), {})
    assert "ainda não descreveu a empresa" in s


def test_duracao_estranha_cai_na_mais_proxima(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    s = rt.montar_system(rt.perfil_empresa("prime-camp"), {"duracao": 50})
    assert "45 segundos" in s


# --------------------------------------------------------------- memoria
def test_a_conversa_e_gravada_local_por_marca_e_volta_como_historico(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, empresa="loja")
    visto = []

    def chamar(msgs):
        visto.append(msgs)
        return ("GANCHOS\n1. Seu celular ainda carrega assim?\n\nROTEIRO PARA GRAVAR (30s)\n1. (0-3s) fala\n\nCTA\nSegue", "gemini-web")

    r1 = rt.responder("prime-camp", "troca de tela de iPhone", opcoes={"estilo": "venda", "duracao": 30}, chamar=chamar)
    assert r1["ok"] and r1["backend"] == "gemini-web"
    cid = r1["chat"]["id"]
    arq = tmp_path / "roteiros" / "prime-camp" / f"{cid}.json"
    assert arq.exists(), "memoria local, por marca"
    dado = json.loads(arq.read_text(encoding="utf-8"))
    assert dado["titulo"] == "troca de tela de iPhone"
    assert [m["role"] for m in dado["mensagens"]] == ["user", "assistant"]
    assert visto[0][0]["role"] == "system" and visto[0][-1]["content"].endswith("troca de tela de iPhone")

    r2 = rt.responder("prime-camp", "deixa mais curto", chat_id=cid, chamar=chamar)
    roles = [m["role"] for m in visto[1]]
    assert roles == ["system", "user", "assistant", "user"], "o historico volta para a IA"
    assert len(r2["chat"]["mensagens"]) == 4
    assert rt.listar("prime-camp")[0]["id"] == cid
    assert rt.renomear("prime-camp", cid, "Tela iPhone")["titulo"] == "Tela iPhone"
    assert rt.apagar("prime-camp", cid) is True and rt.listar("prime-camp") == []


def test_o_nicho_vai_junto_e_a_mensagem_vazia_e_recusada(monkeypatch, tmp_path):
    import pytest
    _casa(monkeypatch, tmp_path)
    visto = []
    rt.responder("prime-camp", "capinha", opcoes={"nicho": "donos de iPhone"}, chamar=lambda m: (visto.append(m) or ("GANCHOS\n1. x", "groq")))
    assert visto[0][-1]["content"].startswith("Nicho/público: donos de iPhone")
    with pytest.raises(ValueError):
        rt.responder("prime-camp", "   ", chamar=lambda m: ("x", "groq"))


def test_resposta_vazia_da_ia_nao_grava_conversa(monkeypatch, tmp_path):
    import pytest
    _casa(monkeypatch, tmp_path)
    with pytest.raises(RuntimeError):
        rt.responder("prime-camp", "x", chamar=lambda m: ("", "groq"))
    assert rt.listar("prime-camp") == []


def test_dados_da_empresa_ficam_na_marca_sem_apagar_o_resto(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    p = rt.salvar_empresa("prime-camp", "Assistência em Campinas")
    assert p["empresa"] == "Assistência em Campinas"
    dado = json.loads((tmp_path / "brands" / "prime-camp.json").read_text(encoding="utf-8"))
    assert dado["endCardCopy"]["line1"] == "Segue @lojaprimecamp", "o cartao final nao pode sumir"
    assert dado["brandName"] == "Prime Camp"


# ---------------------------------------------------------------- recusa
RECUSA = "Sou um modelo de linguagem. Isso está além das minhas habilidades."
BOM = "GANCHOS\n1. Seu celular ainda carrega assim?\n\nCTA\nsegue"


def test_a_sessao_que_recusa_e_repetida_com_reforco(monkeypatch, tmp_path):
    """Caso real da primeira chamada (03/09): a sessão do Gemini respondeu
    'sou um modelo de linguagem, isso está além das minhas habilidades'."""
    _casa(monkeypatch, tmp_path)
    vistos = []

    def chamar(msgs):
        vistos.append(msgs)
        return (RECUSA, "gemini-web") if len(vistos) == 1 else (BOM, "gemini-web")

    r = rt.responder("prime-camp", "capinha", chamar=chamar, groq=lambda m: "x")
    assert r["resposta"].startswith("GANCHOS") and len(vistos) == 2
    assert vistos[1][0]["content"].startswith(rt.REFORCO), "a repeticao leva o reforco no system"


def test_recusa_duas_vezes_cai_no_groq(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    r = rt.responder("prime-camp", "capinha", chamar=lambda m: (RECUSA, "gemini-web"),
                     groq=lambda m: BOM)
    assert r["backend"] == "groq" and r["resposta"].startswith("GANCHOS")


def test_recusa_sem_groq_vira_erro_claro(monkeypatch, tmp_path):
    import pytest
    _casa(monkeypatch, tmp_path)
    from app import llm_gateway as gw
    monkeypatch.setattr(gw, "_groq_key", lambda: "")
    with pytest.raises(RuntimeError, match="recusou"):
        rt.responder("prime-camp", "capinha", chamar=lambda m: (RECUSA, "gemini-web"))
    assert rt.listar("prime-camp") == [], "recusa nao vira conversa gravada"


def test_recusa_e_curta_e_um_roteiro_que_cita_modelo_nao_e_recusa():
    assert rt.recusou(RECUSA)
    assert not rt.recusou("GANCHOS\n1. x\n" + ("fala " * 120) + "modelo de linguagem")
    assert not rt.recusou("")


# --------------------------------------------------------------- limpeza
def test_o_markdown_do_modelo_e_tirado():
    t = "## GANCHOS\n**1.** Seu celular *ainda* carrega assim?\n- item\n```\nROTEIRO\n```\n\n\n\nCTA"
    limpo = rt._limpar(t)
    assert limpo.startswith("GANCHOS\n1. Seu celular ainda carrega assim?")
    assert "**" not in limpo and "##" not in limpo and "```" not in limpo
    assert "\n\n\n" not in limpo
    # hashtag no comeco da linha NAO e cabecalho (a 1a chamada real perdeu o "#campinas")
    assert rt._limpar("LEGENDA DO POST\n#campinas #trocadetela").endswith("#campinas #trocadetela")


def test_so_a_secao_de_ganchos():
    t = "GANCHOS\n1. a\n2. b\n\nROTEIRO PARA GRAVAR (30s)\n1. (0-3s) fala\n\nCTA\nsegue"
    assert rt.secao(t, "GANCHOS") == "1. a\n2. b"
    assert rt.secao(t, "CTA") == "segue"


# ----------------------------------------------------------------- rotas
def test_as_rotas_existem_cobram_licenca_e_o_desktop_delega():
    i = SERVER.index('if (path == "/api/roteiro/chat" or path == "/api/roteiro/empresa"')
    corpo = SERVER[i:i + 2500]
    assert "lic.entitlement()" in corpo and "deny_reason" in corpo
    assert "roteiro.responder(" in corpo and "roteiro.salvar_empresa(" in corpo
    assert "friendly_llm_error" in corpo, "erro da IA vira frase de gente"
    assert 'if path == "/api/roteiro/chats" or path == "/api/roteiro/chat" or path == "/api/roteiro/empresa":' in SERVER
    for rota in ("/api/roteiro/chats", "/api/roteiro/chat", "/api/roteiro/empresa",
                 "/api/roteiro/apagar", "/api/roteiro/renomear"):
        assert f'"{rota}"' in DESKTOP, rota


# ------------------------------------------------------------------ tela
def test_a_tela_esta_abaixo_de_presets_com_os_botoes_prontos():
    nav = HTML[HTML.index('data-view="presets"'):HTML.index('<p class="sb-label">Automação</p>')]
    assert 'data-view="roteiro"' in nav
    i = HTML.index('id="view-roteiro"')
    bloco = HTML[i:HTML.index('id="view-presets"', i)]
    for el in ("rotEstilo", "rotDuracao", "rotObjetivo", "rotTom", "rotNicho", "rotTexto",
               "rotEnviar", "rotChats", "rotNovo", "rotEmpresaTexto", "rotEmpresaSalvar", "rotPensando"):
        assert f'id="{el}"' in bloco, el
    assert bloco.count("data-ideia=") >= 6, "botoes prontos para preencher a ideia"
    assert "rot-dots" in bloco, "animacao enquanto a resposta chega"


def test_o_js_liga_a_tela_e_copia():
    assert 'roteiro: ["Roteiro"' in JS
    assert 'if (name === "roteiro") loadRoteiroUi()' in JS
    i = JS.index("async function rotEnviar(")
    bloco = JS[i:JS.index("\nfunction wireRoteiro", i)]
    assert 'api("/api/roteiro/chat"' in bloco and "rotPensando(true)" in bloco and "rotPensando(false)" in bloco
    j = JS.index("function wireRoteiro(")
    w = JS[j:]
    assert "data-copiar-ganchos" in w and 'rotSecao(txt, "GANCHOS")' in w
    assert "navigator.clipboard.writeText" in JS[JS.index("async function rotCopiar("):]
    assert 'Enter" && !e.shiftKey' in w
    assert "@keyframes rotdot" in CSS
