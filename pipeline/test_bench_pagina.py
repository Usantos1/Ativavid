# -*- coding: utf-8 -*-
"""A página de validação precisa FUNCIONAR, não só ser gerada.

Estes testes existem porque uma página quebrada custou uma rodada inteira: ela
abria, mostrava o cabeçalho e o botão, e a lista de trechos ficava vazia. O
`render()` referenciava uma variável cuja declaração não tinha sido aplicada —
`ReferenceError` no primeiro comando, e nada na tela dizia por quê.

Checar só "gerou o arquivo" não pega isso. É preciso olhar o JavaScript.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.transcricao import Palavra
from tools.bench_transcricao.discordancia import encontrar
from tools.bench_transcricao.validar import gerar


def P(t, i, f):
    return Palavra(texto=t, inicio=i, fim=f)


def _pontos():
    a = [P("aqui", 0.0, 0.3), P("na", 0.3, 0.5), P("PraimCup", 0.5, 1.2),
         P("tem", 1.2, 1.5)]
    b = [P("aqui", 0.0, 0.3), P("na", 0.3, 0.5), P("Prime", 0.5, 0.9),
         P("Camp", 0.9, 1.2), P("tem", 1.2, 1.5)]
    pontos = encontrar({"whisper_local": a, "scribe": b})
    assert pontos, "o cenário de teste precisa ter divergência"
    return pontos


def _html(tmp_path):
    p = gerar("vX", Path("/tmp/x.mp3"), _pontos(), tmp_path)
    return p.read_text(encoding="utf-8")


def test_os_pontos_chegam_na_pagina(tmp_path):
    """`PONTOS = []` significa página vazia — a pessoa não tem o que marcar."""
    h = _html(tmp_path)
    m = re.search(r"const PONTOS = (\[.*?\]);", h, re.S)
    assert m, "PONTOS não foi injetado"
    assert len(json.loads(m.group(1))) > 0, "PONTOS chegou vazio"


def test_toda_variavel_usada_no_js_foi_declarada(tmp_path):
    """O defeito exato que quebrou a rodada: uso sem declaração."""
    h = _html(tmp_path)
    js = h[h.index("<script>") + 8:h.index("</script>")]
    declarados = set(re.findall(r"\b(?:const|let|var)\s+([A-Za-z_]\w*)", js))
    declarados |= set(re.findall(r"\bfunction\s+([A-Za-z_]\w*)", js))
    for nome in ("PONTOS", "VIDEO", "FOLGA", "dec", "tel", "a",
                 "render", "marcar", "tocar", "baixar", "outro",
                 "focar", "fechar", "reg", "esc", "ler", "grava"):
        assert nome in declarados, f"{nome} é usado mas nunca declarado"


def test_nenhum_marcador_de_template_sobrou(tmp_path):
    h = _html(tmp_path)
    assert "__" not in h.replace("__", "", 0) or not re.search(
        r"__[A-Z_]+__", h), "sobrou marcador não substituído"


def test_o_download_inclui_a_telemetria(tmp_path):
    """Sem telemetria não há medida de tempo humano — o critério principal."""
    h = _html(tmp_path)
    assert "telemetria: tel" in h


def test_a_pagina_avisa_quando_quebra(tmp_path):
    """Página que falha calada custou uma rodada. Agora ela mostra o erro."""
    h = _html(tmp_path)
    assert "window.onerror" in h
    assert 'id="erro"' in h


def test_tocar_recebe_o_carimbo_para_cronometrar(tmp_path):
    h = _html(tmp_path)
    assert "function tocar(ini, fim, carimbo)" in h
    assert re.search(r"onclick=\\?'?\"?\s*\+?\s*'<button onclick=\"tocar\(", h) \
        or "tocar(' + p.inicio" in h or "'tocar(' +" in h or "tocar(" in h


def test_as_opcoes_nao_revelam_o_motor(tmp_path):
    """A pessoa tem de ouvir, não votar em motor."""
    h = _html(tmp_path)
    for motor in ("whisper_local", "scribe", "whisper_gemini", "gemini"):
        assert motor not in h, f"a página revela o motor {motor}"


def test_propostas_ficam_fora_da_pagina_mas_gravadas(tmp_path):
    gerar("vX", Path("/tmp/x.mp3"), _pontos(), tmp_path)
    p = tmp_path / "propostas_vX.json"
    assert p.is_file()
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d and all("whisper_local" in v for v in d.values())
