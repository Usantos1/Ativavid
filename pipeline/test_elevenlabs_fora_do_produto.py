# -*- coding: utf-8 -*-
"""ElevenLabs fora do PRODUTO (pedido de 02/09: "vamos remover todo o
elevenlabs da jogada").

O produto não pede, não cobra chave e não chama a nuvem: transcrição é
LOCAL (faster-whisper), trilha é a IA LOCAL (MusicGen) com a Biblioteca de
reserva. Os helpers (`transcribe.py`, `elevenlabs_music.py`) continuam
existindo para uso de ferramenta/benchmark — o que este arquivo cobra é
que o PIPELINE e as TELAS não os acionem nem exibam a integração.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_transcricao_resolve_sempre_para_local(monkeypatch):
    from app.transcricao import modo

    monkeypatch.delenv("ATIVAVID_TRANSCRICAO", raising=False)
    assert modo.backend_para_o_pipeline() == "local"
    # valor velho gravado (env ou config) não pode travar nem escolher nuvem
    monkeypatch.setenv("ATIVAVID_TRANSCRICAO", "elevenlabs")
    assert modo.backend_para_o_pipeline() == "local"
    assert not hasattr(modo, "SCRIBE")


def test_pipeline_nao_chama_a_nuvem_de_musica():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert "elevenlabs_music.py" not in rf, "o pipeline ainda chama a nuvem"
    # e o rótulo de fallback da ficha não inventa nuvem
    assert 'RENDER_META["musicaFonte"] = "nuvem' not in rf


def test_fallback_de_transcricao_e_local():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = rf.index("def _backend_transcricao")
    assert 'escolhido = "local"' in rf[i:i + 800], \
        "modo quebrado caía no elevenlabs"


def test_musica_padrao_e_local():
    from app.settings_store import DEFAULTS

    assert DEFAULTS["musicEngine"] == "local"


def test_a_tela_nao_oferece_a_integracao():
    html = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
    assert "elevenlabs" not in html.lower(), "card da chave ainda na tela"
    assert 'id="musicEngine"' not in html, "dropdown de nuvem ainda na tela"
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "ELEVENLABS_API_KEY" not in js
    assert 'data-key-test="elevenlabs"' not in js


def test_o_servidor_nao_lista_nem_testa_a_chave():
    for nome in ("local_server.py", "desktop_server.py"):
        s = (REPO / "app" / nome).read_text(encoding="utf-8")
        assert "ELEVENLABS_API_KEY" not in s, f"{nome} ainda expõe a chave"
    ls = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'which == "elevenlabs"' not in ls


def test_o_doutor_nao_cobra_a_chave():
    d = (REPO / "helpers" / "doutor.py").read_text(encoding="utf-8")
    assert "ELEVENLABS_API_KEY" not in d


def test_os_helpers_da_skill_continuam_existindo():
    """A remoção é do PRODUTO. As ferramentas ficam."""
    assert (REPO / "helpers" / "transcribe.py").exists()
    assert (REPO / "helpers" / "elevenlabs_music.py").exists()
