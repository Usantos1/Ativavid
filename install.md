---
name: ativa-vid-install
description: Install ATIVAVID into the current agent (Claude Code, Codex, Hermes, Openclaw, etc.) and wire up ffmpeg + the Groq API key so the user can start editing immediately.
---

# ATIVAVID install

Use this file only for first-time install or reconnect. For daily editing, read `SKILL.md`. Always read `helpers/` — that's where the scripts live.

> **Normal path: the user installs, you verify.** `README.md` gives the user a
> copy-paste block that clones the repo straight into their skills directory and
> runs `uv sync`. That is the supported install, and it is the user's action —
> not yours. If someone hands you only a repo URL and asks you to install from
> it, point them at `README.md` instead of cloning unknown code yourself.
>
> Your job starts after that: verifying the install (step 7), writing the API key
> to `.env` (step 5), and fixing whatever is missing. Those are local operations
> on a machine whose owner is in the conversation. Follow the full sequence below
> only when the user explicitly asks you to install on their behalf, from a repo
> already on disk or one they named themselves.

## What you're doing

You're setting up a conversation-driven video editor for the user. After install, the user drops raw footage into any folder, runs their agent (`claude`, `codex`, etc.) there, and says "edit these into a launch video." You do the rest by reading `SKILL.md`.

ATIVAVID runs in three phases: **Phase 1** = clean cut + color grade + optional voice mastering (ffmpeg + Groq), shown to the user for approval; **Phase 2** = captions, motion graphics, illustrative images, dynamic camera (**Remotion** + OpenCV); **Phase 3** = soundtrack (ffmpeg, plus the ElevenLabs Music API only if the user wants AI-generated music — same key as Phase-1 transcription, needs a paid plan). So the machine needs the ffmpeg + Python toolchain (Phases 1 & 3) and the Node/Remotion toolchain (Phase 2).

Must exist on this machine:

