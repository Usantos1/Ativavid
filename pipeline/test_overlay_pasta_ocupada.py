# -*- coding: utf-8 -*-
"""Resto de uma rodada anterior nao pode derrubar o render do overlay.

A pasta de trabalho tem um `node_modules` que e JUNCTION para o cache. Se
outro processo o mantiver ocupado (o render do video vizinho com
parallelJobs=2, um editor aberto), o `rmtree(ignore_errors=True)` falha em
silencio e a pasta continua la — e o `mkdir(parents=True)` seguinte
levantava FileExistsError, matando o render. Achado em 29/08 rodando a
varredura de paridade duas vezes seguidas.
"""
from pathlib import Path

from app.overlay_path import prepare_overlay_remotion


def _projeto_falso(base: Path) -> Path:
    src = base / "remotion"
    (src / "src").mkdir(parents=True)
    (src / "public").mkdir()
    for nome in ("Main.tsx", "Overlay.tsx", "Root.tsx"):
        (src / "src" / nome).write_text(
            "const Karaoke: X = 1; const Inserts: X = 1; "
            "const EndCard: X = 1; const HookIntro: X = 1;", encoding="utf-8")
    (src / "package.json").write_text("{}", encoding="utf-8")
    return src


def test_pasta_que_sobrou_nao_quebra(tmp_path):
    src = _projeto_falso(tmp_path)
    dest = tmp_path / "trabalho"
    # sobra de uma rodada anterior, com um arquivo que "nao se apaga"
    (dest / "src").mkdir(parents=True)
    (dest / "src" / "velho.tsx").write_text("resto", encoding="utf-8")
    prepare_overlay_remotion(src, dest)          # nao pode levantar
    assert (dest / "src" / "Main.tsx").exists()
    assert not (dest / "src" / "velho.tsx").exists(), \
        "o resto antigo ficou misturado com a copia nova"


def test_copia_normal_continua_igual(tmp_path):
    src = _projeto_falso(tmp_path)
    dest = tmp_path / "trabalho2"
    prepare_overlay_remotion(src, dest)
    assert (dest / "src" / "Overlay.tsx").exists()
    assert (dest / "package.json").exists()


def test_mkdir_e_tolerante_no_codigo():
    """Amarra o motivo: sem exist_ok, uma sobra volta a matar o render."""
    s = (Path(__file__).resolve().parent.parent / "app" / "overlay_path.py"
         ).read_text(encoding="utf-8")
    i = s.index("def prepare_overlay_remotion")
    corpo = s[i:i + 1600]
    assert "dest.mkdir(parents=True, exist_ok=True)" in corpo
    assert "dirs_exist_ok=True" in corpo
