# -*- coding: utf-8 -*-
"""A tela de Estilo mostra o estilo que o app USA, não o de fábrica.

`default-style.json` é o "estilo da casa" que a tela carrega como base. Ela
busca `/assets/default-style.json`, que o servidor resolvia para o arquivo
EMBARCADO na instalação — mas "Salvar como padrão" grava em
`~/ATIVAVID/default-style.json`, que só o `load_preset()` lê.

MEDIDO na máquina do usuário: 7 campos divergiam. A tela dizia marca "Padrão"
e cartão final vazio enquanto o render usava "Prime Camp" e o CTA dele; e
`rhythm`/`speechClean`, que decidem o CORTE, apareciam errados.

(Contra o arquivo cru do usuário a diferença parecia 18 campos — número
inflado, porque `load_preset` mescla o embarcado por baixo. O que vale é a
diferença contra o EFETIVO.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_a_rota_serve_o_estilo_efetivo_e_nao_o_de_fabrica():
    """O `_json(load_preset())` tem de vir ANTES da busca pelo arquivo."""
    src = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    # DENTRO do do_GET: o do_HEAD (4.05) também olha `/assets/`, e ancorar
    # na primeira ocorrência do arquivo passou a cair nele.
    get = src.index("def do_GET(self)")
    i = src.index('if path.startswith("/assets/"):', get)
    trecho = src[i:i + 1800]
    assert 'Path(rel).name == "default-style.json"' in trecho
    assert "self._json(load_preset())" in trecho, (
        "a tela voltou a receber o estilo de fábrica"
    )
    j = trecho.index("self._json(load_preset())")
    k = trecho.index("for base in (PREVIEW, STUDIO)")
    assert j < k, "o arquivo embarcado ainda ganha da versão efetiva"


def test_o_que_o_usuario_salvou_vence_o_de_fabrica(tmp_path, monkeypatch):
    """É o que "Salvar como padrão" promete."""
    import app.local_server as ls

    embarcado = tmp_path / "shipped.json"
    embarcado.write_text(json.dumps({
        "brandName": "Padrão", "rhythm": "dinamico", "captions": "stacked",
    }), encoding="utf-8")
    usuario = tmp_path / "user.json"
    usuario.write_text(json.dumps({
        "brandName": "Prime Camp", "rhythm": "calmo",
    }), encoding="utf-8")
    monkeypatch.setattr(ls, "PRESET_PATH", embarcado)
    monkeypatch.setattr(ls, "USER_PRESET_PATH", usuario)

    efetivo = ls.load_preset()
    assert efetivo["brandName"] == "Prime Camp"
    assert efetivo["rhythm"] == "calmo"
    # e o que o usuário NÃO tocou continua vindo do embarcado
    assert efetivo["captions"] == "stacked"


def test_sem_arquivo_do_usuario_fica_o_de_fabrica(tmp_path, monkeypatch):
    import app.local_server as ls

    embarcado = tmp_path / "shipped.json"
    embarcado.write_text(json.dumps({"brandName": "Padrão"}), encoding="utf-8")
    monkeypatch.setattr(ls, "PRESET_PATH", embarcado)
    monkeypatch.setattr(ls, "USER_PRESET_PATH", tmp_path / "nao_existe.json")
    assert ls.load_preset()["brandName"] == "Padrão"


def test_arquivo_do_usuario_quebrado_nao_derruba_a_tela(tmp_path, monkeypatch):
    """Um JSON corrompido ali não pode deixar a tela de Estilo sem base."""
    import app.local_server as ls

    embarcado = tmp_path / "shipped.json"
    embarcado.write_text(json.dumps({"brandName": "Padrão"}), encoding="utf-8")
    ruim = tmp_path / "user.json"
    ruim.write_text("{ nao sou json", encoding="utf-8")
    monkeypatch.setattr(ls, "PRESET_PATH", embarcado)
    monkeypatch.setattr(ls, "USER_PRESET_PATH", ruim)
    assert ls.load_preset()["brandName"] == "Padrão"