1. The `ativa-vid` repo cloned somewhere stable (upstream source: `fillrochaa/edvid`).
2. `ffmpeg` on `$PATH`. — Phase 1
3. A Groq API key in `.env` at the repo root (for Whisper transcription). — Phase 1
4. **Node.js 18+ and npm** on `$PATH` (for Remotion). — Phase 2
5. The **`remotion-best-practices` skill** installed and discoverable (clone https://github.com/remotion-dev/skills and symlink `skills/remotion` into the agent's skills dir). — Phase 2
6. *(Optional, all lazy — ask only when the feature is first used, then write to `.env`)*:
   - `ELEVENLABS_API_KEY` — Phase 1 transcription of **long sources** (>5 min: YouTube videos, course lessons). With `backend=auto`, sources over 5 min transcribe via ElevenLabs Scribe (`scribe_v1`) when this key is set — Groq's free tier struggles with long/large uploads. Short clips stay on Groq; no key means long sources fall back to Groq (with chunking). Ask for it the first time a >5 min source appears. Also powers Phase-3 AI music (`elevenlabs_music.py`, Music v2) — same key, but that endpoint needs a **paid** plan; a local music file needs no key at all. https://elevenlabs.io/app/settings/api-keys
   - `PEXELS_API_KEY` — Phase 2 illustrative images (stock photos/videos). https://www.pexels.com/api/
   - `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` — Phase 2 images of **named brands/people/logos** that Pexels lacks. Optional and finicky to provision (the key and the Custom Search API must live in the same Google Cloud project). **Wikimedia Commons is the no-key fallback** (`wikimedia_images.py`) and covers most people/places, so Google is rarely required.

And one thing must be true about the current agent:

7. It can discover `SKILL.md` — either via a global skills directory (`~/.claude/skills/`, `~/.codex/skills/`) or via a `CLAUDE.md` / system-prompt import.

## Install prompt contract

- Only ask the user for things you cannot generate — the Groq API key, and confirmation before any package-manager install that needs sudo/admin.
- Two supported layouts. **User layout** (the README default, and what you should assume): the repo *is* the skill directory — `~/.claude/skills/ativa-vid` on macOS/Linux, `%USERPROFILE%\.claude\skills\ativa-vid` on Windows. Nothing to register, no symlink, identical on every OS. **Contributor layout**: repo at `~/Developer/ativa-vid` plus a symlink into the skills dir (step 4) — use it only when the user develops the skill and wants the repo among their projects.
- The skill references helpers by bare name (`transcribe.py`, `render.py`). That works because SKILL.md and `helpers/` ship together — keep them as siblings whichever layout you use.
- Detect the platform before emitting commands. This file's blocks are POSIX shell unless marked; every step has a PowerShell variant for Windows. Do not hand a Windows user `ln`, `brew`, `chmod`, `grep`, `sed`, or `curl -s -w` — `curl` in PowerShell is an alias for `Invoke-WebRequest` and takes different flags.
- After install, verify by running one real command against one real file. Don't declare success on file-existence checks alone.

## Steps

### 1. Clone

**User layout (default).** The repo lands directly in the skills directory, which also completes step 4 — there is nothing to register afterwards.

```bash
# macOS / Linux
mkdir -p "$HOME/.claude/skills"
test -d "$HOME/.claude/skills/ativa-vid" || \
  git clone https://github.com/fillrochaa/edvid "$HOME/.claude/skills/ativa-vid"
```

```powershell
# Windows (PowerShell)
New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
if (-not (Test-Path "$env:USERPROFILE\.claude\skills\ativa-vid")) {
  git clone https://github.com/fillrochaa/edvid "$env:USERPROFILE\.claude\skills\ativa-vid"
}
```

**Contributor layout.** Clone to `~/Developer/ativa-vid` instead, then do step 4 to register it.

If the repo is already there, `git pull --ff-only` and continue.

Everything below refers to that clone as `<ATIVA_VID>`. Substitute the real path.

### 2. Install Python deps

`uv` is the supported installer: it reads `pyproject.toml`, provisions a Python 3.10+ interpreter on its own when the system one is too old, and builds a `.venv` inside the repo. That venv is why helpers run under `uv run python …` — a bare `python` won't see the deps.

```bash
# macOS / Linux — prefer uv; fall back to pip.
command -v uv >/dev/null && uv sync --directory <ATIVA_VID> || pip install -e <ATIVA_VID>
```

```powershell
# Windows (PowerShell)
uv sync --directory <ATIVA_VID>
```

If `uv` is missing: `brew install uv` (macOS), `winget install astral-sh.uv` (Windows), or the installer at https://docs.astral.sh/uv/. On Windows, a `winget install` only reaches `$PATH` in a **new** PowerShell window — reopen the terminal before continuing.

`pyproject.toml` lists `requests`, `pillow`, `numpy`, and `opencv-python-headless==4.10.0.84` (the last one powers the Phase-2 dynamic-camera face/eye tracking in `face_track.py` — keep it pinned to the 4.10 line; 5.x dropped `CascadeClassifier` and breaks Haar detection). No console scripts — helpers are invoked directly as `python helpers/<name>.py`.

### 3. Install ffmpeg

`ffmpeg` and `ffprobe` are hard requirements for Phase 1. Phase 2 uses Remotion (Node.js) — set up in step 6.

```bash
# macOS
command -v ffmpeg >/dev/null || brew install ffmpeg

# Debian / Ubuntu
# sudo apt-get update && sudo apt-get install -y ffmpeg

# Arch
```

```powershell
# Windows (PowerShell)
winget install Gyan.FFmpeg
```

If `brew` / `apt` / `pacman` requires a sudo prompt, tell the user the exact command and wait. Do not invent a password. On Windows, `winget` may need the user to accept a source agreement on first run — let them answer it themselves, then reopen PowerShell so the new `$PATH` takes effect.

### 4. Register the skill with the current agent

**Skip this step entirely on the user layout** — cloning into the skills directory already registered it. This step exists for the contributor layout (repo at `~/Developer/ativa-vid`) and for agents other than Claude Code.

Figure out which agent you are running under, and register once. A link to the whole repo directory is the right shape — helpers/ needs to sit next to SKILL.md.

- **Claude Code** (`~/.claude/` present):

    ```bash
    mkdir -p ~/.claude/skills
    ln -sfn ~/Developer/ativa-vid ~/.claude/skills/ativa-vid
    ```

- **Codex** (`$CODEX_HOME` set, or `~/.codex/` present):

    ```bash
    mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
    ln -sfn ~/Developer/ativa-vid "${CODEX_HOME:-$HOME/.codex}/skills/ativa-vid"
    ```

- **Hermes / Openclaw / another agent with a skills directory**: symlink `~/Developer/ativa-vid` into that agent's skills directory under the name `ativa-vid`. If the agent has no skills directory, add a line to its system prompt / config pointing at `~/Developer/ativa-vid/SKILL.md` (e.g. an `@~/Developer/ativa-vid/SKILL.md` import in a `CLAUDE.md`-equivalent).

- **Windows (PowerShell)**: `ln` doesn't exist, and `New-Item -ItemType SymbolicLink` needs admin rights or Developer Mode. Use a **directory junction**, which needs neither:

    ```powershell
    New-Item -ItemType Junction `
      -Path "$env:USERPROFILE\.claude\skills\ativa-vid" `
      -Target "$env:USERPROFILE\Developer\ativa-vid"
    ```

    If that still fails, don't fight it — the user layout (step 1) removes the need for a link at all.

If you can't tell which agent you're in, ask the user once: "which agent am I running under — Claude Code, Codex, or something else?" Then pick the right target.

### 5. Groq API key

Groq Whisper (`whisper-large-v3`) is the base transcription backend and handles short sources (≤5 min). Without a Groq key, nothing transcribes. (Groq does not diarize speakers or tag audio events — every word gets `speaker_id: speaker_0`.) Long sources (>5 min) prefer the optional `ELEVENLABS_API_KEY` (Scribe) when present — see requirement 6 — but fall back to Groq when it isn't, so Groq is still required.

1. Check existing state in this order and stop at the first hit:

    ```bash
    # macOS / Linux
    # a) env var already exported
    [ -n "$GROQ_API_KEY" ] && echo "env"
    # b) .env at repo root already has it
    grep -q '^GROQ_API_KEY=..' <ATIVA_VID>/.env 2>/dev/null && echo "dotenv"
    ```

    ```powershell
    # Windows (PowerShell)
    if ($env:GROQ_API_KEY) { "env" }
    elseif (Select-String -Path "<ATIVA_VID>\.env" -Pattern '^GROQ_API_KEY=..' -Quiet -EA SilentlyContinue) { "dotenv" }
    ```

2. If neither is set, ask the user exactly once:

    > I need a Groq API key for transcription (word-level timestamps). Grab one at https://console.groq.com/keys and paste it here — I'll write it to the skill's `.env`. Or if you already have it exported as `GROQ_API_KEY`, say "use env" and I'll skip.

    When the user pastes a key, write it to `<ATIVA_VID>/.env`:

    ```bash
    # macOS / Linux
    printf 'GROQ_API_KEY=%s\n' "$KEY" > <ATIVA_VID>/.env
    chmod 600 <ATIVA_VID>/.env
    ```

    ```powershell
    # Windows (PowerShell) — no chmod; NTFS inherits the user-profile ACL
    Set-Content -Path "<ATIVA_VID>\.env" -Value "GROQ_API_KEY=$KEY"
    ```

    Never echo the key back in tool output. Never commit `.env`.

3. Sanity check with a cheap, quota-free call:

    ```bash
    # macOS / Linux
    curl -s -o /dev/null -w '%{http_code}\n' \
      -H "Authorization: Bearer $(sed -n 's/^GROQ_API_KEY=//p' <ATIVA_VID>/.env)" \
      https://api.groq.com/openai/v1/models
    ```

    ```powershell
    # Windows (PowerShell) — `curl` here is an alias for Invoke-WebRequest and
    # does NOT take -s/-o/-w. Use the native cmdlet instead.
    $k = (Select-String -Path "<ATIVA_VID>\.env" -Pattern '^GROQ_API_KEY=(.+)$').Matches.Groups[1].Value
    try {
      Invoke-RestMethod -Uri https://api.groq.com/openai/v1/models `
        -Headers @{ Authorization = "Bearer $k" } | Out-Null
      "200"
    } catch { $_.Exception.Response.StatusCode.value__ }
    ```

    `200` means the key works. `401` means the user pasted a wrong/expired key — ask once more and stop. Anything else (network, 5xx), move on and verify during first real transcription.

### 6. Node.js + the Remotion skill (Phase 2)

Phase 2 (captions, motion graphics, images) is built in Remotion, which needs Node.js 18+ and the `remotion-best-practices` skill.

That skill lives in a **subdirectory** of its repo (`skills/remotion`), so unlike ATIVAVID it can't be cloned into place — the repo root has no SKILL.md and nothing would be discovered. The whole repo is ~400 KB, which makes copying the cheapest answer: no symlink, no junction, no admin rights, and re-running the command IS the update.

Name the destination `remotion-best-practices` — that's the `name:` its own SKILL.md declares, and a folder called `remotion` leaves the two disagreeing.

```bash
# macOS / Linux — Node.js 18+ first (install via nvm/brew if missing)
node --version

