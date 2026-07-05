# SHORT-FORM track (Reels / TikTok / Shorts) — Phase 2 + 3 reference

Read this file when the video is vertical short-form and the Phase-1 cut is
approved. Everything here rides on the **data-driven template** at
`assets/shortform/` — the code is immutable; a video is described by ONE JSON.

## The style (the proven default)

- **Frame rate:** render at **30fps when the source is 30fps or higher** (natural
  motion, matches Instagram/TikTok/Shorts capture); only slower sources use 24.
  `render.py` picks this automatically for `cut.mp4` — then set `edit-data.json`
  `fps` to the SAME value as `cut.mp4` (ffprobe it) so the Remotion render matches.
- **Base:** 1080×1920 (fps per the rule above), `<OffthreadVideo src=cut.mp4>` with the **dynamic
  camera**: hard zoom per cut segment (~1.10–1.22, cycles), slow push-in
  (+0.04/segment), clamped eye-tracking (target upper third, never reveals an
  edge). Always on — it's what makes a talking head feel edited.
- **Visual hook (first ~4s):** static copywriting headline (see below). Always on.
- **Captions:** karaoke, one line ≤3 words, words rise from below, Poppins
  Black, lower third, `measureText` fit into **SAFE_WIDTH 720** (~180px each
  side — clears Instagram/TikTok's right action rail; verified on a real
  screenshot). Never rely on `nowrap` alone.
- **Inserts (upper zone):** rounded-card + shadow motif synced to spoken nouns,
  slow Ken-Burns. Pexels for concrete objects; **bespoke motion graphics** when
  a word names something animatable (timeline for "cortes", typewriter sheet
  for "roteiro" — worked examples in `src/CustomGraphics.tsx`).
- **Zones:** inserts/graphics upper third, captions lower third, face clear.
  Minimalist; accent `#33e0a3`.
- **Audio:** whoosh ~0.09 on card entrances, pop ~0.12 on shapes, music ~0.12,
  and ALWAYS a final loudnorm pass (voice+music+SFX summed will clip).

## Workflow

1. **Scaffold (one command, never read the TSX):**
   ```bash
   cp -R <skill>/assets/shortform/. <edit>/remotion/ && cd <edit>/remotion && npm install
   ```
2. **Generate machine data into `remotion/public/`:**
   - `cp cut.mp4 remotion/public/`
   - `transcribe.py cut.mp4 --edit-dir <edit>` → `transcripts/cut.json`
     (cut times are already on the output timeline — never map the source EDL)
   - `captions_for_remotion.py --transcript transcripts/cut.json -o public/captions.json`
   - `face_track.py cut.mp4 -o public/track.json`
   - `public/segments.json` from the EDL: `{"segments":[{"start":0,"dur":3.2},…]}`
     (cumulative output-timeline boundaries)
   - `pexels_search.py "<query>" --out-dir public/pexels --count 3 --orientation portrait`
3. **Write `public/edit-data.json`** — the whole edit in one file (schema in
   `assets/shortform/README.md`): durationSec (exact ffprobe of cut.mp4),
   camera zooms, hook lines/logo/sign, captions config, inserts[], behind[],
   soundtrack (leave `enabled:false` until Phase 3).
4. **Verify with stills, batched:** `npx remotion still Reels --frame=<n> f.png`
   for the hook still (user approval), then ONE contact sheet for spot checks:
   `contact_sheet.py <render> --times t1 t2 t3 -o sheet.png` — one image, not N.
5. **Render:** `npx remotion render Reels out/render.mp4`, then loudnorm →
   `edit/final.mp4` (see Phase 3).

Never edit `src/Main.tsx`. Bespoke graphics go in `src/CustomGraphics.tsx`
(the ONE editable file — read it only when the video needs a custom graphic).

## Visual hook — static headline, first ~4s (always on)

The first 1–2 seconds decide the swipe. Write `hook.lines` like a
social-media/copywriting/virality specialist, not a summarizer: read the cut
transcript, find the core promise/tension, and craft a scroll-stopper. Levers:
**curiosity gap · high stakes/bold claim · specificity/number · urgency ·
pattern interrupt**. Match the video's language; never clickbait it can't pay off.

