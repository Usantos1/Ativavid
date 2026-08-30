# -*- coding: utf-8 -*-
"""A cópia leve atrasada se conserta no projeto que você abriu.

A 4.06 passou a ignorar cópia atrasada (certo) e o apply passou a refazê-la
(a causa). Sobravam os **46 projetos que já estavam atrasados**: eles só
ganhariam a cópia de volta no próximo apply, e projeto entregue raramente
recebe outro.

Varrer os 186 de uma vez custaria uns 6 minutos de máquina para refazer
cópias que talvez ninguém abra. O conserto acontece onde importa: ao abrir
o editor de um projeto atrasado. Essa sessão usa o vídeo cheio; a próxima
já abre leve.

Verificado num projeto real com a cópia 3,7 dias atrasada: abrir devolveu
404 (vídeo cheio) e, minutos depois, 200 com a cópia do dia.
"""
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "helpers"))
sys.path.insert(0, str(REPO))

PS = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")


def _handler(root: Path):
    import preview_server as ps

    h = ps.Handler.__new__(ps.Handler)
    h.root = root
    return h


def _projeto(tmp_path: Path) -> Path:
    ed = tmp_path / "edit"
    ed.mkdir(parents=True)
    (ed / "cut.mp4").write_bytes(b"x" * 100)
    px = ed / "cut_proxy.mp4"
    px.write_bytes(b"x" * 10)
    agora = time.time()
    os.utime(ed / "cut.mp4", (agora, agora))
    os.utime(px, (agora - 600, agora - 600))
    return ed


def test_copia_atrasada_dispara_o_conserto(tmp_path, monkeypatch):
    import make_proxy
    import preview_server as ps

    pedidos = []
    monkeypatch.setattr(make_proxy, "refazer_em_fundo",
                        lambda cut, ed: pedidos.append(Path(ed)) or None)
    ps._PROXY_REFAZENDO.clear()
    ed = _projeto(tmp_path)
    assert _handler(ed)._proxy_util() is None      # a sessão usa o cheio
    assert pedidos == [ed]                          # e o conserto começou


def test_nao_dispara_duas_vezes_para_o_mesmo_projeto(tmp_path, monkeypatch):
    """O editor pergunta pela cópia a cada abertura; sem o registro cada
    pergunta abriria um ffmpeg novo no mesmo arquivo."""
    import make_proxy
    import preview_server as ps

    pedidos = []

    class _T:
        daemon = True

        def join(self):
            time.sleep(60)          # segura o registro durante o teste

    monkeypatch.setattr(make_proxy, "refazer_em_fundo",
                        lambda cut, ed: (pedidos.append(ed), _T())[1])
    ps._PROXY_REFAZENDO.clear()
    ed = _projeto(tmp_path)
    h = _handler(ed)
    for _ in range(5):
        h._proxy_util()
    assert len(pedidos) == 1


def test_copia_em_dia_nao_dispara_nada(tmp_path, monkeypatch):
    import make_proxy
    import preview_server as ps

    pedidos = []
    monkeypatch.setattr(make_proxy, "refazer_em_fundo",
                        lambda cut, ed: pedidos.append(ed) or None)
    ps._PROXY_REFAZENDO.clear()
    ed = _projeto(tmp_path)
    agora = time.time()
    os.utime(ed / "cut_proxy.mp4", (agora + 5, agora + 5))
    assert _handler(ed)._proxy_util() is not None
    assert pedidos == []


def test_o_registro_e_solto_no_fim():
    """Preso para sempre, o projeto nunca mais tentaria de novo."""
    i = PS.index("def _refazer_proxy_atrasado(")
    corpo = PS[i:PS.index("\n    def _proxy_util(", i)]
    assert "_PROXY_REFAZENDO.discard(chave)" in corpo
    assert "t.join()" in corpo
