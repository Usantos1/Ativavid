# -*- coding: utf-8 -*-
"""Importação que falha diz o motivo e deixa rastro.

Em 29/08 o usuário relatou "subi as 3 partes e deu erro" e a máquina não
tinha NADA para investigar: nenhum projeto criado, nenhum log, e a tela
mostrava a mesma frase para qualquer causa ("não consegui ler nenhum
vídeo desse envio"). O motivo real existia — o parser de upload recusa
com mensagens específicas, entre elas "upload terminou antes do fim da
parte", que é o que acontece quando o envio de arquivos grandes é
interrompido — mas morria num print que, num app empacotado, não tem
console para aparecer.
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


def _handler_cls():
    from app import local_server
    for nome in dir(local_server):
        obj = getattr(local_server, nome)
        if isinstance(obj, type) and hasattr(obj, "_registrar_import"):
            return obj
    raise AssertionError("nao achei a classe do handler")


def test_registra_uma_linha_por_tentativa():
    tmp = Path(tempfile.mkdtemp())
    try:
        stub = SimpleNamespace(projects_root=tmp)
        _handler_cls()._registrar_import(
            stub, "upload",
            [(r"C:\Users\x\Parte 1.mov", 1234), ("parte 2.mov", 99)],
            "recusado: upload terminou antes do fim da parte")
        linhas = (tmp / ".ativavid" / "import-log.jsonl").read_text(
            encoding="utf-8").strip().splitlines()
        assert len(linhas) == 1, linhas
        d = json.loads(linhas[0])
        assert d["via"] == "upload"
        assert d["arquivos"][0] == {"nome": "Parte 1.mov", "bytes": 1234}
        assert "terminou antes do fim" in d["resultado"]
        assert d["at"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_o_registro_nunca_derruba_a_importacao():
    """Diagnóstico é auxiliar: pasta impossível não pode virar exceção."""
    stub = SimpleNamespace(projects_root=Path("Z:/nao/existe/mesmo"))
    _handler_cls()._registrar_import(stub, "upload", [], "seja o que for")


def test_so_nome_e_tamanho_vao_para_o_log():
    """Nada do conteúdo do vídeo — e caminho completo não interessa."""
    tmp = Path(tempfile.mkdtemp())
    try:
        stub = SimpleNamespace(projects_root=tmp)
        _handler_cls()._registrar_import(
            stub, "caminhos", [(r"D:\Particular\segredo\video.mov", 7)], "ok")
        d = json.loads((tmp / ".ativavid" / "import-log.jsonl").read_text(
            encoding="utf-8").strip())
        assert d["arquivos"] == [{"nome": "video.mov", "bytes": 7}]
        assert "Particular" not in json.dumps(d)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_a_resposta_de_erro_carrega_o_motivo():
    s = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = s.index("não consegui ler nenhum vídeo desse envio")
    trecho = s[max(0, i - 400):i + 200]
    assert "_erro_import" in trecho, trecho[-300:]


def test_o_upload_recusado_guarda_a_causa():
    s = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
    i = s.index("except mp.MultipartError as e:")
    trecho = s[i:i + 700]
    assert "self._erro_import = str(e)" in trecho, trecho[:300]
    assert "_registrar_import" in trecho
