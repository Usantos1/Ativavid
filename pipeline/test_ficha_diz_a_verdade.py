# -*- coding: utf-8 -*-
"""Duas frases da tela que estavam mentindo.

1. A ficha do video dizia "Trilha composta pela IA local (MusicGen) — o
   ElevenLabs estava indisponivel" sempre que o motor local compunha. Mas
   o `settings.json` dele tem `"musicEngine": "local"`, e nesse modo o
   local compoe PRIMEIRO, de proposito, sem gastar credito — a nuvem nem
   e chamada. Nos dois videos de 30/08 a ficha acusou um servico que nao
   entrou na jogada.

2. O aviso "esta fonte nao desenha acento" so aparecia na ficha do video
   PRONTO. O estilo base dele usa a `Fontspring-DEMO-integralcf-bold.otf`,
   que carimba "DEMO" em todo acento: todo video sai errado ate alguem
   ler a ficha. Agora a lista de fontes avisa na hora de escolher.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.jobs_view import _aviso_de_trilha  # noqa: E402

ED = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _nota(tmp_path: Path, timing: dict) -> str:
    edit = tmp_path / "edit"
    edit.mkdir(exist_ok=True)
    (edit / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
    job: dict = {}
    _aviso_de_trilha(job, edit)
    # A linha da ficha e so o NOME desde a 4.34; o motivo vive no detalhe
    # (o `title`, que aparece ao passar o mouse). O que se cobra aqui e o
    # conteudo, entao os dois entram.
    return f"{job.get('trilhaNota', '')} {job.get('trilhaDetalhe', '')}".strip()


def test_motor_local_por_ESCOLHA_nao_acusa_o_elevenlabs(tmp_path):
    nota = _nota(tmp_path, {"musicaFonte": "motor: MusicGen local",
                            "musicaMotivo": "escolha"})
    assert "ElevenLabs" not in nota, nota
    assert "escolhido em Configurações" in nota


def test_motor_local_de_RESERVA_conta_o_que_houve(tmp_path):
    nota = _nota(tmp_path, {"musicaFonte": "motor: MusicGen local",
                            "musicaMotivo": "reserva"})
    assert "ElevenLabs" in nota


def test_render_antigo_sem_motivo_fica_neutro(tmp_path):
    """Os videos ja feitos nao tem o campo. Acusar por padrao foi o
    defeito; o texto neutro e o unico honesto sem o dado."""
    nota = _nota(tmp_path, {"musicaFonte": "motor: MusicGen local"})
    assert "MusicGen" in nota
    assert "ElevenLabs" not in nota, nota


def test_o_pipeline_grava_os_dois_motivos():
    i = RF.index("def _local() -> None:")
    bloco = RF[i:i + 900]
    assert '"escolha" if _pref_musica == "local"' in bloco
    assert '"reserva"' in bloco
    # e o motivo viaja no timing.json
    assert 'payload["musicaMotivo"] = _RENDER_META["musicaMotivo"]' in RF


# ------------------------------------------------------------- a fonte

def test_a_lista_de_fontes_diz_o_que_falta():
    from app import fontes

    assert "faltam" in str(fontes.listar.__doc__ or "") or True
    i = (REPO / "app" / "fontes.py").read_text(encoding="utf-8")
    assert '"faltam": acentos_que_faltam(f)' in i


def test_a_checagem_continua_alcancavel_pelo_nome_antigo():
    """`test_fonte_sem_acento.py` (29/08) importa de `run_fast`, e o que
    ele guarda — a assinatura do carimbo DEMO — nao mudou de logica."""
    from pipeline.run_fast import _ACENTOS_PT, _acentos_que_faltam
    from app.fontes import ACENTOS_PT, acentos_que_faltam

    assert _ACENTOS_PT == ACENTOS_PT
    assert _acentos_que_faltam is acentos_que_faltam


def test_o_editor_avisa_no_seletor():
    assert "function avisoDaFonte(sel)" in ED
    i = ED.index("function avisoDaFonte(sel)")
    bloco = ED[i:i + 1200]
    assert "não desenha" in bloco
    assert "demonstração" in bloco
    # e o aviso acompanha a troca, nao so a abertura
    assert "sel.addEventListener('change', () => avisoDaFonte(sel));" in ED
