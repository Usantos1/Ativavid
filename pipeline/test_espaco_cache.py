# -*- coding: utf-8 -*-
"""A conta do espaço não pode travar a tela de Configurações.

Botar o `node_modules` na lista do que dá para limpar fez a medida ir de
**0,41s para 6,64s** nos 188 projetos do usuário — 16x. A conta inteira
são as 16 pastas de 636 MB, cerca de 30 mil arquivos cada.

Só entra na conta projeto entregue e parado há uma semana, e o que está
parado não muda de tamanho: a medida vai para cache, com o `mtime` do
`result.json` como chave. Depois de liberar, o cache cai — o que foi
apagado não pode continuar sendo anunciado.
"""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

import liberar_espaco as le  # noqa: E402


def _projeto(raiz: Path, nome: str, *, bytes_: int, dias: float) -> Path:
    p = raiz / nome
    (p / "edit" / "remotion" / "out").mkdir(parents=True)
    (p / "edit" / "remotion" / "out" / "a.mp4").write_bytes(b"x" * bytes_)
    r = p / "edit" / "result.json"
    r.write_text(json.dumps({"status": "done"}), encoding="utf-8")
    velho = time.time() - dias * 86400
    import os
    os.utime(r, (velho, velho))
    return p


def test_a_segunda_medida_sai_do_cache(tmp_path):
    _projeto(tmp_path, "p1", bytes_=4000, dias=30)
    a = le.medir(tmp_path)
    assert (tmp_path / le._CACHE_REL).exists()
    b = le.medir(tmp_path)
    assert a["intermediariosGb"] == b["intermediariosGb"]
    assert json.loads((tmp_path / le._CACHE_REL).read_text(encoding="utf-8"))["p1"][1] == 4000


def test_mexer_no_projeto_remede(tmp_path):
    """A chave é o mtime do result.json: projeto tocado é remedido."""
    import os
    p = _projeto(tmp_path, "p1", bytes_=4000, dias=30)
    le.medir(tmp_path)
    (p / "edit" / "remotion" / "out" / "b.mp4").write_bytes(b"x" * 6000)
    r = p / "edit" / "result.json"
    novo = time.time() - 29 * 86400
    os.utime(r, (novo, novo))
    le.medir(tmp_path)
    guardado = json.loads((tmp_path / le._CACHE_REL).read_text(encoding="utf-8"))
    assert guardado["p1"][1] == 10000


def test_liberar_derruba_o_cache(tmp_path):
    """Anunciar espaço que já foi liberado é mentira."""
    _projeto(tmp_path, "p1", bytes_=4000, dias=30)
    le.medir(tmp_path)
    assert (tmp_path / le._CACHE_REL).exists()
    le.liberar(tmp_path)
    assert not (tmp_path / le._CACHE_REL).exists()
    assert le.medir(tmp_path)["intermediariosGb"] == 0.0


def test_cache_ilegivel_nao_derruba_a_medida(tmp_path):
    _projeto(tmp_path, "p1", bytes_=4000, dias=30)
    alvo = tmp_path / le._CACHE_REL
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text("{isto não é json", encoding="utf-8")
    assert le.medir(tmp_path)["ok"] is True


def test_projeto_novo_nao_entra_na_conta(tmp_path):
    """Só entregue e parado há uma semana — o resto ainda está em uso."""
    _projeto(tmp_path, "p1", bytes_=4000, dias=1)
    assert le.medir(tmp_path)["intermediariosGb"] == 0.0


def test_a_medida_e_esquentada_no_arranque():
    """Sem isto os 6s caem em cima de quem abriu Configurações."""
    fonte = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    assert "def esquentar_medida_do_espaco(" in fonte
    i = fonte.index("srv = ThreadingHTTPServer(")
    assert "esquentar_medida_do_espaco(root)" in fonte[i - 400:i]
