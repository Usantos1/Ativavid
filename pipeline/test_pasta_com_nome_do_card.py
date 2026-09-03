# -*- coding: utf-8 -*-
"""A pasta de entrega tem o nome do card — e ganha o ✅ ao aprovar (03/09).

`publicar/<nome>/` se chamava pela manchete (nome do mp4 final). Ele
nomeava na mão uma pasta "✅ G1 · C2 · CTA3" para guardar. Agora o nome do
CARD manda (stem_override / packStem no state.json) e renomear/aprovar
renomeia a pasta reaproveitando o mover-sem-duplicar que já existia.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.delivery_pack import ensure_delivery_pack, read_pack_dir  # noqa: E402


def _projeto(tmp_path: Path) -> Path:
    edit = tmp_path / "proj" / "edit"
    edit.mkdir(parents=True)
    (edit / "Vale a pena trocar a tela.mp4").write_bytes(b"x" * 1000)
    (edit / "state.json").write_text(json.dumps(
        {"finalVideo": "Vale a pena trocar a tela.mp4"}), encoding="utf-8")
    return edit


def test_sem_pedido_a_pasta_segue_a_manchete(tmp_path):
    edit = _projeto(tmp_path)
    pack = ensure_delivery_pack(edit)
    assert pack.name == "Vale a pena trocar a tela"
    assert (pack / "Vale a pena trocar a tela.mp4").is_file()


def test_o_nome_do_card_manda_e_fica_gravado(tmp_path):
    edit = _projeto(tmp_path)
    ensure_delivery_pack(edit)                       # nasce pela manchete
    pack = ensure_delivery_pack(edit, stem_override="G1 · C2 · CTA3")
    assert pack.name == "G1 · C2 · CTA3"
    assert (pack / "G1 · C2 · CTA3.mp4").is_file()
    assert not (edit.parent / "publicar" / "Vale a pena trocar a tela").exists(), \
        "renomear, nao duplicar"
    st = json.loads((edit / "state.json").read_text(encoding="utf-8"))
    assert st["packStem"] == "G1 · C2 · CTA3"
    assert st["deliveryPack"].endswith("/G1 · C2 · CTA3")
    # o proximo pack SEM override (refazer/Aplicar) mantem o nome do card
    assert ensure_delivery_pack(edit).name == "G1 · C2 · CTA3"


def test_aprovar_poe_o_check_no_nome_da_pasta(tmp_path):
    edit = _projeto(tmp_path)
    ensure_delivery_pack(edit, stem_override="G1 · C2 · CTA3")
    pack = ensure_delivery_pack(edit, stem_override="✅ G1 · C2 · CTA3")
    assert pack.name == "✅ G1 · C2 · CTA3"
    assert read_pack_dir(edit) == pack.resolve()
    assert (pack / "✅ G1 · C2 · CTA3.mp4").is_file()
    assert not (pack / "G1 · C2 · CTA3.mp4").exists(), "a copia velha sai"


def test_caractere_proibido_no_windows_e_limpo(tmp_path):
    edit = _projeto(tmp_path)
    pack = ensure_delivery_pack(edit, stem_override="Vale a pena? G1: CTA3")
    assert pack.name == "Vale a pena G1 CTA3"


def test_renomear_no_hub_renomeia_a_pasta_e_avisa_se_travar():
    ls = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = ls.index('path == "/api/jobs/rename"')
    bloco = ls[i:i + 2600]
    assert "stem_override=title" in bloco
    assert "packWarning" in bloco and "Explorer" in bloco
    js = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
    assert "body.packWarning" in js


def test_o_render_recebe_o_nome_do_card_pelo_ambiente():
    rf = (REPO / "pipeline" / "run_fast.py").read_text(encoding="utf-8")
    assert 'os.environ.get("ATIVAVID_PACK_STEM")' in rf
    ls = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert 'env["ATIVAVID_PACK_STEM"]' in ls, "o worker nao passa o nome do card"
