# -*- coding: utf-8 -*-
"""O card de Concluídos: duração original → final, e início → fim.

Pedido do usuário vendo a tela: "quero a duração original, e duração final;
quero data e hora de início assim como a de conclusão; botão de pasta e legenda
pode ficar dentro do [...] menu".

O card só mostrava "9:16" e a hora de conclusão. Faltavam duas coisas nos
dados, não só no desenho:

- a duração de ORIGEM nunca foi medida (só a entregue, que vem do pipeline);
- `startedAtLabel` era uma cópia de `createdAtLabel`, então "início" dizia a
  hora da IMPORTAÇÃO. Num vídeo que esperou meia hora na fila, os dois números
  não têm nada a ver — e `startedAt`, o de verdade, já era gravado.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _ffmpeg() -> str:
    from app.overlay_compose import _ffmpeg as f

    return f()


@pytest.fixture(scope="module")
def fontes(tmp_path_factory):
    """Dois vídeos REAIS de duração conhecida (2s e 3s).

    Fixture sintética serve aqui: o que se mede é o ffprobe somando durações,
    não o conteúdo. Mas tem de ser arquivo de verdade — um .mp4 falso faria o
    probe devolver 0 e o teste passaria por não medir nada.
    """
    d = tmp_path_factory.mktemp("fontes")
    saidas = []
    for i, seg in enumerate((2, 3), start=1):
        p = d / f"take{i}.mp4"
        subprocess.run([
            _ffmpeg(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=30:duration={seg}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(p),
        ], check=True, capture_output=True)
        saidas.append(p)
    return saidas


def test_a_duracao_de_origem_e_a_soma_das_fontes(fontes):
    from app.local_server import _duracao_das_fontes

    d = _duracao_das_fontes([str(p) for p in fontes])
    assert d == pytest.approx(5.0, abs=0.2), f"esperava ~5s, veio {d}"


def test_fonte_que_nao_existe_nao_derruba_nem_conta(fontes):
    from app.local_server import _duracao_das_fontes

    d = _duracao_das_fontes([str(fontes[0]), str(fontes[0].parent / "sumiu.mp4")])
    assert d == pytest.approx(2.0, abs=0.2)
    assert _duracao_das_fontes([]) == 0.0


def test_o_inicio_e_a_hora_do_processamento_nao_a_da_importacao(tmp_path):
    """O que o usuário pediu como "hora de início". Enquanto era cópia do
    createdAt, um vídeo que esperou na fila mostrava os dois iguais."""
    from app.local_server import enrich_job_display

    job = {
        "createdAt": "2026-08-21T11:21:00Z",
        "startedAt": "2026-08-21T11:52:00Z",
        "finishedAt": "2026-08-21T12:03:00Z",
        "status": "done",
        "editDir": str(tmp_path),
    }
    enrich_job_display(job, tmp_path)
    assert job["createdAtLabel"] != job["startedAtLabel"], (
        "início voltou a ser a hora da importação"
    )
    assert job["startedAtLabel"].endswith("08:52")
    assert job["finishedAtLabel"].endswith("09:03")


def test_sem_startedAt_o_inicio_cai_na_importacao(tmp_path):
    """Job antigo, gravado antes deste campo existir, não pode ficar sem hora."""
    from app.local_server import enrich_job_display

    job = {"createdAt": "2026-08-21T11:21:00Z", "status": "queued",
           "editDir": str(tmp_path)}
    enrich_job_display(job, tmp_path)
    assert job["startedAtLabel"] == job["createdAtLabel"]


def test_a_duracao_de_origem_entra_no_job(tmp_path, fontes):
    from app.local_server import enrich_job_display

    job = {
        "createdAt": "2026-08-21T11:21:00Z", "status": "done",
        "editDir": str(tmp_path), "sources": [str(p) for p in fontes],
    }
    enrich_job_display(job, tmp_path)
    assert job["sourceDurationSec"] == pytest.approx(5.0, abs=0.2)


def test_a_tela_mostra_as_duas_duracoes_e_o_periodo():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert "function duracoesLabel" in js, "não há duração de origem → final"
    assert "function periodoLabel" in js, "não há início → fim"
    assert "sourceDurationSec" in js
    i = js.index("function cardSig(")
    assert "j.startedAtLabel" in js[i:i + 900], (
        "a assinatura do card ignora os campos novos — o card não repinta"
    )


def test_pasta_e_legenda_sairam_para_dentro_do_menu():
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'title="Abrir a pasta publicar"' not in js, "o botão Pasta continua solto"
    assert 'title="Copiar a legenda do post"' not in js, "o botão Legenda continua solto"
    i = js.index("function cardMenuHtml(")
    menu = js[i:i + 2200]
    for item in ("Abrir pasta", "Copiar legenda do post", "Tentar novamente"):
        assert item in menu, f"faltou {item!r} no menu"


def test_o_menu_do_card_e_refeito_no_patch():
    """Ele era montado uma vez e congelado: "Copiar legenda do post" nunca
    aparecia depois que a legenda ficava pronta, e "Ver vídeo final" ficava
    desabilitado para sempre."""
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    i = js.index("function patchCard(")
    corpo = js[i:i + 6000]
    assert "cardMenuHtml(j, opts)" in corpo, "o patch não refaz o menu"
    assert ".pc-menu:not(.hidden)" in corpo, (
        "o menu seria trocado mesmo aberto, sumindo debaixo do clique"
    )
    assert "periodoLabel(j)" in corpo, "o patch não atualiza início → fim"
    assert "duracoesLabel(j)" in corpo, "o patch não atualiza as durações"
