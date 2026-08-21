# -*- coding: utf-8 -*-
"""O pico de áudio: margem de verdade, e conserto que não piora.

**O limite de entrega é −1,0 dBTP** (padrão de Instagram/TikTok/YouTube).
Duas coisas estavam erradas nos vídeos do usuário.

**1. A margem tinha o tamanho do erro.** A composição mirava −1,2, e o próprio
código documenta que o loudnorm entrega 0,1 a 0,2 dB ACIMA do pedido. Medido
nos 40 finais mais recentes: dos 26 do caminho OVERLAY, **12 saíram entre −1,0
e −1,2**, e um em **−1,0 cravado** — passando pela verificação por 0,01 dB.
Quem passa disso não é rejeitado: o job inteiro volta para o Remotion, ~720s a
mais. O caminho completo era pior ainda, mirando `TP=-1` (o próprio limite) com
loudnorm de uma passagem: os 2 únicos finais fora de especificação entre os 40
medidos (−0,8 e −0,9) são os dois desse caminho.

Baixar o alvo **não abaixa o volume**: medido em 4 finais reais, o alvo é
seguido com precisão (−1,5 → −1,5, −1,5, −1,6) e o `I` fica em −14,0 LUFS nos
quatro. `TP` é teto de pico, não ganho.

**2. O conserto podia piorar e o resultado ficava.** `garantir_true_peak`
trocava o arquivo e só então media. Medido no final de 20260820-214720, que
está em −0,8 dBTP: o loudnorm devolve −0,6 com alvo −1,5 e **0,0** (clipping)
com alvo −1,2. A piora ia para o arquivo entregue e saía impressa como
"CORRIGIDO".

Conferido depois da correção, nos arquivos de verdade:

| arquivo | antes | depois | o que fez |
|---|---|---|---|
| 20260820-214720 | −0,8 | −0,8 | recusou piorar, arquivo intacto |
| 20260821-082150 | −1,0 | −1,0 | já dentro, não mexeu |
| 20260815-215711 | −0,9 | **−1,9** | consertou (LUFS −12,8 → −13,9) |
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

LIMITE_DE_ENTREGA = -1.0
# o erro que o loudnorm comete, documentado no próprio módulo
ERRO_DO_LOUDNORM = 0.2


def test_a_margem_e_maior_que_o_erro_do_loudnorm():
    from app.overlay_compose import LOUDNORM_TP

    margem = LIMITE_DE_ENTREGA - LOUDNORM_TP
    assert margem > ERRO_DO_LOUDNORM, (
        f"alvo {LOUDNORM_TP} deixa {margem:.1f} dB contra um erro de "
        f"{ERRO_DO_LOUDNORM} dB — margem do tamanho do erro não é margem"
    )


def test_o_caminho_completo_nao_mira_no_proprio_limite():
    """Era `TP=-1` com loudnorm de UMA passagem: os 2 finais fora de
    especificação entre os 40 medidos vieram daqui."""
    import re

    s = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    alvos = [float(x) for x in re.findall(r"loudnorm=I=-14:TP=(-?[\d.]+):LRA=11", s)]
    assert alvos, "o encode final deixou de normalizar"
    for tp in alvos:
        assert LIMITE_DE_ENTREGA - tp > ERRO_DO_LOUDNORM, (tp, alvos)


def test_os_dois_motores_usam_o_mesmo_alvo():
    """`render_proprio` importa a constante do `overlay_compose`; se alguém
    fixar um número lá, os motores divergem sem ninguém ver."""
    s = (REPO / "app" / "render_proprio.py").read_text(encoding="utf-8")
    assert "LOUDNORM_TP" in s
    import re
    assert not re.search(r"LOUDNORM_TP\s*=\s*-?[\d.]+", s), (
        "o motor próprio passou a definir o próprio alvo de pico"
    )


class _Medidor:
    """ebur128 falso: um valor para o arquivo original, outro para o temporário."""

    def __init__(self, antes: float, depois: float):
        self.antes, self.depois = antes, depois

    def __call__(self, path: Path) -> dict:
        tp = self.depois if ".tp" in Path(path).name else self.antes
        return {"truePeakDb": tp, "integratedLufs": -14.0}


def _preparar(monkeypatch, tmp_path: Path, antes: float, depois: float) -> Path:
    import app.overlay_compose as oc

    final = tmp_path / "final.mp4"
    final.write_bytes(b"o original" * 2000)

    monkeypatch.setattr(oc, "ebur128_summary", _Medidor(antes, depois))
    monkeypatch.setattr(oc, "probe_json", lambda p: {"streams": [
        {"codec_type": "video"}, {"codec_type": "audio"}, {"codec_type": "video"},
    ]})
    monkeypatch.setattr(oc, "measure_loudnorm", lambda *a, **k: {
        "input_i": "-14", "input_tp": "-1", "input_lra": "7",
        "input_thresh": "-24", "target_offset": "0",
    })
    monkeypatch.setattr(oc, "_ffmpeg", lambda: "ffmpeg")

    def _run_falso(cmd, **kw):
        Path(cmd[-1]).write_bytes(b"o consertado" * 2000)

        class R:
            returncode, stderr, stdout = 0, "", ""
        return R()

    monkeypatch.setattr(oc, "_run", _run_falso)
    return final


def test_nao_troca_o_arquivo_quando_o_conserto_piora(monkeypatch, tmp_path):
    """O caso real: -0,8 entra, o loudnorm devolveria -0,6."""
    from app.overlay_compose import garantir_true_peak

    final = _preparar(monkeypatch, tmp_path, antes=-0.8, depois=-0.6)
    au = garantir_true_peak(final)

    assert final.read_bytes().startswith(b"o original"), (
        "guardou o arquivo pior — era o defeito")
    assert au["truePeakDb"] == -0.8, (
        "relatou o pico do arquivo que NÃO ficou no disco")
    assert not list(tmp_path.glob("*.tp*")), "deixou o temporário para trás"


def test_nao_troca_nem_quando_empata(monkeypatch, tmp_path):
    """Empate não justifica reencodar o áudio: perde qualidade à toa."""
    from app.overlay_compose import garantir_true_peak

    final = _preparar(monkeypatch, tmp_path, antes=-0.8, depois=-0.8)
    garantir_true_peak(final)
    assert final.read_bytes().startswith(b"o original")


def test_troca_quando_melhora(monkeypatch, tmp_path):
    """O outro caso real: -0,9 entra e sai -1,9."""
    from app.overlay_compose import garantir_true_peak

    final = _preparar(monkeypatch, tmp_path, antes=-0.9, depois=-1.9)
    au = garantir_true_peak(final)

    assert final.read_bytes().startswith(b"o consertado"), "não aplicou a melhora"
    assert au["truePeakDb"] == -1.9
    assert not list(tmp_path.glob("*.tp*"))


def test_nem_tenta_quando_ja_esta_dentro(monkeypatch, tmp_path):
    from app.overlay_compose import garantir_true_peak

    final = _preparar(monkeypatch, tmp_path, antes=-1.4, depois=-9.9)
    au = garantir_true_peak(final)
    assert final.read_bytes().startswith(b"o original"), (
        "reencodou áudio que já estava dentro do limite")
    assert au["truePeakDb"] == -1.4
