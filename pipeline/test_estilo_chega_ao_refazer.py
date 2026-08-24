# -*- coding: utf-8 -*-
"""O que o usuário escolhe na tela de Estilo chega ao refazer da Fase 2.

A tela tem dois botões que salvam: "Salvar como padrão" (o estilo da casa) e
"Salvar e refazer a Fase 2" (este job). Os dois montam payloads SEPARADOS no
`app.js`, e um knob adicionado a um e esquecido no outro some sem erro nenhum.

Foi o que aconteceu com `contentType` e `endCardCopy`: iam só no padrão. Quem
trocasse o tipo de conteúdo na tela e mandasse refazer via TUDO menos aquilo, e
o job seguia com o tipo antigo.

O efeito não parava no título. `contentType` é um dos knobs congelados em
`edl.json.cutStyle`, e o pipeline só REPLANEJA o corte quando um deles muda —
não chegando, o corte era considerado igual e reaproveitado. É a queixa
"mandei refazer e veio a mesma minutagem".

Este teste não olha os dois casos: olha a REGRA. Todo knob do `STYLE_KEYS` que
o payload do padrão manda tem de estar no payload do refazer.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from app.brand_presets import STYLE_KEYS  # noqa: E402

APP_JS = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")


def _chaves(inicio: str, fim: str) -> set[str]:
    bloco = APP_JS[APP_JS.find(inicio):]
    bloco = bloco[:bloco.find(fim)]
    assert bloco, f"bloco {inicio!r} não encontrado no app.js"
    return set(re.findall(r"^\s{4,6}([A-Za-z][A-Za-z0-9_]*):", bloco, re.M))


PADRAO = _chaves("    const house = {", "    };")
REFAZER = _chaves("  const payload = {", "  };")


def test_os_dois_blocos_existem():
    """Se o app.js for reorganizado, o teste tem de falhar alto — não passar
    vazio por não achar os blocos."""
    assert len(PADRAO) > 15, PADRAO
    assert len(REFAZER) > 15, REFAZER


@pytest.mark.parametrize("knob", sorted(set(STYLE_KEYS) & PADRAO))
def test_knob_do_padrao_tambem_vai_no_refazer(knob):
    assert knob in REFAZER, (
        f"'{knob}' é salvo no estilo padrão mas NÃO é enviado ao refazer a "
        "Fase 2 — quem mudar isso num job vai ver a mudança sumir sem aviso")


def test_o_tipo_de_conteudo_vai_no_refazer():
    """O caso que originou tudo: 86 dos projetos usam contentType, e trocá-lo
    era o jeito de escapar do defeito do tipo 'viral'."""
    assert "contentType" in REFAZER


def test_o_servidor_aceita_o_que_a_tela_manda():
    """Mandar não basta: `preset_from_style_payload` só copia o que está em
    STYLE_KEYS."""
    fora = sorted(k for k in (REFAZER & PADRAO)
                  if k not in STYLE_KEYS and k not in (
                      "elements", "note", "type", "rerender"))
    assert not fora, f"a tela manda knobs que o servidor descarta: {fora}"


def test_dialogo_de_importar_reseta_o_modo():
    """O destaque nunca era resetado e a importacao seguinte herdava o modo da
    anterior em silencio — 3 imports reais sairam em Edicao leve sem o usuario
    perceber (24/08). Cada abertura comeca no recomendado."""
    s = APP_JS if False else (RAIZ / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = s.find("state.pendingRecommended = recommended;")
    assert i > 0
    assert "applyIntentDefaults(recommended" in s[i:i + 700], (
        "o reset do modo sumiu do openImportDialog")


# --- o MODO DE EDICAO troca no refazer --------------------------------------
#
# Um projeto criado em "Edicao leve" ficava preso no modo para sempre: trocar
# o estilo e refazer nunca mudava a minutagem, porque o corte heuristico e
# deterministico e nao existia controle de modo em lugar nenhum depois do
# import. Caso real de 24/08: o mesmo video, 4 estilos, 70,417s nas 4.
#
# O modo mora no job_intent.json (o run_fast faz merge_into_preset a cada
# render) e `editingIntent` e knob do cutStyle — mudar replaneja o corte.


def test_o_refazer_envia_o_modo():
    s = (RAIZ / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    b = s[s.find("  const payload = {"):]
    b = b[:b.find("  };")]
    assert "editingIntent" in b, "o modo nao vai no payload do refazer"


def test_o_save_grava_o_modo_no_job_intent(tmp_path):
    import json as _json
    import sys as _sys

    _sys.path.insert(0, str(RAIZ))
    from app.editing_intent import load, save

    save(tmp_path, {"editingIntent": "light", "contentType": "viral"})
    # o trecho do preview_server, extraido: modo valido troca; invalido nao
    for modo, esperado in (("dynamic", "dynamic"), ("banana", "dynamic"),
                          ("complete", "complete")):
        if modo in ("light", "dynamic", "complete"):
            atual = load(tmp_path) or {}
            if str(atual.get("editingIntent") or "") != modo:
                atual["editingIntent"] = modo
                save(tmp_path, atual)
        d = load(tmp_path)
        assert d["editingIntent"] == esperado
        assert d["contentType"] == "viral", "trocar o modo nao pode perder o tipo"


def test_a_ui_oferece_os_tres_modos():
    s = (RAIZ / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    i = s.find('id="autoEditIntent"')
    assert i > 0
    bloco = s[i:i + 500]
    for v in ("light", "dynamic", "complete"):
        assert f'value="{v}"' in bloco, f"modo {v} sumiu do seletor"
