# -*- coding: utf-8 -*-
"""O vídeo leve só vale enquanto for o mesmo vídeo.

A 4.05 fez o editor voltar a usar o `cut_proxy.mp4` (13 a 22x menor). Ao
medir a melhoria seguinte apareceu o que faltava: **46 dos 186 projetos
do usuário têm o proxy MAIS VELHO que o corte** — um deles por 3,7 dias.

O proxy é uma cópia do corte, e o corte muda: cada "Aplicar alterações"
refaz o `cut.mp4`. Onde o proxy não foi refeito junto, o editor tocaria um
vídeo que **não é o corte atual** — trechos que já não existem. Pior que
lento.

Velho é o mesmo que não existir: o servidor responde 404 e o editor cai
sozinho no arquivo cheio, que é o caminho que ele já sabia tomar.
"""
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


def _handler(root: Path):
    import preview_server as ps

    h = ps.Handler.__new__(ps.Handler)
    h.root = root
    return h


def _projeto(tmp_path: Path, *, proxy_atras_s: float) -> Path:
    ed = tmp_path / "edit"
    ed.mkdir(parents=True)
    (ed / "cut.mp4").write_bytes(b"x" * 100)
    px = ed / "cut_proxy.mp4"
    px.write_bytes(b"x" * 10)
    agora = time.time()
    os.utime(ed / "cut.mp4", (agora, agora))
    os.utime(px, (agora - proxy_atras_s, agora - proxy_atras_s))
    return ed


def test_proxy_mais_novo_serve(tmp_path):
    ed = _projeto(tmp_path, proxy_atras_s=-5)   # proxy mais NOVO
    assert _handler(ed)._proxy_util() is not None


def test_proxy_mais_velho_nao_serve(tmp_path):
    ed = _projeto(tmp_path, proxy_atras_s=600)
    assert _handler(ed)._proxy_util() is None


def test_sem_proxy_nao_serve(tmp_path):
    ed = _projeto(tmp_path, proxy_atras_s=0)
    (ed / "cut_proxy.mp4").unlink()
    assert _handler(ed)._proxy_util() is None


def test_sem_corte_o_proxy_passa(tmp_path):
    """Sem `cut.mp4` não há com o que comparar — e não há o que preferir."""
    ed = _projeto(tmp_path, proxy_atras_s=600)
    (ed / "cut.mp4").unlink()
    assert _handler(ed)._proxy_util() is not None


def test_get_e_head_usam_a_mesma_regra():
    """Se discordarem, o editor pergunta "tem?", ouve sim, e recebe 404."""
    for marca in ('self._sem_corpo(404)', 'self._json({"error": "proxy desatualizado"}, 404)'):
        assert marca in PS
    assert PS.count('p.name == "cut_proxy.mp4" and not self._proxy_util()') == 1
    assert PS.count('alvo.name == "cut_proxy.mp4" and not self._proxy_util()') == 1


def test_as_miniaturas_saem_do_proxy():
    """Mesmas 62 miniaturas: 1,16s pelo proxy contra 8,79s pelo corte."""
    i = PS.index("def _thumbs(self, name: str)")
    corpo = PS[i:i + 800]
    assert "self._proxy_util() or self._current_video()" in corpo


def test_a_onda_de_audio_continua_no_corte():
    """O proxy não tem faixa de áudio nenhuma (conferido com ffprobe)."""
    i = PS.index("def _waveform(self)")
    corpo = PS[i:i + 400]
    assert "self._current_video()" in corpo
    assert "_proxy_util" not in corpo


def test_a_primeira_volta_do_poll_nunca_e_pulada():
    """Sem estado nenhum, pular deixa a tela em branco — e há embutido que
    já nasce marcado como escondido (medido: o editor abria sem vídeo)."""
    app = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "if (document.hidden && !S.applying && S.lastSig) {" in app
