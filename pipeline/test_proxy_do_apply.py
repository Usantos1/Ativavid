# -*- coding: utf-8 -*-
"""Quem refaz o corte refaz a cópia leve.

O `cut_proxy.mp4` nascia só no fim do pipeline. O APPLY — "Aplicar
alterações" — também refaz o `cut.mp4` e nunca refez a cópia: medido nos
projetos do usuário, **46 de 186 ficaram com a cópia atrasada**, uma
delas por 3,7 dias. A partir do primeiro apply o projeto perdia o vídeo
leve do editor para sempre.

A 4.06 fez a coisa certa com o arquivo velho (ignorar). Esta faz a coisa
certa com a causa (refazer) — em segundo plano, porque a cópia leva 3 a
12s e o usuário está esperando um apply que dura ~107s.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

import make_proxy  # noqa: E402

MP = (REPO / "helpers" / "make_proxy.py").read_text(encoding="utf-8")
AE = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")


def test_a_copia_e_escrita_num_temporario():
    """Durante os ~10s de geração existiria um `cut_proxy.mp4` com data
    NOVA e conteúdo pela metade — e a guarda que decide se ele serve
    compara DATAS."""
    i = MP.index("def make_cut_proxy(")
    corpo = MP[i:MP.index("\ndef refazer_em_fundo", i)]
    assert 'tmp = dest.with_name(dest.name + ".tmp.mp4")' in corpo
    assert "str(tmp)," in corpo, "o ffmpeg ainda escreve no destino final"
    assert "os.replace(tmp, dest)" in corpo


def test_o_temporario_some_quando_falha():
    i = MP.index("def make_cut_proxy(")
    corpo = MP[i:MP.index("\ndef refazer_em_fundo", i)]
    assert corpo.count("tmp.unlink(missing_ok=True)") >= 2


def test_o_apply_manda_refazer():
    i = AE.index("hooks.promote_file(cut_tmp, live_cut)")
    trecho = AE[i:i + 800]
    assert "refazer_em_fundo(live_cut, edit)" in trecho


def test_refazer_nao_derruba_o_apply():
    i = AE.index("refazer_em_fundo(live_cut, edit)")
    assert "except Exception" in AE[i:i + 300]


def test_o_interruptor_de_proxy_e_respeitado(monkeypatch):
    monkeypatch.setenv("ATIVAVID_PROXY", "0")
    assert make_proxy.refazer_em_fundo(Path("x.mp4"), Path(".")) is None


def test_refazer_e_em_segundo_plano(tmp_path, monkeypatch):
    """O usuário está esperando o apply; a cópia só serve na próxima vez
    que ele abrir o editor."""
    monkeypatch.delenv("ATIVAVID_PROXY", raising=False)
    chamou = {}

    def falso(cut, dest, **kw):
        chamou["dest"] = dest
        return None

    monkeypatch.setattr(make_proxy, "make_cut_proxy", falso)
    t = make_proxy.refazer_em_fundo(tmp_path / "cut.mp4", tmp_path)
    assert t is not None and t.daemon
    t.join(timeout=5)
    assert chamou["dest"].name == "cut_proxy.mp4"
