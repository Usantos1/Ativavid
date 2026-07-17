---
name: edvid
description: Edvid — edit any video by conversation, in phases. Two tracks — SHORT-FORM (vertical 9:16 for Reels/TikTok/Shorts) and LONGFORM (horizontal 16:9 for YouTube: talking-head+B-roll, tutorials/screen-record, vlogs). PHASE 1 — clean cut + color grade + optional voice EQ/mastering (transcribe, select best takes, cut on silence for short-form or retention arc + cold open for longform, grade; ask if shot in LOG; master the voice), then show the user for approval. PHASE 2 (after the cut is approved) — Remotion visuals from a data-driven template: short-form gets karaoke captions, a static hook, a dynamic camera and behind-the-subject; longform gets B-roll cutaways, lower-thirds, chapter cards, callouts, plus YouTube chapters and .srt captions. PHASE 3 — soundtrack (AI via Treblo or a local file). Illustrative images/video via Pexels + Wikimedia/Google. Ask questions, confirm, execute, iterate, persist.
---

# Edvid

## Principle

1. **Two phases, one gate between them.** PHASE 1 is the clean cut + color grade. Show it and **wait for approval**. PHASE 2 (captions, graphics, images) only starts after the cut is signed off.
2. **LLM reasons from raw transcript + on-demand visuals.** The only derived artifact that earns its keep is the packed phrase-level transcript (`takes_packed.md`). Everything else you derive at decision time.
3. **Audio is primary, visuals follow.** Cut candidates come from speech boundaries and silence gaps.
4. **Ask → confirm → execute → iterate → persist.** Never touch the cut until the user confirms the strategy in plain English.
5. **Generalize.** Look at the material, ask the user, then edit — never assume what kind of video it is.
6. **Artistic freedom is the default.** Specific values here are worked examples, not mandates. Only the Hard Rules are mandatory.
7. **Verify your own output before showing it** — numbers first, images only where the numbers flag (see Self-eval).
8. **Spend tokens where taste lives.** Machine data (raw transcripts, captions.json, track.json, template code) is for programs, not for reading. Batch visual checks into one montage instead of N images.

## Hard Rules (production correctness — non-negotiable)

1. **The phase gate is real.** No Phase-2 work before the cut is approved.
2. **Per-segment extract → lossless `-c copy` concat**, never a single-pass filtergraph.
3. **30ms audio fades at every segment boundary** (encoded in render.py).
4. **Never cut inside a word** — snap to word boundaries from the transcript.
5. **Pad every cut edge** (30–200ms window; trail slightly longer than lead). Cut on silence whenever possible.
6. **Cache transcripts per source.** Never re-transcribe unless the source changed.
7. **Color grade per-segment during extraction**, never post-concat.
8. **Strategy confirmation before execution.**
9. **All session outputs in `<videos_dir>/edit/`** — never inside the edvid repo.
10. **PHASE 2 is Remotion-only** — no ffmpeg/PIL burned text or overlays.
11. **PHASE 2 is data-driven.** Scaffold by copying the track template; describe the video in `public/edit-data.json`. **Never read or edit the template TSX** (`src/Main.tsx` etc.) — the only editable code file is `src/CustomGraphics.tsx`, only for bespoke graphics.
12. **Verify numerically first.** Run `verify_cut.py` on every rendered cut; open images only for flagged junctions. Batch any multi-frame look into one `contact_sheet.py` / `grade.py --candidates` montage.
13. **Never Read machine data into context**: `transcripts/*.json` (raw), `captions.json`, `track.json`, `segments.json`, matte/track binaries. Read `takes_packed.md` and helper stdout instead.

## Execution medium — ffmpeg pipeline (default) vs Adobe Premiere (MCP)

The default engine is the ffmpeg/Remotion pipeline below. **If the user wants the
edit done inside Adobe Premiere Pro via the `premiere-pro` MCP** (e.g. "edite a
sequência no Premiere", "corte via MCP"), the METHOD here is unchanged (audio-primary,
cut on silence, phase gate, grade with taste) but the hands change — **read
`references/premiere-mcp.md`** for the battle-tested Premiere workflow (razor +
ripple recipe, the V/A-link ripple caveat, `color_correct` LOG-strength lesson,
voice master, `export_frame` gotcha, tool cheat-sheet). Transcription/`edl.json`
are identical and cached — reuse an approved `edl.json`; skip `cut.mp4`/preview.

