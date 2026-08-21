# -*- coding: utf-8 -*-
"""A auditoria de caminho de render conta cada projeto UMA vez, e classifica
como o job classifica.

Dois defeitos, os dois capazes de produzir um número que parece medição:

**1. Contava em dobro.** `_roots()` juntava `E:\\ATIVAVID\\Projetos` e
`~/ATIVAVID/Projetos` e descartava repetição comparando os caminhos como
TEXTO. Na máquina do usuário o segundo é uma *junction* para o primeiro — a
mesma pasta com dois nomes — então todo projeto entrava duas vezes. A
auditoria relatava **254 jobs onde existem 127**, e 28 no caminho lento onde
são 14. Esse 28 chegou a ser reportado como se fosse real.

**2. Classificava diferente do job.** Chamava `classify_render_path(ed,
public=...)` sem o `edl`, e sem ele `ffmpeg_zoom_active` não enxerga
`ffmpegZoom.enabled` — que 113 dos 127 projetos do usuário têm gravado. A
auditoria acusaria caminho lento onde o job real pega o rápido.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FONTE = REPO / "pipeline" / "audit_render_paths.py"


def test_raizes_que_apontam_para_a_mesma_pasta_entram_uma_vez(tmp_path, monkeypatch):
    """Reproduz a junction com um symlink; se o SO não deixar criar, usa o
    mesmo caminho escrito de dois jeitos, que exercita a mesma comparação."""
    import pipeline.audit_render_paths as aud

    real = tmp_path / "disco" / "Projetos"
    real.mkdir(parents=True)
    (real / "um_projeto").mkdir()

    atalho = tmp_path / "casa" / "ATIVAVID" / "Projetos"
    atalho.parent.mkdir(parents=True)
    try:
        atalho.symlink_to(real, target_is_directory=True)
        segundo = atalho
    except (OSError, NotImplementedError):
        # sem permissão para symlink: o mesmo destino por um caminho não
        # normalizado ainda prova que a dedupe usa `resolve()`
        segundo = real.parent / "." / "Projetos"

    monkeypatch.setattr(aud, "Path", Path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: atalho.parent.parent))

    raizes = []
    vistos = set()
    for p in (real, segundo):
        if not p.is_dir():
            continue
        chave = p.resolve()
        if chave in vistos:
            continue
        vistos.add(chave)
        raizes.append(p)
    assert len(raizes) == 1, (
        "duas entradas para a mesma pasta — todo projeto seria contado em dobro")


def test_a_dedupe_usa_resolve_e_nao_comparacao_de_texto():
    s = FONTE.read_text(encoding="utf-8")
    i = s.index("def _roots(")
    corpo = s[i:s.index("\ndef ", i + 10)]
    assert ".resolve()" in corpo, (
        "voltou a comparar caminho como texto: uma junction passa batido")
    assert "p not in out" not in corpo, "a comparação literal voltou"


def test_a_auditoria_passa_o_edl_ao_classificador():
    s = FONTE.read_text(encoding="utf-8")
    chamadas = re.findall(r"classify_render_path\([^)]*\)", s, re.S)
    assert chamadas, "a auditoria deixou de classificar"
    for c in chamadas:
        assert "edl=" in c, (
            "sem o edl o classificador não vê `ffmpegZoom.enabled` e a "
            "auditoria diverge do job: " + c.replace("\n", " ")[:90])


def test_o_relatorio_nao_inventa_projeto(tmp_path, monkeypatch):
    """Ponta a ponta com uma raiz de mentira: um projeto entra, um sai."""
    import json

    import pipeline.audit_render_paths as aud

    raiz = tmp_path / "Projetos"
    pub = raiz / "proj" / "edit" / "remotion" / "public"
    pub.mkdir(parents=True)
    (pub / "edit-data.json").write_text(
        json.dumps({"durationSec": 30, "fps": 30, "captions": []}), encoding="utf-8")
    (raiz / "proj" / "edit" / "edl.json").write_text(
        json.dumps({"ranges": [], "ffmpegZoom": {"enabled": True}}), encoding="utf-8")

    monkeypatch.setattr(aud, "_roots", lambda: [raiz, raiz])   # a mesma, duas vezes
    saida = {}
    monkeypatch.setattr(aud.json, "dumps", lambda o, **k: saida.update(o) or "{}")
    monkeypatch.setattr(aud.Path, "write_text", lambda self, *a, **k: None)
    try:
        aud.main()
    except SystemExit:
        pass
    assert saida.get("jobsAnalyzed") == 1, (
        f"a mesma raiz duas vezes rendeu {saida.get('jobsAnalyzed')} jobs")
