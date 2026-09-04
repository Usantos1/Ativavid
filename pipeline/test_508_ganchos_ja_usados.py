# -*- coding: utf-8 -*-
"""5.0.8: o Roteiro recebe os ganchos que a empresa ja usou (✅ = aprovado)."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import roteiro as rt  # noqa: E402


def _proj(raiz, nome, brand, hook, pack="", aihl=""):
    edit = raiz / nome / "edit"
    (edit / "remotion" / "public").mkdir(parents=True)
    (edit / "preset-used.json").write_text(json.dumps({"brandId": brand}), encoding="utf-8")
    ed = {"hook": {"enabled": True, "lines": hook}} if hook else {"aiHeadline": aihl}
    (edit / "remotion" / "public" / "edit-data.json").write_text(json.dumps(ed), encoding="utf-8")
    if pack:
        (edit / "state.json").write_text(json.dumps({"packStem": pack}), encoding="utf-8")


def test_coleta_so_da_empresa_marca_os_aprovados_e_nao_repete(tmp_path):
    raiz = tmp_path / "Projetos"
    _proj(raiz, "a", "prime-camp", ["Seu iPhone", "quebrou hoje?"], pack="✅ G1 · C2 · CTA3")
    _proj(raiz, "b", "prime-camp", ["Seu iPhone", "quebrou hoje?"])           # repetido (Multiplicador)
    _proj(raiz, "c", "prime-camp", [], aihl="Troca de tela em 40 minutos")
    _proj(raiz, "d", "ativa-crm", ["Outra empresa"])
    _proj(raiz, "e", "prime-camp", ["oi"])                                     # curto demais
    g = rt.coletar_ganchos(raiz, "prime-camp")
    textos = sorted(x["gancho"] for x in g)
    assert textos == ["Seu iPhone quebrou hoje?", "Troca de tela em 40 minutos"]
    assert next(x for x in g if x["gancho"].startswith("Seu iPhone"))["aprovado"] is True
    assert next(x for x in g if x["gancho"].startswith("Troca"))["aprovado"] is False
    assert rt.coletar_ganchos(tmp_path / "nao-existe", "prime-camp") == []


def test_o_prompt_lista_os_ganchos_e_pede_para_nao_repetir():
    p = {"nome": "Prime Camp", "cartao": [], "empresa": "", "perfil": {}}
    s = rt.montar_system(p, {}, [{"gancho": "Seu iPhone quebrou hoje?", "aprovado": True},
                                {"gancho": "Troca de tela em 40 minutos", "aprovado": False}])
    assert "GANCHOS QUE ESTA EMPRESA JÁ USOU" in s
    assert "- ✅ Seu iPhone quebrou hoje?" in s and "- Troca de tela em 40 minutos" in s
    assert s.index("GANCHOS QUE ESTA EMPRESA") < s.index("VIRAL QUE VENDE")
    assert "GANCHOS QUE ESTA EMPRESA" not in rt.montar_system(p, {}, [])
    assert "GANCHOS QUE ESTA EMPRESA" not in rt.montar_system(p, {})


def test_a_rota_passa_a_raiz_dos_projetos():
    src = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = src.index("out = roteiro.responder(")
    assert "projects_root=self.projects_root" in src[i:i + 400]
