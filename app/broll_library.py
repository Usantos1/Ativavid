"""Biblioteca local de B-roll (imagens/vídeos curtos do usuário)."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def library_root(projects_root: Path | None = None) -> Path:
    if projects_root:
        root = Path(projects_root).expanduser().resolve().parent / "Biblioteca"
    else:
        root = Path.home() / "ATIVAVID" / "Biblioteca"
    root.mkdir(parents=True, exist_ok=True)
    (root / "images").mkdir(exist_ok=True)
    (root / "clips").mkdir(exist_ok=True)
    (root / "Trilhas").mkdir(exist_ok=True)
    (root / "Efeitos").mkdir(exist_ok=True)
    return root


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", (name or "asset").lower())[:48].strip("-") or "asset"


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VID_EXTS = {".mp4", ".mov", ".webm"}

# A CATEGORIA de um arquivo e o prefixo "rotulo--" do nome. Isto NAO e
# enfeite de tela: e o mesmo contrato que o plano B da musica usa para
# casar a trilha com o clima do video (`_trilha_etiqueta` em run_fast).
# Por isso a tela escreve e le exatamente o mesmo formato — renomear pela
# Biblioteca muda de verdade o que o pipeline escolhe.
CATEGORIAS_TRILHA = ("viral", "humor", "venda", "anuncio", "resenha",
                     "informativo", "educacional", "institucional", "padrao")
# espelho de _TRILHA_CLIMA (run_fast) para os rotulos em portugues — o
# teste test_biblioteca_categorias trava os dois juntos
CLIMA_TRILHA = {
    "viral": "agitado", "humor": "agitado", "venda": "agitado",
    "anuncio": "agitado", "padrao": "agitado",
    "resenha": "medio", "informativo": "medio",
    "educacional": "calmo", "institucional": "calmo",
}
# Categorias sugeridas para as imagens de b-roll. Livre: o usuario pode
# escrever qualquer palavra; estas so aparecem como atalho na tela.
CATEGORIAS_IMAGEM = ("produto", "bancada", "loja", "cliente", "antes-depois",
                     "peca", "marca")
# Videos curtos sao TAKES de apoio: entram no meio da fala como reacao,
# piada ou prova. A categoria e o que o usuario vai procurar na hora
# ("deu uma patada" -> take de humor), entao ela fala do PAPEL do take no
# video, nao do assunto.
CATEGORIAS_CLIPE = ("viral", "meme", "humor", "reacao", "cta", "abertura",
                    "transicao", "produto", "bancada")
# Efeitos: a familia sai do proprio nome do arquivo (os 9 embutidos do app
# nunca tiveram rotulo e nao vao ser renomeados — sao asset do produto).
_FAMILIAS_SFX = (
    # "corte" antes de "clique": cut-click.mp3 casa com os dois
    ("corte", ("cut-click", "corte")),
    ("clique", ("click", "clique", "tap")),
    ("pop", ("pop",)),
    ("whoosh", ("whoosh", "swoosh", "swipe")),
    ("risco", ("scratch", "risco")),
    ("relogio", ("tictac", "tick", "clock")),
    ("impacto", ("impact", "boom", "hit", "punch")),
)
SFX_APP_REL = "app-sfx"      # prefixo de `rel` dos efeitos embutidos
# A categoria do efeito e a VAGA que ele ocupa no video: um arquivo em
# "whoosh--meu.mp3" entra no lugar do whoosh do app. Sem isto, "Adicionar
# efeitos" seria um botao que guarda arquivo e nao muda vídeo nenhum.
SFX_VAGAS = {
    "clique": "caption-click.mp3",
    "risco": "caption-scratch.mp3",
    "whoosh": "whoosh.mp3",
    "pop": "pop.mp3",
    "corte": "cut-click.mp3",
}


def categoria_de(nome: str) -> str:
    """O rotulo antes de `--`, ou "" quando o arquivo nao tem categoria."""
    return nome.split("--", 1)[0].lower().strip() if "--" in nome else ""


def vaga_do_efeito(nome: str) -> str:
    """A vaga que este arquivo ocupa no video, ou "" se nenhuma.

    O casamento era pelo prefixo LITERAL (`categoria_de`), e por isso os
    **70 arquivos `swoosh--*.mp3`** do usuario nunca tocaram: a vaga se
    chama `whoosh`. A tabela de familias do app ja diz que sao a mesma
    coisa — faltava consultar.

    Medido na Biblioteca dele: das 234 pecas, so as 30 de `clique` batiam.
    Categoria sem vaga (`impacto`, `riser`, `sino`) continua de fora: o
    app nao tem lugar para elas, e inventar um mudaria o video no palpite.
    """
    rot = categoria_de(nome)
    if rot in SFX_VAGAS:
        return rot
    if rot:
        for fam, chaves in _FAMILIAS_SFX:
            if fam in SFX_VAGAS and (rot == fam or rot in chaves):
                return fam
        return ""
    fam = familia_sfx(nome)
    return fam if fam in SFX_VAGAS else ""


def familia_sfx(nome: str) -> str:
    rot = categoria_de(nome)
    if rot:
        return rot
    base = nome.lower()
    for fam, chaves in _FAMILIAS_SFX:
        if any(k in base for k in chaves):
            return fam
    return "outros"


def sfx_do_app() -> list[dict[str, Any]]:
    """Os efeitos que ja vem no app (assets/shortform/public/sfx).

    Entram na Biblioteca como somente-leitura: o cliente precisa OUVIR o
    que o video usa (o clique da legenda, o whoosh do corte) para decidir
    se quer somar os proprios — antes eles nao apareciam em lugar nenhum.
    """
    pasta = REPO / "assets" / "shortform" / "public" / "sfx"
    itens: list[dict[str, Any]] = []
    if not pasta.is_dir():
        return itens
    for f in sorted(pasta.iterdir()):
        if not f.is_file() or f.suffix.lower() not in AUDIO_EXTS:
            continue
        itens.append({
            "id": f.stem,
            "name": f.name,
            "kind": "sfx",
            "categoria": familia_sfx(f.name),
            "origem": "app",
            "path": str(f),
            "rel": f"{SFX_APP_REL}/{f.name}",
            "bytes": f.stat().st_size,
            "mtime": int(f.stat().st_mtime),
        })
    return itens


def list_assets(projects_root: Path | None = None) -> dict[str, Any]:
    root = library_root(projects_root)
    items: list[dict[str, Any]] = []
    for kind, folder in (("image", root / "images"), ("clip", root / "clips"),
                         ("track", root / "Trilhas"),
                         ("sfx", root / "Efeitos")):
        folder.mkdir(parents=True, exist_ok=True)
        sufixos = AUDIO_EXTS if kind in ("track", "sfx") else IMG_EXTS | VID_EXTS
        for p in sorted(folder.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not p.is_file():
                continue
            if p.suffix.lower() not in sufixos:
                continue
            # A VAGA que este som ocupa no video — e vazia quando ele nao
            # ocupa nenhuma. Dos 234 efeitos do usuario, 133 sao de
            # categorias que o video nao toca (impacto, transicao, riser):
            # sem dizer isso, a Biblioteca parecia cheia de som em uso.
            vaga = vaga_do_efeito(p.name) if kind == "sfx" else ""
            items.append({
                "id": p.stem,
                "name": p.name,
                "kind": kind,
                "vaga": vaga,
                "tocaNoVideo": bool(vaga) if kind == "sfx" else None,
                "categoria": (familia_sfx(p.name) if kind == "sfx"
                              else categoria_de(p.name)),
                "origem": "usuario",
                "path": str(p),
                "rel": f"{folder.name}/{p.name}",
                "bytes": p.stat().st_size,
                "mtime": int(p.stat().st_mtime),
            })
    items.extend(sfx_do_app())
    return {
        "root": str(root),
        "items": items,
        "categorias": {
            "track": list(CATEGORIAS_TRILHA),
            "image": list(CATEGORIAS_IMAGEM),
            "clip": list(CATEGORIAS_CLIPE),
            "sfx": list(SFX_VAGAS),
        },
        "clima": dict(CLIMA_TRILHA),
    }


def add_file(src: Path, *, kind: str = "image", projects_root: Path | None = None) -> dict[str, Any]:
    root = library_root(projects_root)
    src = Path(src)
    if not src.is_file():
        raise ValueError("arquivo não encontrado")
    folder = root / ("clips" if kind == "clip" else "images")
    dest = folder / f"{_slug(src.stem)}-{int(time.time())}{src.suffix.lower()}"
    shutil.copy2(src, dest)
    return {
        "ok": True,
        "id": dest.stem,
        "name": dest.name,
        "kind": "clip" if kind == "clip" else "image",
        "path": str(dest),
        "rel": f"{folder.name}/{dest.name}",
    }


def add_bytes(
    filename: str,
    data: bytes,
    *,
    kind: str | None = None,
    categoria: str | None = None,
    projects_root: Path | None = None,
) -> dict[str, Any]:
    if not data:
        raise ValueError("arquivo vazio")
    ext = Path(filename).suffix.lower() or ".jpg"
    if kind is None:
        if ext in AUDIO_EXTS:
            kind = "track"
        else:
            kind = "clip" if ext in VID_EXTS else "image"
    if kind in ("track", "sfx") and ext not in AUDIO_EXTS:
        raise ValueError("trilha e efeito precisam ser áudio")
    if ext not in IMG_EXTS | VID_EXTS | AUDIO_EXTS:
        raise ValueError("formato não suportado")
    root = library_root(projects_root)
    folder = {"track": root / "Trilhas", "sfx": root / "Efeitos",
              "clip": root / "clips"}.get(kind, root / "images")
    stem = Path(filename).stem
    rot = _slug(categoria) if categoria else categoria_de(stem)
    # EFEITO sem categoria: o nome costuma dizer qual e. Sem isto,
    # `meu-whoosh.mp3` entrava como "sem categoria" e nunca tocava — o
    # arquivo fica guardado e o botao "Adicionar efeitos" vira um botao
    # que guarda arquivo e nao muda video nenhum. So aceita palpite que
    # cai numa VAGA de verdade; o resto continua sem categoria.
    if kind == "sfx" and not rot:
        rot = vaga_do_efeito(Path(filename).name)
    if "--" in stem:
        stem = stem.split("--", 1)[1]
    stem = _slug(stem)
    # Audio guarda o nome como veio (o rodizio da trilha compara por NOME);
    # imagem/clipe leva carimbo porque duas fotos podem ter o mesmo nome.
    if kind not in ("track", "sfx"):
        stem = f"{stem}-{int(time.time())}"
    nome = f"{rot}--{stem}{ext}" if rot else f"{stem}{ext}"
    dest = folder / nome
    if dest.exists():
        base = f"{rot}--{stem}" if rot else stem
        dest = folder / f"{base}-{int(time.time())}{ext}"
    dest.write_bytes(data)
    return {
        "ok": True,
        "id": dest.stem,
        "name": dest.name,
        "kind": kind,
        "categoria": categoria_de(dest.name),
        "path": str(dest),
        "rel": f"{folder.name}/{dest.name}",
    }


def set_categoria(rel: str, categoria: str,
                  projects_root: Path | None = None) -> dict[str, Any]:
    """Troca a categoria de um arquivo da biblioteca RENOMEANDO ele.

    A categoria mora no nome porque e assim que o pipeline le (o plano B da
    musica escolhe por `rotulo--`); guardar num json a parte criaria uma
    segunda verdade que sai de sincronia na primeira vez que o usuario
    mexer na pasta pelo Explorer.
    """
    root = library_root(projects_root).resolve()
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise ValueError("arquivo inválido")
    alvo = (root / rel).resolve()
    try:
        alvo.relative_to(root)
    except ValueError:
        raise ValueError("fora da biblioteca") from None
    if not alvo.is_file():
        raise ValueError("arquivo não encontrado")
    rot = _slug(categoria) if categoria else ""
    resto = alvo.stem.split("--", 1)[1] if "--" in alvo.stem else alvo.stem
    nome = f"{rot}--{resto}{alvo.suffix}" if rot else f"{resto}{alvo.suffix}"
    novo = alvo.with_name(nome)
    if novo != alvo:
        if novo.exists():
            novo = alvo.with_name(
                f"{Path(nome).stem}-{int(time.time())}{alvo.suffix}")
        alvo.rename(novo)
    return {
        "ok": True,
        "name": novo.name,
        "categoria": categoria_de(novo.name),
        "rel": f"{novo.parent.name}/{novo.name}",
        "path": str(novo),
    }


def _pico_dbfs(arquivo: Path) -> float | None:
    """Pico do arquivo, em dBFS. `None` quando nao deu para medir."""
    import re as _re
    import subprocess as _sp

    try:
        from app.ffmpeg_tools import ffmpeg_bin

        exe = ffmpeg_bin()
    except Exception:  # noqa: BLE001
        exe = "ffmpeg"
    try:
        r = _sp.run([exe, "-hide_banner", "-nostats", "-i", str(arquivo),
                     "-af", "volumedetect", "-f", "null", "-"],
                    capture_output=True, text=True, errors="replace",
                    timeout=30)
    except (OSError, _sp.SubprocessError):
        return None
    m = _re.findall(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", r.stderr or "")
    return float(m[-1]) if m else None


def _ja_estoura(arquivo: Path) -> bool:
    """O arquivo ja vem distorcido (pico colado em 0 dBFS)?

    Medido na biblioteca do usuario: os `swoosh` vao de -24,6 a -6,4 LUFS
    e o `swoosh--002.mp3` chega ao teto (pico 0,0 dBFS, +4,9 de pico real).
    Esse som entra em TODO video, por cima da voz — e a distorcao ja vem
    dentro do arquivo, entao abaixar o volume nao a tira.

    Nao mede? Nao acusa: recusar por falta de medida seria pior que o som.
    """
    pico = _pico_dbfs(arquivo)
    return pico is not None and pico >= -0.1


def aplicar_sfx_do_usuario(public_dir: Path,
                           projects_root: Path | None = None) -> list[str]:
    """Poe os efeitos do usuario por cima dos do app na pasta do projeto.

    Os dois motores (Remotion e o proprio) leem o som em
    `remotion/public/sfx`, entao trocar o arquivo ali vale para os dois. A
    troca e por PROJETO — o template embarcado nunca e alterado.

    Devolve os nomes trocados. Falha aqui nunca pode derrubar um render:
    som e enfeite, video e o produto.
    """
    trocados: list[str] = []
    try:
        pasta = library_root(projects_root) / "Efeitos"
        destino = Path(public_dir) / "sfx"
        if not pasta.is_dir() or not destino.is_dir():
            return trocados
        for vaga, alvo in SFX_VAGAS.items():
            cands = sorted(
                (f for f in pasta.iterdir()
                 if f.is_file() and f.suffix.lower() in AUDIO_EXTS
                 and vaga_do_efeito(f.name) == vaga),
                key=lambda f: f.stat().st_mtime, reverse=True)
            # O primeiro que NAO vem distorcido. O som toca em todo video,
            # por cima da voz, e a distorcao ja vem dentro do arquivo — nao
            # sai baixando o volume.
            escolhido = next((f for f in cands if not _ja_estoura(f)), None)
            if escolhido is None:
                if cands:
                    print(f"[sfx] {vaga}: todos os candidatos vem estourados "
                          f"— fica o som do app", flush=True)
                continue
            shutil.copy2(escolhido, destino / alvo)
            trocados.append(f"{alvo} <- {escolhido.name}")
    except OSError:
        return trocados
    return trocados


def pick_for_query(query: str, projects_root: Path | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """Heurística simples: nome do arquivo contém palavra da query."""
    q = (query or "").lower()
    words = [w for w in re.findall(r"[a-zà-ÿ0-9]{3,}", q) if w]
    # b-roll e IMAGEM/CLIPE: som (trilha, efeito) nunca pode virar figura
    items = [i for i in list_assets(projects_root)["items"]
             if i["kind"] in ("image", "clip")]
    if not words:
        return items[:limit]
    scored = []
    for it in items:
        name = it["name"].lower()
        score = sum(1 for w in words if w in name)
        if score:
            scored.append((score, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:limit]] or items[:limit]


def copy_into_public(src: Path, public_dir: Path) -> dict[str, Any]:
    """Copia um asset da biblioteca (ou outro path local) para remotion/public/library/."""
    src = Path(src)
    if not src.is_file():
        raise ValueError("arquivo não encontrado")
    public_dir = Path(public_dir)
    # Som vai para public/sfx, junto dos efeitos que o app ja usa: e de la
    # que os DOIS motores tocam (`Renderizador._gravar_sfx` e o `Sfx` do
    # template). Em library/ ele seria copiado e nunca tocado.
    som = src.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg", ".aac"}
    pasta = "sfx" if som else "library"
    dest_dir = public_dir / pasta
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if not dest.exists() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    # Uma copia FORA de public/. O render refaz public/ do zero (scaffold),
    # entao a midia que o usuario acabou de escolher sumia antes do pipeline
    # olhar — visto na prova fim a fim de 29/08: "nao achei em public/".
    # `midia_do_editor` repoe a partir daqui.
    try:
        guarda = public_dir.parents[1] / "midia" / pasta
        guarda.mkdir(parents=True, exist_ok=True)
        alvo = guarda / dest.name
        if not alvo.exists() or alvo.stat().st_size != dest.stat().st_size:
            shutil.copy2(dest, alvo)
    except (OSError, IndexError):
        pass
    kind = ("sfx" if som else
            "clip" if dest.suffix.lower() in {".mp4", ".mov", ".webm"}
            else "image")
    return {
        "ok": True,
        "ref": f"{pasta}/{dest.name}",
        "src": f"{pasta}/{dest.name}",
        "kind": kind,
        "path": str(dest),
    }


def resolve_query_to_public(
    query: str,
    public_dir: Path,
    *,
    projects_root: Path | None = None,
    prefer_library: bool = True,
) -> dict[str, Any] | None:
    """Resolve query → arquivo em public/: biblioteca local primeiro, depois Pexels."""
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    q = (query or "").strip()
    if not q:
        return None

    if prefer_library:
        picks = pick_for_query(q, projects_root, limit=1)
        if picks:
            try:
                out = copy_into_public(Path(picks[0]["path"]), public_dir)
                out["query"] = q
                out["source"] = "library"
                out["credit"] = picks[0].get("name") or "biblioteca"
                return out
            except ValueError:
                pass

    # Pexels fallback
    try:
        import sys
        helpers = str(REPO / "helpers")
        if helpers not in sys.path:
            sys.path.insert(0, helpers)
        import pexels_search  # type: ignore

        key = pexels_search.load_api_key()
        photos = pexels_search.search(q, key, 3, "portrait")
        if not photos:
            return None
        photo = photos[0]
        src = photo.get("src") or {}
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            return None
        out_dir = public_dir / "pexels"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = f"{pexels_search.slugify(q)}-ai.jpg"
        dest = out_dir / name
        pexels_search.download(url, dest)
        photographer = (photo.get("photographer") or "Pexels").strip()
        return {
            "ok": True,
            "ref": f"pexels/{name}",
            "src": f"pexels/{name}",
            "kind": "image",
            "path": str(dest),
            "query": q,
            "source": "pexels",
            "credit": photographer,
        }
    except Exception:
        return None
