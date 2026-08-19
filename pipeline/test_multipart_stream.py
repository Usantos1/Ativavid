# -*- coding: utf-8 -*-
"""Upload multipart lido direto para o disco.

O teste forte aqui é o diferencial: para corpos gerados aleatoriamente, o
parser em fluxo tem de dar exatamente o mesmo resultado que o BytesParser da
stdlib, que era quem fazia isto antes (só que carregando tudo na memória).
"""
from __future__ import annotations

import io
import random
import sys
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.multipart_stream import MultipartError, boundary_of, parse  # noqa: E402

BOUND = "----ativavidTeste123"
CTYPE = f"multipart/form-data; boundary={BOUND}"


def monta(partes: list[tuple[str, str | None, bytes]]) -> bytes:
    """partes = [(campo, nome_do_arquivo ou None, conteudo)]"""
    out = bytearray()
    for campo, arq, dados in partes:
        out += f"--{BOUND}\r\n".encode()
        disp = f'form-data; name="{campo}"'
        if arq is not None:
            disp += f'; filename="{arq}"'
        out += f"Content-Disposition: {disp}\r\n".encode()
        if arq is not None:
            out += b"Content-Type: application/octet-stream\r\n"
        out += b"\r\n" + dados + b"\r\n"
    out += f"--{BOUND}--\r\n".encode()
    return bytes(out)


def roda(corpo: bytes, tmp: Path, chunk: int = 1 << 20):
    return parse(io.BytesIO(corpo), CTYPE, len(corpo), tmp, chunk=chunk)


def via_stdlib(corpo: bytes) -> tuple[list[tuple[str, bytes]], dict[str, str]]:
    cru = (b"Content-Type: " + CTYPE.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + corpo)
    msg = BytesParser(policy=policy.default).parsebytes(cru)
    arqs, campos = [], {}
    for p in msg.iter_parts():
        nome = p.get_filename()
        dados = p.get_payload(decode=True) or b""
        campo = (p.get_param("name", header="content-disposition") or "").strip()
        if nome:
            arqs.append((nome, dados))
        elif campo:
            campos[campo] = dados.decode("utf-8", "replace")
    return arqs, campos


# ------------------------------------------------------------------ básico
def test_um_arquivo(tmp_path):
    corpo = monta([("files", "video.mov", b"conteudo do video")])
    arqs, campos = roda(corpo, tmp_path)
    assert campos == {}
    assert [n for n, _ in arqs] == ["video.mov"]
    assert arqs[0][1].read_bytes() == b"conteudo do video"


def test_arquivos_e_campos_juntos(tmp_path):
    corpo = monta([
        ("files", "a.mov", b"AAA"),
        ("intent", None, b'{"contentType":"viral"}'),
        ("files", "b.mov", b"BBB"),
        ("title", None, b"Promo\xc3\xa7\xc3\xa3o"),
    ])
    arqs, campos = roda(corpo, tmp_path)
    assert [n for n, _ in arqs] == ["a.mov", "b.mov"]
    assert [p.read_bytes() for _, p in arqs] == [b"AAA", b"BBB"]
    assert campos["intent"] == '{"contentType":"viral"}'
    assert campos["title"] == "Promoção"


def test_arquivo_vazio(tmp_path):
    arqs, _ = roda(monta([("files", "vazio.mov", b"")]), tmp_path)
    assert arqs[0][1].read_bytes() == b""


def test_parte_sem_filename_nao_vira_arquivo(tmp_path):
    arqs, campos = roda(monta([("intent", None, b"{}")]), tmp_path)
    assert arqs == [] and campos == {"intent": "{}"}


# ----------------------------------------------- o caso que quebra parsers
@pytest.mark.parametrize("chunk", [7, 13, 64, 1000])
def test_delimitador_partido_entre_leituras(tmp_path, chunk):
    """Com pedaço pequeno o delimitador cai no meio de uma leitura."""
    dados = bytes(range(256)) * 40
    corpo = monta([("files", "v.mov", dados), ("title", None, b"x")])
    arqs, campos = roda(corpo, tmp_path, chunk=chunk)
    assert arqs[0][1].read_bytes() == dados
    assert campos == {"title": "x"}


