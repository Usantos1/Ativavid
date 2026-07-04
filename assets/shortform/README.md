# Short-form template (Reels / TikTok / Shorts) — DATA-DRIVEN

The proven Phase-2 Remotion composition for vertical short-form. **The code is
immutable** — everything per-video is data. Do NOT read or edit `src/Main.tsx`;
write `public/edit-data.json` instead. The only editable code file is
`src/CustomGraphics.tsx` (bespoke motion graphics, worked examples inside).

## Scaffold (one command)

```bash
cp -R <skill>/assets/shortform/. <edit>/remotion/ && cd <edit>/remotion && npm install
```

Then copy `cut.mp4` into `public/` and generate the data files below.

## Data pipeline (per video, all into `remotion/public/`)

1. `transcribe.py cut.mp4 --edit-dir <edit>` → `transcripts/cut.json`
   (times already on the output timeline — do NOT map the source EDL).
2. `captions_for_remotion.py --transcript transcripts/cut.json -o public/captions.json`
3. `face_track.py cut.mp4 -o public/track.json`
4. `public/segments.json` — output-timeline cut boundaries from the EDL:
   `{"segments":[{"start":0,"dur":3.2}, …]}` cumulative per range.
5. `pexels_search.py "<query>" --out-dir public/pexels …` for insert images.
6. **Write `public/edit-data.json`** — the whole edit in one file (schema below).

## edit-data.json schema (all times in seconds on the cut timeline)

```jsonc
{
  "width": 1080, "height": 1920, "fps": 24,
  "durationSec": 87.5,              // EXACT cut.mp4 duration (ffprobe)
  "camera": {                        // hard zoom on cuts + push-in + eye track
    "enabled": true,
    "zooms": [1.14, 1.2, 1.12, 1.22, 1.16, 1.1, 1.18],  // per cut segment, cycles
    "pushIn": 0.04, "targetX": 0.5, "targetY": 0.4
  },
  "hook": {                          // static headline, first ~4s (always on)
    "enabled": true, "endSec": 4.0,
    "lines": ["A IA MAIS", "PERIGOSA DO MUNDO", "ACABOU DE SER LIBERADA"],
    "logo": "brand/logo.webp",       // public/ path or null
    "sign": "brand/warning.webp"     // transparent symbol or null
  },
  "captions": {                      // karaoke, ≤3 words, Poppins Black
    "enabled": true, "fontSize": 76, "maxWords": 3,
    "safeWidth": 720,                // clears the platform action rail — keep 720
    "paddingBottom": 420
  },
  "inserts": [                       // rounded-card images, upper zone
    {"src": "pexels/ai.jpg", "start": 1.95, "end": 3.35}
  ],
  "behind": [                        // behind-the-subject (person_matte.py first)
    {"kind": "image", "src": "ill/x.jpg", "matte": "fg_x.mov", "start": 4.15, "dur": 1.65},
    {"kind": "words", "matte": "fg_w.mov", "start": 19.55, "dur": 1.5,
     "words": [{"t": "MAS", "at": 19.55}, {"t": "POR", "at": 19.9}, {"t": "QUE", "at": 20.26}]}
  ],
  "soundtrack": {"enabled": false, "file": "trilha.mp3", "volume": 0.12}
  // Phase 3 flips soundtrack.enabled to true once trilha.mp3 exists
}
```

## The style (locked defaults encoded in src/)

- **1080×1920 @ 24**; base `<OffthreadVideo src=cut.mp4>` with the dynamic
  camera (hard zoom per segment + slow push-in + clamped eye-tracking).
- **Karaoke captions**: one line ≤3 words, words rise in from below, Poppins
  Black, lower third, `measureText` fit into `safeWidth` 720 (action-rail safe).
- **Hook**: static uniform-size headline on a dark-gray rounded card, optional
  logo+symbol row. Copy written like a virality specialist; approve a still first.
- **Inserts**: rounded card + shadow, upper zone, slow Ken-Burns, whoosh on entry.
- **Behind-the-subject**: elements top-anchored; matte gets the same camera via
  `frameOffset`; ProRes 4444 + `<OffthreadVideo transparent>`.
- **Audio**: whoosh ~0.09 / pop ~0.12 / music ~0.12, and ALWAYS a final loudnorm
  pass on the render (voice+music+SFX clip otherwise).

## Render

`npx remotion render Reels out/render.mp4`, loudnorm → `edit/final.mp4`.
Verify stills at cut boundaries (no black edges) before the full render.
`generate_sfx.py` regenerates the sfx pack if ever needed.
