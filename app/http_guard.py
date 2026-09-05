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


# Rotas que a EXTENSÃO do navegador precisa alcançar. Ela posta com origem
# `chrome-extension://<id>`, que a regra geral recusa — e recusava calada:
# durante dois dias a sessão do Gemini nunca chegou ao app, a IA parou de
# planejar o corte e a headline passou a ser um pedaço cru da transcrição
# colado no vídeo. Em 20 e 21/08, 50 de 51 vídeos saíram sem IA.
#
# Abrir só estas rotas, e não a regra inteira, é o que mantém a proteção de
# pé: o ataque que ela existe para barrar é um SITE aberto no navegador, e
# site nenhum consegue forjar origem `chrome-extension://`. Sobra o risco de
# outra extensão já instalada com permissão para localhost — real, mas de
# outra ordem, e estas rotas só gravam uma captura de sessão.
ROTAS_DA_EXTENSAO = frozenset({
    "/api/llm-proxy/capture",
    "/api/llm-proxy/status",
})


def _e_a_extensao(origin: str, caminho: str | None) -> bool:
    if not caminho:
        return False
    return (origin.lower().startswith("chrome-extension://")
            and caminho.split("?", 1)[0].rstrip("/") in
            {r.rstrip("/") for r in ROTAS_DA_EXTENSAO})


# Cabeçalhos que vão em TODA resposta dos servidores locais. Só o navegador
# os lê, e só em documento (HTML): um site de fora não consegue pôr o hub
# num <iframe> invisível e guiar cliques do dono ("clickjacking" — a rota
# de liberar dias no painel de admin é um clique). O hub embute o editor
# (`/p/<pasta>/fase1`) na MESMA origem, e `'self'` deixa isso passar.
# Nada de `X-Content-Type-Options: nosniff`: o Windows às vezes registra
# `.js` como `text/plain` e o nosniff barraria o próprio studio.js.
CABECALHOS_DE_DOCUMENTO = (
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Content-Security-Policy", "frame-ancestors 'self'"),
)


def host_allowed(headers) -> bool:
    """O pedido foi feito para ESTE endereço (127.0.0.1 / localhost / ::1)?

    A guarda de origem (`origin_allowed`) só entra no POST, e o GET ficava
    aberto a um truque antigo: um site cujo DNS passa a apontar para
    127.0.0.1 depois de carregado ("DNS rebinding"). Para o navegador a
    página continua na origem dela, então NÃO manda `Origin` e o
    `Sec-Fetch-Site` diz `same-origin` — e o servidor entregava
    `/api/settings` (e-mail da conta), a lista de licenças do admin, os
    projetos. O que denuncia o truque é o `Host`: vem `evil.com:4850`, e
    este servidor só existe em 127.0.0.1.

    Sem `Host` (HTTP/1.0, ferramenta local) passa: não é navegador.
    """
    host = str(headers.get("Host") or "").strip()
    if not host:
        return True
    return _host_is_local(host)


def origin_allowed(headers, *, host_header: str | None = None,
                   path: str | None = None) -> bool:
    """True se a requisição não veio de outro site.

    `path` permite abrir as rotas da extensão sem afrouxar o resto.
    """
    site = str(headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site and site not in ("same-origin", "same-site", "none"):
        # A extensão manda `cross-site` em alguns navegadores; nas rotas dela
        # isso é esperado.
        if not _e_a_extensao(str(headers.get("Origin") or ""), path):
            return False

    origin = str(headers.get("Origin") or "").strip()
    if not origin or origin.lower() == "null":
        # Sem Origin: não é navegador fazendo cross-site.
        return True

    if _e_a_extensao(origin, path):
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
