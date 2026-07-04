/* Edvid preview — interactive editing timeline.
 * IMMUTABLE app: everything per-session comes from /api/state (state.json,
 * edl.json) + /gen/* (waveform, thumbs) + /media/* (video, captions, edit-data).
 * User adjustments are POSTed to /api/save → <edit>/preview_edits.json and
 * applied by the skill (which re-renders and bumps state).
 */
'use strict';

// ---------- dom ----------
const $ = (id) => document.getElementById(id);
const video = $('video');
const panel = $('timelinePanel');
const timelineEl = $('timeline');
const rulerCv = $('ruler');
const waveCv = $('wave');
const laneVideo = $('laneVideo');
const laneAudio = $('laneAudio');
const laneCaptions = $('laneCaptions');
const insertTracksEl = $('insertTracks');
const needle = $('needle');
const tooltip = $('tooltip');

// minimal solid icons (design-system consistent — no emoji)
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.2v11.6c0 .9 1 1.5 1.8 1L15 9.2c.8-.5.8-1.7 0-2.2L5.8 1.2C5 .7 4 1.3 4 2.2z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.6" height="12" rx="1"/><rect x="9.4" y="2" width="3.6" height="12" rx="1"/></svg>',
  vol: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11 5.2a3.4 3.4 0 0 1 0 5.6V9.4a2 2 0 0 0 0-2.8V5.2z"/></svg>',
  mute: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11.2 6.2l3.6 3.6m0-3.6l-3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>',
};

const LABEL_W = 86; // .track-label width (content x offset of lanes)
const MIN_SEG = 0.2; // s
const THUMB_EVERY = 2.0;

// ---------- state ----------
let S = {
  state: {}, // state.json
  rendered: [], // ranges as rendered (from edl.json) — the video's truth
  draft: [], // user-editable copy [{source,start,end,beat,removed,orig:{start,end}}]
  videoDuration: 0,
  fps: 24,
  captions: [], // grouped caption lines [{text,start,end}] (rendered space)
  editData: null, // edit-data.json content (phase 2)
  insertsDraft: [], // editable inserts [{kind,label,start,end,ref,orig}]
  wave: null,
  thumbCount: 0,
  tab: 1,
  pps: 10, // px per second (zoom)
  minPps: 4,
  selected: -1, // selected clip index (draft)
  lastSig: '', // change detection
  savedPending: false,
};

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};

