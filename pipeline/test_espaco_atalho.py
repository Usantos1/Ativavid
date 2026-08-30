# -*- coding: utf-8 -*-
"""Liberar espaço vê o `node_modules` — e não atravessa atalho.

Nos projetos do usuário: 184 projetos têm `edit/remotion/node_modules`.
**16 são cópias de verdade (10,7 GB)** e **168 são junction** para uma
instalação compartilhada.

O `node_modules` é o maior item da pasta de um projeto e era o único que a
limpeza não olhava. Botá-lo na lista só é seguro com a guarda de atalho:
`rglob` e `rmtree` atravessam junction no Windows, então sem ela `medir`
anunciaria ~107 GB inexistentes e `liberar` apagaria o conteúdo da
instalação compartilhada, quebrando os outros 167 projetos.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

import liberar_espaco as le  # noqa: E402


def _junction(alvo: Path, link: Path) -> bool:
    """Cria um atalho de pasta. Devolve False se este sistema não deixa."""
    try:
        os.symlink(alvo, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name != "nt":
        return False
    r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(alvo)],
                       capture_output=True)
    return r.returncode == 0 and link.exists()


def test_node_modules_esta_na_lista():
    assert "edit/remotion/node_modules" in le._REGENERAVEIS


def test_pasta_de_verdade_conta_os_bytes(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 5000)
    assert le._tamanho(d) == 5000


def test_atalho_conta_zero(tmp_path):
    alvo = tmp_path / "compartilhado"
    alvo.mkdir()
    (alvo / "grande.bin").write_bytes(b"x" * 100_000)
    link = tmp_path / "atalho"
    if not _junction(alvo, link):
        pytest.skip("este sistema não deixa criar atalho de pasta")
    # desfazer o atalho não libera um byte: o conteúdo é de outro dono
    assert le._tamanho(link) == 0


def test_apagar_atalho_nao_toca_no_alvo(tmp_path):
    """O caso que quebraria 167 projetos de uma vez."""
    alvo = tmp_path / "compartilhado"
    alvo.mkdir()
    (alvo / "grande.bin").write_bytes(b"x" * 100_000)
    link = tmp_path / "atalho"
    if not _junction(alvo, link):
        pytest.skip("este sistema não deixa criar atalho de pasta")
    le._apagar(link)
    assert not link.exists()
    assert (alvo / "grande.bin").exists(), "apagou o conteúdo compartilhado"


def test_nao_desce_por_atalho_ao_medir(tmp_path):
    """Atalho DENTRO da pasta medida também não pode ser contado."""
    alvo = tmp_path / "compartilhado"
    alvo.mkdir()
    (alvo / "grande.bin").write_bytes(b"x" * 100_000)
    d = tmp_path / "projeto"
    d.mkdir()
    (d / "meu.bin").write_bytes(b"x" * 700)
    if not _junction(alvo, d / "node_modules"):
        pytest.skip("este sistema não deixa criar atalho de pasta")
    assert le._tamanho(d) == 700


def test_apagar_pasta_de_verdade_apaga(tmp_path):
    d = tmp_path / "real"
    d.mkdir()
    (d / "a.bin").write_bytes(b"x" * 10)
    le._apagar(d)
    assert not d.exists()
