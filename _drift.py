"""Measure audio drift between cut.mp4 and the Remotion render.

Stacked captions inject a click/scratch on nearly every word and the flash adds
its own transient, so the render's audio is NOT the cut's audio. Before choosing
the delivery path we need to know whether the offset is CONSTANT (safe to keep
the Remotion audio, SFX and all) or GROWING (a resample drift — fall back to
re-muxing cut.mp4's audio).

Envelope cross-correlation on 10ms RMS frames, measured in independent windows.
"""
import subprocess, sys, numpy as np

HOP = 0.01  # 10 ms


def env(path, start, dur, sr=8000):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", str(start), "-i", path, "-t", str(dur),
         "-map", "0:a:0", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
        capture_output=True).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = int(sr * HOP)
    x = x[: len(x) // n * n].reshape(-1, n)
    e = np.sqrt((x.astype(np.float64) ** 2).mean(axis=1) + 1e-12)
    return e - e.mean()


def lag_ms(a, b, max_ms=500):
    m = int(max_ms / 1000 / HOP)
    n = min(len(a), len(b))
    a, b = a[:n], b[:n]
    best, bl = -2.0, 0
    for k in range(-m, m + 1):
        if k >= 0:
            u, v = a[k:], b[: n - k]
        else:
            u, v = a[: n + k], b[-k:]
        if len(u) < 100:
            continue
        d = np.linalg.norm(u) * np.linalg.norm(v)
        if d == 0:
            continue
        r = float(np.dot(u, v) / d)
        if r > best:
            best, bl = r, k
    return bl * HOP * 1000, best


cut, ren = sys.argv[1], sys.argv[2]
total = float(subprocess.run(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=nw=1:nk=1", cut], capture_output=True, text=True).stdout)

win = min(15.0, total / 3.2)
spots = [("inicio", 0.2), ("meio", total / 2 - win / 2), ("fim", total - win - 0.2)]
res = []
for name, t in spots:
    t = max(0.0, t)
    ms, r = lag_ms(env(cut, t, win), env(ren, t, win))
    res.append(ms)
    print(f"{name:7s} @ {t:6.2f}s  ({win:.1f}s)  lag = {ms:+7.1f} ms   r = {r:.3f}")

spread = max(res) - min(res)
print(f"\nspread = {spread:.1f} ms over {total:.1f}s")
print("CONSTANT" if spread <= 20 else "GROWING")
