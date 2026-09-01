# -*- coding: utf-8 -*-
"""Emoji não entra em texto de TELA — vira caixa no vídeo.

Print dele em 31/08: a headline "Foi Traído 2 Vezes 🐂🐂" saiu com duas
caixas (tofu) no vídeo renderizado. As fontes de marca (Sora, a Integral
dele, qualquer uma que o usuário instalar) não têm glifo de emoji, e os
DOIS motores desenham o que está em `hook.lines`.

A regra vive no DADO (`sem_emoji` em caption_fixes), aplicada em todos os
funis por onde a headline entra: o render (`build_edit_data`), as opções
do seletor, a preservação entre reprocessos (limpa também o que projetos
antigos guardaram), a edição no editor (`as_headline_lines`), as ações de
IA e a restauração de versão. Limpar só um desenhista deixaria o outro
divergir — e o texto do POST continua aceitando emoji, que lá funciona.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.caption_fixes import sem_emoji  # noqa: E402
from app.quick_corrections import as_headline_lines  # noqa: E402

RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
AI = (REPO / "app" / "ai_actions.py").read_text(encoding="utf-8")
PV = (REPO / "app" / "project_versions.py").read_text(encoding="utf-8")
LLM = (REPO / "helpers" / "llm_cut_plan.py").read_text(encoding="utf-8")


def test_o_caso_do_print():
    assert sem_emoji("Foi Traído  2  Vezes \U0001F402\U0001F402") == "Foi Traído 2 Vezes"


def test_pictogramas_comuns():
    assert sem_emoji("Top demais ⭐ confere ✅!") == "Top demais confere!"
    assert sem_emoji("Promo \U0001F525\U0001F525 hoje") == "Promo hoje"
    # emoji composto (ZWJ + seletor) some inteiro
    assert sem_emoji("Time \U0001F468‍\U0001F527 bom") == "Time bom"


def test_texto_normal_fica_intacto():
    for t in ("Carregador veicular serve no Fusca?",
              "R$ 399 à vista — 10% off!",
              "Ação & reação: 100%"):
        assert sem_emoji(t) == t


def test_o_editor_limpa_ao_gravar():
    assert as_headline_lines("Foi Traído \U0001F402\nde novo \U0001F525") == \
        ["Foi Traído", "de novo"]
    assert as_headline_lines(["Só emoji \U0001F602", "\U0001F602\U0001F602"]) == \
        ["Só emoji"]


def test_o_render_passa_pelo_funil():
    i = RF.index('ai_hl = sem_emoji(preset.get("aiHeadline")')
    assert i > 0
    # e as opcoes do seletor tambem
    assert '_sem_emoji(apply_replacements_to_text(str(cand or "").strip()' in RF
    # e a preservacao (projetos antigos ja gravados)
    j = RF.index('caminho = edit_dir / "headline_ia.json"')
    bloco = RF[j - 200:j + 400]
    assert 'nova = sem_emoji(' in bloco and 'guardada = sem_emoji(' in RF


def test_acoes_de_ia_e_versoes_tambem():
    assert AI.count("sem_emoji(") >= 2, "set_headline e regenerate_hook"
    assert "sem_emoji(x) for x in" in PV, "restaurar versao antiga tem de limpar"


def test_o_prompt_do_plano_avisa():
    """Prevencao na origem; o saneador e a garantia."""
    i = LLM.index('devolva headline curta')
    assert "SEM emoji" in LLM[i:i + 120]
