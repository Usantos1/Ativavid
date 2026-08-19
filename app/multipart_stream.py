"""Lê um upload multipart direto para o disco, sem carregar o vídeo na memória.

O caminho antigo fazia `self.rfile.read(Content-Length)` e entregava tudo ao
BytesParser da stdlib. Medido: importar um vídeo de 250 MB chegava a **3,1 GB**
de memória (12,5x o arquivo), porque o corpo é copiado no buffer, de novo na
mensagem montada, de novo na árvore de partes e mais uma vez no
`get_payload(decode=True)`. Com a fila cheia e o pipeline rodando junto, esse
pico disputa RAM com o ffmpeg e o Remotion.

Aqui o corpo é consumido em pedaços: o que é arquivo vai para o disco enquanto
chega, e só os campos de texto (intent, title) ficam na memória — com teto.

Sobre o delimitador partido entre pedaços: a busca guarda no buffer os últimos
`len(delimitador)-1` bytes, então uma fronteira que cai no meio de uma leitura
é encontrada na seguinte. É por isso que um vídeo cujos bytes por acaso pareçam
o começo de um delimitador não engana o parser.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

CHUNK = 1 << 20              # 1 MB por leitura
MAX_FIELD = 1 << 20          # campo de texto acima disto é recusado
MAX_HEADERS = 64 << 10       # cabeçalho de parte acima disto é lixo


class MultipartError(ValueError):
    """Corpo malformado — o handler responde 400 em vez de estourar."""


def boundary_of(content_type: str) -> bytes | None:
    m = re.search(r'boundary="?([^";]+)"?', content_type or "", flags=re.I)
    return m.group(1).strip().encode("ascii", "ignore") if m else None


def _nome_arquivo(bruto: str) -> str:
    """Só o nome, sem caminho: o cliente manda o que quiser."""
    nome = (bruto or "").replace("\\", "/").split("/")[-1].strip()
    nome = re.sub(r'[<>:"|?*\x00-\x1f]', "_", nome)
    return nome[:120] or "arquivo"


class _Limitado:
    """Lê no máximo `total` bytes do socket — Content-Length manda."""

    def __init__(self, origem: BinaryIO, total: int):
        self.origem, self.resta = origem, max(0, int(total))

    def read(self, n: int) -> bytes:
        if self.resta <= 0:
            return b""
        data = self.origem.read(min(n, self.resta))
        self.resta -= len(data)
        return data


def _cabecalhos(fluxo: _Limitado, buf: bytearray) -> tuple[dict[str, str], bytearray]:
    while b"\r\n\r\n" not in buf:
        if len(buf) > MAX_HEADERS:
            raise MultipartError("cabeçalho de parte grande demais")
        pedaco = fluxo.read(CHUNK)
        if not pedaco:
            raise MultipartError("upload terminou no meio do cabeçalho")
        buf += pedaco
    cru, _, resto = bytes(buf).partition(b"\r\n\r\n")
    heads: dict[str, str] = {}
    for linha in cru.decode("utf-8", "replace").splitlines():
        if ":" in linha:
            k, _, v = linha.partition(":")
            heads[k.strip().lower()] = v.strip()
    return heads, bytearray(resto)


def parse(origem: BinaryIO, content_type: str, total: int, destino: Path,
          *, chunk: int = CHUNK) -> tuple[list[tuple[str, Path]], dict[str, str]]:
    """Devolve ([(nome_do_arquivo, caminho_no_disco)], {campo: valor}).

    Os arquivos são gravados em `destino` com nome único; quem chamou decide
    para onde vão depois.
    """
    bound = boundary_of(content_type)
    if not bound:
        raise MultipartError("Content-Type sem boundary")
    destino.mkdir(parents=True, exist_ok=True)
    fluxo = _Limitado(origem, total)
    marca = b"\r\n--" + bound
    arquivos: list[tuple[str, Path]] = []
    campos: dict[str, str] = {}

    # O primeiro delimitador vem SEM a quebra de linha na frente. Com pedaco
    # pequeno a primeira leitura pode ser menor que ele, entao enche o buffer
    # antes de decidir -- foi o que quebrou com chunk=7.
    primeiro = b"--" + bound
    buf = bytearray()
    while len(buf) < len(primeiro) + 2:
        pedaco = fluxo.read(chunk)
        if not pedaco:
            break
        buf += pedaco
    if buf.startswith(primeiro):
        del buf[:len(primeiro)]
    else:
        # Preambulo antes da primeira parte (raro, mas o formato permite).
        pos = bytes(buf).find(marca)
        while pos < 0:
            pedaco = fluxo.read(chunk)
            if not pedaco:
                raise MultipartError("delimitador nao encontrado no inicio")
            buf += pedaco
            pos = bytes(buf).find(marca)
        del buf[:pos + len(marca)]

    n_partes = 0
    while True:
        if len(buf) < 2:
            buf += fluxo.read(chunk)
        if bytes(buf[:2]) == b"--":       # delimitador final
            break
        if bytes(buf[:2]) == b"\r\n":
            del buf[:2]
        else:
            raise MultipartError("delimitador malformado")

        heads, buf = _cabecalhos(fluxo, buf)
        disp = heads.get("content-disposition", "")
        m_nome = re.search(r'name="?([^";]+)"?', disp, flags=re.I)
        m_arq = re.search(r'filename="?([^"]*)"?', disp, flags=re.I)
        campo = (m_nome.group(1) if m_nome else "").strip()
        e_arquivo = m_arq is not None and (m_arq.group(1) or "").strip() != ""

        alvo = None
        if e_arquivo:
            n_partes += 1
            nome = _nome_arquivo(m_arq.group(1))
            alvo = destino / f"{n_partes:02d}_{nome}"
            saida = alvo.open("wb")
        else:
            acumulado = bytearray()

        guarda = len(marca) - 1
        try:
            while True:
                pos = bytes(buf).find(marca)
                if pos >= 0:
                    miolo = bytes(buf[:pos])
                    del buf[:pos + len(marca)]
                    break
                if len(buf) > guarda:
                    miolo, resto = bytes(buf[:-guarda]), bytes(buf[-guarda:])
                    buf = bytearray(resto)
                else:
                    miolo = b""
                if e_arquivo:
                    saida.write(miolo)
                else:
                    acumulado += miolo
                    if len(acumulado) > MAX_FIELD:
                        raise MultipartError(f"campo '{campo}' grande demais")
                pedaco = fluxo.read(chunk)
                if not pedaco:
                    raise MultipartError("upload terminou antes do fim da parte")
                buf += pedaco
            if e_arquivo:
                saida.write(miolo)
            else:
                acumulado += miolo
        finally:
            if e_arquivo:
                saida.close()

        if e_arquivo:
            arquivos.append((_nome_arquivo(m_arq.group(1)), alvo))
        elif campo:
            campos[campo] = bytes(acumulado).decode("utf-8", "replace")

    return arquivos, campos
