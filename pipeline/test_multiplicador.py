# -*- coding: utf-8 -*-
"""Multiplicador de criativos: ganchos x corpos x CTAs viram TODAS as combinações.

Pedido do usuário (01/09): "3 gancho, 3 corpo e 3 CTA, aí ele monta todas as
combinações possíveis com os mesmos takes". Cada combinação é um projeto
próprio com HARDLINK das fontes (padrão dos Clipes de podcast) e entra na
fila como job multi-take na ordem gancho → corpo → CTA — a ordem de
`sources` é a ordem da concatenação.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.multiplicador import (  # noqa: E402
    MultiplicadorInvalido,
    contar_combos,
    materializar_combos,
    preparar_pasta_mae,
)


def _fontes(tmp_path: Path, n_g=2, n_c=2, n_cta=2):
    origem = tmp_path / "origem"
    origem.mkdir()
    arquivos = {"gancho": [], "corpo": [], "cta": []}
    for papel, n in (("gancho", n_g), ("corpo", n_c), ("cta", n_cta)):
        for i in range(n):
            f = origem / f"{papel} take {i + 1}.mp4"   # espaço no nome de propósito
            f.write_bytes(f"video-{papel}-{i}".encode())
            arquivos[papel].append((f.name, f, False))
    return arquivos


def test_todas_as_combinacoes_na_ordem_gancho_corpo_cta(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    arquivos = _fontes(tmp_path, 2, 2, 2)
    mae, fontes = preparar_pasta_mae(raiz, arquivos)
    combos = materializar_combos(raiz, fontes)

    assert len(combos) == 8
    nomes = [c["name"] for c in combos]
    assert nomes[0] == "G1 · C1 · CTA1"
    assert nomes[-1] == "G2 · C2 · CTA2"
    assert len(set(nomes)) == 8, "nome de combinação repetido"
    for c in combos:
        srcs = [Path(s) for s in c["sources"]]
        assert len(srcs) == 3
        # ordem: gancho, corpo, cta — o prefixo do nome carrega o papel
        assert srcs[0].name.startswith("g")
        assert srcs[1].name.startswith("c") and not srcs[1].name.startswith("cta")
        assert srcs[2].name.startswith("cta")
        assert c["source"] == c["sources"][0]
        assert Path(c["editDir"]).is_dir()


def test_fontes_entram_por_hardlink_nao_por_copia(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    mae, fontes = preparar_pasta_mae(raiz, _fontes(tmp_path))
    combos = materializar_combos(raiz, fontes)
    g1 = fontes["gancho"][0]
    usados = [Path(c["sources"][0]) for c in combos if Path(c["sources"][0]).name == g1.name]
    assert usados, "nenhuma combinação usa o gancho 1"
    for p in usados:
        assert os.path.samefile(p, g1), "a fonte foi copiada em vez de linkada"


def test_pasta_mae_guarda_uma_copia_com_papel_no_nome(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    mae, fontes = preparar_pasta_mae(raiz, _fontes(tmp_path, 1, 1, 1))
    assert "multiplicador-fontes" in mae.name
    assert [p.name for p in fontes["gancho"]] == ["g1-gancho take 1.mp4"]
    assert [p.name for p in fontes["corpo"]] == ["c1-corpo take 1.mp4"]
    assert [p.name for p in fontes["cta"]] == ["cta1-cta take 1.mp4"]


def test_mover_tira_o_arquivo_do_temporario(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    arquivos = _fontes(tmp_path, 1, 1, 1)
    nome, origem, _ = arquivos["gancho"][0]
    arquivos["gancho"][0] = (nome, origem, True)   # upload: move
    mae, fontes = preparar_pasta_mae(raiz, arquivos)
    assert not origem.exists(), "upload deveria MOVER, não copiar"
    assert fontes["gancho"][0].is_file()


def test_caixa_vazia_e_recusada_com_mensagem_de_gente(tmp_path):
    """5.0.35: o papel do meio chama-se "conteúdo" na tela ("corpo não pega bem", 04/09)."""
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    arquivos = _fontes(tmp_path, 2, 0, 2)
    with pytest.raises(MultiplicadorInvalido, match="conteúdo"):
        preparar_pasta_mae(raiz, arquivos)


def test_teto_de_combinacoes(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    arquivos = _fontes(tmp_path, 4, 4, 4)   # 64 > 48
    with pytest.raises(MultiplicadorInvalido, match="teto"):
        preparar_pasta_mae(raiz, arquivos)
    assert contar_combos(arquivos) == 64


def test_intent_e_gravado_em_cada_combinacao(tmp_path):
    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    mae, fontes = preparar_pasta_mae(raiz, _fontes(tmp_path, 1, 1, 1))
    combos = materializar_combos(
        raiz, fontes,
        intent={"editingIntent": "complete", "contentType": "ad",
                "preserveCTA": True},
    )
    from app.editing_intent import load as load_intent

    dado = load_intent(Path(combos[0]["editDir"])) or {}
    assert dado.get("editingIntent") == "complete"
    assert dado.get("contentType") == "ad"


def test_rota_existe_gateada_e_liberada_no_desktop():
    """A rota nova precisa (a) cobrar licença como as irmãs e (b) estar na
    lista de POSTs que o desktop delega ao studio — sem isso o botão só
    funcionaria no navegador."""
    servidor = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = servidor.index('if path == "/api/multiplicador":')
    corpo = servidor[i:i + 1200]
    assert "lic.entitlement()" in corpo, "rota do multiplicador sem gate de licença"
    assert "deny_reason" in corpo

    desktop = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/multiplicador"' in desktop, "desktop não delega /api/multiplicador"


# ------------------------------------------------- marca e preset (4.95)
def test_a_janela_pergunta_marca_e_preset():
    """"quero escolher o preset ou a marca na hora de multiplicar" (03/09):
    o lote saia com o preset padrao ("Novo") e ele via no editor, 27
    videos depois."""
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    i = html.index('<dialog id="dlgMulti"')
    bloco = html[i:html.index("</dialog>", i)]
    assert 'id="multiBrandSelect"' in bloco and 'id="multiPresetSelect"' in bloco
    assert 'id="multiContentType"' in bloco


def test_a_escolha_vai_no_intent_de_cada_combinacao():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function wireMultiplicador(")
    bloco = js[i:js.index("\nasync function importarPorCaminho", i)]
    assert 'brandId: (brandSel && brandSel.value) || state.brandActive?.id || null' in bloco
    assert 'brandPresetId: (presetSel && presetSel.value) || null' in bloco
    assert 'brandStyleSource: "default"' in bloco
    assert "loadMultiPresets()" in bloco, "abrir a janela carrega marca e presets"
    j = js.index("async function loadMultiPresets(")
    fn = js[j:js.index("\nasync function loadBrandsUi", j)]
    assert "/api/brand-presets?brandId=" in fn and '/api/brands' in fn
    assert "brandSel.onchange" in fn, "trocar a marca recarrega os presets"


def test_o_pipeline_le_marca_e_preset_do_intent(tmp_path):
    """O que a janela manda tem de chegar ao preset do job: e o mesmo
    caminho do import normal (resolve_for_edit)."""
    from app.editing_intent import load as load_intent

    raiz = tmp_path / "Projetos"
    raiz.mkdir()
    _mae, fontes = preparar_pasta_mae(raiz, _fontes(tmp_path, 1, 1, 1))
    combos = materializar_combos(
        raiz, fontes,
        intent={"editingIntent": "complete", "contentType": "ad",
                "brandStyleSource": "default",
                "brandId": "prime-camp", "brandPresetId": "topo"})
    dado = load_intent(Path(combos[0]["editDir"])) or {}
    assert dado["brandId"] == "prime-camp" and dado["brandPresetId"] == "topo"
    src = (REPO / "app" / "preset_chain.py").read_text(encoding="utf-8")
    k = src.index("def resolve_for_edit(")
    corpo = src[k:src.index("\ndef ", k + 10) if "\ndef " in src[k + 10:] else len(src)]
    assert 'intent.get("brandId")' in corpo and 'intent.get("brandPresetId")' in corpo