// ---------- draft layout (output-timeline positions) ----------
function draftLayout() {
  let t = 0;
  return S.draft.map((r) => {
    if (r.removed) return { ...r, out: t, dur: 0 };
    const dur = r.end - r.start;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
function renderedLayout() {
  let t = 0;
  return S.rendered.map((r) => {
    const dur = r.end - r.start;
    const item = { ...r, out: t, dur };
    t += dur;
    return item;
  });
}
const draftTotal = () => draftLayout().reduce((a, r) => a + r.dur, 0);

// draft time → rendered time (for scrubbing the old render while editing)
function draftToRendered(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = dl.length - 1; i >= 0; i--) {
    const d = dl[i];
    if (d.removed || t < d.out) continue;
    const off = Math.min(t - d.out, (rl[i]?.dur ?? d.dur) - 0.02);
    return (rl[i]?.out ?? d.out) + Math.max(0, off);
  }
  return Math.min(t, S.videoDuration);
}
// rendered time → draft time (needle position during playback)
function renderedToDraft(t) {
  const dl = draftLayout();
  const rl = renderedLayout();
  for (let i = rl.length - 1; i >= 0; i--) {
    const r = rl[i];
    if (t < r.out) continue;
    if (dl[i]?.removed) return dl[i].out; // playing removed material → park at its slot
    const off = Math.min(t - r.out, dl[i]?.dur ?? r.dur);
    return (dl[i]?.out ?? r.out) + off;
  }
  return t;
}

// ---------- dirty tracking ----------
function edlDirty() {
  return S.draft.some((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end);
}
function insertsDirty() {
  return S.insertsDraft.some((c) => c.start !== c.orig.start || c.end !== c.orig.end);
}
function dirtyCount() {
  let n = S.draft.filter((r) => r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length;
  n += S.insertsDraft.filter((c) => c.start !== c.orig.start || c.end !== c.orig.end).length;
  return n;
}
function refreshHeader() {
  const n = dirtyCount();
  $('dirtyPill').classList.toggle('hidden', n === 0);
  $('dirtyCount').textContent = n;
  $('btnSave').classList.toggle('hidden', n === 0);
  $('btnDiscard').classList.toggle('hidden', n === 0);
  $('savedPill').classList.toggle('hidden', !(S.savedPending && n === 0));
}

// ---------- data loading ----------
async function poll() {
  try {
    const res = await fetch('/api/state');
    const data = await res.json();
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration]);
    if (sig !== S.lastSig) {
      const hadEdits = dirtyCount() > 0;
      if (!hadEdits) {
        S.lastSig = sig;
        await applyState(data);
      } else {
        toast('Novo estado disponível — salve ou descarte seus ajustes para atualizar', 4000);
      }
    }
  } catch (e) { /* server restarting; keep polling */ }
  setTimeout(poll, 2000);
}

async function applyState(data) {
  S.state = data.state || {};
  S.mtimes = data.mtimes || {};
  S.videoDuration = data.videoDuration || 0;
  S.fps = S.state.fps || 24;
  S.savedPending = !!data.hasPendingEdits;

  $('projectName').textContent = S.state.project || 'Edvid';
  $('stateMessage').textContent = S.state.message || '';

  const ranges = (data.edl && data.edl.ranges) || [];
  S.rendered = ranges.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '' }));
  S.draft = S.rendered.map((r) => ({ ...r, removed: false, orig: { start: r.start, end: r.end } }));
  S.selected = -1;

  const hasVideo = S.videoDuration > 0;
  $('emptyState').classList.toggle('hidden', hasVideo);
  $('playerWrap').classList.toggle('hidden', !hasVideo);
  $('timelinePanel').classList.toggle('hidden', !hasVideo);

  if (hasVideo) {
    updateVideoSrc();
    loadWave();
    loadThumbsMeta();
  }

  // phase 2 data
  const tab2 = document.querySelector('[data-tab="2"]');
  tab2.disabled = (S.state.phase || 1) < 2;
  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  if ((S.state.phase || 1) >= 2) {
    if (S.state.captions) {
      try {
        const caps = await (await fetch(`/media/${S.state.captions}?v=${Date.now()}`)).json();
        S.captions = groupCaptions(caps);
      } catch (e) { /* absent yet */ }
    }
    if (S.state.editData) {
      try {
        S.editData = await (await fetch(`/media/${S.state.editData}?v=${Date.now()}`)).json();
        buildInsertsDraft();
      } catch (e) { /* absent yet */ }
    }
  }

  fitZoom();
  renderAll();
  refreshHeader();
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  const rel = (S.tab === 2 && S.state.finalVideo) ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  const vsrc = `/media/${rel}?v=${(S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || 0}`;
  if (video.dataset.src === vsrc) return;
  const t = video.currentTime;
  const wasPlaying = !video.paused && !video.ended;
  video.dataset.src = vsrc;
  video.src = vsrc;
  video.currentTime = t;
  if (wasPlaying) video.play();
}

function groupCaptions(caps) {
  // mirror the template: lines of ≤3 words, break on punctuation
  const lines = [];
  let cur = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text)) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  return lines.map((line) => ({
    text: line.map((w) => w.text.replace(/[.,!?…]+$/, '')).join(' '),
    start: line[0].startMs / 1000,
    end: line[line.length - 1].endMs / 1000,
  }));
}

function buildInsertsDraft() {
  const d = S.editData;
  const list = [];
  if (d.hook && d.hook.enabled) {
    list.push({ kind: 'hook', label: `HOOK — ${(d.hook.lines || []).join(' / ')}`, start: 0, end: d.hook.endSec || 4 });
  }
  (d.inserts || []).forEach((it, i) => {
    list.push({ kind: 'insert', label: (it.src || '').split('/').pop(), start: +it.start, end: +it.end, ref: i });
  });
  (d.behind || []).forEach((b, i) => {
    list.push({ kind: 'behind', label: `BEHIND ${b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop()}`, start: +b.start, end: +b.start + +b.dur, ref: i });
  });
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
}

