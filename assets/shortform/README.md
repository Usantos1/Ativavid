# Short-form editing style (Reels / TikTok / Shorts) — reference build

This is the proven Phase-2 Remotion composition for vertical short-form videos.
Copy these files into `edit/remotion/` and adapt the data (captions, track,
segments, insert timings) per video. `Main.tsx` is the whole style in code.

## The style (defaults)

- **Format:** 1080×1920, 24fps, base is `<OffthreadVideo src=cut.mp4>` (the
  approved Phase-1 graded cut).
- **Karaoke captions** — one line, **≤3 words**, each word **rises in from
  below** (opacity + translateY, `Easing.out(cubic)`). **Poppins Black**, white,
  subtle shadow, lower third (`paddingBottom ~420`). Every line is measured with
  `measureText` and scaled to a **safe width (~880px)** so it never touches the
  edge. Lines hold until the next line starts (no flicker).
- **Illustrative images** — a **consistent rounded card** (radius 28) with a
  **subtle shadow** in the **upper zone** (`marginTop ~90`, fixed
  `objectFit:cover` size so mixed aspect ratios stay uniform). Synced to spoken
  nouns; each card does a slow **Ken-Burns zoom** (grows ~8% while on screen).
  Pull them from Pexels (`helpers/pexels_search.py`).
- **Custom motion graphics, not just photos** — when a word names something
  animatable, build a bespoke animation instead of a stock image. Reference
  components here: `TimelineGraphic` (an editing timeline being cut + caption
  chips + animation shapes, for "cortes/legendas/animações") and `ScriptGraphic`
  (a paper with typewriter text, for "roteiro"). Same upper-zone card motif.
- **Dynamic camera** (on the base video only) — three layers that compose:
  1. **Hard zoom on cuts:** each cut segment gets a different base scale
     (`ZOOMS`, ~1.10–1.22) so size pops at every jump cut. Needs
     `public/segments.json` (output-timeline cut boundaries).
  2. **Slow push-in:** scale grows ~+0.04 within each segment.
  3. **Eye tracking:** `public/track.json` (from `helpers/face_track.py`) holds
     a smoothed per-frame eye point; translate so it maps to the upper third
     (`TARGET_Y≈0.4`), **clamped so no black edge ever shows** (total scale must
     exceed the pan).
- **Layout zones:** inserts/graphics in the **upper third**, captions in the
  **lower third**, face stays clear in the middle.
- **Aesthetic:** minimalist. Accent green `#33e0a3`. Keep it clean.

## Data pipeline (per video, all in `edit/`)

1. `transcribe.py cut.mp4 --edit-dir <edit>` → `transcripts/cut.json`
   (times already on the output timeline — do NOT map the source EDL).
2. `captions_for_remotion.py --transcript transcripts/cut.json -o remotion/public/captions.json`
3. `face_track.py cut.mp4 -o remotion/public/track.json`
4. segments.json — output-timeline cut boundaries from the EDL:
   `[{start,dur}...]` per range, cumulative. (tiny script; see the skill.)
5. `pexels_search.py "<query>" --out-dir remotion/public/pexels ...` for images.
6. Copy `cut.mp4` into `remotion/public/`.

## Deps

`remotion`, `@remotion/cli`, `@remotion/google-fonts` (Poppins),
`@remotion/layout-utils` (measureText). See `package.json`. Node 18+.
`create-video`'s `--no-tailwind` flag may be ignored by the prompt — scaffold
manually (this `package.json` + `tsconfig.json` + `src/`) to stay
non-interactive.

## Render

`npx remotion render Reels out/final.mp4`, then copy to `edit/final.mp4`.
Verify stills at cut boundaries (no black edges) before the full render.
