"""Pasta para postar: vídeo + capa + legenda — só cópia, sem render."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.delivery_pack import ensure_delivery_pack, folder_to_open, read_pack_dir


def test_pack_has_video_cover_legenda(tmp_path: Path):
    proj = tmp_path / "job"
    edit = proj / "edit"
    edit.mkdir(parents=True)
    video = edit / "Roubou a venda no almoco!.mp4"
    video.write_bytes(b"video" * 80)
    (edit / "cover.jpg").write_bytes(b"jpeg" * 120)
    (edit / "legenda.txt").write_text("Gancho\n#loja\n", encoding="utf-8")
    (edit / "state.json").write_text(json.dumps({
        "finalVideo": video.name,
    }), encoding="utf-8")

    dest = ensure_delivery_pack(edit)
    assert dest is not None
    assert dest.name == "Roubou a venda no almoco!"
    assert dest.parent.name == "publicar"
    assert (dest / "Roubou a venda no almoco!.mp4").is_file()
    assert (dest / "capa.jpg").is_file()
    assert (dest / "legenda.txt").read_text(encoding="utf-8").startswith("Gancho")
    assert read_pack_dir(edit) == dest
    assert folder_to_open(edit) == dest


def test_capa_update_replaces_pack_image(tmp_path: Path):
    proj = tmp_path / "job"
    edit = proj / "edit"
    edit.mkdir(parents=True)
    (edit / "Video.mp4").write_bytes(b"video" * 80)
    (edit / "cover.jpg").write_bytes(b"old" * 200)
    (edit / "state.json").write_text(json.dumps({"finalVideo": "Video.mp4"}), encoding="utf-8")
    dest = ensure_delivery_pack(edit)
    assert (dest / "capa.jpg").read_bytes().startswith(b"old")
    (edit / "cover.jpg").write_bytes(b"newcover" * 80)
    ensure_delivery_pack(edit)
    assert (dest / "capa.jpg").read_bytes().startswith(b"newcover")



# ---------------------------------------------------------------------------
# A pasta de entrega segue a MANCHETE — sem deixar cópias para trás.
#
# O pacote se chama pela manchete, e a manchete muda quando o usuário corrige
# o texto no editor. Sem mover o pacote anterior, cada correção deixava uma
# pasta inteira para trás com uma cópia do vídeo. Medido na máquina do usuário
# em 21/08/2026: 11 projetos com pasta duplicada e 1,19 GB de sobra — um deles
# com QUATRO pastas do mesmo vídeo. Pior que o disco: ao abrir `publicar/`, ele
# não tinha como saber qual das quatro era a boa.
# ---------------------------------------------------------------------------


def _projeto(tmp: Path) -> Path:
    edit = tmp / "Projeto" / "edit"
    edit.mkdir(parents=True)
    (edit / "legenda.txt").write_text("oi", encoding="utf-8")
    (edit / "cover.jpg").write_bytes(b"x" * 900)
    return edit


def _entrega(edit: Path, nome: str) -> None:
    """Simula o final ganhando o nome da manchete e o pacote sendo montado."""
    final = edit / f"{nome}.mp4"
    final.write_bytes(b"video" * 200)
    for outro in edit.glob("*.mp4"):
        if outro != final:
            outro.unlink()
    st = {"project": "x", "phase": 3, "finalVideo": final.name}
    antigo = edit / "state.json"
    if antigo.exists():
        st = {**json.loads(antigo.read_text(encoding="utf-8-sig")),
              "finalVideo": final.name}
    antigo.write_text(json.dumps(st), encoding="utf-8")
    ensure_delivery_pack(edit, final=final)


def _pastas(edit: Path) -> list[str]:
    pub = edit.parent / "publicar"
    return sorted(p.name for p in pub.iterdir()) if pub.is_dir() else []


def test_corrigir_a_manchete_move_o_pacote_em_vez_de_duplicar(tmp_path):
    edit = _projeto(tmp_path)
    _entrega(edit, "Celular caiu no vaso")
    assert _pastas(edit) == ["Celular caiu no vaso"]

    _entrega(edit, "Celular caiu no vaso sanitario")

    assert _pastas(edit) == ["Celular caiu no vaso sanitario"], "sobrou pasta"
    pack = read_pack_dir(edit)
    assert pack is not None and pack.is_dir(), "o ponteiro do state quebrou"
    assert sorted(p.name for p in pack.iterdir()) == [
        "Celular caiu no vaso sanitario.mp4", "capa.jpg", "legenda.txt"]


def test_tres_correcoes_seguidas_continuam_deixando_uma_pasta(tmp_path):
    """O projeto com 4 pastas do usuário veio de correções sucessivas."""
    edit = _projeto(tmp_path)
    for nome in ("Oi moco, to precisando de um Carregador",
                 "Entrada de carregador normal existe",
                 "ENTRADA NORMAL NAO EXISTE",
                 "Qual a entrada do carregador"):
        _entrega(edit, nome)
    assert _pastas(edit) == ["Qual a entrada do carregador"]


def test_nao_mexe_numa_pasta_que_ja_existe_com_o_nome_novo(tmp_path):
    """Renomear por cima apagaria o que já estava lá."""
    edit = _projeto(tmp_path)
    _entrega(edit, "Titulo A")
    ocupada = edit.parent / "publicar" / "Titulo B"
    ocupada.mkdir(parents=True)
    (ocupada / "do usuario.txt").write_text("nao apague", encoding="utf-8")

    _entrega(edit, "Titulo B")

    assert (ocupada / "do usuario.txt").read_text(encoding="utf-8") == "nao apague"
    assert (ocupada / "Titulo B.mp4").is_file()


def test_o_ponteiro_do_state_sempre_aponta_para_pasta_que_existe(tmp_path):
    """Era o sintoma visível: 5 de 43 projetos do usuário tinham
    `deliveryPack` apontando para uma pasta inexistente, e "Abrir pasta"
    caía no vazio."""
    edit = _projeto(tmp_path)
    for nome in ("Primeiro", "Segundo", "Terceiro"):
        _entrega(edit, nome)
        rel = json.loads((edit / "state.json").read_text(encoding="utf-8-sig"))["deliveryPack"]
        assert (edit / rel).resolve().is_dir(), rel


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as raw:
        test_pack_has_video_cover_legenda(Path(raw) / "a")
        test_capa_update_replaces_pack_image(Path(raw) / "b")
    print("ok")