## Directory layout

```
<videos_dir>/
├── <source files, untouched>
└── edit/
    ├── project.md               ← memory; appended every session
    ├── takes_packed.md          ← phrase-level transcripts, the primary reading view
    ├── edl.json                 ← cut decisions (Phase 1)
    ├── transcripts/<name>.json  ← cached word-level transcripts (Groq Whisper / ElevenLabs Scribe)
    ├── clips_graded/            ← per-segment extracts with grade + fades
    ├── cut.mp4                  ← PHASE 1 output: clean graded cut (approval artifact)
    ├── verify/                  ← montages / flagged-boundary views
    ├── captions.srt + chapters.txt   ← longform deliverables
    ├── final.mp4                ← delivered render (Phase 2 + 3, loudnorm'd)
    └── remotion/                ← Remotion project (Phase 2 + 3)
        ├── public/              ← cut.mp4, edit-data.json (THE edit), captions.json,
        │                          track.json, segments.json, pexels/ web/ brand/, sfx/, trilha.mp3
        └── src/                 ← immutable template code + CustomGraphics.tsx
```

## Setup

First-time install lives in `install.md`. On cold start just verify:

- `GROQ_API_KEY` resolves (env or `.env` at the edvid repo root). Groq Whisper `whisper-large-v3`; no diarization (every word is `speaker_0`).
- `ELEVENLABS_API_KEY` (optional) — used for LONG sources (>5 min, e.g. YouTube/course lessons) via ElevenLabs Scribe `scribe_v1`, since Groq's free tier chokes on long uploads. `backend=auto` (default) picks Scribe over 5 min when the key exists, else Groq; short clips stay on Groq. No key → long sources fall back to Groq. Ask for it lazily the first time a >5 min source shows up, write to `.env`.
- `ffmpeg` + `ffprobe` on PATH; Python deps (`uv sync`); Node 18+ for Phase 2.
- The `remotion-best-practices` skill for Phase-2 domain knowledge (install from https://github.com/remotion-dev/skills if missing).
- Lazy keys, ask on first use, write to `.env` (never to `<videos_dir>`): `PEXELS_API_KEY` (images), `GOOGLE_API_KEY`+`GOOGLE_CSE_ID` (brand/people images fallback), `TREBLO_API_KEY` (AI music).

Helpers live in `helpers/`, resolved relative to this SKILL.md (symlinked at `~/.claude/skills/edvid/`).

## Helpers

Phase 1:
- **`transcribe.py <video> --edit-dir <edit> [--language pt] [--backend auto|groq|elevenlabs]`** — word-level, cached. `backend=auto` (default): ElevenLabs Scribe for sources >5 min (when `ELEVENLABS_API_KEY` set), else Groq Whisper. Audio uploads as CBR 64kbps mono MP3 (~0.5 MB/min); oversized audio auto-chunks **by bytes**, so every chunk is guaranteed under Groq's 25 MB cap regardless of length. Chunks fetch **in parallel** with per-chunk resume cache and 5x backoff retries (provider blips don't restart the job).
- **`transcribe_batch.py <videos_dir> [--backend auto|groq|elevenlabs]`** — 4-worker parallel transcription for multi-take shoots; same per-file auto backend selection by length.
- **`pack_transcripts.py --edit-dir <dir>`** — transcripts → `takes_packed.md` (phrase-level, breaks on ≥0.5s silence). **The** reading view: 1/10 the tokens of raw JSON.
- **`speech_regions.py <video>`** — acoustic speech intervals via silencedetect. The source of truth for cut edges (Whisper times drift/stretch).
- **`render.py <edl.json> -o cut.mp4 --no-subtitles [--voice-master] [--keep-resolution] [--jobs N]`** — per-segment extract (grade + fades, **parallel**) → lossless concat → optional voice master → loudnorm. Short-form fps is automatic: **30fps for 30fps+ sources, else 24** (longform keeps source fps via `--keep-resolution`). Set `edit-data.json` `fps` to match the resulting `cut.mp4`.
- **`verify_cut.py <edl.json> <cut.mp4> [--min-silence 1.2]`** — numeric self-eval: duration, per-junction pop/clipped-word probes, dead air, black frames, clipping. ~350 tokens of text instead of N images.
- **`grade.py <in> -o <out>`** — grade presets/raw filters. **`--candidates "a=<filter>;b=<preset>;original=" --frame <t> -o cmp.png`** renders N looks on the SAME frame into one labeled montage.
- **`timeline_view.py <video> <start> <end>`** — filmstrip+waveform PNG for ONE flagged spot, not a scan tool.
- **`contact_sheet.py <video> --times t1 t2 … -o sheet.png`** — N frames in one labeled grid; the way to eyeball several moments.

