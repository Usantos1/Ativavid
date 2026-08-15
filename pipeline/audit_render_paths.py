"""Audita jobs existentes com o classificador — não renderiza."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.render_path import analyze_zoom, classify_render_path


def _roots() -> list[Path]:
    out: list[Path] = []
    for p in (
        Path(r"E:\ATIVAVID\Projetos"),
        Path.home() / "ATIVAVID" / "Projetos",
    ):
        if p.is_dir() and p not in out:
            out.append(p)
    try:
        from app.settings_store import load_settings

        extra = load_settings().get("projectsRoot")
        if extra:
            ep = Path(str(extra)).expanduser()
            if ep.is_dir() and ep not in out:
                out.append(ep)
    except Exception:
        pass
    return out


def main() -> int:
    rows: list[dict] = []
    for root in _roots():
        try:
            kids = list(root.iterdir())
        except OSError:
            continue
        for proj in kids:
            edp = proj / "edit" / "remotion" / "public" / "edit-data.json"
            if not edp.exists():
                continue
            try:
                ed = json.loads(edp.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            public = edp.parent
            cls = classify_render_path(ed, public=public)
            zoom = analyze_zoom(ed)
            rows.append({
                "project": proj.name,
                "path": cls["path"],
                "reasons": cls["reasons"],
                "fullReasons": cls["fullReasons"],
                "onlySimpleZoomCuts": cls.get("onlySimpleZoomCuts"),
                "onlyZoomFamily": cls.get("onlyZoomFamily"),
                "ffmpegClass": zoom.get("ffmpegClass"),
            })

    paths = Counter(r["path"] for r in rows)
    full_reasons = Counter()
    for r in rows:
        if r["path"] != "FULL":
            continue
        for reason in r["fullReasons"] or []:
            full_reasons[reason] += 1
    n = len(rows) or 1
    n_full = paths.get("FULL", 0)
    only_cuts = sum(1 for r in rows if r.get("onlySimpleZoomCuts"))
    only_zoom_fam = sum(1 for r in rows if r.get("onlyZoomFamily"))
    ffmpeg_safe = sum(
        1 for r in rows
        if r["path"] == "FULL" and r.get("ffmpegClass") == "FFMPEG_SAFE"
    )
    ffmpeg_approx = sum(
        1 for r in rows
        if r["path"] == "FULL" and r.get("ffmpegClass") == "FFMPEG_APPROXIMATE"
        and r.get("onlyZoomFamily")
    )

    report = {
        "jobsAnalyzed": len(rows),
        "distribution": {
            "FAST": paths.get("FAST", 0),
            "OVERLAY": paths.get("OVERLAY", 0),
            "FULL": n_full,
        },
        "pct": {
            "FAST": round(100.0 * paths.get("FAST", 0) / n, 1),
            "OVERLAY": round(100.0 * paths.get("OVERLAY", 0) / n, 1),
            "FULL": round(100.0 * n_full / n, 1),
        },
        "fullReasonsCounts": dict(full_reasons),
        "fullOnlySimpleZoomCuts": only_cuts,
        "fullOnlySimpleZoomCutsPctOfFull": round(100.0 * only_cuts / n_full, 1) if n_full else 0,
        "fullOnlyZoomFamily": only_zoom_fam,
        "fullOnlyZoomFamilyPctOfFull": round(100.0 * only_zoom_fam / n_full, 1) if n_full else 0,
        "wouldMoveToOverlayIfZoomCutsFfmpeg": only_cuts,
        "wouldMoveToOverlayIfZoomFamilyFfmpeg": only_zoom_fam,
        "ffmpegSafeCount": ffmpeg_safe,
        "ffmpegApproximateZoomFamily": ffmpeg_approx,
        "jobs": rows,
    }
    out = Path(r"E:\Temp\ativavid_overlay_proto") / "job_path_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "jobs"}, indent=2, ensure_ascii=False))
    print(f"wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
