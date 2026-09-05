# -*- coding: utf-8 -*-
"""5.0.43: "Salvar legenda .srt" — a legenda como arquivo, na pasta de entrega.

O vídeo sai com a legenda QUEIMADA; YouTube, LinkedIn e leitores de tela
querem a legenda como arquivo, e só o longform gerava um .srt. O .srt
nasce do `caption-cues.json` (o que foi desenhado), com `captions.json`
(palavras soltas) como reserva, e vai para a pasta de entrega.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from app import legenda_srt as ls  # noqa: E402


def _edit(tmp_path: Path, *, cues=None, palavras=None, pack: Path | None = None) -> Path:
    edit = tmp_path / "p" / "edit"
    public = edit / "remotion" / "public"
    public.mkdir(parents=True)
    if cues is not None:
        (public / "caption-cues.json").write_text(json.dumps(cues), encoding="utf-8")
    if palavras is not None:
        (public / "captions.json").write_text(json.dumps(palavras), encoding="utf-8")
    if pack is not None:
        pack.mkdir(parents=True, exist_ok=True)
        import os
        (edit / "state.json").write_text(json.dumps(
            {"deliveryPack": os.path.relpath(pack, edit)}), encoding="utf-8")
    return edit


CUES = [
    {"startMs": 0, "endMs": 2100, "lines": [[{"text": "Seu", "fromMs": 0, "toMs": 680}],
                                            [{"text": "celular", "fromMs": 680, "toMs": 920}]]},
    {"startMs": 2100, "endMs": 3900, "lines": [[{"text": "ainda"}, {"text": "carrega"}]]},
]


def test_srt_das_cues_desenhadas(tmp_path):
    srt = ls.srt_do_projeto(_edit(tmp_path, cues=CUES))
    assert srt.split("\n")[:4] == ["1", "00:00:00,000 --> 00:00:02,100", "Seu celular", ""]
    assert "2\n00:00:02,100 --> 00:00:03,900\nainda carrega\n" in srt


def test_tempo_srt_usa_virgula_e_horas():
    assert ls._tempo(3_723_456) == "01:02:03,456"
    assert ls._tempo(-5) == "00:00:00,000"


def test_reserva_por_palavras_agrupa(tmp_path):
    palavras = [{"text": f"p{i}", "startMs": i * 400, "endMs": i * 400 + 350} for i in range(10)]
    blocos = ls.blocos_do_projeto(_edit(tmp_path, palavras=palavras))
    assert len(blocos) == 2 and blocos[0][2].startswith("p0 p1") and blocos[0][2].endswith("p6")
    assert blocos[1] == (2800, 3950, "p7 p8 p9")


def test_cues_ganham_das_palavras(tmp_path):
    edit = _edit(tmp_path, cues=CUES, palavras=[{"text": "x", "startMs": 0, "endMs": 1}])
    assert ls.blocos_do_projeto(edit)[0][2] == "Seu celular"


def test_salva_no_edit_e_na_pasta_de_entrega(tmp_path):
    # o pacote mora DENTRO do projeto (read_pack_dir recusa pasta de fora)
    pack = tmp_path / "p" / "publicar" / "Video 1"
    edit = _edit(tmp_path, cues=CUES, pack=pack)
    r = ls.salvar_srt(edit)
    assert r["ok"] and r["blocos"] == 2
    assert Path(r["path"]) == pack / "legendas.srt"
    assert (edit / "legendas.srt").read_text(encoding="utf-8") == (pack / "legendas.srt").read_text(encoding="utf-8")


def test_sem_legenda_avisa(tmp_path):
    r = ls.salvar_srt(_edit(tmp_path))
    assert r["ok"] is False and "não tem legenda" in r["error"]


def test_rota_e_menu():
    srv = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'path == "/api/jobs/srt"' in srv
    desk = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
    assert '"/api/jobs/srt",' in desk, "o app instalado precisa delegar a rota"
    js = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")
    assert 'data-act="srt"' in js and 'act === "srt"' in js
    assert js.index('act === "srt"') < js.index('act === "copyname"')
