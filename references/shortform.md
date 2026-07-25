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
- **Captions:** two styles — **karaoke** (default) and **stacked** (see the
  "Caption style" section; SHOW the user the reference gallery to choose).
  Karaoke: one line ≤3 words, words rise from below, Poppins Black, lower third,
  `measureText` fit into **SAFE_WIDTH 720** (~180px each side — clears
  Instagram/TikTok's right action rail; verified on a real screenshot). Never
  rely on `nowrap` alone.
- **Inserts (upper zone):** rounded-card + shadow motif synced to spoken nouns,
  slow Ken-Burns. Pexels for concrete objects; **bespoke motion graphics** when
  a word names something animatable (timeline for "cortes", typewriter sheet
  for "roteiro" — worked examples in `src/CustomGraphics.tsx`).
- **Zones:** inserts/graphics upper third, captions lower third, face clear.
  Minimalist; accent `#33e0a3`.
- **Audio:** whoosh ~0.09 on card entrances, pop ~0.12 on shapes, music ~0.12,
  and ALWAYS a final loudnorm pass (voice+music+SFX summed will clip). The
  shared sfx pack (`public/sfx/`) also ships `click1`/`click2` (element pops) and
  `tictac` (clocks/countdowns) — trigger any at a local frame by wrapping
  `<Sfx src="click2.mp3" volume={0.7}/>` in a `<Sequence from={frame} layout="none">`.

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
   - **Caption style** — show the user `assets/shortform/caption-styles/stacked.png`
     and ask: **karaoke** (default) or **stacked**. For stacked, ALSO run
     `caption_style.py --transcript transcripts/cut.json -o public/caption-cues.json`
     and set `captions.style:"stacked"` (see the "Caption style" section).
   - `face_track.py cut.mp4 -o public/track.json`
   - `public/segments.json` — cumulative cut boundaries **measured from the
     encoded segments' frame counts, never summed from the EDL's seconds**.
     ffmpeg quantises each segment to whole frames, so EDL arithmetic drifts a
     fraction of a frame per cut and the error ACCUMULATES (~5 frames by 40s on a
     28-cut video). Anything that must land on a cut then sits visibly early.
     ```bash
     python - <<'EOF'
     import subprocess, glob, json
     cum, t = [0], 0
     for f in sorted(glob.glob("clips_graded/seg_*.mp4")):
         n = int(subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
             "-count_frames","-show_entries","stream=nb_read_frames",
             "-of","default=nw=1:nk=1",f], capture_output=True, text=True).stdout)
         t += n; cum.append(t)
     fps = 30  # match cut.mp4
     json.dump({"segments": [{"start": round(cum[i]/fps,4),
                              "dur": round((cum[i+1]-cum[i])/fps,4)}
                             for i in range(len(cum)-1)]},
               open("remotion/public/segments.json","w"), indent=2)
     EOF
     ```
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

## Caption style — karaoke (default) or STACKED

Short-form ships two caption styles. Let the user pick by **showing** the
reference image `assets/shortform/caption-styles/stacked.png` (a montage over
real footage) alongside the plain karaoke default, then set `captions.style`.

- **`"karaoke"`** (default): one line ≤3 words, Poppins Black, lower third.
- **`"stacked"`**: words stacked tight, mixing per line — Poppins bold-italic
  (white→gray gradient) / Poppins regular (smaller) / Playfair serif bold-italic
  in ORANGE `#ff5200` / Poppins bold. Emphasis words appear solo; key ones get a
  hand-drawn green pencil ellipse. **Baked SFX** (no extra step, no Premiere): a
  **click** on every solo word, a **scratch** when a word is circled.

For stacked, the ONE extra data step is the director (reads the same cut
transcript as `captions_for_remotion.py`):
```bash
python helpers/caption_style.py --transcript <edit>/transcripts/cut.json \
    -o remotion/public/caption-cues.json
```
Then set `captions.style:"stacked"` in edit-data.json (keep the other caption
fields — they stay valid). Defaults match the user-approved look: the stack sits
~15.6% of the height below center and SFX play from `public/sfx/caption-click.mp3`
+ `caption-scratch.mp3` (both already in the template). Optional overrides inside
`captions`: `stackedOffsetY` (0–1 of height), `fontScale`, and
`sfx:{enabled,clickVolume(0.45),scratchVolume(0.16)}`. The director groups words
into short cues, gives the orange serif accent to the content word (never a
connective), keeps 1-letter/short connectors from standing alone, and flags
solo/circled words. It is language-tuned for pt-BR (`--lang`); for other
languages it falls back to length heuristics.

A solo word also needs DURATION, not just weight — a word spoken in under
`MIN_SOLO_MS` (340ms) renders as a one-frame flash and reads as a glitch, so the
director folds it into a neighbouring stack instead. Fast connective speech hits
this often. After generating cues, sanity-check the plan (it prints a summary):
every non-`STACK_MIXED` cue should span ≥0.34s, and the word list across all
cues must match the transcript exactly, in order.

## Visual hook — static headline, first ~4s (always on)

The first 1–2 seconds decide the swipe. Write `hook.lines` like a
social-media/copywriting/virality specialist, not a summarizer: read the cut
transcript, find the core promise/tension, and craft a scroll-stopper. Levers:
**curiosity gap · high stakes/bold claim · specificity/number · urgency ·
pattern interrupt**. Match the video's language; never clickbait it can't pay off.

**Two locked styles via `hook.style`** (both user-approved, encoded in the
template):
- **`"card"`** (default): Poppins Black white UPPERCASE on a dark-gray `#232326`
  rounded card, **every line the same font size (~54)** — never a big hero line +
  smaller kicker. Optional row above the card: real brand logo (rounded card,
  w300) + transparent symbol (drop-shadow, w128) — prefer real assets in
  `public/brand/` over drawn SVG; pick a symbol that frames the angle (danger,
  money, trophy…).
- **`"outline"`**: white text + thick black stroke (`WebkitTextStroke` +
  `paintOrder:'stroke fill'`), **no card**, **sentence-case** (write `lines[]`
  normally, not caps), sits lower (`paddingTop` ~330 — may overlap the top of the
  head, which is fine). The TikTok/MrBeast headline look. Tune `fontSizePx` (68),
  `strokePx` (12), `paddingTop` (330), `lineHeight` (1.06). Drop logo/sign.

Both are static hold, fade+rise at the edges, soft whoosh.

Example (Claude Fable video): "A IA MAIS / PERIGOSA DO MUNDO / ACABOU DE SER
LIBERADA". Draft 2–3 copy candidates in chat (text — no renders), let the user
pick, then render ONE still for design approval before the full render.

**De-conflict:** the hook owns the upper zone for its window — push any insert
that wants the same zone to after `hook.endSec` (e.g. move a 2.5s cutaway to
~4.1s).

## Style: "tela dividida" (split screen)

Image on top, talking head below, seam at the subject's hairline. Data lives in
`edit-data.json` `splitInserts[]`; the component is already in the template's
`CustomGraphics.tsx`. Hard cut (no fade), every window snapped to a take cut,
consecutive images contiguous, and `captions.windows` parks the caption on the
seam while it is up. Full rules in `assets/shortform/README.md`.

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

**Take the PICTURE from Remotion and the AUDIO from `cut.mp4`.** Remotion's own
audio track drifts against the source — measured on a 95s edit: the voice is
+90ms late by 8s and +660ms by 78s, i.e. it slides progressively out of lip sync,
unnoticeable at the start and obvious by the end. Its audio track also comes out
~0.7s longer than its video. So never re-encode Remotion's audio; re-mux the
approved master instead and mix the soundtrack here:

```bash
VD=$(ffprobe -v error -select_streams v:0 -show_entries stream=duration -of default=nw=1:nk=1 out/render.mp4)
FADE=$(python3 -c "print(f'{$VD-1.5:.3f}')")
ffmpeg -y -i out/render.mp4 -i ../cut.mp4 -i public/trilha.mp3 \
  -filter_complex "[1:a]adelay=33:all=1[v];\
                   [2:a]volume=0.10,afade=t=in:st=0:d=0.4,afade=t=out:st=$FADE:d=1.5[m];\
                   [v][m]amix=inputs=2:duration=first:normalize=0[mix];\
                   [mix]loudnorm=I=-14:TP=-1:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -ar 48000 -t "$VD" \
  -movflags +faststart ../final.mp4
```

`adelay=33` is one frame at 30fps: OffthreadVideo draws the source frame one
composition frame late (the same VIDEO_LAG the overlays compensate for), so the
picture sits a frame behind cut.mp4's timeline and the voice must follow it.
`-t "$VD"` keeps the audio from outliving the video. **Verify** by correlating the
delivered voice against `cut.mp4` at three points — the offset must be CONSTANT
(≈+33ms). Use 15s windows: short windows lock onto the wrong syllable and report
a drift that is not there. Drop this re-mux ONLY if Phase 2 baked SFX into the
audio (stacked captions' click/scratch), and then verify sync by hand.

If the video has no soundtrack, the same shape without input 2:

```bash
ffmpeg -y -i out/render.mp4 -i ../cut.mp4 -filter_complex "[1:a]adelay=33:all=1,loudnorm=I=-14:TP=-1:LRA=11[out]" \
  -map 0:v -map "[out]" -c:v copy -c:a aac -b:a 192k -ar 48000 -t "$VD" -movflags +faststart ../final.mp4
```

Verify `max_volume ≤ -1 dB` (`-af volumedetect`). Copy to `edit/final.mp4`.