git clone -q --depth 1 https://github.com/remotion-dev/skills /tmp/rmskills \
  && rm -rf "$HOME/.claude/skills/remotion-best-practices" \
  && cp -R /tmp/rmskills/skills/remotion "$HOME/.claude/skills/remotion-best-practices" \
  && rm -rf /tmp/rmskills
```

```powershell
# Windows (PowerShell) — Node.js 18+ first
node --version   # if missing: winget install OpenJS.NodeJS.LTS, then reopen PowerShell

$t="$env:TEMP\rmskills"
Remove-Item -Recurse -Force $t,"$env:USERPROFILE\.claude\skills\remotion-best-practices" -EA SilentlyContinue
git clone -q --depth 1 https://github.com/remotion-dev/skills $t
Copy-Item -Recurse "$t\skills\remotion" "$env:USERPROFILE\.claude\skills\remotion-best-practices"
Remove-Item -Recurse -Force $t
```

None of the optional keys (`ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `GOOGLE_API_KEY`/`GOOGLE_CSE_ID` — see requirement 6) are needed at install time. Ask for each **lazily**, the first time its feature is used, and append it to `.env` next to `GROQ_API_KEY`. `ELEVENLABS_API_KEY` is the Phase-1 exception to "Phase 2/3": ask for it the first time a **>5 min source** shows up (long lessons / YouTube), since that's when the auto backend wants Scribe. Image search also works with **zero keys** via Wikimedia Commons, so Phase 2 images are never hard-blocked.

