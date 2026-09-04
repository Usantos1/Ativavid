# -*- coding: utf-8 -*-
"""5.0.7: o perfil da empresa entra no planejador, na headline e na legenda.

"Cada empresa dessa vai ter essas configurações próprias, o teu estilo,
o teu tipo de hashtag e tudo mais" (04/09). Ate aqui so o Roteiro lia o
perfil; a headline tinha "assistencia tecnica de celulares" fixo.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "helpers", REPO / "pipeline"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app import roteiro as rt  # noqa: E402


def _casa(monkeypatch, tmp_path, perfil=None):
    brands = tmp_path / "brands"
    brands.mkdir()
    (brands / "prime-camp.json").write_text(json.dumps({
        "brandId": "prime-camp", "brandName": "Prime Camp",
        "endCardCopy": {"line1": "Segue @lojaprimecamp", "line2": ""},
        "perfil": perfil or {},
    }), encoding="utf-8")
    (brands / "vazia.json").write_text(json.dumps({"brandId": "vazia", "brandName": "Vazia"}), encoding="utf-8")
    monkeypatch.setattr(rt, "BRANDS_DIR", brands)
    monkeypatch.setattr(rt, "ensure_brands_dir", lambda: None)
    from app import brand_kits as bk
    monkeypatch.setattr(bk, "BRANDS_DIR", brands)
    monkeypatch.setattr(bk, "ensure_brands_dir", lambda: None)


PERFIL = {"vende": "troca de tela de iPhone", "publico": "quem quebrou o celular hoje",
          "local": "Campinas, centro", "contato": "WhatsApp no link da bio",
          "tom": "direto, sem enrolar", "proibido": "preço fechado, concorrentes"}


def test_o_contexto_e_um_bloco_pronto_e_vazio_sem_perfil(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, PERFIL)
    ctx = rt.contexto_da_empresa("prime-camp")
    assert ctx.startswith("CONTEXTO DA EMPRESA")
    assert "- Empresa: Prime Camp" in ctx and "troca de tela de iPhone" in ctx
    assert "O que NÃO falar: preço fechado, concorrentes" in ctx
    assert rt.contexto_da_empresa("vazia") == "", "sem perfil, nada muda"
    assert rt.contexto_da_empresa("") == "" and rt.contexto_da_empresa(None) == ""


def test_o_planejador_recebe_o_perfil(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, PERFIL)
    from llm_cut_plan import _system_prompt
    com = _system_prompt({"brandId": "prime-camp"})
    sem = _system_prompt({"brandId": "vazia"})
    assert "CONTEXTO DA EMPRESA" in com and "quem quebrou o celular hoje" in com
    assert "falar a língua desta empresa" in com
    assert "CONTEXTO DA EMPRESA" not in sem
    assert com.index("PARÂMETROS DO PRESET") < com.index("CONTEXTO DA EMPRESA") < com.index("FORMATO:")


def test_a_headline_avulsa_deixou_de_ser_so_para_assistencia(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, PERFIL)
    import llm_cut_plan as lcp
    visto = {}

    def fake(messages):
        visto["system"] = messages[0]["content"]
        return {"headline": "Tela nova em 40 minutos", "headlineAlts": []}, "groq", ""

    monkeypatch.setattr(lcp, "_chamar_e_parsear", fake)
    r = lcp.headline_apenas("hoje chegou um iphone com a tela toda trincada e a gente trocou na hora", {"brandId": "prime-camp"})
    assert r["headline"] == "Tela nova em 40 minutos"
    assert "para a empresa descrita abaixo" in visto["system"] and "CONTEXTO DA EMPRESA" in visto["system"]
    assert "assistência técnica de celulares" not in visto["system"]
    lcp.headline_apenas("hoje chegou um iphone com a tela toda trincada e a gente trocou na hora", {"brandId": "vazia"})
    assert "para um negócio local no Brasil" in visto["system"] and "CONTEXTO" not in visto["system"]


def test_a_legenda_do_post_recebe_o_perfil(monkeypatch, tmp_path):
    _casa(monkeypatch, tmp_path, PERFIL)
    from app import llm_session
    import run_fast as rf
    visto = {}

    def fake_chat(messages, **k):
        visto["system"] = messages[0]["content"]
        return "Gancho\nCorpo curto", "groq"

    monkeypatch.setattr(llm_session, "chat", fake_chat)
    out = rf._llm_polish_legenda("rascunho", spoken="fala", preset={"brandId": "prime-camp", "endCardCopy": {}})
    assert out and "CONTEXTO DA EMPRESA" in visto["system"]
    assert "Use o tom de voz da empresa" in visto["system"] and "WhatsApp no link da bio" in visto["system"]
    rf._llm_polish_legenda("rascunho", spoken="fala", preset={"brandId": "vazia", "endCardCopy": {}})
    assert "CONTEXTO DA EMPRESA" not in visto["system"]
