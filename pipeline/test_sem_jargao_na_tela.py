# -*- coding: utf-8 -*-
"""O nome de dentro não aparece na tela.

O `apply_tasks.py` já declarava a regra em comentário — "Nunca vazar
REUSE_CUT / REBUILD_CUT / FFmpeg / Remotion / OVERLAY / NVENC" — e nada a
verificava. Em 30/08 o estado vazio do editor dizia:

    "Assim que o `cut.mp4` existir, a timeline aparece aqui sozinha."

Quem lê está esperando um VÍDEO, não um arquivo.

O que NÃO é vazamento: o nome do serviço na tela onde se cola a chave dele
(GROQ, ElevenLabs, Whisper). Ali o nome é a informação — o usuário precisa
saber em qual site criar a conta.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# nomes de dentro que não dizem nada a quem usa
JARGAO = (
    "cut.mp4", "edl.json", "captions.json", "edit-data.json",
    "Remotion", "remotion", "NVENC", "qtrle", "ProRes",
    "REUSE_CUT", "REBUILD_CUT", "OVERLAY", "ffmpeg", "FFmpeg",
    "webpack", "MusicGen",
)

# a tela de Integrações nomeia o serviço porque é lá que se cola a chave —
# saber em qual site criar a conta É a informação
TELAS = (
    Path("assets/preview/index.html"),
    Path("assets/studio/index.html"),
)


def _texto_visivel(html: str):
    """O que fica ENTRE as tags — atributos e comentários não são lidos."""
    sem_comentario = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    sem_script = re.sub(r"<(script|style)\b.*?</\1>", "", sem_comentario,
                        flags=re.S | re.I)
    for m in re.finditer(r">([^<>]{3,200})<", sem_script):
        t = m.group(1).strip()
        if t:
            yield t


def test_nenhuma_tela_mostra_nome_de_arquivo_ou_motor():
    achados = []
    for rel in TELAS:
        html = (REPO / rel).read_text(encoding="utf-8")
        for texto in _texto_visivel(html):
            for termo in JARGAO:
                if termo in texto:
                    achados.append(f"{rel.name}: “{texto[:70]}” ({termo})")
    assert not achados, "jargão interno na tela:\n  " + "\n  ".join(achados)


def test_o_estado_vazio_fala_de_video_nao_de_arquivo():
    html = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
    i = html.index('id="emptyState"')
    # sem os comentários: o comentário que EXPLICA o conserto cita o termo
    # antigo, e ancorar no texto cru fazia o teste acusar a si mesmo
    bloco = re.sub(r"<!--.*?-->", "", html[i:i + 900], flags=re.S)
    assert "Ainda cortando o seu vídeo" in bloco
    assert "cut.mp4" not in bloco
    # e diz que dá para ir embora: o corte leva minutos
    assert "Pode fechar esta tela" in bloco
