# -*- coding: utf-8 -*-
"""O redesenho conta quanto já andou, em vez de uma frase parada.

80,7% do tempo de "Aplicar alterações" é o redesenho do vídeo (mediana
52,4s, medido em 57 aplicações do usuário). Prever QUANTO FALTA já foi
tentado e reprovado — a faixa acertava 47%, cara ou coroa. Contar o que JÁ
FOI é verdade, e o `_gravar_video` sabe em que quadro está.

O aviso é opcional em todas as camadas: sem ele o comportamento é o de
antes, e o pipeline (que não tem ninguém esperando na frente) não paga nada.
"""
import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.apply_execute import _avisar_redesenho     # noqa: E402
from app.apply_tasks import map_internal_stage      # noqa: E402

RP = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
OV = (REPO / "app" / "overlay_path.py").read_text(encoding="utf-8")
AP = (REPO / "app" / "apply_execute.py").read_text(encoding="utf-8")


def test_o_aviso_chega_no_texto_que_a_tela_mostra():
    d = Path(tempfile.mkdtemp())
    for feitos, total, esperado in ((1, 620, "1%"), (310, 620, "50%"),
                                    (620, 620, "99%")):
        _avisar_redesenho(d, feitos, total)
        st = json.loads((d / "apply_status.json").read_text(encoding="utf-8-sig"))
        rotulo = map_internal_stage(st)[2]
        assert "Redesenhando o vídeo" in rotulo
        assert esperado in rotulo, (feitos, rotulo)


def test_nunca_chega_a_100_antes_de_terminar():
    """100% com o arquivo ainda sendo escrito é uma mentira pequena que
    custa confiança — o fim quem anuncia é o passo seguinte."""
    d = Path(tempfile.mkdtemp())
    _avisar_redesenho(d, 999, 620)
    st = json.loads((d / "apply_status.json").read_text(encoding="utf-8-sig"))
    assert "99%" in map_internal_stage(st)[2]


def test_total_zero_nao_quebra():
    d = Path(tempfile.mkdtemp())
    _avisar_redesenho(d, 0, 0)
    assert not (d / "apply_status.json").exists()


def test_o_aviso_e_opcional_em_todas_as_camadas():
    """O pipeline não tem ninguém esperando na frente: sem o aviso, o
    comportamento tem de ser byte a byte o de antes."""
    assert "def render(self, out: Path, *, progresso=None)" in RP
    assert "def _gravar_video(self, alvo: Path, *, progresso=None)" in RP
    assert "out: Path, progresso=None) -> Path:" in RP
    assert "    progresso=None," in OV


def test_o_aviso_conta_no_laco_e_nao_na_escrita():
    """Quadro idêntico ao anterior é reaproveitado com um `continue`;
    contar só os escritos travava a barra em vídeo parado."""
    i = RP.index("for f in range(self.frames):")
    bloco = RP[i:i + 900]
    assert "if progresso is not None and f % 30 == 0:" in bloco
    # o aviso vem ANTES da assinatura, que é quem decide reaproveitar o
    # quadro repetido (ancorar na palavra "continue" casava com o próprio
    # comentário do código, não com o código)
    assert (bloco.index("progresso(f + 1, self.frames)")
            < bloco.index("ass = self._assinatura(f)"))


def test_quem_escuta_quebrar_nao_derruba_o_render():
    i = RP.index("progresso(f + 1, self.frames)")
    assert "progresso = None" in RP[i:i + 260]
    i = AP.index("def _avisar_redesenho(")
    assert "except Exception:" in AP[i:i + 900]
