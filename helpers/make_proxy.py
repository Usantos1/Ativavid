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


def make_cut_proxy(
    cut: Path,
    dest: Path,
    *,
    height: int = 540,
    encoder: str = "libx264",
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
            ffmpeg, "-y", "-i", str(cut),
            "-vf", vf,
            "-c:v", e, *quality[e],
            "-an",
            "-movflags", "+faststart",
            str(tmp),
        ]

    hide = hide_console_kwargs()
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
