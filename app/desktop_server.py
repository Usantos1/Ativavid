#!/usr/bin/env python3
"""ATIVAVID Desktop — hub de import + editor real da skill (timeline/agulha/estilo).

Combina:
  - APIs de fila/1-clique (local_server)
  - Interface de edicao completa (preview_server + assets/preview)

Rotas principais:
  /                 hub CapCut-like (importar + fila)
  /p/<pasta>/fase1  editor com timeline + agulha
  /p/<pasta>/estilo estilos + legendas (cards visuais)
  /p/<pasta>/fase2  final / visual + legenda do post
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parent.parent
HELPERS = REPO / "helpers"
STUDIO = REPO / "assets" / "studio"
sys.path.insert(0, str(HELPERS))
sys.path.insert(0, str(REPO))

import preview_server as ps  # noqa: E402
from app import http_guard as guard  # noqa: E402
from app import local_server as ls  # noqa: E402

# Cliente (WebView) cancela request — comum ao trocar de página / scrub de vídeo.
_CLIENT_GONE = (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)


def _client_gone(exc: BaseException | None) -> bool:
    if exc is None:
        return False
    if isinstance(exc, _CLIENT_GONE):
        return True
    if isinstance(exc, OSError):
        win = getattr(exc, "winerror", None)
        if win in (10053, 10054):  # WSAECONNABORTED / WSAECONNRESET
            return True
        if getattr(exc, "errno", None) in (32, 104):  # EPIPE / ECONNRESET
            return True
    return False


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    """Não despeja traceback quando o WebView aborta a conexão."""

    def handle_error(self, request, client_address) -> None:  # noqa: ARG002
        if _client_gone(sys.exc_info()[1]):
            return
        super().handle_error(request, client_address)


class DesktopHandler(ps.Handler):
    """Preview editor + studio hub/queue APIs on one port."""

    store: ls.JobStore
    worker: ls.Worker
    projects_root: Path

    def _json(self, obj: object, code: int = 200) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", guard.cors_origin(self.headers))
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except _CLIENT_GONE:
            return
        except OSError as e:
            if _client_gone(e):
                return
            raise

    def _studio_file(self, path: Path, ctype: str | None = None) -> None:
        if not path.exists() or not path.is_file():
            self._json({"error": "not found"}, 404)
            return
        # Vídeo/arquivo grande: streaming com HTTP Range (herdado do preview
        # server). O caminho antigo lia o MP4 INTEIRO para a RAM (300 MB por
        # request) e sem Accept-Ranges o player não conseguia pular de posição.
        if path.suffix.lower() in (".mp4", ".mov", ".webm", ".m4v") or path.stat().st_size > (4 << 20):
            self._send_file(path)
            return
        data = path.read_bytes()
        ctype = ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        try:
            self.wfile.write(data)
        except _CLIENT_GONE:
            return
        except OSError as e:
            if _client_gone(e):
                return
            raise

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", guard.cors_origin(self.headers))
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        raw = self.path.split("?", 1)[0]
        # Hub + studio static — BEFORE preview /p scope
        if raw in ("/", "/hub", "/studio", "/index.html"):
            html = (STUDIO / "index.html").read_text(encoding="utf-8")
            try:
                from app.update_check import boot_fingerprint, running_version

                ver = running_version()
                bust = boot_fingerprint().replace("|", "-")
            except Exception:
                ver = "0"
                bust = "0"
            html = html.replace("VERSION_PLACEHOLDER", bust).replace(
                'src="/assets/studio/studio.js"',
                f'src="/assets/studio/studio.js?v={bust}"',
            )
            # meta para debug na UI
            if "<!--ATIVAVID_VER-->" not in html:
                html = html.replace(
                    "<head>",
                    f"<head>\n  <!--ATIVAVID_VER {ver} {bust}-->",
                    1,
                )
            data = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(data)
            except _CLIENT_GONE:
                return
            except OSError as e:
                if _client_gone(e):
                    return
                raise
            return
        # House style + bare editor tabs (applyState used to rewrite
        # /estilo-padrao → /estilo and a reload then 404'd as unknown route
        # on servers that only knew the hub).
        if raw in ("/estilo-padrao", "/estilo", "/fase1", "/fase2"):
            data = (ps.APP_DIR / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if raw.startswith("/assets/studio/"):
            rel = raw[len("/assets/studio/"):]
            self._studio_file(STUDIO / rel)
            return

        # Embedded OpenAI-compatible gateway (same process — no porta 8080)
        if raw in ("/v1/models", "/v1/models/"):
            from app import llm_gateway as gw

            code, payload = gw.list_models()
            self._json(payload, code)
            return
        if raw == "/api/llm-gateway":
            from app import llm_gateway as gw

            self._json(gw.status())
            return

        # Server-Sent Events: um tick a cada mudança de estado (JobStore /
        # índice de applies). O frontend usa isto para só fazer poll rápido
        # quando há trabalho de verdade — app ocioso fica em silêncio.
        if raw == "/api/events":
            from app.event_bus import version, wait_for_change

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", guard.cors_origin(self.headers))
            self.send_header("Vary", "Origin")
            self.end_headers()
            try:
                self.wfile.write(b"retry: 3000\n\n")
                last = version()
                self.wfile.write(f"event: tick\ndata: {last}\n\n".encode())
                self.wfile.flush()
                while True:
                    cur = wait_for_change(last, timeout=15.0)
                    if cur != last:
                        last = cur
                        self.wfile.write(f"event: tick\ndata: {cur}\n\n".encode())
                    else:
                        self.wfile.write(b": ping\n\n")  # heartbeat
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                return
            except OSError:
                return

        # Queue / brand APIs
        if raw == "/api/health":
            keys = ls.load_env_keys()
            llm = ls.load_llm_proxy()
            from app import license as lic
            from app import llm_gateway as gw
            from app.update_check import boot_fingerprint, running_version

            gws = gw.status()
            self._json({
                "ok": True,
                "version": running_version(),
                "fingerprint": boot_fingerprint(),
                "projectsRoot": str(self.projects_root),
                "hasGroq": bool(keys.get("GROQ_API_KEY")),
                "hasLlmProxy": bool(llm.get("hasKey") and llm.get("baseUrl")),
                "llmGateway": gws,
                "busy": self.worker.busy_id,
                "queued": self.worker.q.qsize(),
                "license": lic.public_status(),
            })
            return
        if raw == "/api/doutor":
            self._json(ls.run_doutor())
            return
        if raw == "/api/auditoria":
            self._json(ls.rodar_auditoria())
            return
        if raw == "/api/system":
            from app.system_info import system_payload

            self._json(system_payload(self.projects_root))
            return
        if raw == "/api/hardware":
            from app.render_engine import public_profile, load_profile

            self._json({"ok": True, "public": public_profile(), "profile": load_profile()})
            return
        if raw in (
            "/api/settings",
            "/api/cache",
            "/api/espaco",
            "/api/doutor/copy",
            "/api/recovery",
            "/api/update/check",
            "/api/update/progresso",
            "/api/musica/motor",
            "/api/biblioteca/pacote",
            "/api/brands",
            "/api/brand-presets",
            "/api/roteiro/chats",
            "/api/roteiro/chat",
            "/api/aulas",
            "/api/roteiro/empresa",
            "/api/fontes",
            "/api/content-types",
            "/api/headline-anchors",
            "/api/library",
            "/api/library/file",
            "/api/brands/logo",
            "/api/license",
            "/api/auth",
            "/api/admin/licenses",
            "/api/admin/aberturas",
            "/api/admin/access",
            "/api/admin/devices",
        ):
            return self._studio_get()
        if raw == "/api/preset":
            self._json(ls.load_preset())
            return
        if raw == "/api/keys":
            keys = ls.load_env_keys()
            self._json({
                "GROQ_API_KEY": bool(keys.get("GROQ_API_KEY")),
                "PEXELS_API_KEY": bool(keys.get("PEXELS_API_KEY")),
                "FREEPIK_API_KEY": bool(keys.get("FREEPIK_API_KEY")),
            })
            return
        if raw == "/api/llm-proxy":
            self._json(ls.load_llm_proxy())
            return
        if raw == "/api/llm-proxy/models":
            from app.llm_proxy import list_models

            result = list_models()
            self._json(result, 200 if result.get("ok") else 502)
            return
        if raw == "/api/llm-proxy/sessions":
            self._json({"providers": ls.sessions_public()})
            return
        if raw == "/api/jobs":
            from app.jobs_view import build as build_jobs

            jobs = build_jobs(self.store, self.projects_root, com_links=True)
            for j in jobs:
                # O editor precisa abrir mesmo depois de uma parada em REVISAR.
                edit = Path(j["editDir"])
                if not (edit / "state.json").exists():
                    edit.mkdir(parents=True, exist_ok=True)
                    (edit / "state.json").write_text(
                        json.dumps({
                            "project": j.get("name") or Path(j["projectDir"]).name,
                            "phase": 1,
                            "message": j.get("message") or "Sem corte ainda",
                            "fps": 30,
                            "style": ls.load_preset(),
                        }, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
            self._json({"jobs": jobs, "busy": self.worker.busy_id})
            return
        if raw.startswith("/api/jobs/"):
            # reuse local_server job media routes via a thin shim
            parts = raw.strip("/").split("/")
            if len(parts) >= 3:
                job_id = parts[2]
                job = self.store.get(job_id)
                if not job:
                    self._json({"error": "job not found"}, 404)
                    return
                if len(parts) == 3:
                    folder = Path(job["projectDir"]).name
                    job = dict(job)
                    job["editorUrl"] = f"/p/{folder}/fase1"
                    job["estiloUrl"] = f"/p/{folder}/estilo"
                    job["finalUrl"] = f"/p/{folder}/fase2"
                    job["thumbUrl"] = f"/api/jobs/{job_id}/thumb"
                    self._json(job)
                    return
                action = parts[3]
                edit = Path(job["editDir"])
                if action == "thumb":
                    thumb = ls.ensure_job_thumb(job)
                    if not thumb:
                        self._json({"error": "sem preview"}, 404)
                        return
                    self._studio_file(thumb, "image/jpeg")
                    return
                if action == "final":
                    final = ls.resolve_delivery_mp4(edit)
                    if not final:
                        self._json({"error": "sem vídeo final"}, 404)
                        return
                    self._studio_file(final, "video/mp4")
                    return
                if action == "cut":
                    self._studio_file(edit / "cut.mp4", "video/mp4")
                    return
                if action == "legenda":
                    leg = edit / "legenda.txt"
                    if not leg.exists():
                        self._json({"error": "sem legenda"}, 404)
                        return
                    self._studio_file(leg, "text/plain; charset=utf-8")
                    return
            self._json({"error": "not found"}, 404)
            return

        # Everything else → real preview editor (timeline, agulha, estilo…)
        return ps.Handler.do_GET(self)

    _CORPO_MAX_AO_RECUSAR = 2 * 1024 * 1024 * 1024   # 2 GB

    def _drenar_corpo(self) -> None:
        """Le e joga fora o corpo antes de recusar.

        Sem isto o corpo nao lido sobra no socket e, com conexao reaproveitada,
        a requisicao SEGUINTE e interpretada a partir dele. Foi assim que um
        "origem nao permitida" honesto virou

            Unsupported method ('{"provider":"gemini-web",...}POST')

        na tela do usuario -- mensagem que escondeu a causa por dois dias.
        """
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            n = 0
        # O teto era 8 MB e um video importado tem 50, 150, 200 MB: o
        # servidor lia 8 MB, respondia e deixava o RESTO no socket. E
        # exatamente a sujeira que esta funcao existe para evitar — com
        # conexao reaproveitada, a requisicao seguinte e lida a partir do
        # lixo. (Testei se era isso que virava "falha no upload" no PC
        # bloqueado dele: NAO era — com o teto antigo o 403 chegou
        # inteiro no meu teste de 60 MB. Fica pela higiene, sem a
        # promessa.)
        restante = min(n, self._CORPO_MAX_AO_RECUSAR)
        while restante > 0:
            pedaco = self.rfile.read(min(65536, restante))
            if not pedaco:
                break
            restante -= len(pedaco)

    def do_POST(self) -> None:  # noqa: N802
        """Involucro de higiene do socket — ver _do_POST_rotas para as rotas.

        QUALQUER rota que respondia cedo (403 de licenca, validacao) sem ler
        o corpo deixava os bytes no socket, e a proxima requisicao do
        keep-alive nascia quebrada: "Bad request syntax ('...mp4"]}}POST
        /api/jobs')" na tela de um CLIENTE em trial (26/08) — segunda vez
        que a classe do defeito morde (a primeira foi o "Unsupported method"
        do llm-proxy). Drenar rota a rota nao escala; aqui o corpo e
        pre-lido para um buffer e o rfile original volta no finally, entao
        rota nenhuma consegue mais envenenar a conexao. Multipart/upload
        grande nao e bufferizado: a conexao fecha ao responder.
        """
        try:
            _clen = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            _clen = 0
        _ctype = self.headers.get("Content-Type", "") or ""
        _orig = self.rfile
        if 0 < _clen <= 32_000_000 and "multipart" not in _ctype:
            import io as _io

            self.rfile = _io.BytesIO(_orig.read(_clen))
        elif _clen:
            self.close_connection = True
        try:
            self._do_POST_rotas()
        finally:
            self.rfile = _orig

    def _do_POST_rotas(self) -> None:
        raw = self.path.split("?", 1)[0]

        # CSRF: um site aberto no navegador não pode mandar POST para o app.
        if not guard.origin_allowed(self.headers, path=raw):
            self._drenar_corpo()
            self._json({"error": "forbidden_origin"}, 403)
            return

        # Gate por exclusão. Sem ele, tudo que cai no ps.Handler.do_POST lá
        # embaixo (o editor inteiro, incluindo /api/corrections op=apply, que
        # re-renderiza o final) rodava sem licença.
        from app import license as lic

        denied = lic.gate(raw)
        if denied is not None:
            self._drenar_corpo()
            self._json(denied, 403)
            return

        if raw in ("/v1/chat/completions", "/v1/chat/completions/"):
            from app import llm_gateway as gw

            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
            except (ValueError, json.JSONDecodeError):
                self._json({"error": {"message": "JSON inválido"}}, 400)
                return
            code, payload = gw.chat_completions(body if isinstance(body, dict) else {})
            self._json(payload, code)
            return

        if raw == "/api/hardware/bench":
            from app.render_engine import build_profile, public_profile

            p = build_profile(force_bench=True)
            self._json({"ok": True, "public": public_profile(), "encoder": p.get("recommendedEncoder")})
            return
        if raw in (
            "/api/preset",
            "/api/keys",
            "/api/keys/test",
            "/api/settings",
            "/api/cache/clear",
            "/api/probe",
            "/api/ai-edit",
            "/api/brands",
            "/api/brand-presets",
            "/api/library/add",
            "/api/library/use",
            "/api/library/upload",
            "/api/library/categoria",
            "/api/library/remover",
            "/api/library/mover",
            "/api/entregas/abrir",
            "/api/entregas/reunir",
            "/api/import-preview",
            "/api/musica/motor",
            "/api/biblioteca/pacote",
            "/api/update/open",
            "/api/espaco/liberar",
            "/api/jobs/publicar-instagram",
            "/api/proxy/rebuild",
            "/api/open-path",
            "/api/llm-proxy",
            "/api/llm-proxy/test",
            "/api/llm-proxy/capture",
            "/api/llm-proxy/open-site",
            "/api/llm-proxy/open-extension",
            "/api/license/refresh",
            "/api/license/activate",
            "/api/auth/login",
            "/api/auth/signup",
            "/api/auth/logout",
            "/api/admin/licenses",
            "/api/admin/access",
            "/api/admin/devices",
            "/api/apply-ack",
            "/api/jobs",
            "/api/jobs/open-folder",
            "/api/jobs/open-final",
            "/api/jobs/rename",
            "/api/jobs/retry",
            "/api/jobs/cancel",
            "/api/jobs/requeue-folder",
            "/api/jobs/open-log",
            "/api/jobs/append-cta",
            "/api/jobs/delete",
            "/api/multiplicador",
            "/api/admin/aulas",
            "/api/roteiro/chat",
            "/api/roteiro/empresa",
            "/api/roteiro/apagar",
            "/api/roteiro/renomear",
            "/api/roteiro/perfil-dos-videos",
        ):
            return self._studio_post()

        return ps.Handler.do_POST(self)

    def _studio_get(self) -> None:
        shim_cls = ls.StudioHandler
        shim_cls.store = self.store
        shim_cls.worker = self.worker
        shim_cls.projects_root = self.projects_root
        fake = shim_cls.__new__(shim_cls)
        for name in (
            "client_address", "server", "request", "headers", "rfile", "wfile",
            "command", "path", "request_version", "requestline", "close_connection",
            "connection", "raw_requestline",
        ):
            if hasattr(self, name):
                setattr(fake, name, getattr(self, name))
        if not hasattr(fake, "requestline"):
            fake.requestline = f"GET {self.path} HTTP/1.1"
        if not hasattr(fake, "request_version"):
            fake.request_version = "HTTP/1.1"
        fake.store = self.store
        fake.worker = self.worker
        fake.projects_root = self.projects_root
        shim_cls.do_GET(fake)

    def _studio_post(self) -> None:
        """Run StudioHandler.do_POST on a fully-attributed shim (no requestline crash)."""
        shim_cls = ls.StudioHandler
        shim_cls.store = self.store
        shim_cls.worker = self.worker
        shim_cls.projects_root = self.projects_root
        fake = shim_cls.__new__(shim_cls)
        # Copy every attr BaseHTTPRequestHandler may touch while answering.
        for name in (
            "client_address",
            "server",
            "request",
            "headers",
            "rfile",
            "wfile",
            "command",
            "path",
            "request_version",
            "requestline",
            "close_connection",
            "connection",
            "raw_requestline",
        ):
            if hasattr(self, name):
                setattr(fake, name, getattr(self, name))
        if not hasattr(fake, "requestline"):
            fake.requestline = f"{getattr(self, 'command', 'POST')} {self.path} HTTP/1.1"
        if not hasattr(fake, "request_version"):
            fake.request_version = "HTTP/1.1"
        if not hasattr(fake, "close_connection"):
            fake.close_connection = True
        fake.store = self.store
        fake.worker = self.worker
        fake.projects_root = self.projects_root
        shim_cls.do_POST(fake)


def ensure_hub_root(projects_root: Path) -> Path:
    """Dummy <edit> so preview_server class attrs are valid at boot."""
    hub = projects_root / ".ativavid" / "hub" / "edit"
    hub.mkdir(parents=True, exist_ok=True)
    state = hub / "state.json"
    # Always refresh so Estilo padrão can open the visual catalog
    state.write_text(
        json.dumps({
            "project": "Estilo padrão da marca",
            "phase": 1,
            "message": "Escolha o visual padrão",
            "fps": 30,
            "awaitingStyle": True,
            "style": ls.load_preset(),
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return hub


def build_server(projects_root: Path, port: int) -> tuple[ThreadingHTTPServer, str]:
    projects_root = projects_root.expanduser().resolve()
    projects_root.mkdir(parents=True, exist_ok=True)
    hub_edit = ensure_hub_root(projects_root)

    store = ls.JobStore(projects_root)
    worker = ls.Worker(store)
    worker.start()

    # preview class attrs
    ps.Handler.root = hub_edit
    ps.Handler.projects_roots = [projects_root]
    # O editor mostra o MESMO nome do card (03/09): o preview nao enxerga
    # o banco de jobs, entao o hub empresta o resolvedor
    from app.jobs_view import ficha_do_card as _ficha_do_card
    ps.Handler.titulo_do_card = staticmethod(
        lambda edit: _ficha_do_card(store, edit))

    DesktopHandler.store = store
    DesktopHandler.worker = worker
    DesktopHandler.projects_root = projects_root
    DesktopHandler.root = hub_edit
    DesktopHandler.projects_roots = [projects_root]

    from app import llm_gateway as gw

    gw.ensure_local_base_url(port)

    # O painel de projetos custa 31s na primeira chamada (um ffprobe por
    # projeto, 187 deles). Esquentar aqui tira essa espera de quem abre.
    try:
        ps.esquentar_painel(DesktopHandler.projects_roots)
    except Exception:  # noqa: BLE001
        pass

    srv = QuietThreadingHTTPServer(("127.0.0.1", port), DesktopHandler)
    url = f"http://127.0.0.1:{port}/"
    return srv, url


def main() -> None:
    for k, v in ls.load_env_keys().items():
        os.environ.setdefault(k, v)

    ap = argparse.ArgumentParser(description="ATIVAVID Desktop unified server")
    default_root = Path(
        os.environ.get("ATIVAVID_PROJECTS") or (Path.home() / "ATIVAVID" / "Projetos")
    )
    ap.add_argument("--projects-root", type=Path, default=default_root)
    ap.add_argument("--port", type=int, default=4850)
    args = ap.parse_args()

    # Uma linha por abertura, em ~/ATIVAVID/aberturas.jsonl, e um aviso ao
    # servidor quando ele souber receber. Em segundo plano: registro de uso
    # nao vale um app que demora a abrir.
    try:
        from app.registro_de_uso import registrar_abertura

        registrar_abertura()
    except Exception:  # noqa: BLE001
        pass

    srv, url = build_server(args.projects_root, args.port)
    print(f"ATIVAVID Desktop -> {url}", flush=True)
    print(f"Projetos: {args.projects_root.resolve()}", flush=True)
    print("Hub: /   Editor: /p/<projeto>/fase1", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado", flush=True)


if __name__ == "__main__":
    main()