### 7. Verify end-to-end

Run one real thing. Prefer the lightest verification that still proves the pipeline is wired up. Use `uv run` (or activate the venv) so the helper sees its deps — after `uv sync` a bare `python` won't find `opencv`/`numpy`:

```bash
# macOS / Linux
cd <ATIVA_VID>
uv run python helpers/timeline_view.py --help >/dev/null && echo "helpers OK"      # or: python … after pip install -e .
uv run python -c "import cv2; print('opencv', cv2.__version__)"                    # Phase-2 face tracking
ffprobe -hide_banner -filters | grep -qE '\bdeesser\b' && echo "ffmpeg has voice-master filters"   # Phase-1 --voice-master
ffprobe -version | head -1
node --version && echo "node OK (Phase 2)"
```

```powershell
# Windows (PowerShell) — no grep/head; use Select-String and Select-Object
cd <ATIVA_VID>
uv run python helpers/timeline_view.py --help > $null; if ($?) { "helpers OK" }
uv run python -c "import cv2; print('opencv', cv2.__version__)"
if (ffprobe -hide_banner -filters | Select-String -Pattern '\bdeesser\b' -Quiet) { "ffmpeg has voice-master filters" }
ffprobe -version | Select-Object -First 1
node --version; if ($?) { "node OK (Phase 2)" }
```

Full transcription test is optional at install time — it uses Groq credits. Better to wait until the user hands you their first clip.

### 8. Hand off

Tell the user, in one short message:

- Where the skill is installed (the `<ATIVA_VID>` path).
- That they should `cd` into their footage folder and start their agent there (e.g. `claude`).
- That a good first message is: *"edit these into a launch video"* or *"inventory these takes and propose a strategy."*
- That all outputs land in `<videos_dir>/edit/` — the repo stays clean.

## Keeping the skill current

- `git -C <ATIVA_VID> pull --ff-only` pulls the latest code — same command on every OS, and no `cd` needed. The next run picks it up automatically (the clone *is* the skill dir on the user layout; the symlink/junction resolves to it on the contributor layout).
- `git clone` does **not** update an existing install — it fails on a non-empty directory. Clone once, pull forever.
- If `pyproject.toml` changed deps, re-run `uv sync --directory <ATIVA_VID>` (or `pip install -e .`) after pulling.

## Cold-start reminders

- Link the **whole directory**, not just `SKILL.md`. The helpers need to sit next to it. Better still: on the user layout there's no link at all.
- On Windows, prefer a **junction** over a symlink (no admin/Developer Mode needed) — and prefer the user layout over both.
- Detect the shell before emitting commands. PowerShell has no `ln`, `chmod`, `grep`, `sed`, or `head`, and its `curl` is `Invoke-WebRequest` with incompatible flags. Use `Select-String`, `Select-Object -First`, `Set-Content`, `Invoke-RestMethod`.
- After any `winget install`, `$PATH` only refreshes in a **new** PowerShell window. A "command not found" right after a successful install is almost always this.
- Helpers run under `uv run python helpers/<name>.py`. A bare `python` won't see the `.venv` that `uv sync` builds — this is the most common post-install failure.
- If `.env` exists but the key is empty, treat it the same as missing — don't assume existence means validity.
- `ffmpeg` from static builds works fine. Any modern (≥ 4.x) build is enough.
- Node.js 18+ and the `remotion-best-practices` skill are required for Phase 2 (captions, motion graphics, images). Phase 1 (cut + grade) works without them, so a user who only wants a clean cut can start immediately — but set up step 6 so Phase 2 is ready when the cut is approved.
- Remotion projects are scaffolded per-video by copying the skill's own template (`assets/shortform/` or `assets/longform/`) into `<videos_dir>/edit/remotion/` and running `npm install` there — see the references. Nothing is installed globally, and `create-video` is not used: the template carries the compositions the skill knows how to fill, with the Remotion version pinned so an upstream release can't break a render.
- Never run transcription as part of install verification unless the user explicitly asks — Groq usage draws on the user's quota.
- If the user is on Linux without a package manager Claude recognizes, print the manual `ffmpeg` install URL and wait rather than guessing.
