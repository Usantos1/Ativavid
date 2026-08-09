"""Write a NEUTRAL remotion/public/track.json (tracking element is OFF).

The template imports track.json statically, so the bundle fails to build without
the file even when the follow is disabled. Every point is pinned to the camera
target, leaving the follow nothing to correct.
"""
import json, pathlib

ed = json.loads(pathlib.Path('remotion/public/edit-data.json').read_text(encoding='utf-8'))
n = round(ed['durationSec'] * ed['fps'])
tx, ty = ed['camera']['targetX'], ed['camera']['targetY']
pathlib.Path('remotion/public/track.json').write_text(json.dumps(
    {"fps": ed['fps'], "width": ed['width'], "height": ed['height'],
     "count": n, "points": [[tx, ty]] * n, "neutral": True}))
print(f"track.json — neutral, {n} points at ({tx}, {ty})")
