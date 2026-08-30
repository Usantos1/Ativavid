# -*- coding: utf-8 -*-
"""A lista de prontos mostra o vídeo, não o nome do arquivo da câmera.

Medido nos 184 vídeos do usuário: **61 apareciam como
`Elizangela001_08291440_C039` ou `A001_08191405_C003`** — 33% da lista, e
justamente os mais recentes, que é o padrão de nome que ele usa hoje.

O app já sabia trocar código de câmera por um título legível
(`_resolve_job_title` → `_suggest_title_from_edit`) e já tinha um título
bom para todos os 61, conferido um a um. O que faltava era reconhecer o
padrão: `_OPAQUE_NAME` cobre `IMG_`, `DSC_`, `copy_`… e não cobria o
`reel_clip` das câmeras.

A regra exige `_C<número>` no fim — nenhum dos 164 nomes escritos por ele
tem isso, e nenhum foi apanhado.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import _is_opaque_title  # noqa: E402

# nomes REAIS, tirados da lista dele
DA_CAMERA = [
    "Elizangela001_08291440_C039", "Elizangela001_08251416_C019",
    "A001_08191405_C003", "A001_08221406_C011 (+2)", "A001_08240906_C017",
]
DELE = [
    "Tela descolando", "Parte 1", "iphone_16", "Vitor 52 ou 25",
    "molhou no vaso", "Quero meus 0,10 de troco", "tem_capinha",
    "Nao_usar_celular", "cta_mais_feliz (+1)", "Larissa copo",
    "3 vantagens de trocar a tela", "Fã da Marvel",
    "Sei_ler_a_mente (+1)", "Agendamento", "Kevin conector ruim",
]


def test_nome_de_camera_e_reconhecido():
    for n in DA_CAMERA:
        assert _is_opaque_title(n), n


def test_titulo_escrito_por_ele_nao_e_tocado():
    for n in DELE:
        assert not _is_opaque_title(n), n


def test_arquivo_chamado_so_de_numero():
    """`1` não é nome, é contador — e ele tem um vídeo assim."""
    for n in ("1", "1 (+1)", "12", "007"):
        assert _is_opaque_title(n), n
    assert not _is_opaque_title("2026 foi assim")


def test_os_codigos_que_ja_eram_reconhecidos_continuam():
    for n in ("IMG_4001", "copy_9B49A32B", "DSC_0001", "Screenshot_1"):
        assert _is_opaque_title(n), n


def test_a_regra_exige_o_C_no_fim():
    """Sem essa âncora, `Larissa001` ou `Vitor 52` cairiam junto."""
    assert not _is_opaque_title("Elizangela001_08291440")
    assert not _is_opaque_title("Larissa001_seguranca")