def test_conteudo_que_parece_delimitador(tmp_path):
    """Bytes do vídeo que imitam o começo do delimitador não podem cortar."""
    isca = f"\r\n--{BOUND}".encode()[:-3] + b"XYZ"   # quase o delimitador
    dados = b"antes" + isca + b"depois" + f"--{BOUND}".encode() + b"fim"
    arqs, _ = roda(monta([("files", "v.mov", dados)]), tmp_path, chunk=9)
    assert arqs[0][1].read_bytes() == dados


def test_binario_com_zeros_e_crlf(tmp_path):
    dados = b"\x00\r\n\x00" * 5000
    arqs, _ = roda(monta([("files", "v.mov", dados)]), tmp_path, chunk=17)
    assert arqs[0][1].read_bytes() == dados


# ------------------------------------------------------------- diferencial
@pytest.mark.parametrize("semente", list(range(12)))
def test_igual_ao_parser_da_stdlib(tmp_path, semente):
    rnd = random.Random(semente)
    partes = []
    for i in range(rnd.randint(1, 4)):
        if rnd.random() < 0.3:
            partes.append((f"campo{i}", None, bytes(rnd.randbytes(rnd.randint(0, 50)))
                           .replace(b"\r", b" ")))
        else:
            partes.append((f"files", f"v{i}.mov", rnd.randbytes(rnd.randint(0, 5000))))
    corpo = monta(partes)
    arqs, campos = roda(corpo, tmp_path, chunk=rnd.choice([8, 31, 512, 1 << 16]))
    esperado_arqs, esperado_campos = via_stdlib(corpo)
    assert [(n, p.read_bytes()) for n, p in arqs] == esperado_arqs
    assert campos == esperado_campos


# ------------------------------------------------------------- maldade
def test_nome_com_caminho_nao_escapa_da_pasta(tmp_path):
    arqs, _ = roda(monta([("files", "../../etc/senha.mov", b"x")]), tmp_path)
    nome, caminho = arqs[0]
    assert nome == "senha.mov"
    assert caminho.parent == tmp_path, "gravou fora da pasta de destino"


def test_nome_com_caractere_proibido_no_windows(tmp_path):
    arqs, _ = roda(monta([("files", 'v:deo?"|.mov', b"x")]), tmp_path)
    assert arqs[0][1].exists()


def test_dois_arquivos_com_o_mesmo_nome(tmp_path):
    corpo = monta([("files", "v.mov", b"um"), ("files", "v.mov", b"dois")])
    arqs, _ = roda(corpo, tmp_path)
    assert arqs[0][1] != arqs[1][1], "o segundo sobrescreveria o primeiro"
    assert [p.read_bytes() for _, p in arqs] == [b"um", b"dois"]


def test_corpo_cortado_no_meio_da_erro_claro(tmp_path):
    corpo = monta([("files", "v.mov", b"x" * 1000)])[:400]
    with pytest.raises(MultipartError):
        parse(io.BytesIO(corpo), CTYPE, len(corpo), tmp_path)


def test_content_type_sem_boundary(tmp_path):
    with pytest.raises(MultipartError):
        parse(io.BytesIO(b""), "multipart/form-data", 0, tmp_path)


def test_campo_de_texto_gigante_e_recusado(tmp_path):
    corpo = monta([("title", None, b"a" * (2 << 20))])
    with pytest.raises(MultipartError):
        roda(corpo, tmp_path, chunk=1 << 16)


def test_boundary_entre_aspas():
    assert boundary_of('multipart/form-data; boundary="abc-123"') == b"abc-123"
    assert boundary_of("multipart/form-data; boundary=abc-123") == b"abc-123"
    assert boundary_of("application/json") is None


def test_content_length_menor_que_o_corpo(tmp_path):
    """O socket pode ter mais bytes; quem manda é o Content-Length."""
    corpo = monta([("files", "v.mov", b"x" * 100)])
    with pytest.raises(MultipartError):
        parse(io.BytesIO(corpo), CTYPE, len(corpo) - 50, tmp_path)