async function loadWave() {
  try {
    S.wave = await (await fetch('/gen/waveform.json')).json();
    drawWave();
  } catch (e) { S.wave = null; }
}
async function loadThumbsMeta() {
  try {
    const meta = await (await fetch('/gen/thumbs/meta.json')).json();
    S.thumbCount = meta.count || 0;
    renderClips();
  } catch (e) { S.thumbCount = 0; }
}

// ---------- zoom / layout ----------
function contentWidth() { return LABEL_W + Math.max(draftTotal(), S.videoDuration, 1) * S.pps + 14; }
function fitZoom() {
  const avail = panel.clientWidth - LABEL_W - 40;
  const total = Math.max(draftTotal(), S.videoDuration, 1);
  S.minPps = Math.max(1, avail / total);
  S.pps = S.minPps;
  $('zoom').value = 0;
}
function setZoom(v) { // slider 0..100 → minPps..200
  const maxPps = 200;
  S.pps = S.minPps * Math.pow(maxPps / S.minPps, v / 100);
  renderAll();
}

// ---------- rendering ----------
function renderAll() {
  timelineEl.style.width = `${contentWidth()}px`;
  renderClips();
  renderChips();
  drawRuler();
  drawWave();
  positionNeedle();
}

function renderClips() {
  laneVideo.innerHTML = '';
  const dl = draftLayout();
  const rl = renderedLayout();
  const editable = S.tab === 1;
  dl.forEach((r, i) => {
    if (r.removed && r.dur === 0) {
      // removed: show a slim ghost at its slot
      const g = el('div', 'clip removed', laneVideo);
      g.style.left = `${r.out * S.pps}px`;
      g.style.width = `${Math.max((r.orig.end - r.orig.start) * S.pps * 0.4, 34)}px`;
      g.dataset.i = i;
      g.title = 'clique e pressione delete para restaurar';
      return;
    }
    const c = el('div', 'clip', laneVideo);
    c.style.left = `${r.out * S.pps}px`;
    c.style.width = `${Math.max(r.dur * S.pps, 8)}px`;
    c.dataset.i = i;
    if (i === S.selected) c.classList.add('selected');
    if (r.start !== r.orig.start || r.end !== r.orig.end) c.classList.add('dirty');

    // filmstrip from the rendered cut
    if (S.thumbCount > 0 && rl[i]) {
      const strip = el('div', 'thumbs', c);
      const first = Math.floor(rl[i].out / THUMB_EVERY);
      const n = Math.ceil(rl[i].dur / THUMB_EVERY) + 1;
      for (let k = 0; k < n; k++) {
        const idx = first + k + 1; // ffmpeg %04d is 1-based
        if (idx > S.thumbCount) break;
        const img = el('img', '', strip);
        img.src = `/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = `${THUMB_EVERY * S.pps}px`;
        img.style.objectFit = 'cover';
      }
    }
    const lab = el('div', 'clip-label', c);
    lab.textContent = `${r.beat || r.source} `;
    const dur = el('div', 'clip-dur', c);
    dur.textContent = `${r.dur.toFixed(2)}s`;

    if (editable) {
      el('div', 'handle l', c).dataset.i = i;
      el('div', 'handle r', c).dataset.i = i;
    }
  });
}

function renderChips() {
  const phase2 = S.tab === 2;
  $('trkCaptions').classList.toggle('hidden', !phase2);
  insertTracksEl.classList.toggle('hidden', !phase2);
  insertTracksEl.innerHTML = '';
  if (!phase2) return;

  laneCaptions.innerHTML = '';
  for (const c of S.captions) {
    const start = renderedToDraft(c.start);
    const end = renderedToDraft(c.end);
    const chip = el('div', 'chip caption', laneCaptions);
    chip.style.left = `${start * S.pps}px`;
    chip.style.width = `${Math.max((end - start) * S.pps, 6)}px`;
    chip.textContent = c.text;
    chip.title = c.text;
  }

  // inserts → numbered tracks; overlapping elements stack onto extra tracks
  const order = S.insertsDraft.map((c, i) => ({ c, i }))
    .sort((a, b) => a.c.start - b.c.start || a.c.end - b.c.end);
  const trackEnd = []; // last occupied end per track
  const assign = new Map();
  for (const { c, i } of order) {
    let t = trackEnd.findIndex((end) => c.start >= end - 1e-6);
    if (t < 0) { t = trackEnd.length; trackEnd.push(0); }
    trackEnd[t] = c.end;
    assign.set(i, t);
  }
  const lanes = [];
  for (let t = 0; t < Math.max(trackEnd.length, 1); t++) {
    const trk = el('div', 'track', insertTracksEl);
    el('div', 'track-label orange', trk).textContent = `TRACK ${t + 1}`;
    lanes.push(el('div', 'lane', trk));
  }
  S.insertsDraft.forEach((c, i) => {
    const chip = el('div', `chip insert ${c.kind === 'hook' ? 'hook' : ''}`, lanes[assign.get(i) ?? 0]);
    chip.style.left = `${c.start * S.pps}px`;
    chip.style.width = `${Math.max((c.end - c.start) * S.pps, 10)}px`;
    chip.textContent = c.label;
    chip.title = c.label;
    chip.dataset.i = i;
    if (c.start !== c.orig.start || c.end !== c.orig.end) chip.classList.add('dirty');
    el('div', 'handle l', chip).dataset.i = i;
    el('div', 'handle r', chip).dataset.i = i;
  });
}

// ---------- canvases (viewport-sized, redrawn on scroll) ----------
function canvasSetup(cv, lane) {
  const dpr = window.devicePixelRatio || 1;
  const w = panel.clientWidth;
  const h = lane.clientHeight;
  cv.width = w * dpr;
  cv.height = h * dpr;
  cv.style.width = `${w}px`;
  cv.style.height = `${h}px`;
  cv.style.position = 'absolute';
  // lanes start LABEL_W into the scrolled content — offset the viewport-sized
  // canvas so it covers exactly the visible strip of the lane
  const left = Math.max(0, panel.scrollLeft - LABEL_W);
  cv.style.left = `${left}px`;
  const ctx = cv.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return { ctx, w, h, x0: left };
}

function drawRuler() {
  const { ctx, w, h, x0 } = canvasSetup(rulerCv, rulerCv.parentElement);
  const laneX0 = x0; // canvas positioned at scrollLeft within lane coords
  const t0 = laneX0 / S.pps;
  const t1 = (laneX0 + w) / S.pps;
  // tick step: nice value ≥ 60px apart
  const steps = [0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120];
  const step = steps.find((s) => s * S.pps >= 56) || 300;
  ctx.font = '600 9.5px Poppins, sans-serif';
  ctx.fillStyle = 'rgba(139,148,163,0.9)';
  ctx.strokeStyle = 'rgba(255,255,255,0.14)';
  for (let t = Math.floor(t0 / step) * step; t <= t1; t += step) {
    if (t < 0) continue;
    const x = t * S.pps - laneX0;
    ctx.beginPath();
    ctx.moveTo(x, h - 7);
    ctx.lineTo(x, h);
    ctx.stroke();
    ctx.fillText(fmt(t), x + 3, h - 9);
    // minor ticks
    const minor = step / 5;
    for (let m = 1; m < 5; m++) {
      const xm = (t + m * minor) * S.pps - laneX0;
      ctx.beginPath();
      ctx.moveTo(xm, h - 3.5);
      ctx.lineTo(xm, h);
      ctx.stroke();
    }
  }
}

function drawWave() {
  if (!S.wave) return;
  const { ctx, w, h, x0 } = canvasSetup(waveCv, laneAudio);
  const mid = h / 2;
  ctx.strokeStyle = 'rgba(168,194,43,0.06)';
  ctx.beginPath(); ctx.moveTo(0, mid); ctx.lineTo(w, mid); ctx.stroke();
  ctx.fillStyle = 'rgba(168,194,43,0.75)';
  const pps = S.wave.peaksPerSec;
  for (let px = 0; px < w; px++) {
    const tDraft = (x0 + px) / S.pps;
    if (tDraft > draftTotal()) break;
    const tRend = draftToRendered(tDraft);
    const idx = Math.floor(tRend * pps);
    if (idx < 0 || idx >= S.wave.max.length) continue;
    const hi = (S.wave.max[idx] / 100) * (mid - 2);
    const lo = (S.wave.min[idx] / 100) * (mid - 2);
    ctx.fillRect(px, mid - hi, 1, Math.max(1, hi - lo));
  }
}

// ---------- needle / playback sync ----------
function positionNeedle() {
  const tDraft = renderedToDraft(video.currentTime || 0);
  needle.style.left = `${LABEL_W + tDraft * S.pps}px`;
  $('timeNow').textContent = fmt(tDraft);
  $('timeTotal').textContent = fmt(draftTotal() || S.videoDuration);
}
function rafLoop() {
  positionNeedle();
  if (!video.paused && !video.ended) {
    // keep needle visible
    const x = LABEL_W + renderedToDraft(video.currentTime) * S.pps;
    const right = panel.scrollLeft + panel.clientWidth;
    if (x > right - 80) panel.scrollLeft = x - panel.clientWidth * 0.25;
  }
  requestAnimationFrame(rafLoop);
}

function seekDraft(tDraft) {
  tDraft = Math.max(0, Math.min(tDraft, draftTotal() || S.videoDuration));
  video.currentTime = draftToRendered(tDraft);
  positionNeedle();
}

// ---------- interactions ----------
let drag = null; // {type:'scrub'|'trim'|'chip-trim'|'chip-move', ...}

panel.addEventListener('pointerdown', (e) => {
  const handle = e.target.closest('.handle');
  const clip = e.target.closest('.clip');
  const chip = e.target.closest('.chip.insert');

  if (handle && clip && S.tab === 1) {
    const i = +handle.dataset.i;
    drag = { type: 'trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, r: { ...S.draft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (handle && chip && S.tab === 2) {
    const i = +handle.dataset.i;
    drag = { type: 'chip-trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, c: { ...S.insertsDraft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (chip && S.tab === 2) {
    const i = +chip.dataset.i;
    drag = { type: 'chip-move', i, x0: e.clientX, c: { ...S.insertsDraft[i] } };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (clip) {
    S.selected = +clip.dataset.i;
    renderClips();
    return;
  }
  // background / ruler → scrub
  const rect = timelineEl.getBoundingClientRect();
  const t = (e.clientX - rect.left - LABEL_W) / S.pps;
  drag = { type: 'scrub' };
  seekDraft(t);
  try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
});

panel.addEventListener('pointermove', (e) => {
  if (!drag) return;
  if (drag.type === 'scrub') {
    const rect = timelineEl.getBoundingClientRect();
    seekDraft((e.clientX - rect.left - LABEL_W) / S.pps);
    return;
  }
  const dt = (e.clientX - drag.x0) / S.pps;

  if (drag.type === 'trim') {
    const r = S.draft[drag.i];
    if (drag.side === 'l') {
      r.start = Math.min(Math.max(0, drag.r.start + dt), r.end - MIN_SEG);
    } else {
      r.end = Math.max(drag.r.end + dt, r.start + MIN_SEG);
      const srcDur = (S.state.sourceDurations || {})[r.source];
      if (srcDur) r.end = Math.min(r.end, srcDur);
    }
    renderClips();
    drawWave();
    refreshHeader();
    const d = drag.side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
    showTooltip(e, `${fmt(r.start)} → ${fmt(r.end)} <span class="delta">(${d >= 0 ? '+' : ''}${d.toFixed(2)}s)</span>`);
  } else if (drag.type === 'chip-trim') {
    const c = S.insertsDraft[drag.i];
    if (drag.side === 'l') c.start = Math.min(Math.max(0, drag.c.start + dt), c.end - 0.15);
    else c.end = Math.max(drag.c.end + dt, c.start + 0.15);
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'chip-move') {
    const c = S.insertsDraft[drag.i];
    const dur = drag.c.end - drag.c.start;
    c.start = Math.max(0, drag.c.start + dt);
    c.end = c.start + dur;
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  }
});

['pointerup', 'pointercancel'].forEach((ev) =>
  panel.addEventListener(ev, () => { drag = null; hideTooltip(); })
);

// double-click a clip = reset it
laneVideo.addEventListener('dblclick', (e) => {
  const clip = e.target.closest('.clip');
  if (!clip) return;
  const r = S.draft[+clip.dataset.i];
  r.start = r.orig.start; r.end = r.orig.end; r.removed = false;
  renderAll(); refreshHeader();
});

// keyboard
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT') return;
  if (e.code === 'Space') {
    e.preventDefault();
    video.paused ? video.play() : video.pause();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = e.shiftKey ? 1 : 1 / S.fps;
    seekDraft(renderedToDraft(video.currentTime) + (e.key === 'ArrowRight' ? step : -step));
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.selected >= 0 && S.tab === 1) {
    const r = S.draft[S.selected];
    r.removed = !r.removed;
    renderAll(); refreshHeader();
  }
});

// transport
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
$('btnPlay').addEventListener('click', () => {
  video.paused ? video.play() : video.pause();
});
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; });
$('btnMute').addEventListener('click', () => {
  video.muted = !video.muted;
  $('btnMute').innerHTML = video.muted ? ICON.mute : ICON.vol;
});
$('zoom').addEventListener('input', (e) => setZoom(+e.target.value));
$('btnFit').addEventListener('click', () => { fitZoom(); renderAll(); });
panel.addEventListener('scroll', () => requestAnimationFrame(() => { drawRuler(); drawWave(); }));
window.addEventListener('resize', () => { fitZoom(); renderAll(); });

// tabs
document.querySelectorAll('.tab').forEach((tab) =>
  tab.addEventListener('click', () => {
    if (tab.disabled) return;
    document.querySelectorAll('.tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    S.tab = +tab.dataset.tab;
    S.selected = -1;
    updateVideoSrc(); // Fase 2 plays the Phase-2 render when available
    renderAll();
  })
);

// ---------- save / discard ----------
$('btnSave').addEventListener('click', async () => {
  const payload = { type: 'timeline-edits' };
  if (edlDirty()) {
    payload.edl = {
      ranges: S.draft.filter((r) => !r.removed).map((r) => ({
        source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
      })),
      removed: S.draft.filter((r) => r.removed).map((r) => ({ source: r.source, beat: r.beat, start: r.orig.start, end: r.orig.end })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  if (insertsDirty()) {
    payload.editData = {
      inserts: S.insertsDraft.filter((c) => c.kind === 'insert').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), end: +c.end.toFixed(3) })),
      hook: S.insertsDraft.filter((c) => c.kind === 'hook').map((c) => ({ endSec: +c.end.toFixed(3) }))[0] || null,
      behind: S.insertsDraft.filter((c) => c.kind === 'behind').map((c) => ({ ref: c.ref, start: +c.start.toFixed(3), dur: +(c.end - c.start).toFixed(3) })),
    };
  }
  const res = await fetch('/api/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
  if ((await res.json()).ok) {
    S.savedPending = true;
    S.draft.forEach((r) => { r.orig = { start: r.start, end: r.end }; if (r.removed) r.hardRemoved = true; });
    // keep visual state but clear dirty counters
    S.draft = S.draft.filter((r) => !r.removed);
    S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
    renderAll(); refreshHeader();
    toast('✓ Ajustes salvos em preview_edits.json — peça ao Claude para aplicar e re-renderizar', 5000);
  } else {
    toast('Erro ao salvar — o servidor está de pé?', 4000);
  }
});

$('btnDiscard').addEventListener('click', () => {
  S.draft = S.rendered.map((r) => ({ ...r, removed: false, orig: { start: r.start, end: r.end } }));
  buildInsertsDraft();
  S.selected = -1;
  renderAll(); refreshHeader();
  toast('Ajustes descartados', 2000);
});

// ---------- ui helpers ----------
function showTooltip(e, html) {
  tooltip.innerHTML = html;
  tooltip.style.left = `${e.clientX + 14}px`;
  tooltip.style.top = `${e.clientY - 34}px`;
  tooltip.classList.remove('hidden');
}
function hideTooltip() { tooltip.classList.add('hidden'); }
let toastTimer = null;
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}

// ---------- boot ----------
poll();
rafLoop();
