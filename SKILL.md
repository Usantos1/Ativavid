---
name: edvid
description: Edvid — edit any video by conversation, in phases. Two tracks — SHORT-FORM (vertical 9:16 for Reels/TikTok/Shorts) and LONGFORM (horizontal 16:9 for YouTube: talking-head+B-roll, tutorials/screen-record, vlogs). PHASE 1 — clean cut + color grade + optional voice EQ/mastering (transcribe, select best takes, cut on silence for short-form or retention arc + cold open for longform, grade; ask if shot in LOG; master the voice), then show the user for approval. PHASE 2 (after the cut is approved) — Remotion visuals: short-form gets karaoke captions, a static hook, a dynamic camera and behind-the-subject; longform gets B-roll cutaways, lower-thirds, chapter cards, callouts, plus YouTube chapters and .srt captions. PHASE 3 — soundtrack (AI via Treblo or a local file). Illustrative images/video via Pexels + Wikimedia/Google. Ask questions, confirm, execute, iterate, persist.
---

# Edvid

## Principle

1. **Two phases, one gate between them.** PHASE 1 is the clean cut + color grade. You show it to the user and **wait for approval**. PHASE 2 is everything on top — captions, motion graphics, illustrative images — and it only starts after the cut is approved. Never blur the two: no captions or graphics before the cut is signed off.
2. **LLM reasons from raw transcript + on-demand visuals.** The only derived artifact that earns its keep is a packed phrase-level transcript (`takes_packed.md`). Everything else — filler tagging, retake detection, shot classification — you derive at decision time.
3. **Audio is primary, visuals follow.** Cut candidates come from speech boundaries and silence gaps. Drill into visuals only at decision points.
4. **Ask → confirm → execute → iterate → persist.** Never touch the cut until the user has confirmed the strategy in plain English.
5. **Generalize.** Do not assume what kind of video this is. Look at the material, ask the user, then edit.
6. **Artistic freedom is the default.** Every specific value, preset, font, color, duration, and technique here is a *worked example*, not a mandate. The only things you MUST do are the Hard Rules below. Everything else is yours.
7. **Verify your own output before showing it to the user.** If you wouldn't ship it, don't present it.

## Hard Rules (production correctness — non-negotiable)

1. **The phase gate is real.** Do not build captions, motion graphics, or images until the user has approved the Phase 1 cut. (Principle 1.)
2. **Per-segment extract → lossless `-c copy` concat**, not a single-pass filtergraph. Otherwise you double-encode every segment.
3. **30ms audio fades at every segment boundary** (`afade=t=in:st=0:d=0.03,afade=t=out:st={dur-0.03}:d=0.03`). Otherwise audible pops at every cut.
4. **Never cut inside a word.** Snap every cut edge to a word boundary from the transcript.
5. **Pad every cut edge.** Working window 30–200ms. Whisper timestamps drift 50–100ms; padding absorbs it. Cut on silence gaps whenever possible.
6. **Cache transcripts per source.** Never re-transcribe unless the source file changed.
7. **Color grade per-segment during extraction**, never post-concat (which re-encodes twice).
8. **Strategy confirmation before execution.** Never touch the cut until the user has approved the plain-English plan.
9. **All session outputs in `<videos_dir>/edit/`.** Never write inside the `edvid/` project directory.
10. **PHASE 2 is Remotion-only.** Captions, motion graphics, and illustrative images are built in a Remotion project using the `remotion-best-practices` skill. edvid no longer burns subtitles or renders overlays with ffmpeg/PIL — Remotion owns all on-screen text and graphics.

## Directory layout

```
<videos_dir>/
├── <source files, untouched>
└── edit/
    ├── project.md               ← memory; appended every session
    ├── takes_packed.md          ← phrase-level transcripts, the primary reading view
    ├── edl.json                 ← cut decisions (Phase 1)
    ├── transcripts/<name>.json  ← cached Groq Whisper transcripts (word-level)
    ├── clips_graded/            ← per-segment extracts with grade + fades
    ├── cut.mp4                  ← PHASE 1 output: clean graded cut, no text (the approval artifact)
    ├── verify/                  ← debug frames / timeline PNGs
    ├── final.mp4                ← delivered render (Phase 2 + Phase 3 soundtrack, loudnorm'd)
    └── remotion/                ← Remotion project (Phase 2 + 3)
        ├── public/              ← cut.mp4, captions.json, track.json, segments.json,
        │                          pexels/ web/ images, sfx/*.mp3, trilha.mp3
        ├── src/                 ← compositions
        └── out/                 ← render.mp4 (pre-loudnorm) → final.mp4
```

## Setup

First-time install lives in `install.md`. On cold start just verify:

