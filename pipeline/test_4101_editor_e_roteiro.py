# -*- coding: utf-8 -*-
"""4.101: roteiro viral que vende; marca/preset a vista; midia no editor;
imagem na trilha principal; trilha trocada pela timeline.

A lista dele (03/09, por voz): "deixar o roteiro mais persuasivo, viral,
com gatilhos mentais, que traga clientes, nao so humor"; "o botao de
adicionar so deixa video, quero imagem na principal"; "o modal de buscar
imagem esta muito pequeno, biblioteca separada por audio/imagem/video";
"nao consigo substituir a trilha sonora"; "na hora de importar poder
escolher marca e preset".
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app import append_source as aps  # noqa: E402
from app import roteiro as rt  # noqa: E402

RUN = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
PHTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
PCSS = (REPO / "assets" / "preview" / "app.css").read_text(encoding="utf-8")


# ------------------------------------------------------- roteiro viral
def test_o_prompt_pede_viral_que_vende_com_gatilhos():
    p = {"nome": "Prime Camp", "cartao": ["Segue @lojaprimecamp", ""], "empresa": "",
         "perfil": {"vende": "troca de tela", "provas": "900 avaliações no Google"}}
    s = rt.montar_system(p, {"gatilho": "prova"})
    assert "VIRAL QUE VENDE" in s
    assert "GATILHO PRINCIPAL: prova social" in s
    assert "humor sozinho não serve" in s
    assert "proibido inventar preço, prazo, número" in s
    assert "entre colchetes, o gatilho usado" in s
    assert "POR QUE PARA O SCROLL" in s
    assert "Se ele pedir ÂNGULOS" in s
    assert "900 avaliações no Google" in s, "o perfil entra no prompt"
    assert "auto" in rt.GATILHOS and len(rt.GATILHOS) >= 8


def test_a_secao_por_que_para_o_scroll_e_reconhecida():
    t = "GANCHOS\n1. a [dor]\n\nCTA\nsegue\n\nPOR QUE PARA O SCROLL\nDor + loop aberto\n\nÂNGULOS\n1. x — dor — gancho"
    assert rt.secao(t, "POR QUE PARA O SCROLL") == "Dor + loop aberto"
    assert rt.secao(t, "ÂNGULOS") == "1. x — dor — gancho"
    assert rt.secao(t, "CTA") == "segue"


def test_a_tela_do_roteiro_tem_gatilho_e_explorar_angulos():
    i = SHTML.index('id="view-roteiro"')
    bloco = SHTML[i:SHTML.index('id="view-presets"', i)]
    assert 'id="rotGatilho"' in bloco
    assert 'data-ideia="Me dê 6 ÂNGULOS diferentes de vídeo sobre "' in bloco
    assert 'gatilho: $("#rotGatilho")?.value || "auto"' in SJS
    assert '"gatilhos": roteiro.GATILHOS' in (REPO / "app" / "local_server.py").read_text(encoding="utf-8")


# ----------------------------------------------- marca/preset no importar
def test_marca_e_preset_a_vista_no_importar():
    i = SHTML.index('id="dlgImport"') if 'id="dlgImport"' in SHTML else SHTML.index('id="importBrandSelect"') - 2000
    bloco = SHTML[i:SHTML.index('id="btnImportGo"', i)]
    assert 'id="importBrandSelect"' in bloco and 'id="importPresetSelect"' in bloco
    assert "<summary><h4>Estilo</h4>" not in bloco, "o preset nao fica mais escondido num details"
    assert 'brandId: ($("#importBrandSelect")?.value) || state.brandActive?.id || null' in SJS
    assert 'bsel.onchange = () => loadImportPresets(bsel.value)' in SJS


# ------------------------------------------------------ midia no editor
def test_modal_maior_com_abas_da_biblioteca():
    # 5.0.16: a janela ocupa a tela ("pode ser literalmente maior")
    assert "width: min(1760px, calc(100vw - 32px));" in PCSS
    assert "height: calc(100vh - 32px);" in PCSS
    i = PCSS.index(".img-results {")
    assert "flex: 1 1 auto;" in PCSS[i:i + 400] and "max-height: 64vh" not in PCSS[i:i + 400]
    for k in ("image", "clip", "sfx", "track"):
        assert f'data-libkind="{k}"' in PHTML, k
    assert "function kindDoItem(" in PJS and "function setLibKind(" in PJS
    assert ".filter((it) => kindDoItem(it) === LIB_KIND)" in PJS


def test_a_trilha_se_troca_pela_timeline():
    assert "function abrirMenuTrilha(" in PJS and "function definirTrilha(" in PJS
    assert "chip.addEventListener('click', (e) => { e.stopPropagation(); abrirMenuTrilha(e.clientX, e.clientY); });" in PJS
    assert "data-act=\"remover\"" in PJS and "data-act=\"trocar\"" in PJS
    assert "libraryPath: src ? (libraryPath || '') : ''" in PJS
    assert "card.addEventListener('click', () => usarComoTrilha(it));" in PJS


def test_o_refazer_respeita_a_trilha_escolhida():
    i = RUN.index('_st_ant.get("libraryPath")')
    bloco = RUN[i - 600:i + 900]
    assert 'if _st_ant.get("manual") and _st_ant.get("enabled") and _lib.is_file():' in bloco
    assert "shutil.copy2(_lib, music_tmp)" in bloco and "reuso = True" in bloco
    j = RUN.index('edit_data["soundtrack"]["enabled"] = True')
    assert 'if _music_via.get("manual"):' in RUN[j:j + 400], "a marca manual volta para o edit-data novo"


# --------------------------------------------- imagem na trilha principal
def test_o_importar_da_timeline_aceita_imagem():
    assert ".jpg,.jpeg,.png,.webp" in PHTML
    assert "const ehImagem = " in PJS and "ehImagem ? 5 : await probeLocalDuration(file)" in PJS
    assert aps.dest_cta_path(Path("."), "foto.png").suffix == ".png"
    import pytest
    with pytest.raises(ValueError):
        aps.dest_cta_path(Path("."), "doc.pdf")


def test_a_imagem_vira_clipe_mudo_no_tamanho_do_projeto(monkeypatch, tmp_path):
    visto = {}

    def run(cmd, **k):
        visto["cmd"] = [str(c) for c in cmd]
        Path(cmd[-1]).write_bytes(b"mp4")
        class R: returncode = 0; stderr = b""
        return R()

    monkeypatch.setattr(aps.subprocess, "run", run)
    monkeypatch.setattr(aps, "_ffmpeg", lambda: "ffmpeg")
    monkeypatch.setattr(aps, "_hide", lambda: {})
    out = aps.image_to_clip(tmp_path / "a.jpg", tmp_path / "a.mp4", width=1080, height=1920, seconds=5)
    assert out.exists()
    cmd = " ".join(visto["cmd"])
    assert "-loop 1" in cmd and "-t 5.00" in cmd and "anullsrc" in cmd, "clipe mudo, com faixa de audio para concatenar"
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in cmd and "pad=1080:1920" in cmd


def test_append_cta_converte_a_imagem_e_apaga_o_original(monkeypatch, tmp_path):
    proj = tmp_path / "proj"
    (proj / "edit" / "remotion" / "public").mkdir(parents=True)
    (proj / "edit" / "remotion" / "public" / "edit-data.json").write_text(json.dumps({"width": 1920, "height": 1080}), encoding="utf-8")
    foto = tmp_path / "logo.png"
    foto.write_bytes(b"PNG")
    chamadas = {}

    def fake_clip(src, dest, *, width, height, seconds=5.0, fps=30):
        chamadas.update(src=Path(src), dest=Path(dest), w=width, h=height, s=seconds)
        Path(dest).write_bytes(b"mp4")
        return Path(dest)

    monkeypatch.setattr(aps, "image_to_clip", fake_clip)
    monkeypatch.setattr(aps, "probe_clip", lambda p: {"duration": 5.0, "width": 1920, "height": 1080})
    r = aps.append_cta(proj, src_path=str(foto))
    assert r["ok"] and r["path"].endswith(".mp4") and r["duration"] == 5.0
    assert (chamadas["w"], chamadas["h"]) == (1920, 1080), "no tamanho do projeto (16:9 aqui)"
    assert not chamadas["src"].exists(), "a imagem copiada e apagada depois de virar clipe"
    assert Path(r["path"]).exists()
