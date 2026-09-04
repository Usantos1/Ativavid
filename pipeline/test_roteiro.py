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


def test_cartao_vazio_na_marca_vem_do_preset_ativo(monkeypatch, tmp_path):
    """A marca dele tem endCardCopy vazio; o 'Segue @lojaprimecamp' mora no
    preset ativo. A 1a conversa real saiu com '(sem cartao)'."""
    _casa(monkeypatch, tmp_path)
    (tmp_path / "brands" / "prime-camp.json").write_text(json.dumps({
        "brandId": "prime-camp", "brandName": "Prime Camp",
        "endCardCopy": {"line1": "", "line2": ""}}), encoding="utf-8")
    from app import brand_presets as bp
    monkeypatch.setattr(bp, "get_active", lambda bid: {"id": "novo", "style": {"endCardCopy": {"line1": "Segue @lojaprimecamp", "line2": ""}}})
    p = rt.perfil_empresa("prime-camp")
    assert p["cartao"] == ["Segue @lojaprimecamp", ""]
    assert "Segue @lojaprimecamp" in rt.montar_system(p, {})


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


# ------------------------------------------------ perfil com campos (4.99)
def test_o_perfil_com_campos_entra_no_prompt_uma_linha_por_campo(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    rt.salvar_perfil("prime-camp", {"vende": "troca de tela e bateria", "local": "Campinas",
                                    "proibido": ["preço fechado", "concorrentes"], "lixo": "x"})
    p = rt.perfil_empresa("prime-camp")
    assert p["perfil"] == {"vende": "troca de tela e bateria", "local": "Campinas",
                           "proibido": "preço fechado; concorrentes"}
    assert [c["id"] for c in p["campos"]] == rt._PERFIL_IDS
    s = rt.montar_system(p, {})
    assert "- O que vende / serviços: troca de tela e bateria" in s
    assert "- Cidade / região: Campinas" in s
    assert "- O que NÃO falar: preço fechado; concorrentes" in s
    assert "ainda não descreveu" not in s
    dado = json.loads((tmp_path / "brands" / "prime-camp.json").read_text(encoding="utf-8"))
    assert dado["brandName"] == "Prime Camp", "o resto da marca fica"


def _projeto(raiz, nome, brand, texto, legenda=""):
    edit = raiz / nome / "edit"
    (edit / "transcripts").mkdir(parents=True)
    (edit / "transcripts" / "cut.json").write_text(json.dumps({"text": texto}), encoding="utf-8")
    (edit / "preset-used.json").write_text(json.dumps({"brandId": brand}), encoding="utf-8")
    if legenda:
        (edit / "legenda.txt").write_text(legenda, encoding="utf-8")


def test_coleta_so_as_falas_desta_marca_sem_repetir_as_combinacoes(tmp_path):
    raiz = tmp_path / "Projetos"
    fala = "Seu iPhone quebrou e você não pode ficar sem ele hoje. Na Prime Camp a gente troca a tela em quarenta minutos."
    _projeto(raiz, "20260903-1_G1C1A1_a", "loja-teste", fala, "Troca de tela em 40 min #campinas")
    _projeto(raiz, "20260903-1_G1C2A1_b", "loja-teste", fala + " Com garantia.", "Troca de tela em 40 min #campinas")
    _projeto(raiz, "20260901-1_x", "loja-teste", "Hoje chegou um Xiaomi com a bateria estufada e a gente resolveu na hora com peça original.")
    _projeto(raiz, "20260902-1_outra", "ativa-crm", "Vídeo de outra marca que não pode entrar aqui de jeito nenhum.")
    _projeto(raiz, "20260902-1_curto", "loja-teste", "oi")
    falas = rt.coletar_falas(raiz, "loja-teste")
    textos = [f["texto"] for f in falas]
    assert len(falas) == 2, textos
    assert all("outra marca" not in t for t in textos)
    assert any(f["legenda"].startswith("Troca de tela") for f in falas)


def test_montar_perfil_pelos_videos_devolve_rascunho_sem_gravar(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path)
    raiz = tmp_path / "Projetos"
    _projeto(raiz, "20260903-1_a", "prime-camp", "Na Prime Camp a gente troca a tela do seu iPhone em quarenta minutos com noventa dias de garantia, em Campinas.")
    visto = []

    def chamar(msgs):
        visto.append(msgs)
        return ('{"vende": "troca de tela de iPhone", "local": "Campinas", "diferenciais": "40 minutos, garantia de 90 dias", "oferta": ""}', "gemini-web")

    r = rt.montar_perfil_pelos_videos(raiz, "prime-camp", chamar=chamar)
    assert r["ok"] and r["videos"] == 1
    assert r["perfil"] == {"vende": "troca de tela de iPhone", "local": "Campinas",
                           "diferenciais": "40 minutos, garantia de 90 dias"}
    assert "APENAS um JSON" in visto[0][0]["content"] and "quarenta minutos" in visto[0][1]["content"]
    assert rt.perfil_empresa("prime-camp")["perfil"] == {}, "rascunho nao grava; quem grava e o Salvar"


def test_sem_videos_da_marca_o_botao_explica(monkeypatch, tmp_path):
    import pytest
    _casa(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="Ainda não há vídeos"):
        rt.montar_perfil_pelos_videos(tmp_path / "vazio", "prime-camp", chamar=lambda m: ("{}", "x"))


def test_a_tela_tem_o_formulario_e_o_botao_dos_videos():
    # 5.0.1: o perfil mora na tela de Empresas (view-presets), nao no Roteiro
    i = HTML.index('id="rotEmpresaBox"')
    bloco = HTML[i:HTML.index('id="btnPresetNovo"', i)]
    assert HTML.index('id="view-presets"') < i, "dentro da tela de Empresas"
    assert 'id="rotPerfilGrid"' in bloco and 'id="rotPerfilDosVideos"' in bloco and 'id="rotEmpresaTexto"' in bloco
    assert "function rotMontarPerfilForm(" in JS and "function rotLerPerfilForm(" in JS
    assert 'api("/api/roteiro/perfil-dos-videos"' in JS
    assert "if (!atual[k] && r.perfil[k]) ta.value = r.perfil[k];" in JS, "o rascunho nao apaga o que a pessoa escreveu"
    assert 'perfil: rotLerPerfilForm()' in JS
    assert '"/api/roteiro/perfil-dos-videos"' in DESKTOP
    assert 'if path == "/api/roteiro/perfil-dos-videos":' in SERVER


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
    corpo = SERVER[i:SERVER.index('if path == "/api/brands":', i)]
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
               "rotEnviar", "rotChats", "rotNovo", "rotEmpresaAbrir", "rotPensando"):  # perfil: em Empresas (5.0.1)
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
    # so as mensagens rolam: lista e caixa de digitar paradas (03/09)
    assert "body.view-roteiro-on .ws-body { overflow: hidden; }" in CSS
    assert "#view-roteiro .rot-msgs { flex: 1; min-height: 160px; overflow: auto; }" in CSS
    assert 'document.body.classList.toggle("view-roteiro-on", name === "roteiro")' in JS
