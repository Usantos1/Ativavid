"""Guarda de origem para os servidores HTTP locais.

O app escuta em 127.0.0.1, mas isso não o protege de um site aberto no navegador
do usuário: a porta é fixa e a autenticação é ambiente (o servidor usa o
auth.json do dono). Sem esta checagem, uma página qualquer podia mandar POST
para /api/settings (trocando o Supabase para capturar a senha do próximo login)
ou para /api/admin/access (liberando dias com o JWT de admin da máquina).

Um POST cross-origin de navegador SEMPRE carrega Origin, então recusar Origin
estranha fecha o vetor sem exigir token na UI. Ferramentas locais (curl, o
próprio app) não mandam Origin e seguem funcionando.
"""
from __future__ import annotations

from urllib.parse import urlparse

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}


def _host_is_local(netloc: str) -> bool:
    host = netloc.rsplit(":", 1)[0] if ":" in netloc and not netloc.endswith("]") else netloc
    return host.strip("[]").lower() in {h.strip("[]") for h in _LOCAL_HOSTS}


def origin_allowed(headers, *, host_header: str | None = None) -> bool:
    """True se a requisição não veio de outro site."""
    site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site and site not in ("same-origin", "same-site", "none"):
        return False

    origin = str(headers.get("Origin") or "").strip()
    if not origin or origin.lower() == "null":
        # Sem Origin: não é navegador fazendo cross-site.
        return True

    try:
        parsed = urlparse(origin)
    except ValueError:
        return False
    if parsed.scheme not in ("http", "https"):
        return False
    if not _host_is_local(parsed.netloc):
        return False

    # Mesma porta que o servidor, quando dá para saber.
    host = str(host_header or headers.get("Host") or "").strip()
    if host and parsed.netloc.lower() != host.lower():
        port = host.rsplit(":", 1)[-1] if ":" in host else ""
        origin_port = parsed.netloc.rsplit(":", 1)[-1] if ":" in parsed.netloc else ""
        if port and origin_port and port != origin_port:
            return False
    return True


def cors_origin(headers) -> str:
    """Valor de Access-Control-Allow-Origin — a própria origem, nunca '*'.

    Com '*' qualquer site lia as respostas do app (e-mail da conta, settings,
    lista de licenças).
    """
    origin = str(headers.get("Origin") or "").strip()
    if origin and origin_allowed(headers):
        return origin
    host = str(headers.get("Host") or "127.0.0.1").strip()
    return f"http://{host}"
