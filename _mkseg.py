"""Build remotion/public/segments.json from the ENCODED segment frame counts.

Run from an <edit> dir. Never sums EDL seconds: ffmpeg quantises each segment to
whole frames, so EDL arithmetic drifts and the error accumulates across the cut.
"""
import subprocess, glob, json, pathlib, sys


def frames(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True).stdout.strip()
    return int(out)


segs = sorted(glob.glob("clips_graded/seg_*_v.mp4")) or sorted(glob.glob("clips_graded/seg_*.mp4"))
nranges = len(json.loads(pathlib.Path("edl.json").read_text())["ranges"])
if len(segs) != nranges:
    sys.exit(f"{len(segs)} segments for {nranges} ranges — clips_graded is dirty")

fps = int(round(eval(subprocess.run(
    ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
     "stream=r_frame_rate", "-of", "default=nw=1:nk=1", "cut.mp4"],
    capture_output=True, text=True).stdout.strip())))

cum, t = [0], 0
for f in segs:
    t += frames(f)
    cum.append(t)

real = frames("cut.mp4")
if t != real:
    # render.py's loudnorm pass muxes with -shortest, so a sub-frame audio
    # shortfall summed over the segments lops a frame or two off the TAIL.
    # Only the last segment can absorb that; every earlier cut boundary is
    # already correct. Anything bigger than a few frames is a real desync.
    if not 0 < t - real <= 4:
        sys.exit(f"segments sum {t}f != cut.mp4 {real}f — do not ship this file")
    print(f"note: tail trimmed {t - real}f by loudnorm -shortest; last segment clamped")
    cum[-1] = real
    t = real

data = {"segments": [{"start": round(cum[i] / fps, 4),
                      "dur": round((cum[i + 1] - cum[i]) / fps, 4)}
                     for i in range(len(cum) - 1)]}
pathlib.Path("remotion/public/segments.json").write_text(json.dumps(data, indent=2))
print(f"segments.json — {len(segs)} segments, {t}f @ {fps}fps = {t/fps:.3f}s")
print("cuts at: " + ", ".join(f"{cum[i]/fps:.4f}" for i in range(1, len(cum) - 1)))
