#!/usr/bin/env python3
"""ATIVAVID Local — janela nativa (WebView2) + hub + editor real."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
os.chdir(REPO)
sys.path.insert(0, str(REPO))

# FFmpeg embutido antes de qualquer probe/job
try:
    from app.win_process import refresh_path_env
    from app.ffmpeg_tools import ensure_ffmpeg_on_path

    refresh_path_env()
    ensure_ffmpeg_on_path()
except Exception:
    pass

from app import desktop_server as ds  # noqa: E402
from app import local_server as ls  # noqa: E402

WINDOW_TITLE = "ATIVAVID"


class WindowApi:
    """Botões da titlebar CapCut (min / max / fechar → bandeja)."""

    def __init__(self) -> None:
        self._window = None
        self._maximized = False
        self._restore: tuple[int, int, int, int] | None = None

    def bind(self, window) -> None:
        self._window = window

    def minimize(self) -> None:
        if self._window:
            self._window.minimize()

    def toggle_maximize(self) -> bool:
        hwnd = _find_hwnd()
        if not hwnd:
            if not self._window:
                return False
            try:
                if self._maximized:
                    self._window.restore()
                    self._maximized = False
                else:
                    self._window.maximize()
                    self._maximized = True
            except Exception:
                pass
            return self._maximized

        if self._maximized:
            _set_thick_frame(hwnd, True)
            if self._restore:
                _set_window_rect(hwnd, *self._restore)
            else:
                try:
                    if self._window:
                        self._window.restore()
                except Exception:
                    pass
            self._maximized = False
            _set_maximized_flag(False)
            _apply_dwm_chrome(maximized=False)
            return False

        self._restore = _get_window_rect(hwnd)
        if _fill_work_area(hwnd):
            self._maximized = True
            _set_maximized_flag(True)
            return True
        try:
            if self._window:
                self._window.maximize()
                self._maximized = True
                _set_maximized_flag(True)
                _apply_dwm_chrome(maximized=True)
        except Exception:
            pass
        return self._maximized

    def is_maximized(self) -> bool:
        return bool(self._maximized)

    def close(self) -> None:
        """X da titlebar: esconde na bandeja — servidor e cookies continuam."""
        _hide_to_tray(self)

    def show_window(self) -> None:
        _show_from_tray(self)

    def quit_app(self) -> None:
        """Sair de verdade (menu da bandeja)."""
        global _TRAY_ICON, _QUIT_REQUESTED
        _QUIT_REQUESTED = True
        try:
            if _TRAY_ICON is not None:
                _TRAY_ICON.stop()
        except Exception:
            pass
        _TRAY_ICON = None
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass


_TRAY_ICON = None
_QUIT_REQUESTED = False
_API_REF: WindowApi | None = None
_SHOW_REQUEST = Path.home() / "ATIVAVID" / "show.request"
_RELOAD_REQUEST = Path.home() / "ATIVAVID" / "reload.request"
_HTTP_PORT = 4850
_SINGLE_INSTANCE_HANDLE = None


def _hide_to_tray(api: WindowApi) -> None:
    if not api._window:
        return
    try:
        api._window.hide()
    except Exception:
        try:
            api._window.minimize()
        except Exception:
            pass
    _ensure_tray(api)


def _show_from_tray(api: WindowApi | None = None) -> None:
    api = api or _API_REF
    hwnd = _find_hwnd()
    if hwnd:
        try:
            import ctypes

            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
    if api and api._window:
        try:
            api._window.show()
            api._window.restore()
        except Exception:
            pass
    try:
        if _SHOW_REQUEST.exists():
            _SHOW_REQUEST.unlink()
    except OSError:
        pass


def _ensure_tray(api: WindowApi) -> None:
    global _TRAY_ICON, _API_REF
    _API_REF = api
    if _TRAY_ICON is not None:
        return
    try:
        import pystray
        from PIL import Image
    except ImportError:
        return

    icon_path = REPO / "assets" / "preview" / "ativa-vid-icon.png"
    try:
        image = Image.open(icon_path) if icon_path.exists() else Image.new("RGB", (64, 64), (255, 80, 120))
    except Exception:
        image = Image.new("RGB", (64, 64), (255, 80, 120))

    def on_show(icon, item):  # noqa: ARG001
        _show_from_tray(api)

    def on_quit(icon, item):  # noqa: ARG001
        api.quit_app()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir ATIVAVID", on_show, default=True),
        pystray.MenuItem("Sair", on_quit),
    )
    _TRAY_ICON = pystray.Icon("ativavid", image, "ATIVAVID (em segundo plano)", menu)

    def _run() -> None:
        try:
            _TRAY_ICON.run()
        except Exception:
            pass

    threading.Thread(target=_run, name="ativavid-tray", daemon=True).start()


def _reload_webview(api: WindowApi | None = None) -> None:
    """Recarrega a UI (após update / handoff) para pegar studio.js novo."""
    api = api or _API_REF
    if not api or not api._window:
        return
    try:
        from app.update_check import running_version

        ver = running_version()
    except Exception:
        ver = str(int(time.time()))
    try:
        # force-bust cache do WebView2
        api._window.load_url(f"http://127.0.0.1:{_HTTP_PORT}/?_={ver}&r={int(time.time())}")
    except Exception:
        try:
            api._window.evaluate_js("location.reload(true)")
        except Exception:
            pass


def _watch_show_request(api: WindowApi) -> None:
    while not _QUIT_REQUESTED:
        try:
            if _SHOW_REQUEST.exists():
                _show_from_tray(api)
            if _RELOAD_REQUEST.exists():
                try:
                    _RELOAD_REQUEST.unlink()
                except OSError:
                    pass
                _show_from_tray(api)
                _reload_webview(api)
        except Exception:
            pass
        time.sleep(0.6)


def _kill_listeners_on_port(port: int) -> None:
    """Encerra quem ainda segura a porta (build antiga após atualizar)."""
    if sys.platform != "win32":
        return
    try:
        from app.win_process import hide_console_kwargs

        hide = hide_console_kwargs()
    except Exception:
        hide = {}
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            text=True,
            encoding="utf-8",
            errors="replace",
            **hide,
        )
    except Exception:
        return
    needle = f":{int(port)}"
    pids: set[str] = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        if parts[0].upper() != "TCP":
            continue
        if "LISTENING" not in (p.upper() for p in parts):
            continue
        local = parts[1]
        if not local.endswith(needle):
            continue
        pid = parts[-1]
        if pid.isdigit() and pid != "0":
            pids.add(pid)
    me = str(os.getpid())
    for pid in pids:
        if pid == me:
            continue
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", pid],
                capture_output=True,
                timeout=8,
                **hide,
            )
        except Exception:
            pass


def _handoff_if_running(port: int) -> bool:
    """Se o servidor já está no ar, só reabre a janela (não sobe 2º processo).

    Compara fingerprint do disco com o do processo na porta. O VERSION no disco
    pode já ter sido atualizado pelo instalador enquanto o processo antigo ainda
    roda — por isso não basta comparar a string de versão lida do arquivo.
    """
    health: dict = {}
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.8) as r:
            if r.status != 200:
                return False
            try:
                health = json.loads(r.read().decode("utf-8", errors="replace") or "{}")
            except Exception:
                health = {}
    except Exception:
        return False

    try:
        from app.update_check import disk_fingerprint

        disk_fp = disk_fingerprint()
        run_fp = str(health.get("fingerprint") or "").strip()
        # Build antigo (sem fingerprint) ou fingerprint diferente → mata e sobe o novo
        if not run_fp or run_fp != disk_fp:
            print(
                f"Build em disco ≠ processo na porta "
                f"(disk={disk_fp!r} running={run_fp or health.get('version')!r}) — reiniciando…",
                flush=True,
            )
            _kill_listeners_on_port(port)
            time.sleep(1.0)
            # Confirma que a porta liberou
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=0.4) as r:
                    if r.status == 200:
                        _kill_listeners_on_port(port)
                        time.sleep(0.8)
            except Exception:
                pass
            return False
    except Exception:
        # Em dúvida, não handoff — sobe processo novo
        try:
            _kill_listeners_on_port(port)
            time.sleep(0.8)
        except Exception:
            pass
        return False

    hwnd = _find_hwnd()
    if hwnd:
        try:
            import ctypes

            SW_RESTORE = 9
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
        try:
            _RELOAD_REQUEST.parent.mkdir(parents=True, exist_ok=True)
            _RELOAD_REQUEST.write_text("1", encoding="utf-8")
        except OSError:
            pass
        return True

    # Servidor na porta sem janela (ex.: ficou preso em --browser) — mata e sobe GUI.
    print(
        "ATIVAVID na porta sem janela nativa — reiniciando com interface…",
        flush=True,
    )
    _kill_listeners_on_port(port)
    time.sleep(0.8)
    return False


_MAXIMIZED = False


def _set_maximized_flag(on: bool) -> None:
    global _MAXIMIZED
    _MAXIMIZED = bool(on)


def _is_app_maximized() -> bool:
    return bool(_MAXIMIZED)


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        return (
            int(rect.left),
            int(rect.top),
            int(rect.right - rect.left),
            int(rect.bottom - rect.top),
        )
    except Exception:
        return None


def _dwm_set_attr(hwnd: int, attr: int, value: int) -> None:
    import ctypes
    from ctypes import wintypes

    fn = ctypes.windll.dwmapi.DwmSetWindowAttribute
    fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    fn(hwnd, attr, ctypes.byref(ctypes.c_int(value)), 4)


def _apply_dwm_chrome(*, maximized: bool = False) -> None:
    """Sem borda accent e sem cantos arredondados (evita faixa transparente no topo)."""
    if sys.platform != "win32":
        return
    hwnd = _find_hwnd()
    if not hwnd:
        return
    try:
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWA_BORDER_COLOR = 34
        DWMWA_COLOR_NONE = 0xFFFFFFFE
        DWMWCP_DONOTROUND = 1

        _dwm_set_attr(hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
        # Sempre sem round — em janela o round deixava uma faixa “vazia” acima da titlebar.
        _dwm_set_attr(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND)
    except Exception:
        pass


def _set_window_rect(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    import ctypes

    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    ctypes.windll.user32.SetWindowPos(
        hwnd,
        0,
        int(x),
        int(y),
        int(w),
        int(h),
        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )


def _set_thick_frame(hwnd: int, enabled: bool) -> None:
    """WS_THICKFRAME cria margem invisível — fora no maximize, ligado em janela."""
    if not hwnd:
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        GWL_STYLE = -16
        WS_THICKFRAME = 0x00040000
        WS_CAPTION = 0x00C00000
        WS_MINIMIZEBOX = 0x00020000
        WS_MAXIMIZEBOX = 0x00010000
        WS_SYSMENU = 0x00080000
        SWP_FRAMECHANGED = 0x0020
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010

        style = int(user32.GetWindowLongW(hwnd, GWL_STYLE))
        style &= ~WS_CAPTION
        style |= WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        if enabled:
            style |= WS_THICKFRAME
        else:
            style &= ~WS_THICKFRAME
        user32.SetWindowLongW(hwnd, GWL_STYLE, style)
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def _monitor_work_area(hwnd: int) -> tuple[int, int, int, int] | None:
    """Área útil do monitor (sem a taskbar)."""
    if not hwnd:
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", wintypes.LONG),
                ("top", wintypes.LONG),
                ("right", wintypes.LONG),
                ("bottom", wintypes.LONG),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", RECT),
                ("rcWork", RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        user32 = ctypes.windll.user32
        MONITOR_DEFAULTTONEAREST = 2
        hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not hmon:
            return None
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return (
            int(r.left),
            int(r.top),
            int(r.right - r.left),
            int(r.bottom - r.top),
        )
    except Exception:
        return None


def _fill_work_area(hwnd: int) -> bool:
    """Maximiza sem margens: tira thickframe e preenche a área útil."""
    work = _monitor_work_area(hwnd)
    if not work:
        return False
    _set_thick_frame(hwnd, False)
    _set_window_rect(hwnd, *work)
    _apply_dwm_chrome(maximized=True)
    _set_maximized_flag(True)
    return True


def _clamp_to_work_area() -> None:
    """Corrige maximize nativo que cobre a taskbar ou deixa fresta."""
    hwnd = _find_hwnd()
    if not hwnd:
        return
    work = _monitor_work_area(hwnd)
    if not work:
        return
    cur = _get_window_rect(hwnd)
    if not cur:
        return
    wx, wy, ww, wh = work
    cx, cy, cw, ch = cur
    # Maior que a área útil (cobriu taskbar) OU menor com fresta (borda thickframe)
    covers_taskbar = ch >= wh + 8 or cy + ch > wy + wh + 4
    has_gap = (
        _is_app_maximized()
        and (abs(cx - wx) > 1 or abs(cy - wy) > 1 or abs(cw - ww) > 2 or abs(ch - wh) > 2)
    )
    if covers_taskbar or has_gap:
        _fill_work_area(hwnd)
    else:
        _apply_dwm_chrome(maximized=_is_app_maximized())


def _wait_http(url: str, timeout: float = 25.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as r:
                if r.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.15)
    raise SystemExit(f"servidor nao subiu em {url}")


def _find_hwnd() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import ctypes

        user32 = ctypes.windll.user32
        for title in (WINDOW_TITLE, "ATIVAVID - Seu vídeo editado por IA"):
            hwnd = int(user32.FindWindowW(None, title) or 0)
            if hwnd:
                return hwnd
    except Exception:
        pass
    return 0


def _apply_windows_icon(icon_path: Path) -> None:
    """Set title-bar / taskbar icon on the Edge/WebView2 host window (Win32)."""
    if sys.platform != "win32" or not icon_path.exists():
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.LoadImageW.restype = wintypes.HANDLE

        hwnd = _find_hwnd()
        if not hwnd:
            return
        hicon_big = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
        hicon_small = user32.LoadImageW(None, str(icon_path), IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if hicon_big:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
        if hicon_small:
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
    except Exception:
        pass


def _enable_frameless_resize() -> None:
    """Reativa bordas de resize + Aero Snap em janela frameless (CapCut)."""
    if sys.platform != "win32":
        return
    if _is_app_maximized():
        # Não reintroduz thickframe enquanto maximizado (gera fresta vermelha).
        hwnd = _find_hwnd()
        if hwnd:
            _set_thick_frame(hwnd, False)
            _apply_dwm_chrome(maximized=True)
        return
    hwnd = _find_hwnd()
    if not hwnd:
        return
    _set_thick_frame(hwnd, True)
    _apply_dwm_chrome(maximized=False)


# Mantém refs vivas (senão o GC derruba o wndproc).
_OLD_WNDPROC = None
_WNDPROC_REF = None
_EDGE_HOOKED = False


def _install_edge_to_edge_hook() -> None:
    """Cliente = janela inteira: some a faixa NC e o X cola no canto."""
    global _OLD_WNDPROC, _WNDPROC_REF, _EDGE_HOOKED
    if sys.platform != "win32" or _EDGE_HOOKED:
        return
    hwnd = _find_hwnd()
    if not hwnd:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        GWLP_WNDPROC = -4
        WM_NCCALCSIZE = 0x0083
        WM_NCHITTEST = 0x0084
        HTCLIENT = 1
        HTLEFT, HTRIGHT = 10, 11
        HTTOP, HTTOPLEFT, HTTOPRIGHT = 12, 13, 14
        HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
        BORDER = 8

        LRESULT = ctypes.c_ssize_t
        WNDPROC = ctypes.WINFUNCTYPE(
            LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        if ctypes.sizeof(ctypes.c_void_p) == 8:
            set_long = user32.SetWindowLongPtrW
            call_proc = user32.CallWindowProcW
            set_long.restype = ctypes.c_void_p
            set_long.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
            call_proc.restype = LRESULT
            call_proc.argtypes = [
                ctypes.c_void_p,
                wintypes.HWND,
                wintypes.UINT,
                wintypes.WPARAM,
                wintypes.LPARAM,
            ]
        else:
            set_long = user32.SetWindowLongW
            call_proc = user32.CallWindowProcW
            set_long.restype = ctypes.c_long
            call_proc.restype = LRESULT

        def _proc(hwnd_msg, msg, wparam, lparam):
            if msg == WM_NCCALCSIZE and wparam:
                # Sem área non-client → UI cola nas bordas (CapCut).
                return 0
            if msg == WM_NCHITTEST and not _is_app_maximized():
                # Redimensionar pelas bordas (já que NC sumiu).
                x = ctypes.c_int16(lparam & 0xFFFF).value
                y = ctypes.c_int16((lparam >> 16) & 0xFFFF).value
                rect = wintypes.RECT()
                user32.GetWindowRect(hwnd_msg, ctypes.byref(rect))
                left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
                on_left = (x - left) < BORDER
                on_right = (right - x) < BORDER
                on_top = (y - top) < BORDER
                on_bottom = (bottom - y) < BORDER
                if on_top and on_left:
                    return HTTOPLEFT
                if on_top and on_right:
                    return HTTOPRIGHT
                if on_bottom and on_left:
                    return HTBOTTOMLEFT
                if on_bottom and on_right:
                    return HTBOTTOMRIGHT
                if on_left:
                    return HTLEFT
                if on_right:
                    return HTRIGHT
                if on_top:
                    return HTTOP
                if on_bottom:
                    return HTBOTTOM
                return HTCLIENT
            return int(call_proc(_OLD_WNDPROC, hwnd_msg, msg, wparam, lparam) or 0)

        _WNDPROC_REF = WNDPROC(_proc)
        _OLD_WNDPROC = set_long(hwnd, GWLP_WNDPROC, ctypes.cast(_WNDPROC_REF, ctypes.c_void_p).value)
        _EDGE_HOOKED = True
        # Recalcula frame
        SWP_FRAMECHANGED = 0x0020
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        user32.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def _venv_python() -> Path | None:
    scripts = REPO / ".venv" / "Scripts"
    for name in ("pythonw.exe", "python.exe"):
        p = scripts / name
        if p.exists():
            return p
    return None


def _reexec_under_venv_if_needed() -> None:
    """Se abriu com o Python do sistema, troca pro .venv e sai."""
    target = _venv_python()
    if target is None:
        return
    try:
        cur = Path(sys.executable).resolve()
        want = target.resolve()
    except OSError:
        return
    # Já no .venv (stub Scripts\python*.exe). O processo "filho" em
    # Local\Programs\Python é o interpretador real do stub — não trocar.
    cur_s = str(cur).lower().replace("/", "\\")
    if "\\.venv\\scripts\\" in cur_s or cur.parent == want.parent:
        return
    # Preferir o mesmo flavor (console vs windowed)
    if cur.name.lower() == "python.exe":
        alt = want.with_name("python.exe")
        if alt.exists():
            want = alt
    argv = [str(want), "-X", "utf8", str(Path(__file__).resolve()), *sys.argv[1:]]
    try:
        kwargs: dict = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            )
            kwargs["close_fds"] = True
        subprocess.Popen(argv, cwd=str(REPO), **kwargs)
    except Exception as e:
        print(f"[warn] não consegui trocar pro .venv ({e}) — seguindo assim", flush=True)
        return
    print(f"Reiniciando com {want.name} do .venv…", flush=True)
    raise SystemExit(0)


def _kill_other_launchers() -> None:
    """Mata outros stubs .venv\\Scripts\\python* deste install.

    No Windows o launcher do venv aparece DUAS vezes (stub em .venv + python
    base em Local\\Programs\\Python). Matar o stub-pai do processo atual
    suicida o app (taskkill /T) — por isso ignoramos nosso PID e o ppid.
    """
    if sys.platform != "win32":
        return
    me = os.getpid()
    try:
        parent = os.getppid()
    except Exception:
        parent = 0
    needle = str((REPO / "app" / "launcher.py").resolve()).lower().replace("/", "\\")
    venv_scripts = str((REPO / ".venv" / "Scripts").resolve()).lower().replace("/", "\\")
    try:
        from app.win_process import hide_console_kwargs

        hide = hide_console_kwargs()
    except Exception:
        hide = {}
    try:
        out = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process | "
                "Where-Object { $_.CommandLine -and $_.CommandLine -like '*launcher.py*' } | "
                "ForEach-Object { \"$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.ExecutablePath)`t$($_.CommandLine)\" }",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            **hide,
        )
    except Exception:
        return
    for line in out.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        pid_s, ppid_s, exe_path, cmd = parts[0], parts[1], parts[2], parts[3]
        if not pid_s.isdigit():
            continue
        pid = int(pid_s)
        ppid = int(ppid_s) if ppid_s.isdigit() else 0
        # nunca mate a si, o stub-pai, nem um filho direto
        if pid in (me, parent) or ppid == me:
            continue
        if needle not in cmd.lower().replace("/", "\\"):
            continue
        exe_l = (exe_path or "").lower().replace("/", "\\")
        # só stubs do nosso .venv — nunca o python base (filho do stub)
        if venv_scripts not in exe_l:
            continue
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=8,
                **hide,
            )
            print(f"[warn] encerrei launcher duplicado pid {pid}", flush=True)
        except Exception:
            pass


def _try_claim_single_instance() -> tuple[bool, object | None]:
    """Garante um único ATIVAVID por máquina (Windows named mutex)."""
    if sys.platform != "win32":
        return True, None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Global\\ATIVAVID.SingleInstance.v1")
        if not handle:
            return True, None
        ERROR_ALREADY_EXISTS = 183
        if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False, None
        return True, handle
    except Exception:
        return True, None


def main() -> None:
    for k, v in ls.load_env_keys().items():
        os.environ.setdefault(k, v)

    ap = argparse.ArgumentParser(description="ATIVAVID Local desktop")
    default_root = Path(
        os.environ.get("ATIVAVID_PROJECTS") or (Path.home() / "ATIVAVID" / "Projetos")
    )
    ap.add_argument("--projects-root", type=Path, default=default_root)
    ap.add_argument("--port", type=int, default=4850)
    ap.add_argument("--browser", action="store_true")
    args = ap.parse_args()

    # Extensão de cookies: cópia estável fora de Program Files
    try:
        from app.extension_sync import sync_extension

        sync_extension()
    except Exception:
        pass

    if not args.browser:
        _reexec_under_venv_if_needed()
        if _handoff_if_running(args.port):
            print("ATIVAVID já estava aberto — janela restaurada.", flush=True)
            return
        ok_single, handle = _try_claim_single_instance()
        if not ok_single:
            time.sleep(0.6)
            if _handoff_if_running(args.port):
                print("ATIVAVID já estava aberto — janela restaurada.", flush=True)
                return
            print(
                "ATIVAVID já está em execução. Feche pela bandeja ou abra de novo.",
                flush=True,
            )
            return
        global _SINGLE_INSTANCE_HANDLE
        _SINGLE_INSTANCE_HANDLE = handle
        _kill_other_launchers()

    global _HTTP_PORT
    _HTTP_PORT = int(args.port)

    srv, url = ds.build_server(args.projects_root, args.port)
    print(f"ATIVAVID Local -> {url}", flush=True)
    print(f"Projetos: {args.projects_root.expanduser().resolve()}", flush=True)

    threading.Thread(target=srv.serve_forever, name="ativavid-http", daemon=True).start()
    _wait_http(url)

    # Renova JWT se existir — mantém login entre aberturas
    try:
        from app import auth as au

        au.ensure_session()
    except Exception:
        pass

    if args.browser:
        import webbrowser

        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nencerrado", flush=True)
        return

    try:
        import webview
    except ImportError:
        print("pywebview ausente — abrindo no navegador. Rode: uv sync", flush=True)
        import webbrowser

        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    api = WindowApi()
    # CapCut: frameless + titlebar HTML. Win32 reativa resize/snap.
    # min_size cabe em metade de monitor 1080p (Aero Snap).
    window = webview.create_window(
        title=WINDOW_TITLE,
        url=url,
        width=1480,
        height=920,
        min_size=(900, 600),
        background_color="#0c0c0e",
        text_select=True,
        frameless=True,
        easy_drag=False,
        shadow=False,
        resizable=True,
        fullscreen=False,
        maximized=False,
        js_api=api,
    )
    api.bind(window)
    icon = REPO / "assets" / "preview" / "ativa-vid-icon.ico"
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ATIVAVID.Local.1")
    except Exception:
        pass

    def _on_shown() -> None:
        _enable_frameless_resize()
        _apply_dwm_chrome(maximized=False)
        _apply_windows_icon(icon)
        _install_edge_to_edge_hook()
        threading.Timer(0.35, _enable_frameless_resize).start()
        threading.Timer(0.4, lambda: _apply_dwm_chrome(maximized=False)).start()
        threading.Timer(0.45, _install_edge_to_edge_hook).start()

    def _on_resized() -> None:
        _clamp_to_work_area()

    def _on_maximized() -> None:
        api._maximized = True
        _set_maximized_flag(True)
        hwnd = _find_hwnd()
        if hwnd:
            _fill_work_area(hwnd)

    def _on_restored() -> None:
        api._maximized = False
        _set_maximized_flag(False)
        hwnd = _find_hwnd()
        if hwnd:
            _set_thick_frame(hwnd, True)
        _apply_dwm_chrome(maximized=False)

    try:
        window.events.shown += _on_shown
    except Exception:
        pass
    try:
        window.events.resized += _on_resized
    except Exception:
        pass
    try:
        window.events.maximized += _on_maximized
    except Exception:
        pass
    try:
        window.events.restored += _on_restored
    except Exception:
        pass

    threading.Thread(target=_watch_show_request, args=(api,), name="ativavid-show", daemon=True).start()

    webview.start(gui="edgechromium", debug=False, icon=str(icon) if icon.exists() else None)
    try:
        srv.shutdown()
    except Exception:
        pass
    global _TRAY_ICON
    try:
        if _TRAY_ICON is not None:
            _TRAY_ICON.stop()
    except Exception:
        pass
    _TRAY_ICON = None


if __name__ == "__main__":
    main()
