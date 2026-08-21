"""Cifra segredos em repouso com a DPAPI do Windows.

O refresh_token (semanas de validade) e a service role key (ignora RLS, dá
controle do banco e do Auth admin) ficavam em texto plano em ~/ATIVAVID. Um
backup, uma sincronização de perfil ou um infostealer levava tudo.

CryptProtectData amarra o texto cifrado ao usuário do Windows: copiar o arquivo
para outra máquina ou outra conta não serve de nada. Não protege contra código
já rodando como o próprio usuário — para isso a resposta é rotacionar a chave —,
mas fecha o caso de "o arquivo vazou".

Fora do Windows (ou se a API falhar) o valor fica como está: o app não pode
parar de funcionar por causa disso.
"""
from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes

_PREFIX = "dpapi:"


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def raw(self) -> bytes:
        return ctypes.string_at(self.pbData, self.cbData)


def available() -> bool:
    return os.name == "nt"


def _blob(data: bytes) -> _Blob:
    buf = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _free(blob: _Blob) -> None:
    if blob.pbData:
        ctypes.windll.kernel32.LocalFree(blob.pbData)


def is_protected(value: str) -> bool:
    return str(value or "").startswith(_PREFIX)


def protect(plain: str) -> str:
    """Cifra. Devolve o texto original se não der para cifrar."""
    text = str(plain or "")
    if not text or not available() or is_protected(text):
        return text
    try:
        out = _Blob()
        ok = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(_blob(text.encode("utf-8"))),
            "ATIVAVID",
            None,
            None,
            None,
            0,
            ctypes.byref(out),
        )
        if not ok:
            return text
        try:
            return _PREFIX + base64.b64encode(out.raw()).decode("ascii")
        finally:
            _free(out)
    except Exception:  # noqa: BLE001
        return text


def unprotect(value: str) -> str:
    """Decifra. Valor sem prefixo é legado em texto plano — devolve como está."""
    text = str(value or "")
    if not is_protected(text):
        return text
    if not available():
        return ""
    try:
        raw = base64.b64decode(text[len(_PREFIX):])
    except (ValueError, TypeError):
        return ""
    try:
        out = _Blob()
        ok = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(_blob(raw)),
            None,
            None,
            None,
            None,
            0,
            ctypes.byref(out),
        )
        if not ok:
            return ""
        try:
            return out.raw().decode("utf-8", errors="replace")
        finally:
            _free(out)
    except Exception:  # noqa: BLE001
        return ""
