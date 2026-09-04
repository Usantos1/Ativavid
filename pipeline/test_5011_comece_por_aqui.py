# -*- coding: utf-8 -*-
"""5.0.11: guia "Comece por aqui" no Inicio de uma instalacao nova."""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")


def test_o_guia_tem_tres_passos_com_destino():
    i = SHTML.index('id="comece"')
    bloco = SHTML[i:SHTML.index('id="jobListRecent"', i)]
    assert bloco.count('class="comece-passo"') == 3
    assert 'data-passo="empresa"' in bloco and 'data-view="presets"' in bloco
    assert 'data-passo="aula"' in bloco and 'data-view="aulas"' in bloco
    assert 'data-passo="video"' in bloco and 'id="comeceImportar"' in bloco
    assert 'id="comeceOcultar"' in bloco


def test_so_aparece_sem_video_e_marca_o_que_ja_foi_feito():
    i = SJS.index("function renderComece()")
    fn = SJS[i:SJS.index("function wireComece()", i)]
    assert 'const mostrar = !oculto && !!state.jobsLoaded && (state.jobs || []).length === 0;' in fn
    assert "empresa: !!(state.brandActive && state.brandActive.perfilOk)" in fn
    assert "aula: !!(state.aulas && state.aulas.feitas && state.aulas.feitas.size > 0)" in fn
    assert 'localStorage.setItem(COMECE_KEY, "1")' in SJS
    assert '$("#comeceImportar")?.addEventListener("click", () => $("#btnPick")?.click());' in SJS
    assert "function renderJobs() {\n  renderComece();" in SJS, "repinta a cada carga de jobs"
