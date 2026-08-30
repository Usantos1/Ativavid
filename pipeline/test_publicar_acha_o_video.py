# -*- coding: utf-8 -*-
"""Publicar no Instagram não diz que o vídeo sumiu quando ele está ali.

O arquivo final leva o nome da manchete ("Aquele super desconto da
loja.mp4") e é **renomeado** quando a manchete muda. O `state.json`
acompanha; o `result.json` ficava com o caminho antigo — medido: **10 dos
projetos do usuário apontam para um arquivo que não existe mais**.

"Ver final" e "Abrir pasta" já resolvem por `resolve_delivery_mp4()`. A
publicação no Instagram lia `job.final` direto e respondia

    409 {"error": "vídeo final não encontrado"}

com o vídeo ali, de outro nome.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from app.local_server import resolve_delivery_mp4  # noqa: E402

LS = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
RF = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")


def _projeto(tmp_path: Path) -> Path:
    ed = tmp_path / "edit"
    ed.mkdir(parents=True)
    (ed / "Nome novo da manchete.mp4").write_bytes(b"x" * 5000)
    (ed / "state.json").write_text(
        json.dumps({"finalVideo": "Nome novo da manchete.mp4"}),
        encoding="utf-8")
    (ed / "result.json").write_text(
        json.dumps({"status": "done",
                    "final": str(ed / "Nome VELHO da manchete.mp4")}),
        encoding="utf-8")
    return ed


def test_o_resolvedor_acha_pelo_state(tmp_path):
    ed = _projeto(tmp_path)
    achado = resolve_delivery_mp4(ed)
    assert achado is not None and achado.name == "Nome novo da manchete.mp4"


def test_a_rota_de_publicar_usa_o_resolvedor():
    i = LS.index('if path == "/api/jobs/publicar-instagram"')
    trecho = LS[i:i + 2200]
    assert "resolve_delivery_mp4(edit)" in trecho
    j = trecho.index("resolve_delivery_mp4(edit)")
    # o `job.final` continua como ÚLTIMO recurso, não como primeiro
    assert 'job.get("final")' in trecho[j:j + 500]


def test_a_mensagem_de_erro_so_sai_quando_nao_ha_mesmo():
    i = LS.index('if path == "/api/jobs/publicar-instagram"')
    trecho = LS[i:i + 2200]
    # a string aparece TAMBEM no comentario que explica o conserto — ancorar
    # nela pegava o meu proprio texto (licao ja aprendida nesta base)
    k = trecho.index('self._json({"ok": False, "error": "vídeo final não encontrado"}')
    assert "if final is None:" in trecho[k - 200:k]


def test_o_rename_arruma_o_result_json():
    """Sem isto o ponteiro torto continua nascendo a cada troca de
    manchete."""
    i = RF.index("def promote_final_headline(")
    corpo = RF[i:i + 3000]
    assert 'rd["final"] = str(dest)' in corpo
    j = corpo.index('rd["final"] = str(dest)')
    assert "except (OSError, json.JSONDecodeError, TypeError):" in corpo[j:j + 400]
