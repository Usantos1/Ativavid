# -*- coding: utf-8 -*-
"""O take de apoio cai no instante da palavra que ele ilustra.

Pedido do usuário, nas palavras dele: "quando der uma patada, usar um take
de um cavalo dando patada". Antes disso o b-roll pegava as 3 palavras mais
frequentes do texto INTEIRO e espalhava os inserts em fatias iguais — o
take caía em qualquer lugar menos no momento da piada.

O relógio certo é o do vídeo JÁ CORTADO (`caption-cues.json`, palavra a
palavra com `fromMs`/`toMs`): a transcrição da fonte fala do arquivo
original, e o corte mudou tudo de lugar.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipeline.run_fast import (  # noqa: E402
    _momento_do_take,
    _palavras_do_take,
    _palavras_do_video,
    _sem_acento,
)

FALA = [("quando", 1.0, 1.3), ("ele", 1.3, 1.5), ("deu", 1.5, 1.8),
        ("uma", 1.8, 2.0), ("patada", 2.0, 2.6), ("no", 2.6, 2.7),
        ("celular", 2.7, 3.4)]


def test_o_nome_do_arquivo_diz_o_que_o_take_mostra():
    """A categoria fica de fora: ela diz o PAPEL do take, não o conteúdo —
    casar "humor" com a palavra "humor" da fala seria coincidência."""
    assert _palavras_do_take("humor--cavalo-patada.mp4") == ["cavalo", "patada"]
    assert _palavras_do_take("cavalo_patada.mp4") == ["cavalo", "patada"]
    assert "humor" not in _palavras_do_take("humor--cavalo.mp4")
    # palavra curta demais não vira chave (casaria com meio dicionário)
    assert _palavras_do_take("meme--cao.mp4") == []


def test_o_take_cai_logo_depois_da_palavra():
    quando = _momento_do_take("humor--cavalo-patada.mp4", FALA, 0.0)
    assert quando == 2.6, quando          # fim de "patada"


def test_take_sem_relacao_nao_e_forcado():
    assert _momento_do_take("humor--gato-dormindo.mp4", FALA, 0.0) is None


def test_nao_empilha_dois_takes_no_mesmo_ponto():
    """`depois_de` guarda a folga: dois takes colados viram ruído."""
    assert _momento_do_take("humor--cavalo-patada.mp4", FALA, 3.0) is None


def test_acento_nao_atrapalha():
    assert _sem_acento("reação") == "reacao"
    fala = [("reacao", 5.0, 5.6)]
    assert _momento_do_take("meme--reação.mp4", fala, 0.0) == 5.6


def test_le_o_relogio_do_video_cortado():
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "caption-cues.json").write_text(json.dumps([
            {"startMs": 0, "endMs": 900, "lines": [[
                {"text": "Olha", "fromMs": 100, "toMs": 400},
                {"text": "só,", "fromMs": 400, "toMs": 900}]]},
        ]), encoding="utf-8")
        palavras = _palavras_do_video(tmp)
        assert palavras == [("olha", 0.1, 0.4), ("so", 0.4, 0.9)], palavras
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_sem_legenda_nao_quebra():
    tmp = Path(tempfile.mkdtemp())
    try:
        assert _palavras_do_video(tmp) == []          # arquivo ausente
        (tmp / "caption-cues.json").write_text("[]", encoding="utf-8")
        assert _palavras_do_video(tmp) == []
        (tmp / "caption-cues.json").write_text("{quebrado", encoding="utf-8")
        assert _palavras_do_video(tmp) == []
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_o_pipeline_usa_o_momento_e_tem_plano_b():
    """Sem palavra que case (ou sem legenda), volta para as fatias iguais —
    o b-roll não pode sumir só porque o nome do take não bate."""
    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    i = s.index("def _attach_auto_broll")
    j = s.index("\ndef ", i + 10)
    bloco = s[i:j]
    assert "_momento_do_take" in bloco
    assert "i_livre * slot" in bloco, "o plano B das fatias iguais sumiu"
    assert '"noMomento"' in bloco