Phase 2/3 (see the track references for usage):
- **`captions_for_remotion.py`** (karaoke JSON) · **`face_track.py`** (eye-track JSON) · **`person_matte.py`** (RVM alpha matte; `uv sync --extra matting`) · **`pexels_search.py`** · **`wikimedia_images.py`** (no key, brands/people first choice) · **`google_images.py`** (fallback, mind rights) · **`captions_srt.py`** (longform .srt) · **`chapters.py`** (YouTube chapters) · **`treblo_music.py`** (AI soundtrack — pass a context-driven MUSICAL vibe: genre + instruments + tempo + mood, not SFX-y phrasing; auto-framed as a composed instrumental).

Interface:
- **`preview_server.py --root <edit> [--port 4820]`** — serves the standard preview interface (see the Preview interface section). App code lives at `assets/preview/` and is IMMUTABLE.

## Preview interface (standard — launch it at the start of every edit)

Every edit session gets the same interactive interface in the user's preview panel: a video-editor timeline (video track with filmstrip + audio track with waveform), a live playhead that scrubs the render in real time, per-take trim handles and take removal, and — from Phase 2 — caption and insert tracks. Dark glass, Edvid brand. **Never build a UI per session and never edit `assets/preview/`** — it is data-driven, like the Remotion templates.

**Launch (do this when a session starts, even before the first render — the UI shows a waiting state):**
1. Write `<edit>/state.json`:
   ```json
   {"project": "Nome — C0000", "phase": 1, "video": "cut.mp4", "edl": "edl.json",
    "captions": "remotion/public/captions.json", "editData": "remotion/public/edit-data.json",
    "finalVideo": "final.mp4", "fps": 24, "message": "Fase 1 — cortando",
    "sourceDurations": {"C0000": 1038.5}}
   ```
   (`captions`/`editData`/`finalVideo` only when they exist; the Fase-2 tab plays `finalVideo` — the render WITH captions/inserts — while Fase 1 plays the clean cut; `sourceDurations` lets the UI clamp take extensions.)
2. Ensure `.claude/launch.json` has the config (adjust `--root` per session):
   `{"name": "edvid-preview", "runtimeExecutable": "python3", "runtimeArgs": ["<skill>/helpers/preview_server.py", "--root", "<edit>", "--port", "4820"], "port": 4820}`
3. `preview_start` with name `edvid-preview`.

**Keep state.json fresh** — bump `phase` and `message` at each milestone (cut rendered, cut approved, Phase 2 rendered…). The UI polls and hot-reloads by itself; waveform + filmstrip regenerate automatically when cut.mp4 changes.