**Design is locked** (user-approved standard, encoded in the template): Poppins
Black white UPPERCASE on a dark-gray `#232326` rounded card, **every line the
same font size (~54)** — never a big hero line + smaller kicker. Static hold,
fade+rise at the edges, soft whoosh. Optional row above the card: real brand
logo (rounded card, w300) + transparent symbol (drop-shadow, w128) — prefer
real assets in `public/brand/` over drawn SVG; pick a symbol that frames the
angle (danger, money, trophy…).

Example (Claude Fable video): "A IA MAIS / PERIGOSA DO MUNDO / ACABOU DE SER
LIBERADA". Draft 2–3 copy candidates in chat (text — no renders), let the user
pick, then render ONE still for design approval before the full render.

**De-conflict:** the hook owns the upper zone for its window — push any insert
that wants the same zone to after `hook.endSec` (e.g. move a 2.5s cutaway to
~4.1s).

## Behind-the-subject (element between person and background)

Puts an image or giant word(s) BEHIND the person. Great on medium/wide shots;
on tight close-ups anchor elements to the TOP (template already does). Needs
the matting extra: `uv sync --extra matting` (torch).

```bash
python helpers/person_matte.py cut.mp4 -o remotion/public/fg_<name>.mov --start <s> --duration <d>
```

Then describe each window in `edit-data.json` `behind[]` (kind image/words,
matte file, start, dur, words with per-word `at` times). Gotchas the template
already encodes — do not re-learn them:
- ProRes 4444 `.mov` (libvpx silently drops alpha on some builds)
- source RGB composited with alpha, not RVM's `fgr` (halo otherwise)
- `<OffthreadVideo transparent>` or the matte renders opaque
- matte gets the same camera via `frameOffset` or the person drifts

Matte ONLY the windows you need — each file's frame 0 = its window start.

## Illustrative images

Pexels for generic concepts (key: `PEXELS_API_KEY`). For brands/people/specific
things, **Wikimedia Commons first** (`wikimedia_images.py` — no key, clean
licensing, prints license+author), then `google_images.py` (needs
`GOOGLE_API_KEY`+`GOOGLE_CSE_ID`, mind rights — pass `--rights cc`, flag
licensing to the user for logos/celebrities). Keep photographer credits.

## Phase 3 — soundtrack (short-form)

Ask: **AI-generated** (Treblo) or **local file** (copy to `public/trilha.mp3`).

**Writing the Treblo prompt — derive it from the video's context, and ask for
MUSIC, not a texture.** Read the cut transcript: what's the topic, energy and
emotional arc? Then describe a real **composed instrumental piece** — name a
**genre + key instruments + tempo/BPM + mood**, and (optionally) a reference
artist/style. Match the content: a hype tech/AI reel wants upbeat modern
electronic with a catchy synth melody; a calm tutorial wants warm lo-fi keys; a
luxury/story piece wants cinematic strings. **Avoid SFX-y phrasing** ("bed",
bare "beat", "sound design", "drones", "risers") — that's what makes Treblo
return sound effects instead of a song. `treblo_music.py` auto-frames the vibe
as a composed instrumental and bans SFX/vocals, but the vibe you pass still has
to read musical.
```bash
python helpers/treblo_music.py "upbeat modern electronic, catchy synth melody, warm analog bass, crisp light drums, ~110 BPM, bright and motivational" -o public/trilha.mp3 --length-min 30 --length-max 60
```
Then flip `soundtrack.enabled: true` in edit-data.json. **Volume:** start ~0.25
and check it's clearly audible under wall-to-wall narration (a bed at 0.12 is
usually inaudible once the mix is loudnorm'd to the voice — confirm by listening,
not just by the meter). Re-render. Finish with the mandatory loudnorm:

```bash
ffmpeg -y -i out/render.mp4 -c:v copy -af "loudnorm=I=-14:TP=-1:LRA=11" -c:a aac -b:a 192k -ar 48000 ../final.mp4
```

Verify `max_volume ≤ -1 dB` (`-af volumedetect`). Copy to `edit/final.mp4`.