- `GROQ_API_KEY` resolves (env or `.env` at the edvid repo root). Transcription uses Groq Whisper (`whisper-large-v3`); it does not diarize or tag audio events, so every word carries `speaker_id: speaker_0`.
- `ffmpeg` + `ffprobe` on PATH (Phase 1 cutting + grading).
- Python deps installed (`uv sync` or `pip install -e .` inside the repo).
- **Node.js 18+ and npm** on PATH (Phase 2 Remotion). Verify with `node --version`.
- The **`remotion-best-practices` skill** is installed and discoverable (Phase 2 domain knowledge). If missing, tell the user to install it from https://github.com/remotion-dev/skills.
- `PEXELS_API_KEY` — **only if the user asks for illustrative images**. From https://www.pexels.com/api/.
- `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` — **only if the video names brands/people/specific things** that Pexels can't provide (logos, celebrities). Google Custom Search (see section 5).
- `TREBLO_API_KEY` — **only if the user picks AI-generated music** in Phase 3 (from https://sonauto.ai / Treblo).

All keys are lazy: ask for one the first time that feature is used, write it to `.env` (never to `<videos_dir>`).

Helpers live in `helpers/`, resolved relative to this SKILL.md (the skill is symlinked at `~/.claude/skills/edvid/`).

## Helpers (Phase 1)

- **`transcribe.py <video>`** — single-file Groq Whisper call (long audio auto-chunked). Cached.
- **`transcribe_batch.py <videos_dir>`** — 4-worker parallel transcription for multi-take shoots.
- **`pack_transcripts.py --edit-dir <dir>`** — `transcripts/*.json` → `takes_packed.md` (phrase-level, break on silence ≥ 0.5s).
- **`timeline_view.py <video> <start> <end>`** — filmstrip + waveform PNG. On-demand visual drill-down at decision points, not a scan tool.
- **`speech_regions.py <video>`** — true acoustic speech intervals via `silencedetect`. The source of truth for cut points — Whisper word times drift/stretch and are NOT reliable for edges (see Cut craft).
- **`render.py <edl.json> -o cut.mp4 --no-subtitles`** — per-segment extract (grade + 30ms fades) → lossless concat → optional voice master → loudnorm. This is the Phase 1 cut. Pass `--no-subtitles`; captions/overlays are Phase 2's job now. Add `--voice-master` (or `"voice_master": true` in the EDL) for spoken-word EQ + mastering (see Voice EQ + mastering).
- **`grade.py <in> -o <out>`** — ffmpeg grade chain. Presets + `--filter '<raw>'` for custom.

## Helpers (Phase 2)

- **`pexels_search.py "<query>" --out-dir <remotion/public/pexels> --count N --orientation portrait`** — searches Pexels and downloads images into the Remotion project's `public/`. Prints local paths + photographer credits (keep for attribution). Needs `PEXELS_API_KEY`.
- **`captions_for_remotion.py --transcript <transcripts/cut.json> -o remotion/public/captions.json`** — writes a word-level `@remotion/captions` `Caption[]` JSON. Prefer `--transcript` (a transcript of the final cut.mp4, times already on the output timeline); the `<edl.json>` positional arg is the stretch-prone fallback.
- **`face_track.py cut.mp4 -o remotion/public/track.json`** — OpenCV Haar pre-pass that outputs a smoothed per-frame eye-line point (normalized) for the Phase-2 face/eye-tracking camera. Needs `opencv-python-headless`.
- **`person_matte.py cut.mp4 -o remotion/public/fg_<name>.mov --start <s> --duration <d>`** — Robust Video Matting → the person over transparency (ProRes 4444 alpha), for the **behind-the-subject** effect (see 5d). Needs the `matting` extra (`uv sync --extra matting`, torch — opt-in).
- **`wikimedia_images.py "<query>" --out-dir <dir> --count N`** — freely-licensed images of people/places/brands from Wikimedia Commons. **No key**, cleaner licensing — the recommended first source for brands/people. Prints license + author.
- **`google_images.py "<query>" --out-dir <dir> --count N [--rights cc]`** — Google Custom Search fallback for logos/things Commons lacks. Needs `GOOGLE_API_KEY`+`GOOGLE_CSE_ID`. Mind the rights caveat (section 5).
- **SFX pack** — `assets/shortform/sfx/{whoosh,pop,click}.mp3` (synthesized, royalty-free; regen with `sfx/generate.py`). Copy into `remotion/public/sfx/` and play via `<Audio>` at appearances.

## Helpers (Phase 3)

- **`treblo_music.py "<vibe>" -o remotion/public/trilha.mp3 [--length-min 30 --length-max 60]`** — generates an instrumental background track via Treblo (async). Needs `TREBLO_API_KEY`. Only for the AI-music path.

---

# PHASE 1 — Clean cut + color grade

The goal: pick the best take of every beat, cut on silence, grade the image, and hand the user a clean `cut.mp4` to approve. No text, no graphics.

1. **Inventory.** `ffprobe` every source. `transcribe_batch.py` on the directory. `pack_transcripts.py` → `takes_packed.md`. Sample one or two `timeline_view`s for a first impression. Note the source dimensions/orientation and whether it's vertical, and whether it looks flat/LOG.
2. **Pre-scan for problems.** One pass over `takes_packed.md` noting verbal slips, mis-speaks, and dead-air-stretched words (Whisper stretches a word's end across silence — verify real speech with `timeline_view` waveforms before trusting a long single "phrase").
3. **Converse.** Describe what you see in plain English and ask questions *shaped by the material*: content type, target length/aspect, pacing, must-keep/must-cut moments. Do not use a fixed checklist.
4. **Ask about the color profile.** Explicitly ask: **"Was this shot in a LOG / flat picture profile (S-Log, V-Log, C-Log, HLG/flat), or a standard/Rec.709 look?"** LOG/flat footage looks washed-out and needs a heavier grade (contrast + saturation expansion, or a proper LUT if the user has a `.cube`). Standard footage needs only a light corrective grade — or none. Don't guess; the answer changes the grade substantially.
5. **Propose the cut strategy.** 4–8 sentences: shape, take choices, cut direction, grade direction, length estimate. **Wait for confirmation.**
6. **Execute the cut.** Produce `edl.json` (schema below); use the editor sub-agent brief for multi-take selection. Set cut edges from `speech_regions.py` (acoustic truth), not raw Whisper times; drill into `timeline_view` at ambiguous points. Apply the grade per-segment (iterate on a frame and confirm with the user first — see Color grade). Render with `render.py edl.json -o cut.mp4 --no-subtitles`; add `--voice-master` when the voice needs EQ/mastering (see Voice EQ + mastering).
7. **Self-eval the cut (before showing).** `timeline_view` the **rendered `cut.mp4`** at each cut boundary (±1.5s): check for visual jump, an audio spike past the 30ms fade, grade consistency, and correct duration via `ffprobe`. Sample first/last 2s and 2–3 mid-points. Cap at 3 fix→re-render loops, then flag remaining issues.
8. **Show the user `cut.mp4` and wait for approval.** This is the phase gate. Iterate on cut/grade notes until they sign off. Only then move to Phase 2.

## Color grade

Reason about the image, don't apply a preset blind: look at a frame, decide what's wrong, adjust one thing, look again. Mental model is ASC CDL: per channel `out = (in*slope + offset)**power`, then saturation. Apply **per-segment during extraction** (Hard Rule 7).

**Iterate on a frame, and show the user before committing.** Grade is subjective — never render the whole cut just to test a look. Extract one well-lit, mid-shot frame and render 2–3 candidates on it with `ffmpeg -ss <t> -i <src> -frames:v 1 -vf "<grade>"`. Compare, pick, and — when the user is tuning the look — **show them the candidate frame(s) and let them choose before you apply it to the video.** Only re-render the full cut once the grade is locked. When the user asks for a relative tweak ("+1 exposure", "more saturation"), nudge the specific term (brightness/`eq` saturation/contrast), re-render that one frame, and show it again.

**Build the grade from spaceless filters** so it survives the EDL `grade` string: `eq=contrast=…:saturation=…:brightness=…:gamma=…`, `colorbalance=rm=…:gm=…:bm=…` (skin warmth/tint), `colorlevels=rimin=…:gimin=…:bimin=…` (deep blacks). Avoid `curves='0/0 …'` in the EDL — the spaces break filtergraph parsing when passed as one term; use `colorlevels`/`colorbalance` instead.

- **Standard / Rec.709 footage** — light corrective only: gentle contrast + slight saturation, protect skin. Often `none` is right.
- **LOG / flat footage (the user said yes in step 4)** — needs real work. Expand contrast and saturation to bring the image back: e.g. `eq=contrast=1.15:saturation=1.25:gamma=1.05` as a *starting point*, then check skin on a real frame and back off. If the user provides a LUT, apply it with `lut3d='/path/to.cube'` as the first grade term.
- **Skin is the guardrail.** Push contrast/saturation for punch, but eyeball a mid-shot face at each step — the moment skin goes orange, magenta, or clipped, back off. For rosy/warm skin use `colorbalance` red-in-mids; for natural skin keep it near-neutral. Never ship a grade (especially LOG) without looking at skin on a real frame.
- **Match a reference if given.** If the user sends a reference still, read its contrast, saturation, black depth, and skin tone, and tune toward it on a frame — then confirm.

## Voice EQ + mastering (optional Phase-1 audio polish)

Cleans and masters a single spoken voice so the talking head sounds broadcast-ready, not like raw camera audio. Opt-in — enable with `render.py … --voice-master` or `"voice_master": true` in the EDL. Runs **after** compositing and **before** loudnorm, so loudnorm measures the already-mastered signal and still lands the render at the social target.

The chain (`VOICE_MASTER_CHAIN` in `render.py`, all ffmpeg, applied in order):

1. `highpass=f=80` — kill rumble / HVAC / handling / plosive thump
2. `equalizer=f=200:t=q:w=1.1:g=-2.5` — cut boxiness / mud (voice stops sounding "in a box")
3. `acompressor=threshold=-20dB:ratio=3:attack=12:release=200:makeup=3:knee=6` — even out dynamics, bring the voice forward
4. `equalizer=f=3200:t=q:w=1.6:g=2.5` — presence / intelligibility
5. `treble=g=3:f=9000` — air / brightness (high shelf)
6. `deesser=i=0.35` — tame the sibilance the presence boost exaggerates
7. `alimiter=level_in=1:level_out=1:limit=0.95` — safety ceiling before loudnorm

Every value is a starting point — tune per voice/room. Common asks: **brighter/crisper** → raise the `treble` gain or the 3.2 kHz boost; **warmer/fuller** → back those off, lift ~200 Hz toward 0; **more "radio" glue** → lower the compressor threshold / raise ratio (expect LRA to drop); **more natural/breathy** → gentler compressor (ratio 2, threshold −24 dB). **Verify, don't assume:** after rendering, run `ffmpeg -i cut.mp4 -af astats -vn -f null -` and check **Flat factor = 0** (no clipped/distorted samples) and Peak below 0 dB, plus `loudnorm=print_format=summary` for integrated ≈ −14 LUFS / TP ≤ −1 dBTP. Then let the user hear it and dial to taste.

## Cut craft

- Candidate cuts from word boundaries and silence gaps. Silences ≥ 400ms are cleanest; 150–400ms usable with a visual check; < 150ms is unsafe.
- Preserve peaks — laughs, punchlines, emphasis. Extend past a punchline to include the reaction.
- Never reason audio and video independently. Every cut must work on both tracks.

### Fine-comb the silences (place cuts on acoustic truth, not Whisper times)

Whisper word timestamps are unreliable for cut edges and this bites every time:

- **Onsets drift.** A word's `start` can be 0.5s+ early — snap a segment start to it and you bake in a chunk of dead air at the head of the segment (heard as a silence right after the previous cut).
- **Ends stretch across silence.** Whisper extends a word's `end` to fill the following pause, so a "phrase" that reads as 4s of speech may be 1s of talk + 3s of silence. Never trust a long single word/phrase span.
- **Repeats get collapsed.** When the speaker restarts a line, Whisper often folds the repeat into one stretched word, so the doubled take is invisible in the transcript — but audible in the cut. Verify any take with restarts against the waveform.

The fix: get acoustic boundaries from **`speech_regions.py`** (`silencedetect`), then for each segment snap **start → a region's onset − ~30ms** and **end → that region's offset + ~50–70ms** (the trail preserves the word's decay; cutting exactly at, or before, the offset clips the last letter/sibilant — a very common complaint). When a segment must land inside a merged speech block (e.g. dropping a collapsed repeat), place that one edge by eye on a fine `timeline_view` waveform. After rendering, if the user still flags a gap or a clipped word, re-run `speech_regions.py` around that timestamp rather than nudging blindly.

- **Padding window:** ~30ms lead, ~50–80ms trail. Stay in the 30–200ms window; the trail is usually a touch longer than the lead so nothing clips.
- **Rotation:** phone/mirrorless clips are often stored landscape (e.g. 3840×2160) with a ±90° display-matrix rotation. `render.py` accounts for this so vertical sources scale to 1080×1920, not an oversized 1920×3414 — don't "fix" it by forcing dimensions.

## The packed transcript

`pack_transcripts.py` turns all `transcripts/*.json` into one markdown where each take is phrase-level lines prefixed with `[start-end]`, breaking on silence ≥ 0.5s. This is the artifact you read to pick cuts — word-boundary precision from text alone at 1/10 the tokens of raw JSON.

## Editor sub-agent brief (multi-take selection)

When the task is "pick the best take of each beat across many clips," spawn a sub-agent with this shape:

```
You are editing a <type> video. Pick the best take of each beat and assemble
them chronologically by beat, not by source clip order.

INPUTS: takes_packed.md; product/narrative context (2 sentences); speaker note;
expected structure (pick an archetype or invent one); verbal slips to avoid
(from the pre-scan); target runtime (seconds).

Archetypes: launch/demo (HOOK→PROBLEM→SOLUTION→BENEFIT→EXAMPLE→CTA); tutorial
(INTRO→SETUP→STEPS→GOTCHAS→RECAP); interview (Q→A→FOLLOWUP…); travel
(ARRIVAL→HIGHLIGHTS→QUIET→DEPARTURE); documentary (THESIS→EVIDENCE→COUNTER→
CONCLUSION); or invent your own.

RULES: start/end on word boundaries; pad 30–200ms; prefer silences ≥ 400ms;
keep unavoidable slips only if no better take exists (note in "reason"); if over
budget, drop a beat or trim tails and report the total.

OUTPUT (JSON array, no prose):
  [{"source":"C0103","start":2.42,"end":6.85,"beat":"HOOK","quote":"…","reason":"…"}, …]
```

## EDL format (Phase 1)

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4"},
  "grade": "eq=contrast=1.06:saturation=1.05",
  "voice_master": true,
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK", "quote": "…", "reason": "…"}
  ],
  "total_duration_s": 87.4
}
```

`grade` is a preset name, a raw ffmpeg filter, or `"auto"` (per-segment). `voice_master` (optional bool) turns on the spoken-word EQ + mastering chain. No `overlays` or `subtitles` fields — those belonged to the old ffmpeg pipeline and are gone; Phase 2 handles text and graphics in Remotion.

---

# PHASE 2 — Captions, motion graphics, illustrative images (Remotion)

Only after the user approves `cut.mp4`. Everything on-screen here is built in Remotion.

**Load the `remotion-best-practices` skill** and consult its `rules/` for the domain knowledge — especially `rules/subtitles.md`, `rules/display-captions.md`, `rules/text-animations.md` (word-highlight = karaoke), `rules/transitions.md`, `rules/effects.md`, `rules/images.md`, `rules/timing.md`. Follow its conventions (`interpolate()` over `spring()`, no CSS transitions, assets in `public/`, `staticFile()`).

## The short-form style (Reels / TikTok / Shorts) — the proven default

For vertical short-form, don't design from scratch — **start from `assets/shortform/`** (a real, proven composition + its README) and adapt the per-video data. It encodes the whole style; carry it over unchanged and just re-time it. The recipe:

- **Base:** 1080×1920 @ 24, `<OffthreadVideo src=cut.mp4>` (the approved Phase-1 cut) with the **dynamic camera** on it (see 5b): hard zoom on cuts + slow push-in + clamped eye-tracking. Always on for short-form — it's what makes a talking head feel edited.
- **Visual hook (first ~4s):** a **static, copywriting-driven headline** over the opening — a scroll-stopper that states the stakes before the viewer decides to swipe. Always on for short-form (see the Visual hook section). Optionally paired with a relevant logo/symbol (e.g. the Claude sunburst + a hazard sign).
- **Captions:** karaoke, **one line ≤3 words, each word rises in from below**, **Poppins Black**, lower third, **`measureText` safe-margin fit** (never touch the edge). Timing from the **cut transcript** (section 3).
- **Inserts (upper zone):** a **consistent rounded-card + subtle-shadow** motif, synced to spoken nouns, each with a slow Ken-Burns zoom. Pexels images for concrete objects; **bespoke motion graphics** (not photos) when a word names something animatable — e.g. an editing timeline being cut for "cortes/legendas/animações", a typewriter script sheet for "roteiro". `assets/shortform/Main.tsx` has both as worked examples.
- **Zones:** inserts/graphics upper third, captions lower third, face clear in the middle. Minimalist; accent green `#33e0a3`.
- **Audio:** SFX pack (`public/sfx/`) — a **whoosh** on every card/graphic appearance, a **pop** on shape reveals — plus a **soundtrack bed** (Phase 3). Keep SFX and music quiet (whoosh ~0.09, pop ~0.12, music ~0.12) and **always run a final loudnorm pass** on the render — voice + music + SFX summed will otherwise clip.

Copy `assets/shortform/{Main.tsx,Root.tsx,index.ts,package.json,tsconfig.json,remotion.config.ts}` and `assets/shortform/sfx/` into `edit/remotion/` (sfx → `public/sfx/`), generate the data files (README pipeline), re-time `INSERTS`/`ZOOMS`/graphics to this video, and render. Still-check cut boundaries for black edges before the full render.

## 1. Ask what to add

The moment the cut is approved, ask the user which layers they want (multi-select — they may pick any combination):

- **Legendas** (captions) — karaoke word-by-word or phrase-level.
- **Motion graphics** — *actual animations*, not just images: kinetic text, animated shapes/icons, number pops, lower-thirds, `rules/effects.md` effects, transitions. When a spoken word names something visual/animatable (e.g. "animações", "gráfico", "cresceu 200%"), that's a cue to put a real motion graphic on screen, not a stock photo.
- **Imagens ilustrativas** — stock images from Pexels dropped in over the talk (a consistent rounded-card + subtle-shadow motif reads clean).
- **Dynamic camera** — hard zoom on cuts, slow push-in, and face/eye tracking. See the Dynamic camera section. This is a Phase-2 layer (Remotion transforms on the base video), NOT baked into the Phase-1 cut.

Shape follow-up questions to their picks (caption style/color/font, which moments get graphics, what the images should depict, camera intensity). Then confirm a short Phase-2 plan before building.

## 2. Scaffold the Remotion project

Inside `edit/remotion/` (Hard Rule 9). **Do NOT rely on `npx create-video@latest --blank` non-interactively** — `--no-tailwind` is ignored and it hangs on an "Add TailwindCSS?" prompt. Scaffold **manually / from the template** instead:

- For short-form, copy `assets/shortform/{Main.tsx,Root.tsx,index.ts,package.json,tsconfig.json,remotion.config.ts}` into `edit/remotion/` (src files go in `edit/remotion/src/`), then `npm install`. This is the fastest path and brings the proven style.
- Otherwise write a minimal `package.json` (`remotion`, `@remotion/cli`, `@remotion/google-fonts`, `@remotion/layout-utils`, `react`, `react-dom`), `tsconfig.json` (with `resolveJsonModule`), `src/index.ts` (`registerRoot`), and `src/Root.tsx`, then `npm install`.

Copy `cut.mp4` into `edit/remotion/public/`. Set the composition width/height/fps to match `cut.mp4` (1080×1920 @ 24) and `durationInFrames = round(duration*fps)`. Base layer is `<OffthreadVideo src={staticFile("cut.mp4")}>`; caption/graphic/image layers sequence on top. Node 25 works with Remotion 4.

## 2b. Visual hook — static headline in the first ~4s (always on for short-form)

The single highest-leverage element in short-form: **the first 1–2 seconds decide whether the viewer keeps watching.** Every short-form edit gets a **static, on-screen headline over the opening ~4s** — no per-word animation (it must be instantly readable), a clean fade in/out at the edges, held still in between.

**Write it like a social-media/copywriting/virality specialist, not a summarizer.** Read the cut transcript, find the core promise or tension, and craft a *scroll-stopping* headline. Levers: **curiosity gap** (imply a payoff without giving it away), **high stakes / bold claim**, **specificity/number**, **urgency**, **pattern interrupt**. Match the video's language. It should feel like a headline the viewer *can't not* read — but never clickbait the video can't pay off.

**Design — THE standard headline template (user-approved default; use it verbatim, only rewrite the copy).** The `HookIntro` in `assets/shortform/Main.tsx` *is* the template. Locked spec:

- **Text:** caption-style — Poppins Black (weight 900), **white**, **UPPERCASE**, `letterSpacing: -1`, `textShadow: '0 4px 20px rgba(0,0,0,0.55)'`.
- **Uniform size:** every line at the **same `fontSize` (~54 on a 1080-wide frame)** — *never* a big hero line + a smaller kicker. This is a hard rule.
- **Card:** dark-gray `#232326`, `borderRadius: 24`, `padding: '28px 46px'`, `lineHeight: 1.08`, drop shadow. Centered, upper zone.
- **Logo + symbol row above the card:** real brand asset preferred — logo card `width: 300` + `borderRadius: 18` + shadow; transparent hazard/angle sign `width: 128` + `drop-shadow`.
- **Motion:** static hold with only a clean fade + 24px rise in / fade out at the edges; a soft `whoosh` on entry. Window `from: 0`, `HOOK_END = 4.0s`.

Rewrite `HEADLINE_LINES` and swap `HOOK_LOGO`/`HOOK_SIGN` per video; leave the styling untouched.

- *Example (this "Claude Fable" video — danger + curiosity + urgency):* **"A IA MAIS / PERIGOSA DO MUNDO / ACABOU DE SER LIBERADA"**, all one size.
- Draft 2–3 candidates, pick the strongest, and **show the user a still and get approval before rendering the full video** — headline copy/design is subjective. Offer alternates.

**Pair with a logo/symbol when it sharpens the hook.** If the video is about a named brand/product/person, put its mark up top next to a symbol that frames the angle (danger, money, trophy, fire…). **Prefer a real brand asset if the user provides one** (drop it in `public/`, display via `<Img>` — a logo card gets rounded corners + shadow, a transparent sign gets a `drop-shadow`). Only fall back to an inline SVG mark when no asset exists. `assets/shortform/Main.tsx` has `HookIntro` as the worked example (real-image logo + hazard sign + uniform-size headline card).

**Placement & de-conflicting.** Headline in the upper-center over the forehead/background (face stays visible below, captions still run at the bottom). If an image/graphic insert wants the same top zone in that window, push it to *after* the hook (e.g. move the opening cutaway from 2.5s to ~4.1s) so the two never stack. Mount the hook above the base video but below the captions layer.

## 3. Captions (if chosen)

**Get caption timing by transcribing the final cut, not by mapping the source.** Run `transcribe.py cut.mp4 --edit-dir <edit>` then `captions_for_remotion.py --transcript <edit>/transcripts/cut.json -o edit/remotion/public/captions.json`. The cut's word times are already on the output timeline and free of the source's Whisper stretch/dead-air artifacts — so the first word of every segment (e.g. the hook's "Esse") is captioned with correct timing. The `<edl.json>` fallback exists but drops/mis-times stretched edge words.

Load `rules/display-captions.md` + `rules/assets/text-animations-word-highlight.tsx` for karaoke, and match the style the user asked for (font, color, size).

**Safe margins are non-negotiable — captions must clear the frame edge AND the platform's right-side action rail.** A single line of ≤3 words can still overflow when the words are long (e.g. "com inteligência artificial"). Measure every line with `measureText()` from `@remotion/layout-utils` (font/size/weight/letterSpacing must match the rendered style) and scale the line down to fit a safe width: `const fit = Math.min(1, SAFE_WIDTH / measured.width)`, then `style={{scale: String(fit)}}`. Do NOT rely on `whiteSpace: nowrap` alone — it overflows silently.

**`SAFE_WIDTH = 720` on a 1080 frame (~180px each side) is the standing default.** A centered caption ~880px wide *looks* fine in isolation but its right end collides with Instagram/TikTok/Reels' **like/comment/share action rail** (~130–160px from the right edge, at the caption's vertical band). 720 pulls both ends inward enough to clear it. Verified against a real Instagram screenshot. Also keep captions above the platform's bottom UI (clear the bottom ~25–30%).

## 4. Motion graphics (if chosen)

Build real animations as Remotion components (`interpolate()` + `Sequence`), synced to spoken moments — get the payoff word's timestamp from the cut transcript and land the animation on it. Use `rules/text-animations.md`, `rules/transitions.md`, `rules/effects.md`. Motion graphics are more than dropped-in photos: kinetic/animated text, animated shapes and icons, number counters, progress reveals, and `effects.md` effects. When the speaker names something animatable — "animações", "gráfico", a statistic — prefer an actual on-screen animation over a stock image. Don't let images be the only visual layer.

## 5. Illustrative images (if chosen)

These need `PEXELS_API_KEY` (see Setup — ask for it if missing). For each moment that wants an image, pick a concrete query, then:

```bash
python helpers/pexels_search.py "<query>" --out-dir edit/remotion/public/pexels --count 3 --orientation portrait
```

Download to the Remotion `public/pexels/` folder, display with `<Img src={staticFile("pexels/<file>")}>` (see `rules/images.md`), and animate the entry/exit. Keep the photographer credits the helper prints for attribution. Prefer images that match the aspect and leave the speaker readable (cutaway full-frame, or inset).

**Brands, people, specific things (logos, celebrities, places)** — Pexels won't have these. Detect proper nouns in the cut transcript (a named brand/person/product) and fetch a real image for that moment. **Prefer Wikimedia Commons first** — freely-licensed, no key, and it covers people, places, and many brand logos (e.g. the Google wordmark is public-domain there):

```bash
python helpers/wikimedia_images.py "Neymar" --out-dir edit/remotion/public/web --count 3
```

Fall back to **`google_images.py`** (Google Custom Search) only for logos/things Commons lacks:

```bash
python helpers/google_images.py "A24 studio logo" --out-dir edit/remotion/public/web --count 3 --rights cc
```

**Rights caveat:** Google returns web images that are usually copyrighted/trademarked. For anything published/monetized, prefer the Wikimedia result (keep its license + author for attribution), pass `--rights cc` to Google, and flag the licensing to the user for logos/celebrities.

## 5b. Dynamic camera (if chosen)

Motion applied to the base `<OffthreadVideo>` in Remotion — this is why zoom/tracking live in Phase 2, not the Phase-1 cut (keep the cut a stable, re-transformable base). Three layers that compose (sum the scales, clamp the pan so the frame is always covered — no black edges):

- **Hard zoom on cuts.** Give each cut segment a fixed base scale that differs from its neighbours (e.g. cycle ~1.10–1.20) so the size *pops* at every jump cut. Map each EDL segment's output start to a frame; switch scale on that frame (a step, not a ramp).
- **Dynamic push-in.** Within a segment, `interpolate` the scale slowly upward (e.g. +0.04 over the segment) so the image is always gently growing. Ease it; reset at the next cut.
- **Face / eye tracking.** Run `face_track.py cut.mp4 -o edit/remotion/public/track.json` (OpenCV Haar pre-pass) to get a smoothed per-frame eye-line point. In Remotion, at total scale `S`, translate so the tracked point maps to a fixed target (upper third): `tx = targetX - faceX*S`, clamp to `[W - W*S, 0]` (same for Y) so edges never show. Keep it subtle and lagged (heavy smoothing) — a gentle follow, not a jerky lock.

Total scale must always be ≥ 1 plus the pan amount, or the transform reveals black. Verify with stills at a few cut boundaries.

## 5c. Sound effects (if chosen)

Copy `assets/shortform/sfx/` into `edit/remotion/public/sfx/` and play a short SFX at each appearance with `<Audio src={staticFile("sfx/whoosh.mp3")} volume={0.09}/>` **placed inside that element's `<Sequence>`** (it fires at the sequence start). Default mapping: **whoosh** on card/graphic entrances, **pop** on shape reveals, **click** for a hard accent. Keep volumes low (see the audio-safety note in Phase 3) — SFX stacked on the voice will clip without it.

## 5d. Behind-the-subject (element between the person and the background)

Puts an image or word **behind the person** (person in front, element in front of the real background). A cinematic upgrade for a talking head — great for a hero image (person in front of an explosion/scene) or a big kinetic word that the person occludes. Best on medium/wide shots; on a tight close-up the person covers most of a *centered* element, so **anchor the element to the TOP of the frame** (image top-weighted, words near the top) — it frames the head and reads far better than centering it behind the torso. (Even better: shoot with headroom/negative space knowing this effect will fill it.)

**Pipeline — matte the person, then layer.** Needs the `matting` extra (`uv sync --extra matting`, torch — heavy, so it's opt-in):

```bash
python helpers/person_matte.py cut.mp4 -o edit/remotion/public/fg_<name>.mov --start <s> --duration <d>
```

`person_matte.py` runs **Robust Video Matting** (RVM, temporally-stable hair edges) and writes the person over transparency. Matte **only the windows** you need (per behind-element) — each file's frame 0 = its window start. Non-obvious things that all bit once and matter:

- **Format: ProRes 4444 `.mov`, NOT WebM.** libvpx on some ffmpeg builds silently drops the alpha (encodes `yuv420p`); ProRes carries a real alpha plane and Remotion's renderer decodes it. The helper defaults to `.mov`.
- **Composite the ORIGINAL source RGB with the alpha, not RVM's `fgr`.** Because the background stays the same base cut, source pixels make the person seamless over the base; `fgr`'s decontaminated foreground rims the person with a light halo. (The helper already does this.)
- **Remotion needs `<OffthreadVideo transparent />`.** Without the `transparent` prop it ignores the alpha and the matte renders opaque, hiding everything under it.
- **The matte must get the SAME dynamic camera as the base**, or the person drifts off its body. Reuse the `DynamicVideo` wrapper with a `frameOffset` = the sequence's `from` so its camera math uses the global frame while the matte plays from its own frame 0.

**Layer order (in the element's `<Sequence>`):** the element first, then the person matte on top:

```tsx
<Sequence from={F} durationInFrames={D} layout="none">
  <BehindImageEl src="ill/x.jpg" totalFrames={D} />          {/* or big word(s), one at a time */}
  <DynamicVideo src="fg_x.mov" frameOffset={F} transparent /> {/* person redrawn on top */}
</Sequence>
```

Mount the whole `<BehindSubject>` **right after the base `<DynamicVideo/>`** so the person matte stays *behind* the front layers (captions, graphics, hook still render in front of the person). `assets/shortform/Main.tsx` has `BehindSubject` + `BehindImageEl` + `BehindWordsEl` + the `DynamicVideo({src, frameOffset, transparent})` refactor as the worked example.

## 6. Preview, render, iterate

Preview in `npx remotion studio`; sanity-check a frame with `npx remotion still <comp> --frame=<n>`. Render the final:

```bash
npx remotion render <composition-id> edit/remotion/out/final.mp4
```

`ffprobe` the output to confirm duration/dimensions. Iterate on the user's notes — re-render only Phase 2 (the approved cut doesn't change unless they reopen Phase 1).

---

# PHASE 3 — Soundtrack

The final layer. **Always ask the user how they want the music:**

- **AI-generated (Treblo)** — `treblo_music.py "<vibe>" -o edit/remotion/public/trilha.mp3`. Default vibe: minimal, warm, unobtrusive instrumental for a talking head; put any genre the user names into the prompt. It's async (~1 min). Show the track (or the video with it) for approval; regenerate if they want another vibe.
- **Local file** — the user points at a music file; copy it to `edit/remotion/public/trilha.mp3`.

Add it as a background bed in Remotion: `<Audio src={staticFile("trilha.mp3")} volume={(f)=>fade(...)}/>` at ~0.12 with a fade in/out (see `assets/shortform/Main.tsx` `Soundtrack`). Optional ducking: drop the music volume where the voice is loud (use the transcript word times); a low fixed volume usually suffices for talking-head.

**Audio safety (non-negotiable):** voice + music bed + SFX summed **will clip** (peaks hit 0 dBFS). Keep every added layer quiet (music ~0.12, SFX ~0.09) **and run a final loudnorm pass on the Remotion render** — it caps true-peak and sets social loudness:

```bash
ffmpeg -y -i out/render.mp4 -c:v copy -af "loudnorm=I=-14:TP=-1:LRA=11" -c:a aac -b:a 192k -ar 48000 out/final.mp4
```

Verify `max_volume` ≤ -1 dB with `ffmpeg -i final.mp4 -af volumedetect -f null -`. Then copy to `edit/final.mp4` and show for final approval.

# LONGFORM — YouTube (16:9)

Everything above is the **short-form** track (vertical social). **Longform is a second track** for YouTube: horizontal, minutes-long, retention-driven. It **reuses the whole Phase-1 engine and Phase-3 soundtrack unchanged** — only the *cut philosophy*, the *output spec*, the *captions*, and the *Phase-2 visual language* differ. Use this track when the source is horizontal, or the user says YouTube / longform / tutorial / vlog. Covers **talking-head + B-roll, tutorial / screen-record, and vlog / narrative**. Ask, confirm, execute, iterate — same rules, same phase gate.

## What changes vs short-form (the only deltas)

| | Short-form | **Longform** |
|---|---|---|
| Aspect / res | 1080×1920 @ 24 | **16:9 at source resolution** (1080p or 4K), source fps |
| Cut goal | maximum compression | **retention arc**, keep pacing/breath |
| Silence trim | aggressive (30–80ms pads) | **gentle** — cut fillers/mistakes/dead-air > ~0.8s only; keep 300–600ms beats |
| Captions | karaoke burned (≤3 words) | **`.srt` for YouTube CC** (not burned) |
| Hook | static 4s headline | **cold open** (5–15s tease) + intro |
| Camera | hard-zoom dynamic | mostly static; **B-roll cutaways** carry visual variety |
| Phase-2 template | `assets/shortform/` | **`assets/longform/`** (16:9, rich) |

## Phase 1 (longform) — cut for retention, not compression

Same helpers (`transcribe` → `pack` → editor sub-agent → `speech_regions` → `render`), different intent:

1. **Structure the cut as a retention arc**, not a chronological trim:
   - **COLD OPEN (0–15s):** pull the single most compelling line/moment from *anywhere* in the footage to the very front — a payoff tease, a bold claim, the "after". This is the retention make-or-break.
   - **INTRO:** who / what / the promise (what the viewer gets by staying). Keep it short.
   - **BODY:** sections/chapters, each opening with its own mini-hook and closing a loop. Reorder beats for flow; longform is assembled by *argument*, not by clip order.
   - **PAYOFF → OUTRO/CTA:** deliver the promise, then subscribe / next-video. **Reserve the last ~20s** for end-screen cards (keep it visually calm there).
2. **Gentle silence pass.** Run `speech_regions.py` but only cut **filler words, false starts, restarts, and dead air > ~0.8–1.0s**. Keep natural 300–600ms beats — longform that's cut as tight as a Reel feels breathless. (Tune `speech_regions` toward a longer `min_silence`.)
3. **Re-hooks / open loops.** "But first…", "the reason this matters…", tease what's coming so retention survives the mid-video dip.
4. **Editor sub-agent brief:** use the multi-take brief but with a longform archetype — *tutorial* (INTRO→SETUP→STEPS→GOTCHAS→RECAP), *talking-head essay* (COLD-OPEN→THESIS→POINTS→COUNTER→CONCLUSION→CTA), or *vlog* (COLD-OPEN→ARRIVAL→BEATS→REFLECTION). Tell it to place a cold open and label chapters.
5. **Render 16:9 at source resolution** (not 1080p): `render.py edl.json -o cut.mp4 --no-subtitles --keep-resolution` *(new flag — keeps the source's 16:9 dimensions/fps instead of forcing 1080p)*. Grade + `--voice-master` + loudnorm all apply unchanged. `-14 LUFS` is YouTube's target too.
6. **Screen-record (tutorial):** the base may be a screen capture — treat it as the base video; add crop-zoom to the active region + callouts in Phase 2 rather than a face camera.

## Chapters + timestamps (YouTube description)

Derive chapters from the EDL section labels and emit a **YouTube chapters block** for the description (`chapters.txt` in `edit/`). Rules YouTube enforces: **first line must be `00:00`**, **≥ 3 chapters**, **each ≥ 10s**, in order.

```
00:00 Cold open
00:14 O que é X
01:32 Passo a passo
…
```

## Captions — `.srt` for YouTube CC (not burned)

Transcribe the **final cut** (`transcribe.py cut.mp4`) and emit a broadcast-style **`.srt`** (`edit/captions.srt`): 1–2 lines, ~42 chars/line, sentence case, break on natural phrase boundaries, min ~1s / max ~6s per cue. The user uploads it as a subtitle track — YouTube shows it as optional CC, so it never covers the picture. *(New helper — `captions_srt.py`, sibling of `captions_for_remotion.py`.)*

## Phase 2 (longform) — rich 16:9 visuals in Remotion

Scaffold from **`assets/longform/`** (16:9 template) — same idea as the shortform template but composed for a horizontal, less-dense, more-produced look. Graphics **punctuate**, they don't saturate (a longform frame is mostly the talker or the B-roll). The layers:

- **B-roll cutaways** — the core of longform visual variety. Cover the talking head with a full-frame image/clip for a few seconds while narration continues, then cut back. Stills get a slow Ken-Burns; Pexels **video** clips (`pexels_search.py` also fetches video) play underneath. Sync to what's being said.
- **Lower-thirds** — name/title/handle cards that slide in, hold ~3–4s, slide out. For the speaker and for anyone/anything named.
- **Chapter cards** — a title card at each chapter start (full-frame beat, or a corner tag). Doubles as the visual for the chapters above.
- **Callouts** — highlight boxes, arrows, underlines, number pops, a keyword lower-third — to emphasize a point. Occasional emphasis text (NOT word-by-word karaoke).
- **Screen-record zoom** — for tutorials, crop-zoom into the active UI region and pan, with callouts, so a full-screen capture reads on a phone.
- **Intro/outro** — optional channel sting at the top; keep the last ~20s calm for YouTube end cards.

Reuse where it helps: the **dynamic camera**, **SFX**, **behind-the-subject** matte, and **illustrative-image** helpers all work in 16:9 — just apply them sparingly (longform ≠ Reel density).

**Longform helpers (built):**
- `render.py edl.json -o cut.mp4 --no-subtitles --keep-resolution --voice-master` — Phase-1 cut at source resolution/fps.
- `captions_srt.py --transcript <edit>/transcripts/cut.json -o <edit>/captions.srt` — `.srt` for YouTube CC.
- `chapters.py <edit>/edl.json -o <edit>/chapters.txt` — YouTube chapters block (mark sections with a `"chapter": "Title"` field on the opening range of each section).
- `assets/longform/` — the 16:9 Remotion template (`BROLL` / `LOWER_THIRDS` / `CHAPTERS` / `CALLOUTS` data arrays + `Base`/`Soundtrack`; set the composition size/fps in `Root.tsx` to match `cut.mp4`).

## Memory — `project.md`

Append one section per session at `<edit>/project.md`:

```markdown
## Session N — YYYY-MM-DD
**Phase reached:** cut approved? phase 2 layers built?
**Strategy:** approach in a paragraph
**Decisions:** take choices, cuts, grade (LOG?), caption/graphic/image choices + why
**Outstanding:** deferred items
```

On startup, read `project.md` if it exists and summarize the last session in one sentence before asking whether to continue.

## Anti-patterns

- **Starting Phase 2 before the cut is approved.** The gate is a Hard Rule.
- **Burning captions or overlays with ffmpeg/PIL.** Phase 2 is Remotion-only now; this ffmpeg may not even have libass.
- **Assuming the color profile.** Ask about LOG explicitly — a LOG source ungraded looks broken.
- **Setting cut edges from Whisper word times.** They drift (early onsets → leading dead air) and stretch (late ends → collapsed repeats, clipped words). Use `speech_regions.py`.
- **Cutting a segment end exactly at (or before) the word offset.** Clips the last letter/sibilant. Leave a ~50–70ms decay trail.
- **Committing a grade without a frame preview.** Grade on one frame, show the user, then render the whole cut.
- **`curves` with spaces in the EDL grade string.** Breaks filtergraph parsing; use `colorlevels`/`colorbalance`.
- **Single-pass filtergraph when extracting.** Per-segment extract → concat (Hard Rule 2).
- **Hard audio cuts at boundaries.** 30ms fades (Hard Rule 3).
- **Re-transcribing cached sources.** Immutable outputs of immutable inputs.
- **Assuming what kind of video it is.** Look first, ask second, edit last.
