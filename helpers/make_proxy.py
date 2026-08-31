"""Gera proxy leve do cut para preview fluido."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
try:
    from app.win_process import hide_console_kwargs
except Exception:  # noqa: BLE001
    def hide_console_kwargs() -> dict:  # type: ignore[misc]
        return {}


# BELOW_NORMAL_PRIORITY_CLASS: o Windows so tira tempo deste processo
# quando ninguem mais precisa. Sem isto a copia disputa com o proprio
# player que ela existe para aliviar.
_ABAIXO_DO_NORMAL = 0x00004000


def _fundo(kwargs: dict) -> dict:
    """Mesmo `subprocess`, mas com prioridade de segundo plano no Windows."""
    if sys.platform != "win32":
        return kwargs
    k = dict(kwargs)
    k["creationflags"] = int(k.get("creationflags") or 0) | _ABAIXO_DO_NORMAL
    return k


def make_cut_proxy(
    cut: Path,
    dest: Path,
    *,
    height: int = 540,
    encoder: str = "libx264",
    com_audio: bool = False,
) -> Path | None:
    """Escreve dest (ex.: edit/cut_proxy.mp4). Retorna path ou None."""
    if not cut.exists():
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    h = max(360, min(int(height or 540), 720))
    # even dimensions
    vf = f"scale=-2:{h}"
    enc = encoder if encoder in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf") else "libx264"
    # -preset veryfast/-crf são flags de x264: nos encoders de GPU elas
    # falhavam SEMPRE e todo proxy pagava um encode perdido antes do fallback.
    quality = {
        "libx264": ["-preset", "veryfast", "-crf", "28"],
        "h264_nvenc": ["-preset", "p1", "-rc", "vbr", "-cq", "32", "-b:v", "0"],
        "h264_qsv": ["-preset", "veryfast", "-global_quality", "30"],
        "h264_amf": ["-quality", "speed", "-rc", "cqp", "-qp_i", "30", "-qp_p", "32"],
    }

    # ESCREVE NUM TEMPORARIO. Durante os ~10s de geracao existiria um
    # `cut_proxy.mp4` com data NOVA e conteudo pela metade — e a guarda que
    # decide se o proxy serve compara DATAS, entao ela serviria justamente
    # esse arquivo. Renomear no fim e o que torna a troca instantanea.
    tmp = dest.with_name(dest.name + ".tmp.mp4")

    def _cmd(e: str) -> list[str]:
        return [
            # A copia e CONFORTO e roda enquanto ele assiste o video: com
            # as threads soltas o ffmpeg toma a maquina inteira e a propria
            # copia que deveria destravar o player o travava por 10-30 s.
            # Duas threads levam mais tempo e nao disputam com a
            # reproducao.
            ffmpeg, "-y", "-threads", "2", "-i", str(cut),
            "-vf", vf,
            "-c:v", e, *quality[e],
            # A copia da Fase 1 e MUDA de proposito (a linha do tempo tem a
            # onda). A do FINAL nao pode ser: ele abre a aba Visual para
            # conferir o video pronto — trilha, efeito e voz.
            *(["-c:a", "aac", "-b:a", "96k"] if com_audio else ["-an"]),
            "-movflags", "+faststart",
            str(tmp),
        ]

    hide = _fundo(hide_console_kwargs())
    try:
        r = subprocess.run(_cmd(enc), capture_output=True, text=True, timeout=180, **hide)
        if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
            if enc != "libx264":
                r = subprocess.run(
                    _cmd("libx264"), capture_output=True, text=True, timeout=180, **hide)
            if r.returncode != 0 or not tmp.exists():
                tmp.unlink(missing_ok=True)
                return None
        os.replace(tmp, dest)
        return dest
    except (OSError, subprocess.TimeoutExpired):
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _perfil() -> dict:
    """Perfil de desempenho do app (encoder de GPU quando ele tem um).

    O proxy do corte ja escolhe assim, pela rota `/api/proxy/rebuild`; o
    do final entra pelo servidor do editor, que nao passa por la.
    """
    try:
        from app.performance import profile_settings
        from app.settings_store import load_settings

        return profile_settings(load_settings().get("performanceProfile")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _encoder_do_perfil() -> str:
    return str(_perfil().get("encoder")
               or os.environ.get("ATIVAVID_ENCODER") or "libx264")


def _altura_do_perfil() -> int:
    try:
        return int(_perfil().get("proxyHeight")
                   or os.environ.get("ATIVAVID_PROXY_HEIGHT") or 540)
    except (TypeError, ValueError):
        return 540


def refazer_em_fundo(cut: Path, edit_dir: Path) -> threading.Thread | None:
    """Refaz `edit/cut_proxy.mp4` depois que o corte mudou. Nao espera.

    O proxy nascia so no fim do pipeline. O APPLY tambem refaz o
    `cut.mp4` e nao refazia a copia: medido nos projetos do usuario, **46
    de 186** ficaram com a copia atrasada, uma delas por 3,7 dias — a
    partir do primeiro apply o projeto perdia o video leve para sempre.

    Em segundo plano porque o usuario esta esperando o apply (mediana de
    107s) e a copia leva 3 a 12s. Ela so serve na PROXIMA vez que ele
    abrir o editor.
    """
    if os.environ.get("ATIVAVID_PROXY", "1") in ("0", "false", "False"):
        return None

    def _trabalho() -> None:
        try:
            make_cut_proxy(
                cut, Path(edit_dir) / "cut_proxy.mp4",
                height=int(os.environ.get("ATIVAVID_PROXY_HEIGHT") or 540),
                encoder=os.environ.get("ATIVAVID_ENCODER") or "libx264",
            )
        except Exception:  # noqa: BLE001 — copia e conforto, nunca o produto
            pass

    t = threading.Thread(target=_trabalho, daemon=True, name="proxy-do-apply")
    t.start()
    return t


def proxy_do_final(final: Path, edit_dir: Path) -> threading.Thread | None:
    """Copia leve do VIDEO PRONTO, para a aba Visual. Nao espera.

    A Fase 1 tem copia leve desde sempre; a Visual nunca teve — ela toca o
    arquivo entregue, 1080x1920. Medido no video dele de 1:30 (159 MB,
    13,9 Mbps): decodificar em UMA thread leva 50,1 s para 90,2 s de video,
    1,8x o tempo real. A copia de 540 de altura leva 5,4 s — 16,7x o tempo
    real, e o arquivo cai para 7,2 MB.

    E o que ele descreveu: "com lag gigante no video e dando umas travadas
    ainda... se eu abrir a pasta e abrir em outro player nao trava". O
    player externo manda o decodificador do hardware; a janela do app nem
    sempre.
    """
    if os.environ.get("ATIVAVID_PROXY", "1") in ("0", "false", "False"):
        return None
    final = Path(final)
    if not final.is_file():
        return None

    def _trabalho() -> None:
        try:
            make_cut_proxy(
                final, Path(edit_dir) / "final_proxy.mp4",
                height=_altura_do_perfil(), encoder=_encoder_do_perfil(),
                com_audio=True,
            )
        except Exception:  # noqa: BLE001 — copia e conforto, nunca o produto
            pass

    t = threading.Thread(target=_trabalho, daemon=True, name="proxy-do-final")
    t.start()
    return t
