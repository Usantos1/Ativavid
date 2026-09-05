# -*- coding: utf-8 -*-
"""5.0.57: a trilha abaixa sozinha sob a voz (ducking).

É o que separa um vídeo que soa profissional de um com música por cima da
fala — e o motivo de o volume da trilha viver em 0,12: baixo o bastante
para não atrapalhar, e por isso quase inaudível nas pausas. Com o ducking
a música pode viver mais alta e ceder só quando alguém fala.

Medido no cut real dele + uma trilha da Biblioteca (música em 0,12, queda
durante a fala): ratio 8 → −18,1 dB (some), 4 → −12,0, **3 → −9,3**
(escolhido, a faixa de podcast), 2,5 → −6,8 (a música ainda briga).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app.brand_presets import STYLE_KEYS  # noqa: E402
from app.overlay_compose import (  # noqa: E402
    DUCK_ATAQUE, DUCK_LIMIAR, DUCK_REDUCAO, DUCK_SOLTA, _mix_audio_graph,
)

PJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
HTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
OP = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")


def _graf(**kw):
    base = dict(sfx=False, music=True, trilha_volume=0.12,
                duration_sec=10.0, fade_out_at=8.0)
    base.update(kw)
    return _mix_audio_graph(**base)


def test_a_voz_e_o_gatilho_e_nao_e_consumida_duas_vezes():
    g = _graf()
    juntos = "\n".join(g)
    assert "asplit=2[voice][voiceduck]" in juntos, (
        "a copia da voz alimenta o sidechain; a original segue para o mix")
    assert "[music][voiceduck]sidechaincompress=" in juntos
    # o mix leva a musica JA comprimida, e a voz inteira
    mix = [x for x in g if "amix=" in x][0]
    assert "[musicd]" in mix and "[voice]" in mix and "[music]" not in mix.replace("[musicd]", "")


def test_desligado_volta_ao_mix_de_antes():
    g = _graf(duck=False)
    juntos = "\n".join(g)
    assert "sidechaincompress" not in juntos and "asplit" not in juntos
    assert "[voice][music]amix=inputs=2" in juntos


def test_sem_musica_nao_ha_sidechain():
    juntos = "\n".join(_graf(music=False))
    assert "sidechaincompress" not in juntos
    assert "[voice]anull[pre]" in juntos


def test_os_numeros_sao_os_medidos():
    assert (DUCK_REDUCAO, DUCK_LIMIAR) == (3.0, 0.06), "9 dB medidos no áudio real"
    assert DUCK_ATAQUE == 20 and DUCK_SOLTA == 350, (
        "solta lenta o bastante para não bombear entre palavras")
    g = "\n".join(_graf())
    assert f"threshold={DUCK_LIMIAR}:ratio={DUCK_REDUCAO}" in g


def test_ligado_por_padrao_e_desligavel_pelo_estilo():
    assert "musicDuck" in STYLE_KEYS
    assert 'duck=st.get("duck") is not False' in OP, "sem o campo, liga"
    assert OP.count('duck=st.get("duck") is not False') == 2, "os dois caminhos de composicao"
    src = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'edit_data["soundtrack"]["duck"] = False' in src
    assert 'id="autoMusicDuck"' in HTML
    assert "['autoMusicDuck', 'musicDuck', '1']" in PJS
    assert PJS.count("musicDuck: S.style.musicDuck ?? '1'") == 3
