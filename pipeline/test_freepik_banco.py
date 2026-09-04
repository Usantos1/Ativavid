# -*- coding: utf-8 -*-
"""Freepik (Magnific) como banco de imagens e vídeos (4.96).

Ele em 03/09: "quero implementar com o magnific antigo freepik pra banco
de imagens como o pexels". Conferido contra a API real no mesmo dia:
busca em `api.magnific.com/v1/resources` e `/v1/videos`, chave no
cabeçalho `x-magnific-api-key`, download por id que devolve a URL assinada
— e o vídeo vem no ORIGINAL (.mov 4K, 328 MB por 34 s), por isso o helper
converte para 1080p mp4 depois de baixar.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
for p in (REPO, REPO / "helpers"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import freepik_search as fs  # noqa: E402

PREVIEW = (REPO / "helpers" / "preview_server.py").read_text(encoding="utf-8")
APPJS = (REPO / "assets" / "preview" / "app.js").read_text(encoding="utf-8")
PHTML = (REPO / "assets" / "preview" / "index.html").read_text(encoding="utf-8")
SERVER = (REPO / "app" / "local_server.py").read_text(encoding="utf-8")
DESKTOP = (REPO / "app" / "desktop_server.py").read_text(encoding="utf-8")
SHTML = (REPO / "assets" / "studio" / "index.html").read_text(encoding="utf-8")
SJS = (REPO / "assets" / "studio" / "studio.js").read_text(encoding="utf-8")

FOTO = {"id": 396648207, "title": "Capinha", "url": "https://www.freepik.com/x",
        "image": {"type": "photo", "source": {"url": "https://img.freepik.com/a.jpg"}},
        "licenses": [{"type": "premium"}], "author": {"name": "savandreameta"}}
VIDEO = {"id": 7571364, "name": "Mãos no celular", "url": "https://www.magnific.com/v",
         "duration": "00:00:08", "premium": 1,
         "thumbnails": [{"url": "https://videocdn.cdnpk.net/t.jpg"}],
         "previews": [{"url": "https://videocdn.cdnpk.net/p.mp4"}],
         "author": {"name": "Yuri Arcurs"}}


class _Resp:
    def __init__(self, status, payload=None, content=b"", ctype="application/json"):
        self.status_code = status
        self._payload = payload
        self.content = content or (json.dumps(payload).encode() if payload is not None else b"")
        self.text = self.content.decode("utf-8", "replace")
        self.headers = {"Content-Type": ctype}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _servidor(monkeypatch, respostas, chamadas):
    def get(url, params=None, headers=None, timeout=None, stream=False):
        chamadas.append({"url": url, "params": params or {}, "headers": headers or {}})
        for prefixo, resp in respostas:
            if url.startswith(prefixo):
                return resp() if callable(resp) else resp
        return _Resp(404, {"message": "nope"})
    monkeypatch.setattr(fs.requests, "get", get)
    monkeypatch.setattr(fs, "_HOST_OK", None)


# --------------------------------------------------------------- busca
def test_a_busca_de_fotos_usa_o_host_novo_e_a_chave_no_cabecalho(monkeypatch):
    chamadas = []
    _servidor(monkeypatch, [("https://api.magnific.com/v1/resources", _Resp(200, {"data": [FOTO]}))], chamadas)
    out = fs.search("celular capinha", "CHAVE", 12, "portrait")
    c = chamadas[0]
    assert c["headers"]["x-magnific-api-key"] == "CHAVE"
    assert c["params"]["term"] == "celular capinha"
    assert c["params"]["filters[content_type][photo]"] == 1, "so foto: vetor/PSD vem .zip"
    assert c["params"]["filters[orientation][portrait]"] == 1
    assert out == [{"id": 396648207, "title": "Capinha", "thumb": "https://img.freepik.com/a.jpg",
                    "credit": "savandreameta", "creditUrl": "https://www.freepik.com/x",
                    "premium": True, "kind": "image"}]


def test_sem_o_host_novo_cai_para_o_antigo_com_o_cabecalho_antigo(monkeypatch):
    chamadas = []
    def cai(*a, **k):
        raise fs.requests.ConnectionError("dns")
    _servidor(monkeypatch, [("https://api.magnific.com", cai),
                            ("https://api.freepik.com/v1/resources", _Resp(200, {"data": [FOTO]}))], chamadas)
    assert len(fs.search("x", "K", 3, None)) == 1
    assert chamadas[-1]["headers"] == {"x-freepik-api-key": "K", "Accept-Language": "pt-BR"}
    assert fs._HOST_OK[0] == "https://api.freepik.com", "o host que respondeu fica"


def test_a_busca_de_videos_traduz_a_orientacao(monkeypatch):
    chamadas = []
    _servidor(monkeypatch, [("https://api.magnific.com/v1/videos", _Resp(200, {"data": [VIDEO]}))], chamadas)
    out = fs.search_videos("celular", "K", 5, "portrait")
    assert chamadas[0]["params"]["filters[orientation][vertical]"] == 1, "Pexels fala portrait; Freepik, vertical"
    assert chamadas[0]["params"]["filters[duration][to]"] == 20, "so o original 4K existe: clipe curto baixa em tempo de gente"
    assert out[0]["kind"] == "video" and out[0]["duration"] == "00:00:08"
    assert out[0]["thumb"].endswith("t.jpg") and out[0]["preview"].endswith("p.mp4")
    assert out[0]["credit"] == "Yuri Arcurs" and out[0]["premium"] is True


def test_erro_da_api_vira_mensagem_e_nao_lista_vazia(monkeypatch):
    import pytest
    _servidor(monkeypatch, [("https://api.magnific.com/v1/resources", _Resp(401, {"message": "bad key"})),
                            ("https://api.freepik.com/v1/resources", _Resp(401, {"message": "bad key"}))], [])
    with pytest.raises(RuntimeError, match="401"):
        fs.search("x", "K", 3, None)


# ------------------------------------------------------------ download
def test_a_foto_e_baixada_pelo_id_com_a_url_assinada(monkeypatch, tmp_path):
    chamadas = []
    _servidor(monkeypatch, [
        ("https://api.magnific.com/v1/resources/396648207/download",
         _Resp(200, {"data": {"filename": "a.jpg", "url": "https://cdn/a.jpg", "signed_url": "https://cdn/signed.jpg"}})),
        ("https://cdn/signed.jpg", _Resp(200, content=b"JPEGDATA", ctype="image/jpeg")),
    ], chamadas)
    dest = fs.download(396648207, "K", tmp_path / "f.jpg", image_size="large")
    assert dest.read_bytes() == b"JPEGDATA"
    assert chamadas[0]["params"] == {"image_size": "large"}
    assert chamadas[1]["url"] == "https://cdn/signed.jpg", "a assinada tem prioridade"


def test_zip_de_vetor_nao_e_gravado_como_foto(monkeypatch, tmp_path):
    import pytest
    _servidor(monkeypatch, [
        ("https://api.magnific.com/v1/resources/1/download", _Resp(200, {"data": {"url": "https://cdn/a.zip"}})),
        ("https://cdn/a.zip", _Resp(200, content=b"PK..", ctype="application/zip")),
    ], [])
    with pytest.raises(RuntimeError, match="zip"):
        fs.download(1, "K", tmp_path / "f.jpg")
    assert not (tmp_path / "f.jpg").exists()


def test_o_video_e_convertido_para_1080p_mp4(monkeypatch, tmp_path):
    """O download devolve o ORIGINAL (.mov 4K de centenas de MB); o app
    precisa de um mp4 1080p para inserir na linha do tempo."""
    chamadas = []
    _servidor(monkeypatch, [
        ("https://api.magnific.com/v1/videos/7571364/download",
         _Resp(200, {"data": {"filename": "0_Hands_2160x3840.mov", "url": "https://cdn/orig.mov"}})),
        ("https://cdn/orig.mov", _Resp(200, content=b"MOVDATA", ctype="video/quicktime")),
    ], chamadas)
    rodou = {}
    def ffmpeg(origem, destino):
        rodou["origem"], rodou["destino"] = Path(origem), Path(destino)
        Path(destino).write_bytes(b"MP4")
    monkeypatch.setattr(fs, "_converter_1080p", ffmpeg)
    dest = fs.download_video(7571364, "K", tmp_path / "v.mp4")
    assert dest == tmp_path / "v.mp4" and dest.read_bytes() == b"MP4"
    assert rodou["origem"].suffix == ".mov", "o original vem com a extensao do arquivo"
    assert not rodou["origem"].exists(), "o original gigante nao fica no projeto"


def test_a_conversao_chama_o_ffmpeg_com_1080_de_largura_maxima(monkeypatch, tmp_path):
    visto = {}
    def run(cmd, **k):
        visto["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")
        class R: returncode = 0; stderr = b""
        return R()
    monkeypatch.setattr(fs.subprocess, "run", run)
    monkeypatch.setattr(fs, "_ffmpeg", lambda: "ffmpeg")
    fs._converter_1080p(tmp_path / "o.mov", tmp_path / "d.mp4")
    cmd = " ".join(str(c) for c in visto["cmd"])
    assert "scale=" in cmd and "1080" in cmd and "libx264" in cmd and "-an" not in cmd


# ------------------------------------------------------------- servidor
def test_o_picker_do_editor_busca_e_baixa_pela_freepik():
    assert 'source=qs.get("source", [""])[0]' in PREVIEW
    i = PREVIEW.index("def _images_search_freepik(")
    bloco = PREVIEW[i:PREVIEW.index("\n    def _images_pick(", i)]
    assert "freepik_search.search_videos(query, key, 12" in bloco
    assert "freepik_search.search(query, key, 12" in bloco
    assert 'if not rid.isdigit()' in bloco, "o download e por ID; URL do cliente nao entra"
    assert 'public" / "freepik"' in bloco
    assert 'freepik_search.download_video(rid, key, dest)' in bloco
    j = PREVIEW.index("    def _images_pick(self)")
    assert 'if str(body.get("source") or "").lower() == "freepik":' in PREVIEW[j:j + 600]


def test_a_tela_do_editor_tem_as_tres_fontes():
    i = PHTML.index('id="imgPexelsPane"')
    bloco = PHTML[i:PHTML.index('id="imgLibraryPane"', i)]
    assert bloco.count("data-fonte=") == 3
    assert 'data-fonte="freepik" data-kind="video"' in bloco
    i = APPJS.index("const IMG_FONTE_KEY")
    bloco = APPJS[i:APPJS.index("\n// header", i)]
    assert "&source=freepik&kind=" in bloco
    assert "{ source: 'freepik', id: r.id, kind: r.kind || 'image', query, credit: r.credit }" in bloco
    assert "img-selo" in bloco, "video mostra a duracao no card"


def test_a_chave_entra_nas_integracoes_e_tem_testar():
    for src, nome in ((SERVER, "local_server"), (DESKTOP, "desktop_server")):
        assert '"FREEPIK_API_KEY": bool(keys.get("FREEPIK_API_KEY"))' in src, nome
    assert '"GROQ_API_KEY", "PEXELS_API_KEY", "FREEPIK_API_KEY",' in SERVER
    assert 'if which == "freepik":' in SERVER
    assert 'id="keyFreepik"' in SHTML and 'data-key-test="freepik"' in SHTML
    assert "body.FREEPIK_API_KEY = fp" in SJS and 'ok.push("Freepik")' in SJS
    assert 'for k in ("GROQ_API_KEY", "PEXELS_API_KEY", "FREEPIK_API_KEY"):' in SERVER


def test_broll_automatico_e_planejador_caem_na_freepik_sem_pexels():
    broll = (REPO / "app" / "broll_library.py").read_text(encoding="utf-8")
    assert "def _freepik_para_public(" in broll
    i = broll.index("def resolve_query_to_public(")
    assert "return _freepik_para_public(q, public_dir)" in broll[i:broll.index("\ndef _freepik_para_public", i)]
    auto = (REPO / "helpers" / "auto_broll.py").read_text(encoding="utf-8")
    assert "def _inserts_freepik(" in auto
    i = auto.index("def build_auto_inserts(")
    assert "return _inserts_freepik(" in auto[i:auto.index("\ndef _inserts_freepik", i)]
