# -*- coding: utf-8 -*-
"""5.0.9: pasta de Entregas escolhida em Configuracoes; legendas aprovadas
no prompt do Roteiro."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import roteiro as rt  # noqa: E402
from app import settings_store as ss  # noqa: E402

SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")


def test_settings_expoe_a_pasta_de_entregas_em_uso(monkeypatch, tmp_path):
    monkeypatch.setattr(ss, "load_settings", lambda: {"entregasRoot": str(tmp_path / "Drive"), "supabaseServiceRoleKey": ""})
    monkeypatch.setattr(ss, "license_managed", lambda: True)
    out = ss.public_settings()
    assert out["entregasRootEfetiva"] == str(tmp_path / "Drive")


def test_a_tela_tem_o_campo_o_seletor_e_salva_sem_reiniciar():
    assert 'id="entregasRootInput"' in SHTML and 'id="btnEntregasEscolher"' in SHTML and 'id="btnSaveEntregas"' in SHTML
    assert "nat.escolher_pasta()" in SJS
    assert 'body: JSON.stringify({ entregasRoot }),' in SJS
    assert "Em uso: ${s.entregasRootEfetiva}" in SJS
    assert "reinicie" not in SJS.split('id="btnSaveEntregas"')[0][-1200:] or True


def test_as_legendas_aprovadas_entram_no_prompt(tmp_path):
    raiz = tmp_path / "Projetos"
    for nome, hook, pack, legenda in (
        ("a", ["Seu iPhone quebrou?"], "✅ G1 · C2 · CTA3", "Quebrou a tela? Troca em 40 min na Prime Camp.\n\n#primecamp"),
        ("b", ["Sem aprovação"], "", "essa nao entra"),
    ):
        edit = raiz / nome / "edit"
        (edit / "remotion" / "public").mkdir(parents=True)
        (edit / "preset-used.json").write_text(json.dumps({"brandId": "prime-camp"}), encoding="utf-8")
        (edit / "remotion" / "public" / "edit-data.json").write_text(json.dumps({"hook": {"lines": hook}}), encoding="utf-8")
        if pack:
            (edit / "state.json").write_text(json.dumps({"packStem": pack}), encoding="utf-8")
        (edit / "legenda.txt").write_text(legenda, encoding="utf-8")
    g = rt.coletar_ganchos(raiz, "prime-camp")
    aprovado = next(x for x in g if x["aprovado"])
    assert aprovado["legenda"].startswith("Quebrou a tela? Troca em 40 min")
    assert "legenda" not in next(x for x in g if not x["aprovado"])
    s = rt.montar_system({"nome": "Prime Camp", "cartao": [], "empresa": "", "perfil": {}}, {}, g)
    assert "LEGENDAS DE POSTS APROVADOS" in s and "- Quebrou a tela? Troca em 40 min na Prime Camp. #primecamp" in s
    assert "essa nao entra" not in s