**When the user saves timeline adjustments in the UI**, it writes `<edit>/preview_edits.json` (never touches edl.json). To apply: read its `edl.changes` / `edl.removed` digest (small), validate each new edge against `speech_regions.py` (warn if an edge clips a word — the user's intent wins, but say so), update `edl.json`, re-render, `verify_cut.py`, delete `preview_edits.json`, update `state.json`. Same for `editData` adjustments (insert/hook/behind timings → edit-data.json → re-render Phase 2).

---

# PHASE 1 — Clean cut + color grade

Goal: best take of every beat, cut on silence, graded image, clean `cut.mp4` for approval. No text, no graphics.

1. **Inventory.** `ffprobe` every source. `transcribe_batch.py` (or `transcribe.py`) → `pack_transcripts.py` → read `takes_packed.md`. Note dimensions/orientation and whether it looks flat/LOG.
2. **Pre-scan** `takes_packed.md` for verbal slips, mis-speaks, and dead-air-stretched words (Whisper stretches a word's end across silence — verify long "phrases" against `speech_regions.py`/waveform before trusting them).
3. **Converse.** Describe what you see; ask questions shaped by the material (content type, target length/aspect, pacing, must-keep/must-cut). No fixed checklist.
4. **Ask about the color profile:** "Was this shot in LOG/flat (S-Log, V-Log, HLG) or standard/Rec.709?" LOG needs a real grade; standard needs light correction or none. Don't guess.
5. **Propose the cut strategy** (4–8 sentences: shape, takes, cut direction, grade direction, length estimate). **Wait for confirmation.**
6. **Execute.** Produce `edl.json` (schema below; editor sub-agent brief for multi-take). Set cut edges from `speech_regions.py`, not raw Whisper times. Render: `render.py edl.json -o cut.mp4 --no-subtitles` (+`--voice-master` if wanted; longform: `--keep-resolution`).
7. **Self-eval (numeric first).** `verify_cut.py edl.json cut.mp4` (longform: `--min-silence 1.2`). Clean → done. Flags → `timeline_view` ONLY the flagged junctions, fix, re-render. Cap 3 loops, then surface remaining flags to the user.
8. **Show `cut.mp4` and wait for approval.** The phase gate. Then read the track reference: **`references/shortform.md`** or **`references/longform.md`**.

## Color grade

Reason about the image, don't preset-blind. Mental model ASC CDL: per channel `out = (in*slope + offset)**power`, then saturation. Applied per-segment at extraction (Hard Rule 7).

- **Iterate on ONE frame via a candidates montage, and let the user choose:**
  `grade.py <src> --candidates "punch=eq=contrast=1.15:saturation=1.25;suave=…;original=" --frame <t> -o edit/verify/grades.png` — one image, all looks labeled, side by side. Only render the full cut once the grade is locked.
- **Build from spaceless filters** so the string survives the EDL: `eq=…`, `colorbalance=…`, `colorlevels=…`. No `curves` with spaces (breaks filtergraph parsing).
- **Standard/Rec.709** → light corrective or none. **LOG/flat** → real expansion, e.g. `eq=contrast=1.15:saturation=1.25:gamma=1.05` as a start; a user `.cube` goes first as `lut3d=`.
- **Skin is the guardrail.** The moment skin goes orange/magenta/clipped, back off. Check a mid-shot face at each step.
- **Relative tweaks** ("+1 exposure", "mais saturação") → nudge that one term, re-montage the same frame, show again.

## Voice EQ + mastering (optional Phase-1 audio polish)

Opt-in: `render.py … --voice-master` or `"voice_master": true` in the EDL. Runs after compositing, before loudnorm. Chain (`VOICE_MASTER_CHAIN` in render.py): highpass 80 → mud cut −2.5dB@200 → compressor (3:1, −20dB, makeup 3) → presence +2.5dB@3.2k → air +3dB@9k shelf → deesser → limiter 0.95.

Tune per voice: brighter → raise treble/3.2k; warmer → back those off, lift ~200Hz; more "radio" → lower threshold / raise ratio; more natural → ratio 2, threshold −24dB. **Verify:** `ffmpeg -i cut.mp4 -af astats -vn -f null -` → Flat factor 0, peak < 0dB; loudnorm summary ≈ −14 LUFS / TP ≤ −1. Then let the user hear it.

## Cut craft

- Silences ≥ 400ms are the cleanest cuts; 150–400ms usable with a check; < 150ms unsafe.
- Preserve peaks (laughs, punchlines, emphasis) — extend past a punchline to include the reaction.
- Every cut must work on audio AND video.

**Fine-comb the silences — Whisper times are NOT cut edges:**
- Onsets drift early (bakes dead air at a segment head); ends stretch across silence (a 4s "phrase" may be 1s of talk); restarts get collapsed into one stretched word (the doubled take is invisible in text but audible).
- Fix: edges from `speech_regions.py` — start → region onset −30ms, end → offset +50–80ms (the trail keeps the word's decay; cutting at the offset clips the last sibilant). Inside merged speech blocks, place the edge by eye on a fine `timeline_view`.
- If the user flags a gap/clip after render, re-run `speech_regions.py` around that timestamp — don't nudge blindly.
- **Rotation:** phone clips are often stored landscape with a ±90° display-matrix; render.py handles it — don't force dimensions.

## Editor sub-agent brief (multi-take selection)

```
You are editing a <type> video. Pick the best take of each beat and assemble
chronologically by beat, not clip order.
INPUTS: takes_packed.md; narrative context (2 sentences); speaker note;
expected structure (archetype or invent); verbal slips to avoid; target runtime.
Archetypes: launch (HOOK→PROBLEM→SOLUTION→BENEFIT→EXAMPLE→CTA); tutorial
(INTRO→SETUP→STEPS→GOTCHAS→RECAP); interview (Q→A→FOLLOWUP…); essay
(COLD-OPEN→THESIS→POINTS→COUNTER→CONCLUSION→CTA); vlog; or invent.
RULES: edges on word boundaries; pad 30–200ms; prefer ≥400ms silences; keep
unavoidable slips only if no better take (note in "reason"); if over budget,
drop a beat or trim tails and report.
OUTPUT (JSON array, no prose):
[{"source":"C0103","start":2.42,"end":6.85,"beat":"HOOK","quote":"…","reason":"…"}]
```

For a single long source (longform), the main context can pick cuts directly from `takes_packed.md`; for sources > ~30 min, delegate to the sub-agent so the full transcript never enters the main context.

## EDL format (Phase 1)

```json
{
  "version": 1,
  "sources": {"C0103": "/abs/path/C0103.MP4"},
  "grade": "eq=contrast=1.06:saturation=1.05",
  "voice_master": true,
  "ranges": [
    {"source": "C0103", "start": 2.42, "end": 6.85, "beat": "HOOK",
     "quote": "…", "reason": "…", "chapter": "Only on longform section openers"}
  ],
  "total_duration_s": 87.4
}
```

`grade`: preset name, raw filter, or `"auto"`. `chapter` fields feed `chapters.py` (longform).

---

# PHASE 2 + 3 — read the track reference (after the gate)

The cut is approved → ask which layers the user wants, then load **one** file:

- **Vertical / Reels / TikTok / Shorts → read `references/shortform.md`.** Karaoke captions, static hook headline, dynamic camera, inserts, behind-the-subject, SFX, soundtrack.
- **Horizontal / YouTube / tutorial / vlog → read `references/longform.md`.** Retention cut is there too (read it BEFORE Phase 1 on longform jobs), B-roll, lower-thirds, chapter cards, callouts, .srt + chapters, soundtrack.

Both tracks: scaffold with one `cp -R` of the template, describe the video in `public/edit-data.json`, verify with montage stills, render, loudnorm, deliver `edit/final.mp4`. Load the `remotion-best-practices` skill when writing any Remotion code (CustomGraphics).

## Memory — `project.md`

Append one section per session at `<edit>/project.md`:

```markdown
## Session N — YYYY-MM-DD
**Phase reached:** …  **Strategy:** …
**Decisions:** takes, cuts, grade (LOG?), layer choices + why
**Outstanding:** deferred items
```

On startup, read it if it exists and summarize the last session in one sentence before asking whether to continue.

## Anti-patterns

- Starting Phase 2 before cut approval (the gate is a Hard Rule).
- Reading `transcripts/*.json`, `captions.json`, `track.json`, `segments.json`, or template TSX into context — machine data; read `takes_packed.md`/helper output instead.
- Editing `src/Main.tsx` — the template is data-driven; the JSON is the edit.
- `timeline_view` on every boundary — run `verify_cut.py` and image ONLY the flags.
- N single-frame images when one `contact_sheet.py` / `--candidates` montage answers it.
- Setting cut edges from Whisper word times (drift/stretch/collapsed repeats) — use `speech_regions.py`.
- Cutting exactly at a word's offset (clips the sibilant) — leave the 50–80ms trail.
- Committing a grade without the one-frame candidates montage + user pick.
- Burning captions/overlays with ffmpeg/PIL — Phase 2 is Remotion-only.
- Assuming the color profile — ask about LOG explicitly.
- Re-transcribing cached sources; re-rendering Phase 1 when only Phase 2 changed.
- Building a per-session preview UI or editing `assets/preview/` — launch the standard interface and feed it `state.json`.
- Applying `preview_edits.json` blindly — validate new edges against `speech_regions.py` first (flag clipped words to the user).
- Assuming what kind of video it is. Look first, ask second, edit last.
