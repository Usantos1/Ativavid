/* ATIVAVID preview — interactive editing timeline.
 * IMMUTABLE app: everything per-session comes from /api/state (state.json,
 * edl.json) + /gen/* (waveform, thumbs) + /media/* (video, captions, edit-data).
 * User adjustments are POSTed to /api/save → <edit>/preview_edits.json and
 * applied by the skill (which re-renders and bumps state).
 *
 * Three interaction rules worth knowing before editing this file:
 *  - Tracks are identified by ICON only (ICON.captions/video/audio/inserts/music),
 *    painted into .tl-chip cards. LABEL_W must stay in sync with .track-label's
 *    width. The gutter masks the lanes with .track-label::before painted in
 *    --panel-bg (the panel is a solid surface for exactly this reason), pinned by
 *    native position:sticky. #gutterLine is the divider, pinned by a scroll-driven
 *    CSS timeline on `translate`. Do NOT re-drive either from a JS scroll handler
 *    or a clip-path animation — both lag a frame and the column visibly breathes
 *    while scrolling. JS only publishes --max-scroll (on zoom/resize).
 *  - Correction markers: M (or the transport button) drops an IN, the next M closes
 *    the range and opens the note editor. They ride in S.notes and ship as
 *    payload.notes on save; watch_edits.py turns each save into a chat notification.
 *  - Zoom: the slider is anchored on the needle, trackpad pinch (wheel+ctrlKey)
 *    on the pointer. Both go through applyZoom(pps, t, anchorX) — never on scroll 0.
 *  - Layout follows the SOURCE aspect: portrait clips get body.portrait (player
 *    right at full column height up to the appbar; transport stays on the
 *    timeline column and stops at the preview). Landscape keeps the stacked
 *    layout. #stage keeps the split from swallowing anything below it.
 *  - Timecode uses a MONOSPACE stack: Poppins ships no tabular figures, so
 *    `font-variant-numeric: tabular-nums` silently does nothing and every digit
 *    change resized the readout, shoving the whole transport row sideways.
 *  - No glows anywhere — depth shadows are fine, coloured halos are not.
 *  - The style gate (STYLE_CATALOG → #styleSetup) stands BETWEEN the phases: when
 *    state.awaitingStyle is true it replaces the stage entirely, so the choice of
 *    editing style / caption style / edit elements cannot be skipped. It saves to
 *    <edit>/preview_style.json (never preview_edits.json — different screens,
 *    different moments, one would clobber the other).
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
  // "ajustar a janela": as duas bordas e a seta abrindo entre elas
  // Apagar para um lado, no desenho do CapCut: a barra e o corte e o
  // colchete e o lado que FICA; o bloco apagado some.
  // So formas PREENCHIDAS: o `.btn.icon svg` do app forca `fill:
  // currentColor`, e o CSS ganha do atributo `fill="none"` — icone de traco
  // virava mancha (foi o que saiu na 3.75, e o usuario viu botao vazio).
  cortarEsq: '<svg viewBox="0 0 16 16"><rect x="1.4" y="3.6" width="4.6" height="8.8" rx="1.1" opacity=".38"/><rect x="7.1" y="1.6" width="1.8" height="12.8" rx=".9"/><path d="M10.6 3.6h3.4v1.7h-1.7v5.4h1.7v1.7h-3.4z"/></svg>',
  cortarDir: '<svg viewBox="0 0 16 16"><rect x="10" y="3.6" width="4.6" height="8.8" rx="1.1" opacity=".38"/><rect x="7.1" y="1.6" width="1.8" height="12.8" rx=".9"/><path d="M5.4 3.6H2v1.7h1.7v5.4H2v1.7h3.4z"/></svg>',
  fit: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3v10M14 3v10"/><path d="M4.8 8h6.4"/><path d="M6.6 6.2L4.8 8l1.8 1.8M9.4 6.2L11.2 8l-1.8 1.8"/></svg>',
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.2v11.6c0 .9 1 1.5 1.8 1L15 9.2c.8-.5.8-1.7 0-2.2L5.8 1.2C5 .7 4 1.3 4 2.2z"/></svg>',
  pause: '<svg viewBox="0 0 16 16"><rect x="3" y="2" width="3.6" height="12" rx="1"/><rect x="9.4" y="2" width="3.6" height="12" rx="1"/></svg>',
  vol: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11 5.2a3.4 3.4 0 0 1 0 5.6V9.4a2 2 0 0 0 0-2.8V5.2z"/></svg>',
  mute: '<svg viewBox="0 0 16 16"><path d="M2 6v4h2.8L9 13.4V2.6L4.8 6H2z"/><path d="M11.2 6.2l3.6 3.6m0-3.6l-3.6 3.6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/></svg>',
  // track identity — icons replace text labels (data-icon in index.html)
  captions: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="3.4" y="8.4" width="4.4" height="1.5" rx=".75"/><rect x="8.9" y="8.4" width="3.7" height="1.5" rx=".75"/></svg>',
  video: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M6.5 5.9v4.2c0 .4.44.64.79.42l3.3-2.1a.5.5 0 0 0 0-.85l-3.3-2.1a.5.5 0 0 0-.79.43z"/></svg>',
  audio: '<svg viewBox="0 0 16 16"><path d="M2.4 6.2v3.6h2.4l3.5 2.8V3.4L4.8 6.2H2.4z"/><path d="M10.5 5.7a3.2 3.2 0 0 1 0 4.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M12.4 3.9a5.7 5.7 0 0 1 0 8.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  inserts: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.2" width="13.6" height="9.6" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.3" cy="6.6" r="1.15"/><path d="M2.6 11.7l3-2.9a1 1 0 0 1 1.34-.05l1.84 1.58 1.5-1.24a1 1 0 0 1 1.29.02l1.72 1.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  music: '<svg viewBox="0 0 16 16"><path d="M13.1 1.9 6.6 3.5a.8.8 0 0 0-.6.78v6.06a2.25 2.25 0 1 0 1.5 2.12V6.6l5-1.22v3.5a2.25 2.25 0 1 0 1.5 2.12V2.68a.8.8 0 0 0-.9-.78z"/></svg>',
  text: '<svg viewBox="0 0 16 16"><path d="M2 2.6h12v2.5h-1.5V4.1H8.75v8.1h1.6v1.3H5.65v-1.3h1.6V4.1H3.5v1H2V2.6z"/></svg>',
  notes: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
  // O marcador do CapCut: a fita com o entalhe embaixo. A bandeirinha de
  // mastro que estava aqui nao e o desenho que o usuario reconhece.
  flag: '<svg viewBox="0 0 16 16"><path d="M4.4 1.8h7.2a1.2 1.2 0 0 1 1.2 1.2v11.2L8 11.3l-4.8 2.9V3a1.2 1.2 0 0 1 1.2-1.2z"/></svg>',
  // Ponteiro de selecao — a seta de sempre, com o rastro do laco atras
  laco: '<svg viewBox="0 0 16 16"><path d="M3.4 1.6 12.2 7.4a.5.5 0 0 1-.16.9l-3.3.78-1.5 3.1a.5.5 0 0 1-.92-.08L3.4 1.6z"/><path d="M12.6 11.2c1.2.5 1.9 1.2 1.9 2 0 1.4-2.4 2.2-5.2 2.2s-5.2-.8-5.2-2.2c0-.6.4-1.1 1.1-1.5" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-dasharray="2.2 2"/></svg>',
  folder: '<svg viewBox="0 0 16 16"><path d="M1.6 3.6c0-.66.54-1.2 1.2-1.2h3.1c.4 0 .78.2 1 .53l.6.87h5.9c.66 0 1.2.54 1.2 1.2v7.4c0 .66-.54 1.2-1.2 1.2H2.8c-.66 0-1.2-.54-1.2-1.2V3.6z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  sun: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="3.1" fill="none" stroke="currentColor" stroke-width="1.4"/><g stroke="currentColor" stroke-width="1.4" stroke-linecap="round"><path d="M8 1.4v1.7M8 12.9v1.7M14.6 8h-1.7M3.1 8H1.4M12.6 3.4l-1.2 1.2M4.6 11.4l-1.2 1.2M12.6 12.6l-1.2-1.2M4.6 4.6L3.4 3.4"/></g></svg>',
  moon: '<svg viewBox="0 0 16 16"><path d="M13.8 9.9A6 6 0 1 1 6.1 2.2a5 5 0 0 0 7.7 7.7z"/></svg>',
  undo: '<svg viewBox="0 0 16 16"><path d="M4.2 4.6H10a4 4 0 1 1 0 8H6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M6.6 1.8 3.2 4.6l3.4 2.8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  redo: '<svg viewBox="0 0 16 16"><path d="M11.8 4.6H6a4 4 0 1 0 0 8h4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M9.4 1.8l3.4 2.8-3.4 2.8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  // a razor blade, not scissors — scissors implies "remove a piece"; this is
  // "cut here, keep both sides", the same visual shorthand every NLE uses
  razor: '<svg viewBox="0 0 16 16"><path d="M8 1v9.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M8 10.4 4.6 15h2.1L8 13.2 9.3 15h2.1z" fill="currentColor"/><circle cx="8" cy="1.6" r="1.1" fill="currentColor"/></svg>',
  imgSearch: '<svg viewBox="0 0 16 16"><rect x="1.2" y="2.6" width="13.6" height="10.8" rx="2.2" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.4" cy="6.2" r="1.2"/><path d="M2.4 12.2l3.2-3.1a1 1 0 011.35-.05l1.9 1.62 1.5-1.25a1 1 0 011.3.02l2 1.75" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  // a frame with a corner folded down — "this single frame", not "a photo"
  cover: '<svg viewBox="0 0 16 16"><path d="M2.6 1.6h6.6l4.2 4.2v8.6a.6.6 0 0 1-.6.6H2.6a.6.6 0 0 1-.6-.6V2.2a.6.6 0 0 1 .6-.6z" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M9.2 1.6v4.2h4.2" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><circle cx="5.6" cy="9.2" r="1.15"/><path d="M3.2 13l2.5-2.4a.9.9 0 0 1 1.2 0l1.5 1.3 1.2-1a.9.9 0 0 1 1.15.02l1.5 1.3" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  trash: '<svg viewBox="0 0 16 16"><path d="M3.2 4.2h9.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M6.1 4.1V2.8c0-.4.32-.7.7-.7h2.4c.38 0 .7.3.7.7v1.3" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M4.4 4.2 5 13.1c.06.7.64 1.2 1.34 1.2h3.32c.7 0 1.28-.5 1.34-1.2l.6-8.9" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>',
  appendCta: '<svg viewBox="0 0 16 16"><rect x="1" y="3" width="14" height="10" rx="2.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 5.4v5.2M5.4 8h5.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  lock: '<svg viewBox="0 0 16 16"><rect x="3.2" y="7.2" width="9.6" height="7" rx="1.4" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M5.2 7.2V5.4a2.8 2.8 0 0 1 5.6 0v1.8" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
};

// the "Nenhuma" card's mark — a plain slash-circle, not a rendered look (there
// is nothing to render), so it has to read as "off" at a glance
const NONE_ICON = '<svg viewBox="0 0 16 16" width="22" height="22"><circle cx="8" cy="8" r="6.4" fill="none" stroke="rgba(255,255,255,.32)" stroke-width="1.4"/><path d="M3.9 3.9l8.2 8.2" stroke="rgba(255,255,255,.32)" stroke-width="1.4" stroke-linecap="round"/></svg>';

/* ---------- style catalog (the Fase 1 → Fase 2 gate) ----------
 * The one place that knows which looks ATIVAVID can build. It is APP-level, not
 * session-level: a new editing style or caption style is a new entry here plus
 * its implementation in the track reference — never a per-session UI.
 * The user's pick ships to <edit>/preview_style.json; the skill reads it once,
 * at the gate, and builds Fase 2 from it.
 */
const STYLE_CATALOG = {
  edits: [
    {
      // First on purpose: defaultStyle() takes edits[0], so this is also the
      // default for every new project — a clean full-frame cut, with inserts as
      // something the user opts into.
      id: 'limpa',
      name: 'Limpo',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="48" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="14" y="14" width="38" height="4.4" rx="2.2" fill="rgba(255,255,255,.5)"/>
        <rect x="20" y="21.5" width="26" height="4.4" rx="2.2" fill="rgba(255,255,255,.3)"/>
        <rect x="12" y="74" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'split',
      name: 'Tela dividida',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="36" rx="5" fill="rgba(255,119,19,.16)"/>
        <circle cx="17" cy="15" r="3.6" fill="rgba(255,119,19,.6)"/>
        <path d="M6 36l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgba(255,119,19,.6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M3 40.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        <rect x="3" y="42" width="60" height="73" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="70" r="12" fill="rgba(255,255,255,.16)"/>
        <path d="M15 115a18 18 0 0136 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="12" y="35" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="39.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="39.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="39.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'split2',
      name: 'Tela dividida com mídia',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="65" rx="5" fill="rgba(255,255,255,.05)"/>
        <circle cx="33" cy="24" r="11" fill="rgba(255,255,255,.16)"/>
        <path d="M16 68a17 17 0 0134 0z" fill="rgba(255,255,255,.16)"/>
        <path d="M3 69.5h60" stroke="rgba(255,255,255,.5)" stroke-width="1.2"/>
        <rect x="3" y="71" width="60" height="44" rx="5" fill="rgba(255,119,19,.16)"/>
        <circle cx="17" cy="83" r="3.6" fill="rgba(255,119,19,.6)"/>
        <path d="M6 111l11-11a2 2 0 013 0l7 7 5-4a2 2 0 013 0l11 8" fill="none" stroke="rgba(255,119,19,.6)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        <rect x="12" y="58" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="62.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="62.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="62.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'moldura',
      name: 'Moldura',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="2" y="2" width="62" height="114" rx="6" fill="rgba(255,119,19,.22)"/>
        <rect x="7" y="9" width="52" height="100" rx="6" fill="rgba(255,255,255,.07)"/>
        <circle cx="33" cy="48" r="11" fill="rgba(255,255,255,.16)"/>
        <path d="M16 109a17 17 0 0134 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="14" y="76" width="38" height="10" rx="5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="18" y="80" width="10" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="80" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="80" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'barra',
      name: 'Barra inferior',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="82" rx="5" fill="rgba(255,255,255,.07)"/>
        <circle cx="33" cy="38" r="12" fill="rgba(255,255,255,.16)"/>
        <path d="M14 85a19 19 0 0138 0z" fill="rgba(255,255,255,.16)"/>
        <path d="M3 85.5h60" stroke="rgba(255,255,255,.4)" stroke-width="1"/>
        <rect x="3" y="87" width="60" height="28" rx="5" fill="rgba(255,255,255,.03)"/>
        <rect x="12" y="94" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="98.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="98.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="98.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'desfocado',
      name: 'Fundo desfocado',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="2" y="2" width="62" height="114" rx="6" fill="rgba(255,255,255,.05)"/>
        <circle cx="14" cy="20" r="10" fill="rgba(255,255,255,.06)"/>
        <circle cx="55" cy="45" r="13" fill="rgba(255,255,255,.05)"/>
        <circle cx="12" cy="96" r="12" fill="rgba(255,255,255,.06)"/>
        <rect x="9" y="12" width="48" height="94" rx="7" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.2)"/>
        <circle cx="33" cy="48" r="10" fill="rgba(255,255,255,.18)"/>
        <path d="M17 106a16 16 0 0132 0z" fill="rgba(255,255,255,.18)"/>
        <rect x="15" y="74" width="36" height="10" rx="5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="19" y="78" width="10" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="31" y="78" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'degrade',
      name: 'Degradê',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <defs><linearGradient id="gDeg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0.5" stop-color="rgba(0,0,0,0)"/>
          <stop offset="1" stop-color="rgba(0,0,0,.8)"/>
        </linearGradient></defs>
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.07)"/>
        <circle cx="33" cy="44" r="13" fill="rgba(255,255,255,.16)"/>
        <path d="M12 112a21 21 0 0142 0z" fill="rgba(255,255,255,.16)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="url(#gDeg)"/>
        <rect x="12" y="92" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="96.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="96.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="96.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'vinheta',
      name: 'Vinheta',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <defs><radialGradient id="gVin" cx="50%" cy="50%" r="70%">
          <stop offset="0.45" stop-color="rgba(0,0,0,0)"/>
          <stop offset="1" stop-color="rgba(0,0,0,.82)"/>
        </radialGradient></defs>
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.10)"/>
        <circle cx="33" cy="44" r="13" fill="rgba(255,255,255,.18)"/>
        <path d="M12 112a21 21 0 0142 0z" fill="rgba(255,255,255,.18)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="url(#gVin)"/>
        <rect x="12" y="74" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'cinema',
      name: 'Cinema',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.09)"/>
        <circle cx="33" cy="46" r="13" fill="rgba(255,255,255,.18)"/>
        <path d="M12 105a21 21 0 0142 0z" fill="rgba(255,255,255,.18)"/>
        <path d="M3 8a5 5 0 015-5h50a5 5 0 015 5v6H3z" fill="#000"/>
        <path d="M3 104h60v6a5 5 0 01-5 5H8a5 5 0 01-5-5z" fill="#000"/>
        <rect x="12" y="80" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="84.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="84.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="84.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
    {
      id: 'borda',
      name: 'Borda da marca',
      mock: `<svg viewBox="0 0 66 118" xmlns="http://www.w3.org/2000/svg">
        <rect x=".5" y=".5" width="65" height="117" rx="7" fill="#0b0e13" stroke="rgba(255,255,255,.12)"/>
        <rect x="3" y="3" width="60" height="112" rx="5" fill="rgba(255,255,255,.08)"/>
        <circle cx="33" cy="46" r="13" fill="rgba(255,255,255,.18)"/>
        <path d="M12 115a21 21 0 0142 0z" fill="rgba(255,255,255,.18)"/>
        <rect x="6.5" y="6.5" width="53" height="105" rx="4" fill="none" stroke="rgba(255,119,19,.85)" stroke-width="2"/>
        <rect x="12" y="74" width="42" height="11" rx="5.5" fill="#0b0e13" stroke="rgba(9,181,183,.65)"/>
        <rect x="16" y="78.5" width="12" height="2.4" rx="1.2" fill="rgba(9,181,183,.9)"/>
        <rect x="30" y="78.5" width="8" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
        <rect x="40" y="78.5" width="10" height="2.4" rx="1.2" fill="rgba(255,255,255,.5)"/>
      </svg>`,
    },
  ],
  // No names on purpose: the sample headline IS the label. Ids and geometry
  // mirror HL_STYLES in the template's Main.tsx — keep the two in step.
  headlines: [
    {id: 'outline', name: 'Contorno', hl: 'outline'},
    {id: 'card', name: 'Cartão', hl: 'card'},
    {id: 'realce', name: 'Realce', hl: 'realce'},
    // display order stays as designed; `default: true` is a separate flag so
    // defaultStyle() doesn't have to mean "first card" — see the captions
    // catalog below for the same split.
    {id: 'misto', name: 'Misto', hl: 'misto', default: true},
    {id: 'sombra', name: 'Sombra dura', hl: 'sombra'},
    {id: 'sublinhado', name: 'Sublinhado', hl: 'sublinhado'},
    {id: 'pilula', name: 'Pílula', hl: 'pilula'},
    {id: 'manchete', name: 'Manchete', hl: 'manchete'},
    {id: 'carimbo', name: 'Carimbo', hl: 'carimbo'},
    {id: 'pergunta', name: 'Pergunta → Resposta', hl: 'pergunta'},
    {id: 'faixa', name: 'Faixa cheia', hl: 'faixa'},
    {id: 'fita', name: 'Fita', hl: 'fita'},
    {id: 'neon', name: 'Neon', hl: 'neon'},
    {id: 'vazado', name: 'Vazado', hl: 'vazado'},
    {id: 'gradiente', name: 'Degradê na letra', hl: 'gradiente'},
    // Os quatro de 04/09: ate aqui os estilos novos tinham chegado so a
    // LEGENDA, e a lista de manchete estava igual a de 29/08.
    {id: 'recorte', name: 'Recorte', hl: 'recorte'},
    {id: 'etiqueta', name: 'Etiqueta', hl: 'etiqueta'},
    {id: 'marcador', name: 'Marca-texto', hl: 'marcador'},
    {id: 'linhas', name: 'Entre linhas', hl: 'linhas'},
    {id: 'riscado', name: 'Riscado', hl: 'riscado'},
    {id: 'caixas', name: 'Duas caixas', hl: 'caixas'},
    {id: 'quadro', name: 'Quadro', hl: 'quadro'},
    // opts out of the hook entirely (hook.enabled:false in edit-data.json) — a
    // real final look (talking-head cut, images placed by hand later), not a
    // placeholder, so it earns its own card and label like the mockups do.
    {id: 'nenhuma', name: 'Nenhuma', none: true},
  ],
  captions: [
    {id: 'karaoke', name: 'Karaokê', demo: 'karaoke'},
    {id: 'stacked', name: 'Empilhado', demo: 'stacked', default: true},
    {id: 'impacto', name: 'Impacto', demo: 'impacto'},
    {id: 'scatter', name: 'Disperso', demo: 'scatter'},
    {id: 'recorte', name: 'Recorte', stat: 'recorte'},
    {id: 'bolha', name: 'Bolha de conversa', stat: 'bolha'},
    {id: 'simples', name: 'Simples', stat: 'simples'},
    {id: 'serifada', name: 'Serifada', stat: 'serifada'},
    {id: 'classica', name: 'Clássica', stat: 'classica'},
    {id: 'bloco', name: 'Bloco', stat: 'bloco'},
    {id: 'metal', name: 'Metálico', stat: 'metal'},
    {id: 'vidro', name: 'Vidro', stat: 'vidro'},
    {id: 'traco', name: 'Contorno fino', stat: 'traco'},
    {id: 'moldura', name: 'Moldura', stat: 'moldura'},
    {id: 'eco', name: 'Eco', stat: 'eco'},
    {id: 'neon', name: 'Neon', stat: 'neon'},
    {id: 'degrade', name: 'Degradê', stat: 'degrade'},
    {id: 'bandeira', name: 'Bandeira', stat: 'bandeira'},
    {id: 'maquina', name: 'Máquina de escrever', stat: 'maquina'},
    {id: 'pilula', name: 'Pílula', stat: 'pilula'},
    {id: 'etiqueta', name: 'Etiqueta', stat: 'etiqueta'},
    {id: 'fitadegrade', name: 'Fita degradê', stat: 'fitadegrade'},
    {id: 'fitadupla', name: 'Fita dupla', stat: 'fitadupla'},
    {id: 'etiquetacanto', name: 'Etiqueta recortada', stat: 'etiquetacanto'},
    {id: 'marcador', name: 'Marca-texto', stat: 'marcador'},
    // opts out of burned captions (captions.enabled:false) — same reasoning.
    {id: 'nenhuma', name: 'Nenhuma', none: true},
  ],
  elements: [
    {
      id: 'tracking',
      name: 'Movimento de tracking',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><path d="M2 5.6V3.4A1.4 1.4 0 013.4 2h2.2M10.4 2h2.2A1.4 1.4 0 0114 3.4v2.2M14 10.4v2.2a1.4 1.4 0 01-1.4 1.4h-2.2M5.6 14H3.4A1.4 1.4 0 012 12.6v-2.2" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="8" cy="8" r="2.1"/></svg>',
    },
    {
      id: 'zoomAuto',
      name: 'Automação de zoom in',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><circle cx="7" cy="7" r="4.6" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M10.6 10.6L14 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" fill="none"/><path d="M7 5.1v3.8M5.1 7h3.8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" fill="none"/></svg>',
    },
    {
      id: 'zoomCuts',
      name: 'Zoom in e out nos cortes',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.2" y="3.4" width="6" height="9.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="9.6" y="1.9" width="5.2" height="12.2" rx="1.6" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8.4 8h.7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
    },
    {
      id: 'flashCut',
      name: 'Flash na transição',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><path d="M3 13.2L13 3.2" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" fill="none"/><path d="M6.6 14L9.4 11.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/><path d="M6.6 4.8L3.8 2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>',
    },
    {
      // OFF por padrão: só faz sentido em vídeo de lista ("3 motivos…").
      // Liga → badge 1º/2º/3º aparece sincronizado com a enumeração falada.
      id: 'listCounter',
      name: 'Contador de lista (1º, 2º…)',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.6" y="2.2" width="4.4" height="4.4" rx="1.2"/><path d="M8.4 4.4h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none"/><rect x="1.6" y="9.4" width="4.4" height="4.4" rx="1.2" opacity=".55"/><path d="M8.4 11.6h6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" fill="none" opacity=".55"/></svg>',
    },
    {
      // OFF por padrão: emoji divide opiniões — é uma decisão da marca,
      // não um padrão do produto. Mapa curado PT, no máximo 1 a cada 6s.
      id: 'emojiCaptions',
      name: 'Emoji nas legendas',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.4" fill="none" stroke="currentColor" stroke-width="1.4"/><circle cx="5.8" cy="6.6" r="0.9"/><circle cx="10.2" cy="6.6" r="0.9"/><path d="M5.2 9.6c.7 1.2 1.7 1.8 2.8 1.8s2.1-.6 2.8-1.8" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
    },
    {
      id: 'musicAI',
      name: 'Trilha sonora com IA',
      def: true,
      icon: '<svg viewBox="0 0 16 16"><path d="M12.6 1.6L6.9 3a.7.7 0 00-.55.68v5.6a2 2 0 101.35 1.9V5.9l4.4-1.05v2.9a2 2 0 101.35 1.9V2.3a.7.7 0 00-.85-.7z"/><path d="M2.4 2.2l.6 1.5 1.5.6-1.5.6-.6 1.5-.6-1.5-1.5-.6 1.5-.6z"/></svg>',
    },
    {
      // OFF by default: a sign-off is right for a brand's own feed and wrong
      // for a one-off, so it should be a decision rather than something that
      // quietly appears on every video.
      id: 'endCard',
      name: 'Card final da marca',
      def: false,
      icon: '<svg viewBox="0 0 16 16"><rect x="1.4" y="3" width="13.2" height="10" rx="2" fill="none" stroke="currentColor" stroke-width="1.4"/><rect x="4.4" y="6.2" width="7.2" height="1.7" rx=".85"/><rect x="5.9" y="9.2" width="4.2" height="1.4" rx=".7" opacity=".6"/></svg>',
    },
  ],
};

/* ---------- caption previews: the template's animation, not an impression ----
 * Every number here is lifted from the render (Main.tsx Karaoke/Word and
 * StackedCaptions.tsx STACK_MIXED) and scaled by boxWidth/1080, so the preview
 * shows the real proportions, the real faces and the real motion. If the
 * template's caption look changes, change it HERE too — a preview that lies
 * about the style is worse than no preview.
 */
const CAP_TEXT = 'É assim que sua legenda irá aparecer';
const FPS_REF = 30; // the template's reference fps for frame-based timings

// cubic-bezier solver — the stacked style eases on bezier(.16,1,.3,1)
function bez(x1, y1, x2, y2) {
  const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
  const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
  const fx = (t) => ((ax * t + bx) * t + cx) * t;
  const dfx = (t) => (3 * ax * t + 2 * bx) * t + cx;
  return (x) => {
    let t = x;
    for (let i = 0; i < 6; i++) {
      const e = fx(t) - x;
      if (Math.abs(e) < 1e-4) break;
      const d = dfx(t);
      if (Math.abs(d) < 1e-6) break;
      t -= e / d;
    }
    return ((ay * t + by) * t + cy) * t;
  };
}
const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3); // Easing.out(Easing.cubic)
const easeStack = bez(0.16, 1, 0.3, 1);
const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);

let capAnims = []; // step(nowSeconds) per visible caption demo

// Karaoke: lines of ≤3 words (captions.maxWords), Poppins 900 white, each word
// rises 34px and fades in over 7 frames; the line is replaced by the next one.
function buildKaraokeDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const lines = [];
  for (let i = 0; i < words.length; i += 3) lines.push(words.slice(i, i + 3));

  const STEP = 0.26, ENTER = 7 / FPS_REF, HOLD = 0.6;
  const rise = 34 * s;
  const built = [];
  let t = 0;
  for (const ln of lines) {
    const box = el('div', 'kar-line', wrap);
    box.style.fontSize = `${76 * s}px`;
    const spans = ln.map((w) => {
      const sp = el('span', '', box);
      sp.textContent = w;
      sp.style.marginRight = `${18 * s}px`;
      return sp;
    });
    const start = t;
    t = start + (ln.length - 1) * STEP + ENTER + HOLD;
    built.push({ box, spans, start, end: t });
  }
  const cycle = t + 0.3;

  return (now) => {
    const p = now % cycle;
    for (const L of built) {
      const on = p >= L.start && p < L.end;
      L.box.style.display = on ? '' : 'none';
      if (!on) continue;
      L.spans.forEach((sp, j) => {
        const e = easeOutCubic(clamp01((p - (L.start + j * STEP)) / ENTER));
        sp.style.opacity = e;
        sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      });
    }
  };
}

// Stacked: one cue, lines cycling the STACK_MIXED styles (bold-italic gradient →
// regular small → Playfair italic orange). Words rise 46px with a blur that
// resolves; the cue leaves with the blur_up exit.
const STK_LINES = [
  { words: ['É', 'assim'], style: 0 },
  { words: ['que', 'sua', 'legenda'], style: 1 },
  { words: ['irá', 'aparecer'], style: 2 },
];
function buildStackedDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'stk-cue', wrap);

  const STEP = 0.2, ENTER = 8 / FPS_REF, HOLD = 0.8, EXIT = 7 / FPS_REF;
  const rise = 46 * s, blurIn = 5 * s, upY = 55 * s, cueBlur = 14 * s;
  const shadow = `drop-shadow(0 ${(5 * s).toFixed(2)}px ${(9 * s).toFixed(2)}px rgba(0,0,0,0.5))`;
  const all = [];
  let idx = 0;
  for (const L of STK_LINES) {
    const row = el('div', 'stk-line', cue);
    let size = 86;
    if (L.style === 1) size = Math.round(size * 0.72);
    if (L.style === 2) size = Math.round(size * 0.95);
    row.style.fontSize = `${size * s}px`;
    L.words.forEach((w, i) => {
      // the face/gradient belongs to the WORD, like the template's `...ls` spread
      const sp = el('span', `s${L.style}`, row);
      sp.textContent = w + (i < L.words.length - 1 ? ' ' : '');
      all.push({ sp, start: idx * STEP });
      idx++;
    });
  }
  const exitStart = (idx - 1) * STEP + ENTER + HOLD;
  // short gap after the exit: side by side with the karaoke card, a preview that
  // sits blank for half a second reads as broken rather than as a cue boundary
  const cycle = exitStart + EXIT + 0.15;

  return (now) => {
    const p = now % cycle;
    const ex = clamp01((p - exitStart) / EXIT);
    cue.style.opacity = 1 - ex;
    cue.style.translate = `0px ${(-upY * ex).toFixed(2)}px`;
    cue.style.filter = ex > 0.02 ? `blur(${(cueBlur * ex).toFixed(2)}px)` : '';
    for (const w of all) {
      const e = easeStack(clamp01((p - w.start) / ENTER));
      const eb = (1 - e) * blurIn;
      w.sp.style.opacity = e;
      w.sp.style.translate = `0px ${((1 - e) * rise).toFixed(2)}px`;
      w.sp.style.filter = `${eb > 0.06 ? `blur(${eb.toFixed(2)}px) ` : ''}${shadow}`;
    }
  };
}

/* ---------- headline previews: the template's own hook styles ----------------
 * Same contract as the caption demos — these render what `HookInner` renders,
 * scaled from 1080-wide. The two-line break and the size fit run the SAME
 * algorithm as the template (balance by measured width, then fit to safeW), so
 * the preview shows the real break at the real size, not an approximation.
 * HL_STYLES exists on both sides; change one, change the other.
 */
const HEADLINE_TEXT = 'É assim que vai ficar a sua headline';
const HL_MIN = 40;
const HL_STYLES = {
  outline: { weights: [800, 800], cap: 92, safeW: 900, lh: 1.02 },
  card: { weights: [900, 900], cap: 82, safeW: 820, lh: 1.06 },
  realce: { weights: [900, 900], cap: 86, safeW: 830, lh: 1.04 },
  misto: { weights: [400, 900], cap: 98, safeW: 900, lh: 0.98 },
  sombra: { weights: [900, 900], cap: 92, safeW: 860, lh: 1.02 },
  sublinhado: { weights: [900, 900], cap: 84, safeW: 850, lh: 1.0 },
  pilula: { weights: [700, 700], cap: 44, safeW: 780, lh: 1.1 },
  manchete: { weights: [800, 800], cap: 54, safeW: 780, lh: 1.14 },
  carimbo: { weights: [900, 900], cap: 80, safeW: 720, lh: 1.05 },
  pergunta: { weights: [800, 900], cap: 84, safeW: 840, lh: 1.05 },
  faixa: { weights: [900, 900], cap: 78, safeW: 900, lh: 1.06 },
  fita: { weights: [900, 900], cap: 84, safeW: 800, lh: 1.05 },
  neon: { weights: [900, 900], cap: 92, safeW: 880, lh: 1.02 },
  vazado: { weights: [900, 900], cap: 86, safeW: 820, lh: 1.04 },
  gradiente: { weights: [900, 900], cap: 96, safeW: 900, lh: 1.0 },
  recorte: { weights: [900, 900], cap: 86, safeW: 860, lh: 1.04 },
  etiqueta: { weights: [900, 900], cap: 82, safeW: 840, lh: 1.05 },
  marcador: { weights: [900, 900], cap: 88, safeW: 880, lh: 1.06 },
  linhas: { weights: [800, 800], cap: 80, safeW: 860, lh: 1.12 },
  riscado: { weights: [900, 900], cap: 88, safeW: 860, lh: 1.06 },
  caixas: { weights: [900, 900], cap: 84, safeW: 840, lh: 1.05 },
  quadro: { weights: [800, 800], cap: 82, safeW: 860, lh: 1.10 },
};

// Measured in RENDER units (1080-wide), scaled to the box only at the end — the
// template's letterSpacing is -1px at 1080, which is NOT proportional once the
// preview shrinks it, so measuring in preview px would break the fit.
let hlMeter = null;
function measureType(text, size, weight, family, tracking) {
  if (!text) return 0;
  if (!hlMeter) {
    hlMeter = document.createElement('span');
    hlMeter.style.cssText =
      'position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre;';
    document.body.appendChild(hlMeter);
  }
  hlMeter.style.fontFamily = family || "'Poppins',sans-serif";
  hlMeter.style.letterSpacing = `${tracking == null ? -1 : tracking}px`;
  hlMeter.style.fontSize = `${size}px`;
  hlMeter.style.fontWeight = String(weight);
  hlMeter.textContent = text;
  return hlMeter.offsetWidth;
}
const hlWidth = (text, size, weight) => measureType(text, size, weight);

// Balance by MEASURED width, not word count: "É assim que vai" and "ficar a sua
// headline" are 4 and 3 words but nearly the same width — counting words breaks
// the line in the wrong place.
function hlTwoLines(text, weights) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] || '', ''];
  let best = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) { bestDiff = d; best = [a, b]; }
  }
  return best;
}

function hlFit(lines, S) {
  const widest = (size) =>
    Math.max(hlWidth(lines[0], size, S.weights[0]), hlWidth(lines[1], size, S.weights[1]));
  let size = Math.floor((S.safeW / Math.max(1, widest(100))) * 100);
  size = Math.floor((S.safeW / Math.max(1, widest(size))) * size);
  return Math.max(HL_MIN, Math.min(size, S.cap));
}

function buildHeadlineDemo(host, styleId) {
  const s = host.clientWidth / 1080;
  const S = HL_STYLES[styleId];
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const upperHl = styleId === 'card' || styleId === 'manchete' || styleId === 'carimbo'
    || styleId === 'faixa' || styleId === 'vazado';
  const raw = upperHl ? HEADLINE_TEXT.toUpperCase() : HEADLINE_TEXT;
  const lines = hlTwoLines(raw, S.weights);
  const size = hlFit(lines, S) * s;
  const box = el('div', `hl-demo hl-${styleId}`, wrap);
  box.style.lineHeight = String(S.lh);
  box.style.letterSpacing = `${-1 * s}px`;

  if (styleId === 'pilula') {
    // uma linha só, no pill escuro com o ponto na cor da headline
    const one = HEADLINE_TEXT;
    const sz = hlFit([one, ''], S) * s;
    box.style.borderRadius = '999px';
    box.style.padding = `${sz * 0.3}px ${sz * 0.6}px`;
    box.style.gap = `${sz * 0.35}px`;
    const dot = el('span', 'hl-pilula-dot', box);
    dot.style.width = `${sz * 0.3}px`;
    dot.style.height = `${sz * 0.3}px`;
    const t = el('span', 'hl-pilula-text', box);
    t.style.fontSize = `${sz}px`;
    t.textContent = one;
    return;
  }
  if (styleId === 'manchete') {
    box.style.borderRadius = `${18 * s}px`;
    box.style.padding = `${26 * s}px ${44 * s}px`;
    box.style.gap = `${26 * s}px`;
    const bar = el('span', 'hl-manchete-bar', box);
    bar.style.width = `${12 * s}px`;
    bar.style.borderRadius = `${6 * s}px`;
    const col = el('span', 'hl-manchete-lines', box);
    for (const l of lines) {
      if (!l) continue;
      const d = el('div', '', col);
      d.style.fontSize = `${size}px`;
      d.textContent = l;
    }
    return;
  }
  if (styleId === 'carimbo') {
    const bw = Math.max(3 * s, size * 0.09);
    box.style.border = `${bw}px solid var(--hl-accent)`;
    box.style.borderRadius = `${18 * s}px`;
    box.style.padding = `${size * 0.18}px ${size * 0.4}px`;
    box.style.transform = 'rotate(-6deg)';
    for (const l of lines) {
      if (!l) continue;
      const d = el('div', 'hl-carimbo-line', box);
      d.style.fontSize = `${size}px`;
      d.textContent = l;
    }
    return;
  }

  if (styleId === 'pergunta') {
    // fase 1 (pergunta branca) + fase 2 (resposta na pílula do accent),
    // empilhadas no card para comunicar a virada
    const q = el('div', 'hl-pergunta-q', box);
    q.style.fontSize = `${size * 0.72}px`;
    q.textContent = 'Aguenta martelada?';
    const a = el('div', 'hl-block hl-pergunta-a', box);
    a.style.fontSize = `${size * 0.86}px`;
    a.style.borderRadius = `${12 * s}px`;
    a.style.marginTop = `${10 * s}px`;
    a.textContent = 'Aguenta. Olha isso';
    return;
  }
  if (styleId === 'faixa' || styleId === 'fita' || styleId === 'vazado') {
    // os tres sao caixa cheia; muda o corte, o giro e quem fica no buraco
    for (const [i, l] of lines.entries()) {
      if (!l) continue;
      const b = el('div', `hl-block hl-${styleId}-line`, box);
      b.style.fontSize = `${size}px`;
      if (styleId === 'faixa') b.style.borderRadius = '0';
      if (styleId === 'fita') {
        b.style.borderRadius = `${6 * s}px`;
        b.style.transform = `rotate(${i === 0 ? -2.4 : 1.8}deg)`;
      }
      if (styleId === 'vazado') b.style.borderRadius = `${10 * s}px`;
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'gradiente') {
    for (const l of lines) {
      if (!l) continue;
      const d = el('div', 'hl-gradiente-line', box);
      d.style.fontSize = `${size}px`;
      d.textContent = l;
    }
    return;
  }
  if (styleId === 'realce' || styleId === 'recorte' || styleId === 'etiqueta') {
    for (const l of lines) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${(styleId === 'etiqueta' ? 8 : 12) * s}px`;
      if (styleId === 'recorte') {
        // as cores trocadas: caixa branca, letra na cor da marca
        b.style.background = '#ffffff';
        b.style.color = 'var(--hl-accent)';
      }
      if (styleId === 'etiqueta') {
        b.style.background = 'var(--hl-accent)';
        b.style.boxShadow =
          `inset 0 0 0 ${Math.max(2, size * 0.045)}px #fff, 0 10px 28px rgba(0,0,0,.45)`;
      }
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'riscado') {
    for (const l of lines) {
      if (!l) continue;
      const holder = el('div', 'hl-under', box);
      const bar = el('div', 'hl-under-bar', holder);
      const h = Math.max(3, size * 0.14);
      bar.style.height = `${h}px`;
      bar.style.top = `calc(52% - ${h / 2}px)`;
      bar.style.bottom = 'auto';
      bar.style.borderRadius = `${3 * s}px`;
      const t = el('div', 'hl-under-text', holder);
      t.style.fontSize = `${size}px`;
      t.textContent = l;
    }
    return;
  }
  if (styleId === 'caixas') {
    for (const [i, l] of lines.entries()) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${12 * s}px`;
      if (i === 0) {
        b.style.background = 'var(--hl-accent)';
      } else {
        b.style.background = '#ffffff';
        b.style.color = 'var(--hl-accent)';
      }
      b.textContent = l;
    }
    return;
  }
  if (styleId === 'quadro') {
    const fio = Math.max(2, size * 0.06);
    box.style.border = `${fio}px solid var(--hl-accent)`;
    box.style.borderRadius = `${10 * s}px`;
    box.style.background = 'rgba(0,0,0,.28)';
    box.style.padding = `${size * 0.22}px ${size * 0.36}px`;
    for (const l of lines) {
      if (!l) continue;
      const d = el('div', '', box);
      d.style.fontSize = `${size}px`;
      d.textContent = l;
    }
    return;
  }
  if (styleId === 'marcador') {
    // a faixa cobre o CORPO da letra; o texto passa por cima dela
    for (const l of lines) {
      if (!l) continue;
      const holder = el('div', 'hl-under', box);
      const bar = el('div', 'hl-under-bar', holder);
      bar.style.height = `${Math.max(4, size * 0.72)}px`;
      bar.style.bottom = `${size * 0.10}px`;
      bar.style.borderRadius = `${4 * s}px`;
      const t = el('div', 'hl-under-text', holder);
      t.style.fontSize = `${size}px`;
      t.textContent = l;
    }
    return;
  }
  if (styleId === 'linhas') {
    const fio = Math.max(2, size * 0.06);
    box.style.borderTop = `${fio}px solid var(--hl-accent)`;
    box.style.borderBottom = `${fio}px solid var(--hl-accent)`;
    box.style.padding = `${size * 0.12}px ${size * 0.06}px`;
    for (const l of lines) {
      if (!l) continue;
      const d = el('div', '', box);
      d.style.fontSize = `${size}px`;
      d.textContent = l;
    }
    return;
  }
  if (styleId === 'sublinhado') {
    box.style.gap = `${Math.round(size * 0.16)}px`;
    for (const l of lines) {
      if (!l) continue;
      const holder = el('div', 'hl-under', box);
      const bar = el('div', 'hl-under-bar', holder);
      const barH = Math.max(8 * s, size * 0.19);
      bar.style.height = `${barH}px`;
      bar.style.borderRadius = `${barH / 2}px`;
      bar.style.bottom = `${size * 0.06}px`;
      const t = el('div', 'hl-under-text', holder);
      t.style.fontSize = `${size}px`;
      t.textContent = l;
    }
    return;
  }
  if (styleId === 'card') {
    box.style.borderRadius = `${24 * s}px`;
    box.style.padding = `${28 * s}px ${46 * s}px`;
  }
  if (styleId === 'outline') {
    box.style.webkitTextStroke = `${12 * s}px #000`;
  }
  if (styleId === 'neon') {
    const g = Math.max(4 * s, size * 0.16);
    box.style.textShadow = `0 0 ${g}px var(--hl-accent), 0 0 ${g * 2.3}px var(--hl-accent), 0 0 ${g * 4.3}px var(--hl-accent)`;
  }
  if (styleId === 'sombra') {
    // same offset formula as the template, scaled to the card
    const off = Math.max(4 * s, size * 0.07);
    box.style.textShadow = `${off}px ${off}px 0 var(--hl-accent), 0 ${6 * s}px ${18 * s}px rgba(0,0,0,0.5)`;
  }
  lines.forEach((l, i) => {
    if (!l) return;
    const d = el('div', '', box);
    d.style.fontSize = `${size}px`;
    d.style.fontWeight = String(S.weights[i]);
    // var(), not a literal — an inline colour would beat the accent variable and
    // this preview would keep painting orange while the others followed the pick
    if (styleId === 'misto') d.style.color = i === 1 ? 'var(--hl-accent)' : '#fff';
    d.textContent = l;
  });
}

// Scatter ("disperso"): serif, lowercase, one word at a time, off-white with a
// slight darkening toward the baseline. Ordinary words FADE only — no movement;
// the one highlighted word resolves out of a blur and dissolves back into it.
// Mirrors ScatterCaptions.tsx: same line rules, same SPREAD, same hash.
const SCAT = { base: 72, hiScale: 1.62, gap: 12, spread: 0.45, safeW: 820 };
const scatHash = (n) => { const x = Math.sin(n * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

function buildScatterDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const cue = el('div', 'scat-cue', wrap);

  const words = CAP_TEXT.toLowerCase().split(' ');
  // highlight = longest word of the cue, and only if it carries weight (>6)
  let hiIdx = -1, hiLen = 6;
  words.forEach((w, i) => { if (w.length > hiLen) { hiLen = w.length; hiIdx = i; } });

  // ragged lines of 3–4 words; the highlighted word takes a line of its own
  const lines = [];
  let line = [];
  words.forEach((w, i) => {
    if (i === hiIdx) {
      if (line.length) lines.push(line);
      lines.push([{ w, i, hi: true }]);
      line = [];
      return;
    }
    line.push({ w, i, hi: false });
    if (line.length >= (scatHash(31 + i) > 0.5 ? 4 : 3)) { lines.push(line); line = []; }
  });
  if (line.length) lines.push(line);

  const STEP = 0.22, ENTER = 7 / FPS_REF, HI_ENTER = 10 / FPS_REF, HOLD = 0.9, EXIT = 8 / FPS_REF;
  const all = [];
  lines.forEach((ln, li) => {
    const row = el('div', 'scat-line', cue);
    row.style.gap = `${SCAT.gap * s}px`;
    let w = 0;
    for (const it of ln) {
      const sp = el('span', it.hi ? 'hi' : '', row);
      sp.textContent = it.w;
      sp.style.fontSize = `${(it.hi ? SCAT.base * SCAT.hiScale : SCAT.base) * s}px`;
      all.push({ sp, start: it.i * STEP, hi: it.hi });
      w += sp.offsetWidth + SCAT.gap * s;
    }
    const room = Math.max(0, (SCAT.safeW * s - w) / 2) * SCAT.spread;
    row.style.translate = `${((scatHash(17 + li * 5 + 3) * 2 - 1) * room).toFixed(1)}px 0px`;
  });

  const exitStart = (words.length - 1) * STEP + ENTER + HOLD;
  const cycle = exitStart + EXIT + 0.35;
  const blurIn = 26 * s, blurOut = 30 * s;

  return (now) => {
    const p = now % cycle;
    const out = clamp01((p - exitStart) / EXIT);
    for (const w of all) {
      const t = easeOutCubic(clamp01((p - w.start) / (w.hi ? HI_ENTER : ENTER)));
      w.sp.style.opacity = t * (1 - out);
      if (w.hi) {
        const b = (1 - t) * blurIn + out * blurOut;
        w.sp.style.filter = b > 0.1 ? `blur(${b.toFixed(2)}px)` : '';
      }
    }
  };
}

/* ---------- the three STATIC caption styles ---------------------------------
 * No animation, so no entry in capAnims — built once and left alone. Mirrors
 * SIMPLE_VARIANTS in SimpleCaptions.tsx, including the rule that matters most:
 * lines are grouped by MEASURED WIDTH, capped at maxWords. That is why a long
 * word ends up alone and short ones ride together.
 */
const STATIC_VARIANTS = {
  simples: {family: "'Poppins',sans-serif", weight: 600, size: 82, maxWords: 3, lines: 1, sx: 0.9, sy: 0.9, tracking: -3, maxW: 860},
  serifada: {family: "'Libre Baskerville',serif", weight: 700, size: 84, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 860},
  classica: {family: "'Inter',sans-serif", weight: 500, size: 52, maxWords: 14, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 840},
  bloco: {family: "'Poppins',sans-serif", weight: 800, size: 76, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -2, maxW: 760, block: true},
  recorte: {family: "'Poppins',sans-serif", weight: 800, size: 78, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 800, sticker: true},
  bolha: {family: "'Inter',sans-serif", weight: 500, size: 46, maxWords: 12, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 760, bubble: true},
  metal: {family: "'Poppins',sans-serif", weight: 800, size: 76, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 800, modo: 'metal'},
  vidro: {family: "'Poppins',sans-serif", weight: 600, size: 72, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 840, modo: 'vidro'},
  traco: {family: "'Poppins',sans-serif", weight: 800, size: 74, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 820, modo: 'traco'},
  moldura: {family: "'Inter',sans-serif", weight: 600, size: 44, maxWords: 6, lines: 1, sx: 1, sy: 1, tracking: 6, maxW: 700, modo: 'moldura'},
  eco: {family: "'Poppins',sans-serif", weight: 800, size: 78, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -2, maxW: 800, modo: 'eco'},
  neon: {family: "'Poppins',sans-serif", weight: 800, size: 74, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 800, modo: 'neon'},
  degrade: {family: "'Poppins',sans-serif", weight: 800, size: 78, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -2, maxW: 800, modo: 'degrade'},
  bandeira: {family: "'Poppins',sans-serif", weight: 800, size: 62, maxWords: 4, lines: 1, sx: 1, sy: 1, tracking: 0, maxW: 760, modo: 'bandeira'},
  maquina: {family: "'Inter',sans-serif", weight: 600, size: 56, maxWords: 8, lines: 2, sx: 1, sy: 1, tracking: 1, maxW: 840, modo: 'maquina'},
  pilula: {family: "'Poppins',sans-serif", weight: 800, size: 66, maxWords: 4, lines: 1, sx: 1, sy: 1, tracking: 0, maxW: 720, modo: 'pilula'},
  etiqueta: {family: "'Inter',sans-serif", weight: 600, size: 52, maxWords: 8, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 780, modo: 'etiqueta'},
  fitadegrade: {family: "'Poppins',sans-serif", weight: 800, size: 62, maxWords: 4, lines: 1, sx: 1, sy: 1, tracking: 0, maxW: 760, modo: 'fitadegrade'},
  fitadupla: {family: "'Poppins',sans-serif", weight: 800, size: 62, maxWords: 4, lines: 1, sx: 1, sy: 1, tracking: 0, maxW: 760, modo: 'fitadupla'},
  etiquetacanto: {family: "'Inter',sans-serif", weight: 600, size: 52, maxWords: 8, lines: 2, sx: 1, sy: 1, tracking: 0, maxW: 780, modo: 'etiquetacanto'},
  marcador: {family: "'Poppins',sans-serif", weight: 800, size: 74, maxWords: 3, lines: 1, sx: 1, sy: 1, tracking: -1, maxW: 800, modo: 'marcador'},
};
// os mesmos padroes do SimpleCaptions.tsx / render_proprio
const NEON_PADRAO = '#4de1ff';
const DEGRADE_PADRAO = '#ff6a00';
const BANDEIRA_PADRAO = '#ff6a00';
const ETIQUETA_FUNDO = 'rgba(11,13,16,0.86)';
const ETIQUETA_BARRA = 10;
const FITA_ESCURO = 0.55;
const MARCADOR_PADRAO = '#ffd400';
const MARCADOR_PADY = 0.14;
const MARCADOR_PADX = 0.16;
function escurecer(hex, f) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => Math.round(v * f));
  return `rgb(${rgb.join(',')})`;
}

// Quem desenha em CAIXA ALTA — muda a MEDIDA das linhas, entao esta lista
// tem de ser a mesma nos tres motores (SimpleCaptions.tsx e render_proprio).
const CAP_MAIUSCULA = new Set(['metal', 'moldura', 'eco', 'degrade', 'bandeira', 'fitadegrade', 'fitadupla']);
const CAP_LH = {metal: 1.1, vidro: 1.16, traco: 1.16, moldura: 1.2, eco: 1.14,
                neon: 1.16, degrade: 1.14, bandeira: 1.2, maquina: 1.3,
                pilula: 1.2, etiqueta: 1.25, fitadegrade: 1.2, marcador: 1.16,
                fitadupla: 1.2, etiquetacanto: 1.25};
// Os MESMOS numeros do render_proprio (VIDRO_OPACO/VIDRO_FIO/METAL_OPACO).
const VIDRO_OPACO = 0.32;
const VIDRO_FIO = 0.92;
const METAL_OPACO = 0.88;

/* As cinco paradas do cromado, tiradas DA COR escolhida — mesma conta do
 * `degradeMetal` no template. A parada escura no meio com o estalo de luz
 * logo abaixo e o que o olho le como metal. */
function degradeMetal(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || '').trim());
  const n = m ? parseInt(m[1], 16) : 0xe8edf3;
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  // PRATA LISO — sem a faixa escura, que o usuario leu (com razao) como um
  // risco atravessando a letra.
  return [[0, 1.38], [42, 1.06], [100, 0.74]]
    .map(([pos, f]) => {
      const rgb = c.map((v) => Math.round(f > 1 ? v + (255 - v) * Math.min(1, f - 1) : v * f));
      return `rgb(${rgb.join(',')}) ${pos}%`;
    })
    .join(', ');
}

/* Contorno por sombras em 8 direcoes (nao `-webkit-text-stroke`, que come
 * metade da espessura para dentro do glifo). */
function contornoCss(r, cor) {
  const d = (0.7071 * r).toFixed(1);
  return [
    `${r}px 0 0 ${cor}`, `-${r}px 0 0 ${cor}`,
    `0 ${r}px 0 ${cor}`, `0 -${r}px 0 ${cor}`,
    `${d}px ${d}px 0 ${cor}`, `-${d}px ${d}px 0 ${cor}`,
    `${d}px -${d}px 0 ${cor}`, `-${d}px -${d}px 0 ${cor}`,
  ];
}
const ORPHAN_PT = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

// Ink for the "bloco" slab, from the slab's own brightness. Must stay in step
// with inkOn() in SimpleCaptions.tsx — a preview that lies about legibility is
// worse than no preview, and this exact case (white slab, white text) shipped
// invisible until it was looked at on screen.
function inkOn(bg) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(bg || '').trim());
  if (!m) return '#fff';
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 ? '#111214' : '#fff';
}

function buildStaticDemo(host, id) {
  const V = STATIC_VARIANTS[id];
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.split(' ');
  const caixaAlta = !!V.sticker || CAP_MAIUSCULA.has(V.modo);
  const wOf = (ws) => measureType(
    (caixaAlta ? ws.join(' ').toUpperCase() : ws.join(' ')),
    V.size, V.weight, V.family, V.tracking,
  ) * V.sx;

  // the WHOLE sentence, cut into cues exactly as the render would
  const cues = [];
  let cur = [];
  for (const w of words) {
    const trial = [...cur, w];
    if (cur.length && (trial.length > V.maxWords || wOf(trial) > V.maxW * V.lines)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
  }
  if (cur.length) cues.push(cur);

  const boxes = cues.map((cue) => {
    let lines = [cue];
    if (V.lines === 2 && cue.length > 1) {
      let best = 1, bestScore = Infinity;
      for (let i = 1; i < cue.length; i++) {
        const score = Math.abs(wOf(cue.slice(0, i)) - wOf(cue.slice(i))) + (ORPHAN_PT.test(cue[i - 1]) ? 200 : 0);
        if (score < bestScore) { bestScore = score; best = i; }
      }
      lines = [cue.slice(0, best), cue.slice(best)];
    }
    const box = el('div', `stat-demo${V.block ? ' stat-block' : ''}`, wrap);
    box.style.fontFamily = V.family;
    box.style.fontWeight = String(V.weight);
    box.style.fontSize = `${V.size * s}px`;
    box.style.letterSpacing = `${V.tracking * s}px`;
    box.style.transform = V.sx === 1 && V.sy === 1 ? '' : `scale(${V.sx}, ${V.sy})`;
    if (V.bubble) {
      // mini-preview da Bolha de conversa: verde WhatsApp, canto de chat
      const pad = V.size * 0.34 * s;
      for (const ln of lines) {
        const b = el('div', 'stat-block-line', box);
        b.style.padding = `${pad * 0.7}px ${pad}px`;
        b.style.borderRadius = `${V.size * 0.42 * s}px`;
        b.style.borderBottomRightRadius = `${V.size * 0.12 * s}px`;
        b.style.background = '#005C4B';
        b.style.color = '#fff';
        b.textContent = ln.join(' ');
      }
      return box;
    }
    if (V.block) {
      // mirrors SimpleCaptions' block branch: the slab carries the picked
      // caption colour, and the INK comes from the slab's luminance. This
      // project picks #FFFFFF, which produced a white slab with white text
      // until inkOn existed — see the same function in SimpleCaptions.tsx.
      const pad = V.size * 0.16 * s;
      const slab = S.style.captionAccent || '#111214';
      box.style.gap = `${V.size * 0.14 * s}px`;
      for (const ln of lines) {
        const b = el('div', 'stat-block-line', box);
        b.style.padding = `${pad * 0.55}px ${pad}px ${pad * 0.75}px`;
        b.style.borderRadius = `${V.size * 0.16 * s}px`;
        b.style.color = inkOn(slab);
        b.textContent = ln.join(' ');
      }
      return box;
    }
    if (V.modo) {
      const t = (ln) => (caixaAlta ? ln.join(' ').toUpperCase() : ln.join(' '));
      box.style.lineHeight = String(CAP_LH[V.modo]);
      // superficie (brilho, degrade, fita, capsula, barra) = cor da ENFASE
      const CAP_SUP = ['neon', 'degrade', 'bandeira', 'pilula', 'etiqueta', 'fitadegrade', 'fitadupla', 'etiquetacanto'];
      const cor = (CAP_SUP.includes(V.modo)
        ? (S.style.emphasisAccent || S.style.captionAccent)
        : S.style.captionAccent) || '';
      if (V.modo === 'metal') {
        // duas copias: a de baixo so o contorno, a de cima o cromado. Uma
        // copia so nao serve — com `background-clip: text` o fundo e pintado
        // antes das sombras, e o contorno taparia o degrade.
        const R = Math.max(1, Math.round(V.size * 0.035 * s));
        const dentro = el('div', 'stat-metal', box);
        dentro.style.position = 'relative';
        const baixo = el('div', '', dentro);
        baixo.style.color = 'transparent';
        baixo.style.textShadow = [...contornoCss(R, '#0e1013'),
                                  '0 5px 12px rgba(0,0,0,0.5)'].join(', ');
        const cima = el('div', '', dentro);
        cima.style.position = 'absolute';
        cima.style.left = '0';
        cima.style.top = '0';
        cima.style.width = '100%';
        cima.style.backgroundImage = `linear-gradient(180deg, ${degradeMetal(cor || '#e8edf3')})`;
        cima.style.webkitBackgroundClip = 'text';
        cima.style.backgroundClip = 'text';
        cima.style.color = 'transparent';
        cima.style.webkitTextFillColor = 'transparent';
        cima.style.opacity = String(METAL_OPACO);
        for (const alvo of [baixo, cima]) {
          for (const ln of lines) el('div', '', alvo).textContent = t(ln);
        }
        return box;
      }
      if (V.modo === 'neon') {
        const g = cor || NEON_PADRAO;
        box.style.color = '#ffffff';
        box.style.textShadow = [`0 0 ${4 * s}px ${g}`, `0 0 ${11 * s}px ${g}`, `0 0 ${23 * s}px ${g}`,
                                `0 ${4 * s}px ${10 * s}px rgba(0,0,0,0.5)`].join(', ');
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'degrade') {
        const R = Math.max(1, Math.round(V.size * 0.03 * s));
        const dentro = el('div', 'stat-metal', box);
        dentro.style.position = 'relative';
        const baixo = el('div', '', dentro);
        baixo.style.color = 'transparent';
        baixo.style.textShadow = [...contornoCss(R, '#0e1013'), '0 5px 12px rgba(0,0,0,0.5)'].join(', ');
        const cima = el('div', '', dentro);
        cima.style.position = 'absolute';
        cima.style.left = '0';
        cima.style.top = '0';
        cima.style.width = '100%';
        cima.style.backgroundImage = `linear-gradient(180deg, #ffffff 0%, ${cor || DEGRADE_PADRAO} 100%)`;
        cima.style.webkitBackgroundClip = 'text';
        cima.style.backgroundClip = 'text';
        cima.style.color = 'transparent';
        cima.style.webkitTextFillColor = 'transparent';
        for (const alvo of [baixo, cima]) {
          for (const ln of lines) el('div', '', alvo).textContent = t(ln);
        }
        return box;
      }
      if (V.modo === 'pilula' || V.modo === 'fitadegrade' || V.modo === 'fitadupla') {
        const fundo = cor || (V.modo === 'pilula' ? '#ffffff' : BANDEIRA_PADRAO);
        box.style.display = 'flex';
        box.style.flexDirection = 'column';
        box.style.alignItems = 'center';
        box.style.padding = `${V.size * 0.30 * s}px ${V.size * 0.55 * s}px`;
        if (V.modo === 'pilula') {
          box.style.background = fundo;
          box.style.borderRadius = '9999px';
        } else {
          box.style.backgroundImage = `linear-gradient(180deg, ${fundo} 0%, ${escurecer(fundo, FITA_ESCURO)} 100%)`;
          box.style.borderRadius = `${V.size * 0.14 * s}px`;
        }
        box.style.color = inkOn(fundo);
        box.style.boxShadow = V.modo === 'fitadupla'
          ? `0 ${5 * s}px 0 ${escurecer(fundo, 0.45)}, 0 ${10 * s}px ${15 * s}px rgba(0,0,0,0.45)`
          : `0 ${6 * s}px ${15 * s}px rgba(0,0,0,0.45)`;
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'etiquetacanto') {
        const canto = V.size * 0.5 * s;
        box.style.display = 'flex';
        box.style.flexDirection = 'column';
        box.style.alignItems = 'center';
        box.style.padding = `${V.size * 0.34 * s}px ${V.size * 0.55 * s}px`;
        box.style.background = ETIQUETA_FUNDO;
        box.style.borderLeft = `${ETIQUETA_BARRA * s}px solid ${cor || '#ffffff'}`;
        box.style.borderRadius = `${6 * s}px`;
        box.style.color = '#ffffff';
        box.style.clipPath = `polygon(0 0, calc(100% - ${canto}px) 0, 100% ${canto}px, 100% 100%, 0 100%)`;
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'etiqueta') {
        box.style.display = 'flex';
        box.style.flexDirection = 'column';
        box.style.alignItems = 'center';
        box.style.padding = `${V.size * 0.34 * s}px ${V.size * 0.55 * s}px`;
        box.style.background = ETIQUETA_FUNDO;
        box.style.borderLeft = `${ETIQUETA_BARRA * s}px solid ${cor || '#ffffff'}`;
        box.style.borderRadius = `${6 * s}px`;
        box.style.color = '#ffffff';
        box.style.boxShadow = `0 ${8 * s}px ${18 * s}px rgba(0,0,0,0.45)`;
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'marcador') {
        const faixa = S.style.emphasisAccent || MARCADOR_PADRAO;
        const padX = V.size * MARCADOR_PADX * s;
        const padY = V.size * MARCADOR_PADY * s;
        for (const ln of lines) {
          const b = el('div', '', box);
          b.style.padding = `${padY}px ${padX}px`;
          b.style.background = faixa;
          b.style.color = inkOn(faixa);
          b.style.textShadow = `0 ${2 * s}px ${7 * s}px rgba(0,0,0,0.35)`;
          b.textContent = t(ln);
        }
        return box;
      }
      if (V.modo === 'bandeira') {
        const fita = cor || BANDEIRA_PADRAO;
        box.style.display = 'flex';
        box.style.flexDirection = 'column';
        box.style.alignItems = 'center';
        box.style.padding = `${V.size * 0.28 * s}px ${V.size * 0.55 * s}px`;
        box.style.background = fita;
        box.style.color = inkOn(fita);
        box.style.transform = 'skewX(-8deg)';
        box.style.boxShadow = `0 ${6 * s}px ${15 * s}px rgba(0,0,0,0.45)`;
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'maquina') {
        // a demo mostra a linha inteira (a digitacao e do video)
        box.style.color = cor || '#f4f1e9';
        box.style.textShadow = `0 ${2 * s}px ${9 * s}px rgba(0,0,0,0.55)`;
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'traco' || V.modo === 'eco') {
        box.style.color = cor || '#fff';
        if (V.modo === 'traco') {
          const R = Math.max(1, Math.round(V.size * 0.035 * s));
          box.style.textShadow = [...contornoCss(R, '#101215'),
                                  '0 4px 10px rgba(0,0,0,0.4)'].join(', ');
        } else {
          // a PRIMEIRA sombra da lista e a que fica por cima
          const d = Math.max(2, Math.round(V.size * 0.085 * s));
          box.style.textShadow = [`${-d}px ${-d}px 0 #28e0d8`,
                                  `${d}px ${d}px 0 #ff2e88`,
                                  '0 5px 13px rgba(0,0,0,0.45)'].join(', ');
        }
        for (const ln of lines) el('div', '', box).textContent = t(ln);
        return box;
      }
      if (V.modo === 'vidro') {
        // A LETRA e de vidro: 32% de branco, o take aparece atraves dela.
        // O fio de luz e o que garante a leitura sobre qualquer imagem.
        const R = Math.max(1, V.size * 0.028 * s);
        const cor2 = cor || '#ffffff';
        box.style.position = 'relative';
        const fundo = el('div', '', box);
        fundo.style.color = cor2;
        fundo.style.opacity = String(VIDRO_OPACO);
        const fio = el('div', '', box);
        fio.style.position = 'absolute';
        fio.style.left = '0';
        fio.style.top = '0';
        fio.style.width = '100%';
        fio.style.color = 'transparent';
        fio.style.webkitTextStrokeWidth = `${R * 2}px`;
        fio.style.webkitTextStrokeColor = cor2;
        fio.style.opacity = String(VIDRO_FIO);
        for (const alvo of [fundo, fio]) {
          for (const ln of lines) el('div', '', alvo).textContent = t(ln);
        }
        return box;
      }
      const vidro = false;
      box.style.display = 'flex';
      box.style.flexDirection = 'column';
      box.style.alignItems = 'center';
      box.style.gap = `${V.size * 0.16 * s}px`;
      box.style.padding = `${V.size * (vidro ? 0.44 : 0.4) * s}px ${V.size * (vidro ? 0.62 : 0.72) * s}px`;
      box.style.borderRadius = vidro ? `${V.size * 0.6 * s}px` : '4px';
      box.style.background = vidro
        ? 'linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.02)), rgba(13,15,20,0.46)'
        : 'rgba(11,13,16,0.30)';
      box.style.border = vidro
        ? '2px solid rgba(255,255,255,0.34)'
        : `2px solid ${cor || '#ffffff'}d9`;
      box.style.color = cor || (vidro ? '#f7f9fc' : '#ffffff');
      for (const ln of lines) el('div', '', box).textContent = t(ln);
      return box;
    }
    if (V.sticker) {
      // mirrors SimpleCaptions' sticker branch — outline por sombras em 8
      // direções, texto na cor da legenda (contorno escuro garante leitura)
      const R = Math.max(3, Math.round(V.size * 0.09 * s));
      const D = (0.7071 * R).toFixed(1);
      const edge = '#141518';
      box.style.color = S.style.captionAccent || '#fff';
      box.style.textShadow = [
        `${R}px 0 0 ${edge}`, `-${R}px 0 0 ${edge}`,
        `0 ${R}px 0 ${edge}`, `0 -${R}px 0 ${edge}`,
        `${D}px ${D}px 0 ${edge}`, `-${D}px ${D}px 0 ${edge}`,
        `${D}px -${D}px 0 ${edge}`, `-${D}px -${D}px 0 ${edge}`,
        '0 8px 18px rgba(0,0,0,0.5)',
      ].join(', ');
      for (const ln of lines) el('div', '', box).textContent = ln.join(' ').toUpperCase();
      return box;
    }
    for (const ln of lines) el('div', '', box).textContent = ln.join(' ');
    return box;
  });

  // A style with no animation still has a RHYTHM — the cues replacing each other
  // is what the viewer sees. So the card plays the whole sentence, cue by cue,
  // on hard cuts. A single-cue style (the two-line "classica" fits the sentence
  // whole) has nothing to step through and stays still.
  if (boxes.length < 2) return null;
  const HOLD = 0.95;
  const cycle = boxes.length * HOLD;
  return (now) => {
    const i = Math.floor((now % cycle) / HOLD);
    boxes.forEach((b, k) => { b.style.display = k === i ? '' : 'none'; });
  };
}

// Impacto: cues de 3 palavras em caixa alta; a palavra "falada" ganha uma
// caixa sólida na cor de ênfase que entra com um pop. Mesmos números do
// ImpactCaptions.tsx (POP 5f, overshoot back(2.2) aproximado).
function buildImpactDemo(host) {
  const s = host.clientWidth / 1080;
  host.innerHTML = '';
  const wrap = el('div', 'cap-demo', host);
  const words = CAP_TEXT.toUpperCase().split(' ');
  const cues = [];
  for (let i = 0; i < words.length; i += 3) cues.push(words.slice(i, i + 3));

  const STEP = 0.3, POP = 5 / FPS_REF, TAIL = 0.5;
  const box = S.style.emphasisAccent || '#ffd400';
  const ink = inkOn(box);
  const built = [];
  let t = 0;
  for (const cue of cues) {
    const line = el('div', 'imp-line', wrap);
    line.style.fontSize = `${72 * s}px`;
    line.style.gap = `${16 * s}px`;
    const spans = cue.map((w) => {
      const sp = el('span', 'imp-word', line);
      sp.textContent = w;
      sp.style.borderRadius = `${13 * s}px`;
      sp.style.padding = `${4 * s}px ${13 * s}px ${6 * s}px`;
      return sp;
    });
    const start = t;
    t = start + (cue.length - 1) * STEP + STEP + TAIL;
    built.push({ line, spans, start, end: t });
  }
  const cycle = t + 0.3;

  return (now) => {
    const p = now % cycle;
    for (const L of built) {
      const on = p >= L.start && p < L.end;
      L.line.style.display = on ? '' : 'none';
      if (!on) continue;
      let hot = 0;
      L.spans.forEach((_, j) => { if (p >= L.start + j * STEP) hot = j; });
      L.spans.forEach((sp, j) => {
        const isHot = j === hot;
        sp.style.background = isHot ? box : 'transparent';
        sp.style.color = isHot ? ink : '#fff';
        sp.style.textShadow = isHot ? 'none' : '0 3px 12px rgba(0,0,0,0.6)';
        if (isHot) {
          const e = clamp01((p - (L.start + j * STEP)) / POP);
          const over = 1 + 0.18 * Math.sin(Math.min(1, e) * Math.PI); // pop com leve overshoot
          sp.style.transform = `scale(${(0.82 + 0.18 * e) * over})`;
        } else {
          sp.style.transform = '';
        }
      });
    }
  };
}

const CAP_BUILDERS = { karaoke: buildKaraokeDemo, stacked: buildStackedDemo, scatter: buildScatterDemo, impacto: buildImpactDemo };

const LABEL_W = 48; // .track-label width (content x offset of lanes)
const MIN_SEG = 0.2; // s
const THUMB_EVERY = 2.0;

/* ---------- serving ANOTHER project's editor, at /p/<pasta>/ --------------
 * The dashboard opens any scanned project here. Every request below is
 * relative to whatever prefix the page itself was served at, so the server
 * scopes them to that project; served at "/" the prefix is empty and this is
 * exactly the old behaviour.
 */
const BASE = (location.pathname.match(/^\/p\/[^/]+/) || [''])[0];
function mediaHref(rel) {
  const encoded = String(rel || '').replace(/\\/g, '/').split('/').filter(Boolean)
    .map(encodeURIComponent).join('/');
  return `${BASE}/media/${encoded}`;
}
// Desktop hub "Estilo padrão" — full visual STYLE_CATALOG, saves house preset only
const HOUSE_STYLE = location.pathname === '/estilo-padrao';
// Hub embeds the catalog inside sidebar/appbar — hide preview chrome
const HUB_EMBED = HOUSE_STYLE && new URLSearchParams(location.search).get('embed') === '1';
/* Editando UM preset, e nao o estilo base.
 *
 * "onde edita o estilo de um preset?" (30/08) — nao editava: o Salvar do
 * editor gravava o estilo base e copiava por cima do preset PADRAO, fosse
 * qual fosse o preset carregado na tela. Com `presetId` o alvo e um so. */
const EDIT_PRESET_ID = new URLSearchParams(location.search).get('presetId') || '';
if (HUB_EMBED) {
  document.documentElement.classList.add('hub-embed');
  document.body.classList.add('hub-embed');
}

// ---------- tab routing ----------
// A real path per tab (/fase1, /estilo, /fase2), not a #hash — a link to a
// specific tab lands there directly, refresh keeps you where you were, and
// the address bar reads as an actual page instead of a fragment. Needs
// preview_server.py to serve index.html for these three paths too (a hash
// never leaves the browser; a path does) — see do_GET's route list.
const TAB_TO_PATH = { 1: '/fase1', style: '/estilo', 2: '/fase2' };
const PATH_TO_TAB = { '/fase1': 1, '/estilo': 'style', '/fase2': 2 };
function tabFromPath() {
  if (HOUSE_STYLE) return 'style';
  // under /p/<pasta>/ the tab is the part AFTER the prefix
  return PATH_TO_TAB[location.pathname.slice(BASE.length)] ?? 1;
}

// ---------- state ----------
let S = {
  state: {}, // state.json
  rendered: [], // ranges as rendered (from edl.json) — the video's truth
  draft: [], // user-editable copy [{source,start,end,beat,removed,orig:{start,end}}]
  videoDuration: 0,
  fps: 24,
  pollEspera: 2000, // ms ate o proximo /api/state (cresce ocioso)
  captions: [], // grouped caption lines [{text,start,end}] (rendered space)
  editData: null, // edit-data.json content (phase 2)
  insertsDraft: [], // editable inserts [{kind,label,start,end,ref,orig}]
  enquadrando: null, // índice do bloco em modo Enquadrar (pan do conteúdo)
  styleTocado: false, // mexeu na aba Estilo sem salvar por lá — o Aplicar leva junto
  wave: null,
  thumbCount: 0,
  tab: tabFromPath(),
  pps: 10, // px per second (zoom)
  minPps: 4,
  selected: -1, // selected clip index (draft)
  lastSig: '', // change detection
  staleNotice: false,
  savedPending: false,
  notes: [], // correction markers [{id,start,end,text}] — draft-timeline seconds
  blocoSel: -1,    // bloco posto na mao que esta selecionado (Delete apaga)
  ferramenta: 'agulha',  // 'agulha' (padrao) ou 'laco' (selecionar varios)
  takeSel: [],     // takes marcados pelo laco
  blocosSel: [],   // blocos postos na mao marcados pelo laco
  pendingIn: null, // an IN is open, waiting for its OUT
  editingNote: null, // id of the note the editor is bound to
  style: null, // current picks {edit, captions, elements:{…}, note}
  jcut: null, // jcut_timeline from edl.json — real output positions per take
  // A1/A2 live folded inside the audio track. They answer "where is the J-cut",
  // which is a question you ask once — so the default is closed, and the choice
  // is remembered rather than re-made every reload.
  // Opens by default now — A1/A2 answer "where's the J-cut", which used to be
  // worth hiding behind a click, but people kept missing it entirely. Still
  // remembers an explicit collapse (only '0' turns it off; unset/'1' both open).
  jcutOpen: localStorage.getItem('ativa-vid.jcutOpen') !== '0',
  // ON by default: the whole point is catching a wrong word before paying for
  // a render, and a check nobody switches on does not get made.
  capPreviewOn: localStorage.getItem('ativa-vid.capPreview') !== '0',
  history: [], // undo stack: snapshots of {draft, insertsDraft, notes} taken BEFORE each edit
  future: [], // redo stack: snapshots popped off history by undo()
  // caption text corrections, keyed by index into S.captions: {from, to}.
  // The UI never rewrites captions.json — it records the intent and the skill
  // re-runs the caption pipeline, which is what owns word timings.
  captionFixes: {},
  // Legendas APAGADAS. Lista separada de proposito: `captionFixes` e indexado
  // pela posicao em `S.captions`, e remover uma legenda desloca todas as de
  // baixo — guardar o apagar no mesmo dicionario faria a correcao de texto de
  // uma legenda aparecer noutra. Aqui cada item se descreve sozinho.
  capApagadas: [],
  // Assinatura das legendas COMO ESTAO NO ARQUIVO. Ver a nota em applyState:
  // a comparacao tem de ser disco contra disco, nunca disco contra a lista
  // local, que carrega as edicoes ainda nao salvas.
  capsSigDisco: null,
  // Selecao multipla de legendas (indices em S.captions). Ctrl/Cmd+clique
  // marca uma, Shift+clique marca o intervalo, Delete apaga todas.
  capSel: [],
  capSelAncora: -1,
  applying: false,
  applyToastAt: '',
  applyDoneAt: '',
  applyStage: '',
  corrections: { dirty: { headline: false, captions: false, edl: false, style: false }, finalStale: false, captionsTimedTo: null },
  captionActiveIndex: -1,
  editingHeadline: false,
  pendingEdit: null, // {projectId, edlRevision, operations, timestamp, ...}
  finalFailed: false,
  protectedRanges: [],
  contentType: null,
  lastMarkRange: null,
};

// The "house style" — every catalog default above is the FALLBACK, used
// only until (and unless) default-style.json loads. That file is shared
// across every project (it lives under the skill's own assets/preview/, not
// any one project's --root — see preview_server.py), written by the "Salvar
// como padrão" button in the Estilo footer. So the real default isn't a
// code edit anymore: a user changes it from the UI and every project after
// that opens on the new house look, this session included (no reload
// needed — see the button's own handler).
let SHARED_DEFAULT_STYLE = null;
async function loadSharedDefaultStyle() {
  try {
    const r = await fetch('/assets/default-style.json', { cache: 'no-store' });
    if (r.ok) {
      SHARED_DEFAULT_STYLE = await r.json();
      S.fastMode = !!(SHARED_DEFAULT_STYLE.oneClick ?? SHARED_DEFAULT_STYLE.fastMode);
      S.endCardCopy = SHARED_DEFAULT_STYLE.endCardCopy || null;
    }
  } catch (e) { /* no shared default saved yet, or server hiccup — catalog fallback stands */ }
  refreshFastMode();
  refreshAutoControls();
}

function defaultStyle() {
  const elements = {};
  for (const e of STYLE_CATALOG.elements) elements[e.id] = !!e.def;
  const fallback = {
    edit: STYLE_CATALOG.edits[0].id,
    headline: (STYLE_CATALOG.headlines.find((h) => h.default) || STYLE_CATALOG.headlines[0]).id,
    captions: (STYLE_CATALOG.captions.find((c) => c.default) || STYLE_CATALOG.captions[0]).id,
    accent: ACCENT_DEFAULT,
    // legenda/ênfase used to start unpicked (null → the style's own natural
    // colour) — now default to explicit picks so a new project opens on the
    // house look instead of every style's own default clashing project to
    // project. círculo stays null on purpose: its own default green already
    // IS the house look, no override needed.
    captionAccent: '#FFFFFF', // "legenda": base text (karaoke line, static styles)
    emphasisAccent: '#FF0000', // "ênfase": stacked serif line, scatter highlighted word
    circleAccent: null,    // "círculo riscado": stacked pencil-circle stroke only
    // "marca-texto": a ênfase pinta o fundo em vez de circular (opt-in,
    // pedido do usuário 26/08). 'circle' é o visual de sempre.
    emphasisStyle: 'circle',
    elements,
    note: '',
  };
  if (!SHARED_DEFAULT_STYLE) return fallback;
  // merge, not replace — a saved default that predates a new catalog field
  // (e.g. a future 4th caption colour) shouldn't leave that field undefined
  return {
    ...fallback,
    ...SHARED_DEFAULT_STYLE,
    elements: { ...fallback.elements, ...(SHARED_DEFAULT_STYLE.elements || {}) },
  };
}

const fmt = (t) => {
  if (!isFinite(t) || t < 0) t = 0;
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${m}:${s.toFixed(2).padStart(5, '0')}`;
};
// O que ele digitou em cada filtro de estilo. Fora do `radios` porque a
// tela repinta a cada troca de preset — e perder o filtro no meio da busca
// e o tipo de coisa que faz desistir de procurar.
const FILTRO_DE_ESTILO = {};

const el = (tag, cls, parent) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (parent) parent.appendChild(e);
  return e;
};

// ---------- draft layout (output-timeline positions) ----------
/* Per-take J-cut geometry, in seconds. `lead` is how far the take's sound runs
 * ahead of its picture; `tail` is what was trimmed off its end. Both are fixed
 * frame counts, so they survive the user trimming a take in the UI. */
function jcutGeom(i) {
  // S.jcut is per-ORIGINAL-take, written by render.py — it has no entry for
  // a piece that only exists because the user just split or range-deleted
  // inside the draft editor. Reading it by S.draft's CURRENT position (the
  // old bug) meant one split anywhere shifted every later take's lookup to
  // the wrong S.jcut entry — even an untouched take a bar rebuild wouldn't
  // otherwise change appeared to move (seen live: its own displayed duration
  // changed with no edit made to it). srcIdx is the fix: each draft entry
  // remembers which S.jcut/S.rendered slot it actually IS, set once when
  // S.draft is first built and carried through trims unchanged — a split
  // piece gets srcIdx:null (below) since it has no real per-piece geometry
  // yet, but every OTHER entry keeps its own correct lookup regardless of
  // how the array reshuffles around it.
  const srcIdx = S.draft[i]?.srcIdx;
  const j = (srcIdx != null && S.jcut) ? S.jcut[srcIdx] : null;
  if (!j) return { lead: 0, tail: 0 };
  return {
    lead: Math.max(0, (j.video_start_in_output || 0) - (j.audio_start_in_output || 0)),
    tail: (j.tail_trim_frames || 0) / (S.fps || 30),
  };
}

/* The draft timeline has to model the J-cut, not just sum the ranges: a take's
 * picture is shorter than its range by the lead it gives up plus the tail it had
 * trimmed. Summing raw ranges made the ruler read 8.07s over a 7.60s render, and
 * every clip after the first sat late by the accumulated lead. Each item also
 * carries its AUDIO placement (aout/adur), which is what the A1/A2 lanes draw —
 * derived here so the lanes follow the user's trims instead of going stale. */
function draftLayout() {
  let t = 0;
  let at = 0;
  return S.draft.map((r, i) => {
    if (r.removed) return { ...r, out: t, dur: 0, aout: at, adur: 0 };
    const g = jcutGeom(i);
    const span = r.end - r.start;
    const adur = Math.max(0, span - g.tail);
    const dur = Math.max(0, adur - g.lead);
    const item = { ...r, out: t, dur, aout: Math.max(0, at - g.lead), adur, lead: g.lead };
    t += dur;
    at = item.aout + adur;
    return item;
  });
}
function renderedLayout() {
  // Under a J-cut the rendered positions come from render.py, not from summing
  // the ranges — the takes overlap in sound and the picture of each one starts
  // a few frames in. Summing here would place every clip after the first too late.
  if (S.jcut && S.jcut.length === S.rendered.length) {
    return S.rendered.map((r, i) => ({
      ...r,
      out: S.jcut[i].video_start_in_output,
      dur: S.jcut[i].video_duration,
    }));
  }
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

// draft-timeline seconds within take i's span → source-file seconds. Same
// geometry draftLayout()/renderedToDraft() already use for playback: the
// picture starts `lead` into the source and stops `tail` short of `r.end`,
// so "where the playhead LOOKS like it is" and "what start/end means in the
// EDL" are offset by that lead whenever a J-cut is active.
function draftTimeToSource(i, draftT) {
  const r = S.draft[i];
  const item = draftLayout()[i];
  const g = jcutGeom(i);
  return r.start + g.lead + (draftT - item.out);
}

/* ---------- frame-accurate trim from the keyboard ----------
 * Dragging a handle is fine for "roughly here" but cannot express "one frame
 * later" — at fit-zoom a frame is a fraction of a pixel. Alt+←/→ moves the
 * selected take's OUT edge by exactly 1/fps; add Shift for the IN edge.
 *
 * History coalescing: holding the key fires many keydowns, and one undo step
 * per frame would make Ctrl+Z useless. Consecutive nudges of the SAME edge on
 * the SAME take inside NUDGE_GROUP_MS collapse into the one snapshot taken
 * when the run started — so undo rewinds the whole adjustment, like a drag.
 */
const NUDGE_GROUP_MS = 900;
let _nudgeRun = null; // {i, side, until}

function nudgeTakeEdge(i, side, dir) {
  const r = S.draft[i];
  if (!r || r.removed) return;
  const step = dir / (S.fps || 30);
  const now = Date.now();

  const cont = _nudgeRun && _nudgeRun.i === i && _nudgeRun.side === side && now < _nudgeRun.until;
  if (!cont) pushHistory();
  _nudgeRun = { i, side, until: now + NUDGE_GROUP_MS };

  if (side === 'l') {
    r.start = Math.min(Math.max(0, r.start + step), r.end - MIN_SEG);
  } else {
    r.end = Math.max(r.end + step, r.start + MIN_SEG);
    const srcDur = (S.state.sourceDurations || {})[r.source];
    if (srcDur) r.end = Math.min(r.end, srcDur);
  }
  renderAll(); refreshHeader();

  const d = side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
  const frames = Math.round(d * (S.fps || 30));
  toast(`${side === 'l' ? 'começo' : 'fim'} ${fmt(side === 'l' ? r.start : r.end)}  ` +
        `(${frames >= 0 ? '+' : ''}${frames}f)`, 1100);
}

/* ---------- the post's caption, shown next to the edit it belongs to -------
 * Read-only here: the text is written to <edit>/legenda.txt (see
 * post_brief.py) and this just surfaces it where the video is, so publishing
 * does not mean going to hunt for a file. Placeholder text written by the
 * helper counts as "not written yet" — otherwise the panel would proudly
 * display its own stub.
 */
const LEGENDA_STUB = '(a legenda do post entra aqui';
const HASHTAG_MAX = 5;   // teto da casa — ver SKILL.md

function formatReelCaption(txt) {
  const raw = String(txt || '').replace(/\r\n/g, '\n').trim();
  if (!raw) return '';
  const tags = raw.match(/#[\wÀ-ÿ]+/g) || [];
  const paras = raw
    .split(/\n+/)
    .map((p) => p.replace(/(?:^|\s)#[\wÀ-ÿ]+/g, ' ').replace(/[ \t]+/g, ' ').trim())
    .filter(Boolean);
  let lines = paras.length ? paras : [raw.replace(/(?:^|\s)#[\wÀ-ÿ]+/g, ' ').replace(/\s+/g, ' ').trim()].filter(Boolean);
  if (lines.length === 1) {
    const one = lines[0];
    const m = one.match(/^(.{12,90}?[.!?…😂🙏✨])\s+(.+)$/s);
    if (m) lines = [m[1].trim(), m[2].trim()];
  }
  const tagLine = [...new Set(tags)].slice(0, HASHTAG_MAX).join(' ');
  const body = lines.filter((l) => !/^#/.test(l)).join('\n\n');
  return tagLine ? `${body}\n\n${tagLine}` : body;
}

const SAIU_ROTULO = {
  silence: 'silêncio',
  repetition: 'repetição',
  false_start: 'recomeço',
  abandoned_take: 'recomeço',
  non_content: 'sem fala útil',
  estilo: 'ritmo/estilo (IA)',
  outro: 'outros',
};

function fmtSaiuTempo(sec) {
  const t = Math.max(0, Math.round(sec));
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
}

// "O que saiu do corte": o relatorio vira lista com "Trazer de volta" por
// item. A mecanica e a do corte do editor (preview_edits) — restaurar um
// trecho reescreve o EDL e o refazer entra como corte manual.
function renderSaiuPanel() {
  const panel = $('saiuPanel');
  if (!panel) return;
  const rel = S.corteRelatorio;
  const itens = (rel && Array.isArray(rel.itens)) ? rel.itens : [];
  const mostrar = S.tab === 2 && itens.length > 0;
  panel.classList.toggle('hidden', !mostrar);
  if (!mostrar) return;
  const hint = $('saiuHint');
  if (hint) hint.textContent = rel.resumo || '';
  const list = $('saiuList');
  list.innerHTML = '';
  itens.forEach((it) => {
    const row = el('div', 'saiu-item', list);
    const quando = el('span', 'saiu-quando', row);
    quando.textContent = `${fmtSaiuTempo(it.start)}–${fmtSaiuTempo(it.end)}`;
    const motivo = el('span', 'saiu-motivo', row);
    motivo.textContent = `${SAIU_ROTULO[it.classe] || it.classe} · ${Math.max(1, Math.round(it.dur))}s`;
    const texto = el('span', 'saiu-texto', row);
    texto.textContent = it.texto || '';
    if (it.texto) texto.title = it.texto;
    const btn = el('button', 'btn ghost small', row);
    btn.type = 'button';
    btn.textContent = 'Trazer de volta';
    btn.onclick = () => trazerDeVolta(it, btn);
  });
}

async function trazerDeVolta(item, btn) {
  if (btn) { btn.disabled = true; btn.textContent = 'Voltando…'; }
  try {
    const r = await fetch(`${BASE}/api/restaurar-trecho`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start: item.start, end: item.end }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || 'não deu para restaurar');
    if (!body.changed) {
      toast(body.hint || 'Esse trecho já está no corte');
      if (btn) { btn.textContent = 'Já no corte'; }
      return;
    }
    if (BASE && BASE.startsWith('/p/')) {
      const folder = decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
      const rq = await fetch('/api/jobs/requeue-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder }),
      });
      if (!rq.ok) throw new Error('restaurado, mas não entrou na fila — refaça em Projetos');
    }
    toast('✓ Trecho de volta — refazendo o vídeo');
    if (btn) btn.textContent = 'Voltou ✓';
  } catch (err) {
    toast(err.message, 5000);
    if (btn) { btn.disabled = false; btn.textContent = 'Trazer de volta'; }
  }
}

async function loadPostCaption() {
  const panel = $('postPanel');
  panel.classList.toggle('hidden', S.tab !== 2);
  if (S.tab !== 2) return;
  let txt = '';
  // post/ was where this used to live. Projects finished before the move still
  // have their caption in there, and nobody is going to reorganise a delivered
  // video by hand — so fall back to the old path instead of showing "ainda não
  // escrita" over a caption that exists.
  for (const path of ['legenda.txt', 'post/legenda.txt']) {
    try {
      const r = await fetch(`${mediaHref(path)}?v=${Date.now()}`, {cache: 'no-store'});
      if (r.ok) { txt = (await r.text()).trim(); if (txt) break; }
    } catch (e) { /* not written yet */ }
  }

  const box = $('postText');
  const written = txt && !txt.startsWith(LEGENDA_STUB);
  const shown = written ? formatReelCaption(txt) : '';
  box.classList.toggle('empty', !written);
  box.textContent = written
    ? shown
    : 'Ainda não escrita — a legenda aparece aqui depois da edição.';
  $('postCopy').disabled = !written;
  const tags = written ? (shown.match(/#[\wÀ-ÿ]+/g) || []).length : 0;
  // 5 is the house ceiling (see SKILL.md). Counting by eye is exactly how
  // "no máximo 5" quietly became eleven, so the count says when it is over.
  const over = tags > HASHTAG_MAX;
  $('postHint').classList.toggle('over', over);
  $('postHint').textContent = written
    ? `${shown.length} caracteres · ${tags} hashtag${tags === 1 ? '' : 's'}`
      + (over ? ` — acima do limite de ${HASHTAG_MAX}` : '')
    : 'ainda não escrita';
  refreshProjectChrome();
}


// ---------- razor: split the selected take at the playhead ----------
// A split is just "one range in edl.ranges becomes two, same source, back
// to back" — that's already inside what the save payload can express (see
// btnSave below: it sends the WHOLE current ranges list, not a diff), so
// this needs no new save-schema and no server change.
/* Apagar da agulha para um lado — o Q e o W do CapCut.
 *
 * No nosso modelo o corte e uma lista de trechos: apagar a esquerda e
 * encurtar o COMECO do trecho ate a agulha; a direita, o FIM. Nao quebra o
 * take em dois nem apaga o resto do video — e o mesmo resultado, feito com
 * a peca que ja existe (o trim), o que mantem o EDL valido e o refazer
 * funcionando.
 *
 * Sem take selecionado, vale o que estiver SOB a agulha: exigir selecao
 * antes seria um passo a mais para o gesto mais comum da edicao. */
/* O bloco posto na mao tem duracao? Entao ele se corta como um take. */
function blocoTemDuracao(c) {
  return c && (c.kind === 'insert' || c.kind === 'emoji');
}

/* Cortar/encurtar o BLOCO selecionado. Devolve true quando cuidou do
 * pedido — o chamador so segue para os takes se aqui nao era o caso. */
function acaoNoBlocoSelecionado(acao) {
  if (S.blocoSel < 0) return false;
  const c = S.insertsDraft[S.blocoSel];
  if (!c) return false;
  if (c.kind === 'sfx') {
    toast('Efeito é um ponto no tempo: arraste para mover, ou Excluir para tirar', 3200);
    return true;
  }
  if (!blocoTemDuracao(c)) return false;
  const t = renderedToDraft(video.currentTime);
  const margem = 0.12;
  if (t <= c.start + margem || t >= c.end - margem) {
    toast('Leve a agulha para dentro do bloco', 2200);
    return true;
  }
  pushHistory();
  if (acao === 'cortar') {
    const b = { ...c, start: t, orig: { start: t, end: c.end } };
    c.end = t;
    c.orig = { start: c.start, end: t };
    S.insertsDraft.splice(S.blocoSel + 1, 0, b);
    toast('Bloco cortado — agora são 2', 2000);
  } else if (acao === 'esq') {
    c.start = t;
    toast('Começo do bloco encurtado até a agulha', 2000);
  } else {
    c.end = t;
    toast('Fim do bloco encurtado até a agulha', 2000);
  }
  renderAll();
  desenharMidiaNoPreview();
  refreshHeader();
  scheduleAutosave();
  return true;
}

function apagarAteAAgulha(lado) {
  if (S.applying) return;
  // o que esta SELECIONADO vem primeiro: com a imagem marcada, responder
  // "selecione um take" e responder sobre outra coisa
  if (acaoNoBlocoSelecionado(lado)) return;
  if (S.tab !== 1) { toast('Corte só na aba Edição', 1600); return; }
  const draftT = renderedToDraft(video.currentTime);
  const layout = draftLayout();
  let i = S.selected;
  if (i < 0 || !S.draft[i] || S.draft[i].removed
      || draftT < layout[i].out || draftT > layout[i].out + layout[i].dur) {
    i = layout.findIndex((it, k) => !S.draft[k].removed
      && draftT >= it.out && draftT <= it.out + it.dur);
  }
  if (i < 0) { toast('Leve a agulha até um take', 1800); return; }
  const r = S.draft[i];
  const item = layout[i];
  const corte = draftTimeToSource(i, draftT);
  const dentro = corte > r.start + MIN_SEG && corte < r.end - MIN_SEG;
  if (!dentro) {
    toast('A agulha está na borda do take — nada para apagar deste lado', 2400);
    return;
  }
  pushHistory();
  if (lado === 'esq') r.start = corte;
  else r.end = corte;
  S.selected = i;
  renderAll(); refreshHeader();
  persistEdl();
  const seg = (lado === 'esq' ? corte - item.srcIn : 0);
  toast(lado === 'esq' ? 'Apagado até a agulha (esquerda)'
                       : 'Apagado da agulha em diante (direita)', 2000);
}

function splitAtPlayhead() {
  if (S.applying) return;
  if (acaoNoBlocoSelecionado('cortar')) return;
  if (S.tab !== 1) { toast('Corte só na aba Edição', 1600); return; }
  if (S.selected < 0) {
    // legenda tem editor proprio; o resto pede um take
    toast(S.capSel.length
      ? 'A legenda se ajusta pelo texto: clique nela para editar'
      : 'Selecione um take, uma imagem ou um emoji para cortar', 2600);
    return;
  }
  const r = S.draft[S.selected];
  if (!r || r.removed) { toast('Esse take está removido', 1600); return; }
  const item = draftLayout()[S.selected];
  const draftT = renderedToDraft(video.currentTime);
  const margin = Math.max(MIN_SEG, 0.05);
  if (draftT <= item.out + margin || draftT >= item.out + item.dur - margin) {
    toast('Posicione a agulha dentro do take, longe das bordas', 2200);
    return;
  }
  let sourceSplit = draftTimeToSource(S.selected, draftT);
  sourceSplit = Math.min(Math.max(sourceSplit, r.start + MIN_SEG), r.end - MIN_SEG);

  pushHistory();
  // srcIdx:null on both halves — neither is the original take any more, so
  // neither inherits its J-cut lead/tail (see jcutGeom)
  const halfA = { source: r.source, start: r.start, end: sourceSplit, beat: r.beat, removed: false, srcIdx: null, orig: { start: r.start, end: r.end } };
  const halfB = { source: r.source, start: sourceSplit, end: r.end, beat: r.beat, removed: false, srcIdx: null, orig: { start: r.start, end: r.end } };
  S.draft.splice(S.selected, 1, halfA, halfB);
  S.selected = S.selected + 1;
  renderAll(); refreshHeader();
  persistEdl();
  toast('Cortado — agora são 2 takes', 1800);
}

// ---------- drag-select a range INSIDE a clip → ripple-delete just that
// piece (same idea as split, twice, with the middle marked removed — reuses
// draftLayout()'s existing "removed = zero output width" so the two
// surviving pieces close the gap for free, no separate ripple logic) ----------
function clipRangeFromPixels(i, xA, xB) {
  const item = draftLayout()[i];
  if (!item || item.removed) return null;
  const rect = timelineEl.getBoundingClientRect();
  let tA = (Math.min(xA, xB) - rect.left - LABEL_W) / S.pps;
  let tB = (Math.max(xA, xB) - rect.left - LABEL_W) / S.pps;
  tA = Math.max(item.out, tA);
  tB = Math.min(item.out + item.dur, tB);
  if (tB - tA < MIN_SEG) return null;
  return { tA, tB };
}
function showClipRangeSelection(range) {
  let sel = document.getElementById('clipRangeSel');
  if (!sel) {
    sel = document.createElement('div');
    sel.id = 'clipRangeSel';
    sel.className = 'clip-range-sel';
    laneVideo.appendChild(sel);
  }
  if (!range) { sel.classList.add('hidden'); return; }
  sel.style.left = `${range.tA * S.pps}px`;
  sel.style.width = `${(range.tB - range.tA) * S.pps}px`;
  sel.classList.remove('hidden');
}
function hideClipRangeSelection() { showClipRangeSelection(null); }

function deleteClipRange(i, xA, xB) {
  const r = S.draft[i];
  const range = clipRangeFromPixels(i, xA, xB);
  if (!r || r.removed || !range) { S.selected = i; renderClips(); return; } // too small a drag — treat as a click-select instead

  let selStart = Math.max(r.start, draftTimeToSource(i, range.tA));
  let selEnd = Math.min(r.end, draftTimeToSource(i, range.tB));
  if (selEnd - selStart < MIN_SEG) { S.selected = i; renderClips(); return; }

  pushHistory();
  const pieces = [];
  if (selStart - r.start >= MIN_SEG) {
    pieces.push({ source: r.source, start: r.start, end: selStart, beat: r.beat, removed: false, srcIdx: null, orig: { start: r.start, end: r.end } });
  }
  pieces.push({ source: r.source, start: selStart, end: selEnd, beat: r.beat, removed: true, srcIdx: null, orig: { start: r.start, end: r.end } });
  if (r.end - selEnd >= MIN_SEG) {
    pieces.push({ source: r.source, start: selEnd, end: r.end, beat: r.beat, removed: false, srcIdx: null, orig: { start: r.start, end: r.end } });
  }
  S.draft.splice(i, 1, ...pieces);
  S.selected = -1;
  renderAll(); refreshHeader();
  persistEdl();
  toast('Trecho apagado', 1800);
}

// ---------- undo / redo ----------
// One shared history for both timelines (takes AND inserts) plus correction
// notes — a user thinks of Ctrl+Z as "undo my last edit", not "undo my last
// take edit, separately from my last insert edit". structuredClone is safe
// here: draft/insertsDraft/notes are plain data (numbers, strings, booleans,
// plain objects/arrays), never DOM nodes or functions.
const MAX_HISTORY = 100;
function snapshotState() {
  // style included: a mis-click on a caption style is exactly as worth undoing
  // as a mis-drag on a take, and the user thinks of Ctrl+Z as one history
  return structuredClone({
    draft: S.draft, insertsDraft: S.insertsDraft, notes: S.notes, style: S.style,
    captionFixes: S.captionFixes,
    capApagadas: S.capApagadas,
    captions: S.captions,
    hookLines: headlineLines(),
  });
}
function refreshUndoRedoButtons() {
  $('btnUndo').disabled = S.history.length === 0;
  $('btnRedo').disabled = S.future.length === 0;
}
function pushHistory(snap) {
  S.history.push(snap || snapshotState());
  if (S.history.length > MAX_HISTORY) S.history.shift();
  S.future = []; // a fresh edit invalidates whatever redo used to be possible
  refreshUndoRedoButtons();
}
function restoreSnapshot(snap) {
  // Keep the selection across an undo when it still means the same take, so
  // "nudge, nudge, Ctrl+Z, nudge again" keeps working on the clip you were
  // adjusting. Only drop it when the array length changed (a split or a
  // range-delete undone): indices shift then, and holding the old one would
  // silently select a different take.
  const keepSel = snap.draft.length === S.draft.length ? S.selected : -1;
  // O laco NAO sobrevive ao desfazer, nem quando o tamanho bate: ele marca
  // tres listas ao mesmo tempo (take, legenda e bloco) e basta uma delas ter
  // mudado de tamanho para os indices das outras apontarem outra coisa.
  // Uma marca invisivel apagando o item errado e pior que remarcar.
  S.takeSel = [];
  S.blocosSel = [];
  S.draft = snap.draft;
  S.insertsDraft = snap.insertsDraft;
  S.notes = snap.notes;
  if (snap.style) S.style = snap.style;
  S.captionFixes = snap.captionFixes || {};
  // Desfazer um apagar precisa devolver a legenda a lista, nao so tirar o
  // pedido: `S.captions` foi encurtado na hora para o usuario ver o efeito.
  if (snap.capApagadas) S.capApagadas = snap.capApagadas;
  if (snap.captions) {
    // Devolve SO o que o apagar tirou. Restaurar a lista inteira punha na tela
    // o texto ANTIGO de uma correcao que ja esta gravada no servidor — a
    // correcao de texto e persistida no clique, o apagar nao. Ai o Ctrl+Z
    // mentia do outro lado: a tela voltava, o arquivo nao, e o `index` da
    // proxima correcao passava a apontar para a palavra errada.
    const chave = (c) => `${c.start}|${c.end}`;
    const vivos = new Map(S.captions.map((c) => [chave(c), c]));
    S.captions = snap.captions.map((c) => vivos.get(chave(c)) || c);
  }
  S.capSel = [];
  S.capSelAncora = -1;
  if (snap.hookLines && S.editData) {
    S.editData.hook = { ...(S.editData.hook || {}), enabled: true, lines: snap.hookLines };
  }
  closeCaptionEditor();
  S.selected = keepSel;
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderAll(); refreshHeader(); renderNotes();
  persistUndoState();
  // the Estilo tab is built from S.style, so it has to be rebuilt too — and
  // the accent CSS vars re-applied (these read S.style themselves), or the
  // demos keep painting the colours from before the undo
  if (S.style) {
    applyAccent();
    applyCaptionAccent();
    applyEmphasisAccent();
    renderSetup();
  }
}
function undo() {
  if (!S.history.length) { toast('Nada para desfazer', 1200); return; }
  S.future.push(snapshotState());
  restoreSnapshot(S.history.pop());
  refreshUndoRedoButtons();
  toast('Desfeito', 1000);
}
function redo() {
  if (!S.future.length) { toast('Nada para refazer', 1200); return; }
  S.history.push(snapshotState());
  restoreSnapshot(S.future.pop());
  refreshUndoRedoButtons();
  toast('Refeito', 1000);
}

// ---------- dirty tracking ----------
function edlDirty() {
  return S.draft.some((r) => r.added || r.removed || r.start !== r.orig.start || r.end !== r.orig.end);
}
function geoDoInsert(c) {
  return JSON.stringify([+(+c.start).toFixed(3), +(+c.end).toFixed(3),
    c.x ?? null, c.y ?? null, c.w ?? null, c.h ?? null, c.size ?? null,
    c.entrada ?? null, c.saida ?? null, c.fx ?? null, c.fy ?? null,
    c.zoom ?? null, c.srcIn ?? null, c.camada ?? null, c.volume ?? null]);
}
function manualMudou() {
  return !!S.manualApagado || S.insertsDraft.some(
    (c) => (c.kind === 'insert' || c.kind === 'emoji' || c.kind === 'sfx')
      && (c.isNew || (c.manual && c.origGeo != null && c.origGeo !== geoDoInsert(c))));
}
function insertsDirty() {
  // isNew: added from the image picker this session, so there is no orig to
  // diff against — it is dirty by existing at all
  return manualMudou()
    || S.insertsDraft.some((c) => c.isNew || c.start !== c.orig.start || c.end !== c.orig.end);
}
function dirtyCount() {
  let n = S.draft.filter((r) => r.added || r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length;
  n += S.insertsDraft.filter((c) => c.isNew || c.start !== c.orig.start || c.end !== c.orig.end).length;
  n += S.notes.length; // each correction marker is an unsaved adjustment too
  n += Object.keys(S.captionFixes).length; // and each caption text fix
  n += (S.capApagadas || []).length;       // e cada legenda apagada
  return n;
}
function pendingFlags() {
  const d = (S.corrections && S.corrections.dirty) || {};
  return {
    headline: !!d.headline,
    captions: !!d.captions || Object.keys(S.captionFixes).length > 0
      || (S.capApagadas || []).length > 0,
    edl: !!d.edl || edlDirty(),
    style: !!d.style || !!S.styleTocado,
    // Midia posta na mao (imagem/video/som/emoji) TAMBEM e alteracao
    // pendente: sem isto o "Aplicar alteracoes" ficava apagado depois de
    // adicionar um video e o usuario tinha de achar o salvar no "Mais…".
    midia: insertsDirty(),
  };
}
function pendingList() {
  const f = pendingFlags();
  const labels = { headline: 'headline', captions: 'legenda', edl: 'corte', style: 'estilo', midia: 'mídia' };
  return Object.keys(labels).filter((k) => f[k]).map((k) => labels[k]);
}
function refreshHeader() {
  const list = pendingList();
  const n = list.length;
  const session = dirtyCount();
  const save = $('btnSave');
  const discard = $('btnDiscard');
  const apply = $('btnApply');
  const pending = $('pendingPill');
  $('dirtyPill').classList.add('hidden');
  $('dirtyCount').textContent = n;
  if (pending) {
    pending.classList.toggle('hidden', n === 0 && !S.applying);
    pending.textContent = S.applying
      ? (S.applyStage || 'Aplicando alterações...')
      : 'Alterações pendentes';
    pending.title = S.applying
      ? (S.applyStage || 'Atualizando o vídeo final')
      : (n === 0 ? '' : list.map((x) => x[0].toUpperCase() + x.slice(1)).join(' · '));
  }
  if (apply) {
    apply.classList.remove('hidden');
    if (S.applying) {
      apply.disabled = true;
      apply.textContent = S.applyStage || 'Aplicando alterações...';
      apply.title = S.applyStage || 'Aplicando alterações';
    } else {
      apply.disabled = n === 0;
      apply.textContent = n === 0
        ? 'Aplicar alterações'
        : (n === 1 ? 'Aplicar 1 alteração' : `Aplicar ${n} alterações`);
      apply.title = n === 0
        ? 'Nada para aplicar'
        : list.map((x) => x[0].toUpperCase() + x.slice(1)).join(' · ');
    }
  }
  if (save) {
    save.classList.remove('hidden');
    save.disabled = session === 0 && n === 0;
  }
  if (discard) {
    discard.classList.remove('hidden');
    discard.disabled = n === 0 && session === 0;
    discard.title = discard.disabled ? 'Nada para descartar' : 'Descartar correções deste vídeo';
  }
  $('savedPill').classList.toggle('hidden', !(S.savedPending && n === 0 && session === 0));
  refreshFinalButton();
  refreshProjectChrome();
  refreshQuickFixes();
}

function hasFinalVideo() {
  return !!(S.state && S.state.finalVideo);
}

function refreshFinalButton() {
  const btn = $('btnOpenFinal');
  if (!btn) return;
  const ok = hasFinalVideo();
  const stale = !!(S.corrections && S.corrections.finalStale) || pendingList().length > 0;
  btn.disabled = !ok;
  btn.classList.toggle('is-stale', !!(ok && stale));
  btn.textContent = 'Ver final';
  if (!ok) {
    btn.title = 'O vídeo final ainda não está pronto';
  } else if (stale) {
    btn.title = 'O vídeo final ainda não inclui as alterações pendentes.';
    btn.textContent = 'Final anterior';
  } else {
    btn.title = 'Abrir o vídeo final';
  }
}

function friendlyBeatLabel(beat, fallback) {
  const raw = String(beat || '').trim();
  if (!raw) return fallback || '';
  const up = raw.toUpperCase();
  if (up === 'HOOK') return 'Gancho';
  if (up === 'KEEP') return 'Mantido';
  if (up === 'CTA') return 'CTA';
  const scene = up.match(/^B(\d+)$/);
  if (scene) return `Cena ${Number(scene[1])}`;
  return raw;
}

function fmtClock(sec) {
  const s = Math.max(0, Math.round(Number(sec) || 0));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

function videoAspectLabel() {
  const w = video.videoWidth || 0;
  const h = video.videoHeight || 0;
  if (!w || !h) return '';
  const r = w / h;
  if (r < 0.72) return '9:16';
  if (r > 1.5) return '16:9';
  if (Math.abs(r - 1) < 0.08) return '1:1';
  return `${w}×${h}`;
}

function generatedProjectTitle() {
  const ed = S.editData || {};
  const hook = ed.hook || {};
  const lines = hook.lines || hook.text || [];
  const arr = Array.isArray(lines) ? lines : [lines];
  for (const ln of arr) {
    const s = String(ln || '').trim();
    if (s.length >= 6) return s;
  }
  const hl = String(ed.headline || ed.aiHeadline || '').trim();
  if (hl.length >= 6) return hl;
  const post = $('postText')?.textContent || '';
  if (post && !post.startsWith('Ainda não')) {
    const line = post.split('\n').find((l) => {
      const t = l.trim();
      return t.length >= 8 && !t.startsWith('#');
    });
    if (line) return line.replace(/\s+#.*$/, '').trim().slice(0, 72);
  }
  return '';
}

function headlineLines() {
  const ed = S.editData || {};
  const hook = ed.hook || {};
  const lines = hook.lines || hook.text || [];
  const arr = Array.isArray(lines) ? lines : [lines];
  return arr.map((x) => String(x || '').trim()).filter(Boolean);
}

async function persistCorrection(body) {
  if (!BASE) return null;
  if (S.applying && body && body.op !== 'apply' && body.op !== 'plan' && body.op !== 'load') {
    toast('Estou aplicando as alterações. Espere terminar para editar.', 2400);
    return null;
  }
  try {
    const res = await fetch(`${BASE}/api/corrections`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (data && data.corrections) S.corrections = data.corrections;
    refreshHeader();
    return data;
  } catch {
    toast('Não consegui gravar a correção neste projeto', 2800);
    return null;
  }
}

function applyApplyStatus(st, task) {
  const qa = task && typeof task === 'object' ? task : null;
  const qaBusy = !!(qa && (qa.status === 'queued' || qa.status === 'running'));
  const running = !!(st && st.running) || qaBusy;
  const was = !!S.applying;
  S.applying = running;
  const stageMsg = (qa && qa.stageLabel)
    || (st && st.message)
    || 'Aplicando edição...';
  S.applyStage = running ? String(stageMsg) : '';
  document.body.classList.toggle('applying-corrections', running);
  const stageEl = $('applyStage');
  if (stageEl) {
    stageEl.hidden = !running;
    stageEl.classList.toggle('hidden', !running);
    if (running) stageEl.textContent = S.applyStage;
  }
  if (running) {
    refreshHeader();
    return;
  }
  const at = String((qa && qa.finishedAt) || (st && st.at) || '');
  const ok = (qa && qa.status === 'completed') || (st && st.ok === true);
  const fail = (qa && qa.status === 'failed') || (st && st.ok === false);
  const ackId = (qa && (qa.taskId || qa.finishedAt)) || at;
  const ackKey = ackId ? `ativavid-apply-ack:${ackId}` : '';
  let alreadyAck = false;
  try { alreadyAck = !!(ackKey && localStorage.getItem(ackKey) === '1'); } catch { alreadyAck = false; }
  if (qa && qa.acknowledgedAt) alreadyAck = true;
  if (ok && at && at !== S.applyToastAt && was && !alreadyAck) {
    S.applyToastAt = at;
    if (ackKey) {
      try { localStorage.setItem(ackKey, '1'); } catch { /* ignore */ }
    }
    fetch('/api/apply-ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ taskId: (qa && qa.taskId) || '', projectId: (qa && qa.projectId) || '' }),
    }).catch(() => {});
    const title = (typeof generatedProjectTitle === 'function' && generatedProjectTitle())
      || (S.state && S.state.project)
      || '';
    toast(title ? `Vídeo atualizado\n${title} está pronto.` : 'Vídeo atualizado', 4000);
  } else if (fail && at && at !== S.applyToastAt && was && !alreadyAck) {
    S.applyToastAt = at;
    if (ackKey) {
      try { localStorage.setItem(ackKey, '1'); } catch { /* ignore */ }
    }
    fetch('/api/apply-ack', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ taskId: (qa && qa.taskId) || '', projectId: (qa && qa.projectId) || '' }),
    }).catch(() => {});
    toast((st && st.message) || 'Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido.', 5000);
  }
  if (ok && at && at !== S.applyDoneAt) {
    S.applyDoneAt = at;
    S.history = [];
    S.future = [];
    S.captionFixes = {};
    S.capApagadas = [];
    refreshUndoRedoButtons();
    S.lastSig = '';
    if (BASE) {
      fetch(`${BASE}/api/state`).then((r) => r.json()).then((data) => applyState(data)).catch(() => {});
    }
  }
  if (was || ok || fail) refreshHeader();
}

async function persistHeadline(lines) {
  const list = (lines || []).map((x) => String(x || '').trim()).filter(Boolean);
  if (!list.length) return null;
  return persistCorrection({ op: 'set_headline', lines: list });
}

/* Escreve uma legenda ONDE NAO HA nenhuma — b-roll, fala baixa, ou uma
 * frase que ninguem falou e que o usuario quer na tela. O resto do editor
 * so corrige o que a transcricao ouviu.
 * O tempo e o da agulha, no relogio do cut.mp4 — o mesmo de captions.json. */
async function escreverLegendaAqui() {
  const t = video.currentTime || 0;
  const texto = await pedirTexto('Escrever legenda neste momento', '', 'Adicionar');
  if (!texto) return;
  const data = await persistCorrection({ op: 'add_caption', text: texto, start: t });
  if (!data) return;
  if (data.ok === false) {
    toast(data.erro || data.error || 'Não consegui escrever a legenda aqui', 3600);
    return;
  }
  if (Array.isArray(data.captionWords)) {
    S.captions = groupCaptions(data.captionWords);
    S.captionFixes = {};
    S.capApagadas = [];
    S.capSel = [];
    S.capSelAncora = -1;
  }
  if (data.corrections) S.corrections = data.corrections;
  renderAll();
  highlightCurrentCaption(currentCaptionIndex());
  const seg = ((data.janela ? (data.janela.fimMs - data.janela.inicioMs) : 0) / 1000);
  toast(seg ? `Legenda escrita (${seg.toFixed(1).replace('.', ',')}s)`
            : 'Legenda escrita', 2200);
}

async function persistCaptionFix(from, to, extra) {
  const data = await persistCorrection({ op: 'fix_caption', from, to, ...(extra || {}) });
  if (data && data.ok === false) {
    toast(data.error || 'Essa palavra aparece mais de uma vez. Clique na legenda certa.', 3600);
    return data;
  }
  if (data && Array.isArray(data.captionWords) && data.captionWords.length) {
    S.captions = groupCaptions(data.captionWords);
    S.captionFixes = {};
    S.capApagadas = [];
    // A lista veio outra: os indices marcados apontam para legendas
    // diferentes agora, e um Delete apagaria a errada.
    S.capSel = [];
    S.capSelAncora = -1;
  }
  return data;
}

/* Onde caem as emendas na linha do tempo do rascunho: o fim acumulado de
 * cada trecho mantido, menos o ultimo. E o que a regua marca e o que o
 * pipeline numera (indice 0 = entre o 1o e o 2o trecho). */
function fronteirasDoRascunho() {
  const out = [];
  let t = 0;
  const vivos = S.draft.filter((r) => !r.removed);
  vivos.forEach((r, i) => {
    t += Math.max(0, r.end - r.start);
    if (i < vivos.length - 1) out.push(t);
  });
  return out;
}

function tipoDaEmenda(i) {
  const por = (S.editData && S.editData.transicoesPorCorte) || {};
  const escolhido = por[String(i)];
  if (escolhido) return { tipo: escolhido, proprio: true };
  const doEstilo = (S.style && S.style.transicao) || 'flash';
  const ligado = !(S.style && S.style.elements && S.style.elements.flashCut === false);
  return { tipo: ligado ? doEstilo : 'nenhuma', proprio: false };
}

const COR_DA_TRANSICAO = {
  flash: '#ffd166', brilho: '#ffffff', escurece: '#8b94a3', faixa: 'var(--hl-accent, #ff5200)', nenhuma: 'transparent',
  // 5.0.51
  cortina: 'var(--hl-accent, #ff5200)', blocos: 'var(--hl-accent, #ff5200)',
  moldura: 'var(--hl-accent, #ff5200)', traco: '#ffe9a8',
};

function draftRangesPayload() {
  return S.draft.filter((r) => !r.removed).map((r) => ({
    source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
  }));
}

async function persistEdl() {
  const data = await persistCorrection({ op: 'set_edl', ranges: draftRangesPayload() });
  if (data && data.ok) {
    S.draft.forEach((r) => {
      if (!r.removed) {
        r.orig = { start: r.start, end: r.end };
        r.added = false;
      }
    });
    refreshHeader();
  }
  return data;
}

let _undoPersistTimer = null;
function persistUndoState() {
  clearTimeout(_undoPersistTimer);
  _undoPersistTimer = setTimeout(() => {
    persistHeadline(headlineLines());
    persistEdl();
  }, 200);
}

function isTypingContext() {
  if (S.applying || S.editingHeadline) return true;
  if (document.getElementById('capEditor')) return true;
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || '').toUpperCase();
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || ae.isContentEditable) return true;
    if (ae.closest && ae.closest('#capEditor, #hlOverlay, #quickFixes, .cap-input, .note-editor, .ai-panel, .img-modal, .help-modal, .versions-panel, dialog, .av-dlg')) {
      return true;
    }
  }
  const overlayOpen = (id) => {
    const n = $(id);
    if (!n) return false;
    if ((n.tagName || '').toUpperCase() === 'DIALOG') return !!n.open;
    return !n.classList.contains('hidden') && !n.hidden;
  };
  return overlayOpen('helpModal') || overlayOpen('imgModal') || overlayOpen('aiPanel') || overlayOpen('versionsPanel') || overlayOpen('noteEditor') || overlayOpen('dlgAutosave');
}
function isQuickEditing() { return isTypingContext(); }

// Estilo "pergunta": a headline tem duas fases; o editor edita a que está
// NA TELA (pergunta antes de answerAtSec, resposta depois).
function hlAnswerMode() {
  if (((S.style && S.style.headline) || '') !== 'pergunta') return false;
  const hook = (S.editData && S.editData.hook) || {};
  const at = Number(hook.answerAtSec) || 2.5;
  return (video.currentTime || 0) >= at;
}

function hlAnswerLines() {
  const hook = (S.editData && S.editData.hook) || {};
  return Array.isArray(hook.answerLines)
    ? hook.answerLines.map((s) => String(s).trim()).filter(Boolean)
    : [];
}

function commitHeadline(text, isAnswer) {
  const lines = String(text || '').split('\n').map((s) => s.trim()).filter(Boolean);
  if (!lines.length) return;
  if (isAnswer) {
    if (lines.join('\n') === hlAnswerLines().join('\n')) return;
    pushHistory();
    if (!S.editData) S.editData = {};
    S.editData.hook = { ...(S.editData.hook || {}), answerLines: lines };
    persistCorrection({ op: 'set_headline_answer', lines });
    renderAll();
    refreshHeader();
    refreshProjectChrome();
    return;
  }
  if (lines.join('\n') === headlineLines().join('\n')) return;
  pushHistory();
  if (!S.editData) S.editData = {};
  S.editData.hook = { ...(S.editData.hook || {}), enabled: true, lines };
  persistHeadline(lines);
  renderAll();
  refreshHeader();
  refreshProjectChrome();
}

// `ev` = o evento do clique que abriu a edicao, quando houve um. Com ele o
// cursor vai para ONDE o usuario clicou; sem ele (chip da barra, atalho) o
// texto inteiro fica selecionado, que e o certo para "digitar por cima".
function beginHeadlineEdit(ev) {
  if (S.applying) return;
  const box = $('hlOverlay');
  const answerMode = hlAnswerMode();
  const cur = (answerMode && hlAnswerLines().length ? hlAnswerLines() : headlineLines()).join('\n');
  S.editingHeadline = true;
  if (box) {
    box.classList.remove('hidden');
    let line = box.querySelector('.hl-overlay-line');
    if (!line) {
      box.innerHTML = '';
      line = el('div', 'hl-overlay-line', box);
      line.textContent = cur;
    }
    line.contentEditable = 'true';
    line.focus();
    const sel = window.getSelection();
    sel.removeAllRanges();
    // O elemento so vira editavel AGORA, entao o clique que abriu a edicao nao
    // deixou cursor nenhum: era preciso pedir o ponto ao navegador. Antes daqui
    // saia sempre `selectNodeContents`, ou seja, TUDO selecionado — clicar no
    // meio da manchete para apagar uma palavra nao funcionava e so restava
    // andar com as setas.
    let range = null;
    if (ev && ev.clientX != null) {
      if (document.caretRangeFromPoint) {
        range = document.caretRangeFromPoint(ev.clientX, ev.clientY);
      } else if (document.caretPositionFromPoint) {
        const cp = document.caretPositionFromPoint(ev.clientX, ev.clientY);
        if (cp) {
          range = document.createRange();
          range.setStart(cp.offsetNode, cp.offset);
          range.collapse(true);
        }
      }
      if (range && !line.contains(range.startContainer)) range = null;
    }
    if (!range) {
      range = document.createRange();
      range.selectNodeContents(line);
    }
    sel.addRange(range);
    let cancelled = false;
    const finish = () => {
      S.editingHeadline = false;
      line.contentEditable = 'false';
      line.removeEventListener('blur', finish);
      if (!cancelled) commitHeadline(line.textContent, answerMode);
      else line.textContent = cur;
    };
    line.addEventListener('blur', finish);
    line.onkeydown = (e) => {
      e.stopPropagation();
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); line.blur(); }
      if (e.key === 'Escape') {
        e.preventDefault();
        cancelled = true;
        line.textContent = cur;
        line.blur();
      }
    };
    return;
  }
  S.editingHeadline = false;
  pedirTexto(answerMode ? 'Resposta desta headline' : 'Headline deste vídeo',
             cur, 'Salvar')
    .then((next) => { if (next != null) commitHeadline(next, answerMode); });
}

function refreshQuickFixes() {
  const bar = $('quickFixes');
  if (!bar) return;
  const hl = headlineLines();
  const show = !HOUSE_STYLE && (!!hl.length || S.captions.length > 0);
  bar.classList.toggle('hidden', !show);
  const chip = $('hlChip');
  if (chip) chip.textContent = hl.length ? hl.join(' / ') : 'Headline';
  refreshHeadlineOptions(hl);
}

// 3 opções de headline vindas da IA (headline_options.json do render):
// clicar troca a headline na hora, pelo mesmo caminho do editar manual (com
// undo e persistência). A opção atual não vira chip.
function headlineTwoLines(text) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean);
  if (words.length <= 1) return words.join(' ');
  const mid = Math.max(1, Math.floor(words.length / 2));
  return words.slice(0, mid).join(' ') + '\n' + words.slice(mid).join(' ');
}

function refreshHeadlineOptions(hlLines) {
  const host = $('hlOptions');
  if (!host) return;
  const current = (hlLines || headlineLines()).join(' ').trim().toLowerCase();
  const opts = (S.headlineOptions || [])
    .filter((o) => String(o || '').trim())
    .filter((o) => o.trim().toLowerCase() !== current);
  const sig = opts.join('|') + '::' + current;
  if (host.dataset.sig === sig) return;
  host.dataset.sig = sig;
  host.innerHTML = '';
  host.classList.toggle('hidden', !opts.length || S.applying);
  if (!opts.length) return;
  const label = el('span', 'hl-options-label', host);
  label.textContent = 'IA sugere:';
  for (const opt of opts.slice(0, 2)) {
    const b = el('button', 'quick-chip hl-alt', host);
    b.type = 'button';
    b.textContent = opt;
    b.title = 'Usar esta headline';
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      commitHeadline(headlineTwoLines(opt));
      toast('Headline trocada — Aplicar alterações para gravar no vídeo');
    });
  }
}

/** Apaga uma ou VARIAS legendas. Indices em S.captions. */
function apagarLegendas(indices, semHistorico = false) {
  const alvos = [...new Set(indices.map(Number))]
    .filter((i) => i >= 0 && S.captions[i])
    .sort((a, b) => b - a);            // de tras para frente: nao desloca o resto
  if (!alvos.length) return;
  // Quando o laco apaga as tres especies de uma vez, o historico e UM so:
  // o Ctrl+Z tem de desfazer o gesto inteiro, nao um terco dele.
  if (!semHistorico) pushHistory();
  const pedidos = [];
  for (const i of alvos) {
    const c = S.captions[i];
    pedidos.push({
      from: c.text, start: c.start, end: c.end,
      index: c.wordIndex, tokenId: c.tokenId || undefined, cueId: c.cueId || undefined,
    });
    S.captions.splice(i, 1);
    // As correcoes de TEXTO sao indexadas por posicao: tirar a legenda i faz
    // tudo abaixo dela descer uma casa. Sem isto a correcao de uma legenda
    // passava a aparecer noutra.
    const desloc = {};
    for (const k of Object.keys(S.captionFixes)) {
      const n = Number(k);
      if (n === i) continue;
      desloc[n > i ? n - 1 : n] = S.captionFixes[k];
    }
    S.captionFixes = desloc;
  }
  S.capApagadas.push(...pedidos);
  S.capSel = [];
  S.capSelAncora = -1;
  renderAll();
  refreshHeader();
  if (!semHistorico) {
    toast(alvos.length === 1
      ? 'Legenda apagada — Ctrl+Z desfaz'
      : `${alvos.length} legendas apagadas — Ctrl+Z desfaz`, 3000);
  }
  // NAO grava no servidor agora, de proposito. Uma correcao de TEXTO gravada
  // na hora ainda da para reescrever; uma palavra APAGADA no arquivo nao volta
  // pelo Ctrl+Z, que so restaura a tela — o usuario desfaria, veria a legenda
  // de volta na linha do tempo e ela ja estaria fora do captions.json. O
  // apagar fica pendente e vai junto no salvar, como qualquer outra edicao da
  // linha do tempo.
}

function currentCaptionIndex(t) {
  const time = t == null ? (video.currentTime || 0) : t;
  return S.captions.findIndex((c) => time >= c.start && time < c.end);
}

function highlightCurrentCaption(i) {
  S.captionActiveIndex = i;
  const lane = typeof laneCaptions !== 'undefined' ? laneCaptions : document.getElementById('laneCaptions');
  if (lane) {
    lane.querySelectorAll('.chip.caption').forEach((ch) => {
      ch.classList.toggle('current', +ch.dataset.ci === i);
    });
  }
  const panel = $('capNow');
  if (panel) {
    const c = i >= 0 ? S.captions[i] : null;
    const fix = c && S.captionFixes[i];
    // Sem legenda aqui, a pastilha CONVIDA em vez de so mostrar um traco:
    // era o unico lugar da tela que falava de legenda e mandava embora.
    const text = c ? (fix ? fix.to : c.text) : '+ escrever legenda';
    if (panel.textContent !== text) panel.textContent = text;
    panel.classList.toggle('current', i >= 0);
  }
}

function projectFileLabel() {
  const raw = String(S.state.project || S.state.video || '').trim();
  if (!raw) return '';
  return raw.split(/[/\\]/).pop();
}

function refreshProjectChrome() {
  const pn = $('projectName');
  const meta = $('projectMeta');
  if (!pn) return;
  if (HOUSE_STYLE) {
    pn.textContent = 'Estilo padrão da marca';
    if (meta) meta.classList.add('hidden');
    return;
  }
  const file = projectFileLabel();
  const title = generatedProjectTitle();
  const bits = [file];
  const dur = S.videoDuration || video.duration || 0;
  if (dur) bits.push(fmtClock(dur));
  const aspect = videoAspectLabel();
  if (aspect) bits.push(aspect);
  // O NOME DO CARD ("G3 · C1 · CTA3") tambem entra aqui — pedido de 03/09:
  // "deve mostrar tambem o nome do video editado". E a mesma regra do hub
  // (displayTitle): o stem do arquivo final, exceto final/cut genericos.
  const nomeDoCard = nomeDoVideoEditado();
  const pintarMeta = (lista) => {
    if (!meta) return;
    meta.textContent = '';
    if (nomeDoCard) {
      const b = el('b', 'proj-nome', meta);
      b.textContent = nomeDoCard;
      if (S.state && S.state.jobId) {
        // Renomear e aprovar daqui mesmo (03/09): ele abre o video, aprova
        // e marca o nome com ✅ na mao — agora e um clique e um checkbox.
        b.setAttribute('role', 'button');
        b.title = 'Clique para renomear';
        b.addEventListener('click', () => { renomearVideoEditado(); });
        const lab = el('label', 'proj-aprovado', meta);
        const chk = el('input', '', lab);
        chk.type = 'checkbox';
        chk.checked = APROVADO_RE.test(nomeDoCard);
        chk.title = 'Marca o nome com ✅';
        lab.appendChild(document.createTextNode(' Aprovado'));
        chk.addEventListener('change', () => { alternarAprovado(chk.checked); });
      }
      // Copiar o nome COMPLETO (com o ✅): ele cria a pasta de entrega com
      // esse nome (03/09). Botao proprio — o clique no nome e renomear.
      const cp = el('button', 'proj-copiar', meta);
      cp.type = 'button';
      cp.textContent = '⧉';
      cp.title = 'Copiar o nome (para nomear a pasta)';
      cp.addEventListener('click', async () => {
        const ok = await copiarTextoEditor(nomeDoCard);
        toast(ok ? `Nome copiado: ${nomeDoCard}` : 'Não consegui copiar o nome', 2600);
      });
      if (lista.length) meta.appendChild(document.createTextNode(' · '));
    }
    meta.appendChild(document.createTextNode(lista.join(' · ')));
    meta.classList.toggle('hidden', !nomeDoCard && lista.length === 0);
  };
  if (title && file && title.toLowerCase() !== file.toLowerCase()) {
    pn.textContent = title;
    pintarMeta(bits.filter(Boolean));
  } else {
    pn.textContent = file || 'ATIVAVID';
    pintarMeta(bits.slice(1));
  }
}

/* Aprovado = o nome comeca com ✅ (o mesmo sinal que ele ja punha na mao
 * ao aprovar a edicao). Renomear passa pelo /api/jobs/rename do hub, que
 * trava o titulo — e o card do hub mostra o mesmo nome. */
const APROVADO_RE = /^\s*✅\s*/u;

async function copiarTextoEditor(texto) {
  const t = String(texto || '');
  if (!t) return false;
  try {
    await navigator.clipboard.writeText(t);
    return true;
  } catch { /* segue para o caminho velho */ }
  try {
    const ta = document.createElement('textarea');
    ta.value = t;
    ta.setAttribute('readonly', '');
    ta.style.position = 'fixed';
    ta.style.top = '0';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    ta.remove();
    return !!ok;
  } catch {
    return false;
  }
}

async function gravarNomeDoVideo(novo) {
  const id = S.state && S.state.jobId;
  const titulo = String(novo || '').replace(/\s+/g, ' ').trim().slice(0, 80);
  if (!id || !titulo) return false;
  try {
    const r = await fetch('/api/jobs/rename', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id, title: titulo }),
    });
    const body = await r.json().catch(() => ({}));
    if (!r.ok || body.error) throw new Error(body.error || 'não deu para renomear');
    S.state.jobTitle = titulo;
    refreshProjectChrome();
    // a pasta de entrega e renomeada junto; se o Explorer a segurou, avisa
    if (body.packWarning) toast(`Nome salvo, mas ${body.packWarning}`, 6000);
    return true;
  } catch (e) {
    toast(`Renomear falhou: ${e.message || e}`, 4500);
    return false;
  }
}

async function renomearVideoEditado() {
  const atual = nomeDoVideoEditado();
  const novo = await pedirTexto('Nome do vídeo', atual, 'Salvar');
  if (novo == null || novo.trim() === atual) return;
  if (await gravarNomeDoVideo(novo)) toast('✓ Nome atualizado', 2200);
}

async function alternarAprovado(marcar) {
  const atual = nomeDoVideoEditado();
  const limpo = atual.replace(APROVADO_RE, '');
  const novo = marcar ? `✅ ${limpo}` : limpo;
  if (novo === atual) return;
  if (await gravarNomeDoVideo(novo)) {
    toast(marcar ? '✓ Aprovado — ✅ no nome' : 'Aprovação retirada', 2200);
  } else {
    refreshProjectChrome();   // desfaz o checkbox que ficou marcado a toa
  }
}

function nomeDoVideoEditado() {
  // O servidor manda o titulo DO CARD (mesma regra do hub, inclusive o
  // titulo travado dos criativos do Multiplicador — "G2 · C1 · CTA2");
  // sem ele (servidor antigo), o stem do arquivo final.
  const doCard = String((S.state && S.state.jobTitle) || '').trim();
  if (doCard) return doCard.slice(0, 80);
  const fin = String((S.state && S.state.finalVideo) || '').trim();
  if (!fin) return '';
  const stem = fin.split(/[/\\]/).pop().replace(/\.[^.]+$/, '').trim();
  if (!stem || /^(final|cut)$/i.test(stem)) return '';
  return stem.slice(0, 80);
}

// ---------- data loading ----------

/* Ritmo do poll de estado.
 *
 * Ocioso, o editor pedia `/api/state` a cada 2s para sempre: 1800
 * chamadas por hora, 6,5 ms e 10 KB cada (medido na maquina do usuario),
 * lendo state.json, edl.json e os mtimes a cada volta. Isso disputa a
 * maquina com o RENDER, que e o trabalho de verdade.
 *
 * O teto de 8s e o pior caso de atraso para notar algo que comecou
 * NOUTRA janela — contra os ~107s que um apply dura, e barato. */
const POLL_VIVO = 2000;
const POLL_OCIOSO = 8000;
// Escondido, uma batida a cada ~32s (4 voltas de 8s) so para o caso de
// o embutido estar mentindo sobre a visibilidade.
const POLL_ESCONDIDO = 32000;

function acordarPoll() {
  S.pollEspera = POLL_VIVO;
}

// Qualquer sinal de vida zera a espera: a janela voltou, o usuario clicou,
// o teclado foi usado. Sem isto, voltar para a janela mostraria estado
// velho por ate 8s.
for (const ev of ['visibilitychange', 'focus', 'pointerdown', 'keydown']) {
  const alvo = ev === 'visibilitychange' ? document : window;
  alvo.addEventListener(ev, acordarPoll, { passive: true });
}

async function poll() {
  // Aba escondida: o `visibilitychange` acorda no instante em que ela
  // volta, entao aqui basta uma batida lenta. NAO parar de vez e
  // proposital — ha embutidos que dizem "escondido" com a janela a
  // vista, e um editor que congela nesse caso seria pior que o gasto.
  // `S.lastSig` vazio = ainda nao ha estado nenhum. Pular a PRIMEIRA
  // volta deixaria o editor em branco ate a proxima — e ha embutido
  // que ja nasce marcado como escondido. Medido: a tela abria sem
  // video nenhum.
  if (document.hidden && !S.applying && S.lastSig) {
    S.pollEspera = POLL_ESCONDIDO;
    if ((S.pollPulos = (S.pollPulos || 0) + 1) < 4) {
      setTimeout(poll, POLL_OCIOSO);
      return;
    }
  }
  S.pollPulos = 0;
  try {
    const res = await fetch(`${BASE}/api/state`);
    if (!res.ok) return;
    const data = await res.json();
    const sig = JSON.stringify([data.state, data.edl, data.mtimes, data.videoDuration, data.hasCut, data.corrections]);
    applyApplyStatus(data.applyStatus, data.applyTask);
    if (sig !== S.lastSig) {
      // Primeira carga SEMPRE aplica. Dialog fechado / foco em select não é edição.
      const firstLoad = !S.lastSig;
      const hadEdits = !firstLoad && (dirtyCount() > 0 || S.history.length > 0);
      acordarPoll();   // mudou algo: volta ao ritmo rapido
      if (!hadEdits) {
        S.lastSig = sig;
        S.staleNotice = false;
        await applyState(data);
      } else if (!S.staleNotice) {
        S.staleNotice = true;
        toast('Novo estado disponível — salve ou descarte seus ajustes para atualizar', 4000);
      }
    }
  } catch (e) { /* server restarting; keep polling */ }
  if (S.applying) {
    S.pollEspera = POLL_VIVO;
    setTimeout(poll, 700);   // trabalho ao vivo: a barra depende disto
    return;
  }
  // Nada mudou nesta volta: espera um pouco mais na proxima, ate o teto.
  S.pollEspera = Math.min(POLL_OCIOSO,
                          Math.round((S.pollEspera || POLL_VIVO) * 1.5));
  setTimeout(poll, S.pollEspera);
}

async function applyState(data) {
  const next = data.state || {};
  if ((next.finalVideo || '') !== (S.state.finalVideo || '')) S.finalFailed = false;
  S.state = next;
  S.mtimes = data.mtimes || {};
  S.videoDuration = data.videoDuration || 0;
  S.hasCut = !!data.hasCut || S.videoDuration > 0;
  S.presetUsed = (data.presetUsed && typeof data.presetUsed === 'object') ? data.presetUsed : null;
  S.headlineOptions = Array.isArray(data.headlineOptions) ? data.headlineOptions : [];
  S.fps = S.state.fps || 24;
  S.savedPending = !!data.hasPendingEdits;
  if (data.corrections) S.corrections = data.corrections;

  $('projectName').textContent = S.state.project || 'ATIVAVID';
  // Opened from the dashboard, this is NOT the project the session is watching:
  // watch_edits.py is armed on one edit dir, so a save here lands in a file
  // nobody is reading. The toast still says "salvo" and the work still does not
  // happen — the exact silent failure the skill warns about. Say so, and name
  // the folder, because "peça ao Claude" is useless if you ask in the session
  // pointed at a different video.
  let statusLine = '';
  if (BASE) {
    const folder = decodeURIComponent(BASE.slice('/p/'.length));
    statusLine = `Projeto ${folder} — o que você salvar aqui vale só para este vídeo`;
  } else {
    statusLine = S.state.message || '';
  }
  const sm = $('stateMessage');
  if (sm) {
    sm.textContent = statusLine;
    sm.classList.remove('warn');
  }
  const pn = $('projectName');
  if (pn) pn.title = statusLine || (S.state.project || '');

  const ranges = (data.edl && data.edl.ranges) || [];
  const timedTo = (data.corrections && data.corrections.captionsTimedTo) || null;
  const edlPending = !!(data.corrections && data.corrections.dirty && data.corrections.dirty.edl);
  // Relógio do cut.mp4 / captions.json — não o EDL pendente. Assim a overlay
  // da legenda continua no tempo do vídeo até o Apply.
  const cutClock = (edlPending && Array.isArray(timedTo) && timedTo.length) ? timedTo : ranges;
  // J-cut timeline, written by render.py. Under a J-cut the picture of every take
  // after the first starts a few frames into itself, so the rendered clip is
  // SHORTER than end-start and the takes do not simply abut. Without this the
  // filmstrip and the needle drift a little further at each junction.
  S.jcut = (edlPending && timedTo) ? null : ((data.edl && data.edl.jcut_timeline) || null);
  S.rendered = cutClock.map((r) => ({ source: r.source, start: +r.start, end: +r.end, beat: r.beat || '' }));
  // srcIdx: this entry's position in S.rendered/S.jcut — jcutGeom() reads
  // lead/tail through THIS, not the entry's current S.draft position, so a
  // split earlier in the array can't shift an untouched later take's
  // geometry out from under it. Split-off pieces get srcIdx:null (see
  // splitAtPlayhead/deleteClipRange) — there's no real per-piece geometry
  // for those until the skill re-renders and writes a fresh jcut_timeline.
  S.draft = ranges.map((r, srcIdx) => ({
    source: r.source, start: +r.start, end: +r.end, beat: r.beat || '',
    removed: false, srcIdx, orig: { start: +r.start, end: +r.end },
  }));
  S.corteRelatorio = data.corteRelatorio || null;
  if (data.intent) {
    S.protectedRanges = Array.isArray(data.intent.protectedRanges) ? data.intent.protectedRanges : [];
    S.contentType = data.intent.contentType || S.contentType;
    S.editIntent = data.intent.editingIntent || S.editIntent || null;
    const mEl = $('autoEditIntent');
    if (mEl && S.editIntent && ['light','dynamic','complete','intact'].includes(S.editIntent)) mEl.value = S.editIntent;
    // O payload só carrega o modo se o USUÁRIO mexeu nele nesta tela. Uma aba
    // do Estilo aberta desde antes de uma troca de modo mostrava o valor
    // velho no seletor, e o "Salvar e refazer" mandava esse valor por cima do
    // job_intent — caso real (25/08): o projeto estava em Vídeo completo e
    // uma aba da véspera o rebaixou para Edição leve sem ninguém pedir.
    if (mEl && !mEl.dataset.wired) {
      mEl.dataset.wired = '1';
      mEl.addEventListener('change', () => { S.editIntentTocado = true; });
    }
    const ct = $('autoContentType');
    if (ct && S.contentType) ct.value = S.contentType;
  }
  S.selected = -1;
  S.history = []; S.future = []; refreshUndoRedoButtons(); // fresh server data — old snapshots no longer apply
  // Caption fixes are keyed by index into S.captions, so they only go stale if
  // the caption LIST changed. applyState also runs for unrelated reasons (a new
  // render's mtime, a duration re-probe) — dropping the fixes then would throw
  // away typing the user had not saved yet, and close the box mid-edit.
  // The actual comparison happens after S.captions is rebuilt, below.
  //
  // A comparacao e DISCO contra DISCO. Comparar com `S.captions` funcionava
  // enquanto toda edicao de legenda ia para o servidor na hora — a lista local
  // e a do arquivo andavam juntas. O APAGAR fica pendente ate salvar, entao a
  // lista local passa a ser legitimamente menor que a do arquivo, e o poll
  // seguinte lia isso como "mudou embaixo de mim" e jogava fora a exclusao que
  // o usuario tinha acabado de fazer. Na pratica a selecao sumia sozinha.
  S.captionsSigBefore = S.capsSigDisco;

  // style picks: the skill's copy wins, so applying a change (or reopening the
  // session) shows what is actually rendered — not a stale local selection
  S.style = { ...defaultStyle(), ...(S.state.style || {}) };
  S.style.elements = { ...defaultStyle().elements, ...((S.state.style || {}).elements || {}) };
  // House-style page: prefer the shared default-style.json over empty hub state
  if (HOUSE_STYLE && SHARED_DEFAULT_STYLE) {
    S.style = { ...defaultStyle(), ...SHARED_DEFAULT_STYLE };
    S.style.elements = { ...defaultStyle().elements, ...(SHARED_DEFAULT_STYLE.elements || {}) };
    if (SHARED_DEFAULT_STYLE.endCardCopy) S.endCardCopy = { ...SHARED_DEFAULT_STYLE.endCardCopy };
    if (typeof SHARED_DEFAULT_STYLE.oneClick === 'boolean') S.fastMode = SHARED_DEFAULT_STYLE.oneClick;
    else if (typeof SHARED_DEFAULT_STYLE.fastMode === 'boolean') S.fastMode = SHARED_DEFAULT_STYLE.fastMode;
  }
  refreshAutoControls();
  // Agora `S.style` existe: se o seletor da enfase ficou de fora no
  // DOMContentLoaded (estado ainda nao tinha chegado), liga aqui.
  wireEmphStyle();
  $('setupNote').value = S.style.note || '';
  // the skill opened the gate → land the user on the Estilo tab
  if (S.state.awaitingStyle || HOUSE_STYLE) S.tab = 'style';

  const hasVideo = S.videoDuration > 0 || !!S.hasCut;
  $('playerWrap').classList.toggle('hidden', !hasVideo || HOUSE_STYLE);
  $('editorCol').classList.toggle('hidden', !hasVideo || HOUSE_STYLE);
  $('transportBar')?.classList.toggle('hidden', !hasVideo || HOUSE_STYLE);

  if (hasVideo && !HOUSE_STYLE) {
    detectProxy().then(() => updateVideoSrc());
    loadWave();
    loadThumbsMeta();
    refreshScorePill();
    ensureInitialVersion();
  }

  // phase 2 data
  const tab2 = document.querySelector('[data-tab="2"]');
  tab2.disabled = HOUSE_STYLE || (S.state.phase || 1) < 2;
  // Estilo opens when the catalog applies to this job: the skill asked for a
  // pick, or one is already recorded. Before that there is nothing to choose.
  const tabS = document.querySelector('[data-tab="style"]');
  tabS.disabled = HOUSE_STYLE ? false : (!S.state.awaitingStyle && !S.state.style);
  const tab1 = document.querySelector('[data-tab="1"]');
  if (tab1) tab1.disabled = !!HOUSE_STYLE;

  if (HOUSE_STYLE) {
    document.body.classList.add('house-style');
    const pnHouse = $('projectName');
    if (pnHouse) {
      pnHouse.textContent = 'Estilo padrão da marca';
      pnHouse.title = 'Escolhas visuais iguais às do editor — salvas para todos os vídeos';
    }
    const smHouse = $('stateMessage');
    if (smHouse) smHouse.textContent = 'Escolhas visuais iguais às do editor — salvas para todos os vídeos';
  }
  if (tabS.disabled && S.tab === 'style') S.tab = 1;
  // a deep link to #fase2 before Fase 2 exists yet has nothing to show
  if (tab2.disabled && S.tab === 2) S.tab = 1;
  document.querySelectorAll('.tab').forEach((x) => {
    const on = String(x.dataset.tab) === String(S.tab);
    x.classList.toggle('active', on);
    x.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  // replaceState, not the click handler's real navigation: applyState reruns
  // on every 2s poll, and pushing a history entry each time would make the
  // back button useless (dozens of identical entries instead of one per tab)
  const wantPath = HOUSE_STYLE ? '/estilo-padrao' : (BASE + TAB_TO_PATH[S.tab]);
  let wantSearch = '';
  if (HUB_EMBED) {
    const q = new URLSearchParams(location.search);
    q.set('embed', '1');
    wantSearch = `?${q.toString()}`;
  }
  if (location.pathname !== wantPath || (HUB_EMBED && location.search.indexOf('embed=1') < 0)) {
    history.replaceState(null, '', wantPath + wantSearch);
  }
  S.captions = [];
  S.editData = null;
  S.insertsDraft = [];
  if ((S.state.phase || 1) >= 2) {
    if (S.state.captions) {
      try {
        const caps = await (await fetch(`${mediaHref(S.state.captions)}?v=${Date.now()}`)).json();
        S.captions = groupCaptions(caps);
        S.capsSigDisco = JSON.stringify(S.captions.map((c) => c.text));
      } catch (e) { /* absent yet */ }
    }
    if (S.state.editData) {
      try {
        S.editData = await (await fetch(`${mediaHref(S.state.editData)}?v=${Date.now()}`)).json();
        buildInsertsDraft();
        garantirFonteDaMarca();
      } catch (e) { /* absent yet */ }
    }
  }

  // see S.captionsSigBefore above: only discard pending caption fixes when the
  // caption lines themselves actually changed under us
  const sigAgora = JSON.stringify(S.captions.map((c) => c.text));
  if (S.captionsSigBefore != null && sigAgora !== S.captionsSigBefore) {
    S.captionFixes = {};
    S.capApagadas = [];
    S.capSel = [];
    S.capSelAncora = -1;
    closeCaptionEditor();
  } else {
    // O arquivo nao mudou: reaplica as edicoes pendentes por cima da lista
    // recem-lida, senao o proximo poll desfaz o apagar na tela.
    const apagar = new Set((S.capApagadas || []).map((f) => f.from));
    if (apagar.size) S.captions = S.captions.filter((c) => !apagar.has(c.text));
  }

  fitZoom();
  renderAll();
  renderSetup();
  refreshHeader();
  loadPostCaption(); // picks up a caption written between polls
  renderSaiuPanel();
  carregarPresetDoVideo().catch(() => {});
  loadBrandPresets({ applyActive: !!(HOUSE_STYLE || HUB_EMBED) });
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  const wantFinal = S.tab === 2 && S.state.finalVideo && !S.finalFailed;
  let rel = wantFinal ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  // proxy leve no corte (Fase 1) quando existir — scrub mais fluido
  if (S.tab !== 2 && S.hasProxy && !S.proxyFailed && rel === 'cut.mp4') rel = 'cut_proxy.mp4';
  // ...e no VIDEO PRONTO (aba Visual), que ate a 4.34 tocava o arquivo
  // entregue inteiro. Medido no video dele de 1:30: 159 MB, e decodificar
  // em uma thread leva 50,1 s para 90,2 s de video — 1,8x o tempo real,
  // sem folga nenhuma. A copia de 540 leva 5,4 s (16,7x) e tem 7,2 MB. O
  // quadro do player tem ~500 px de largura: os 1080 nao aparecem.
  if (wantFinal && S.hasFinalProxy && !S.finalProxyFailed) rel = 'final_proxy.mp4';
  const vsrc = `${mediaHref(rel)}?v=${(S.mtimes && (S.mtimes.finalVideo || S.mtimes.video)) || Date.now()}`;
  if (video.dataset.src === vsrc) return;
  const t = wantFinal ? 0 : video.currentTime;
  const wasPlaying = !video.paused && !video.ended;
  video.dataset.src = vsrc;
  video.dataset.rel = rel;
  video.src = vsrc;
  const applyT = () => {
    if (wantFinal) video.currentTime = 0;
    else if (t) video.currentTime = t;
  };
  if (video.readyState >= 1) applyT();
  else video.addEventListener('loadedmetadata', applyT, { once: true });
  if (wasPlaying) video.play().catch(() => {});
}

async function rebuildProxy() {
  if (!BASE || !BASE.startsWith('/p/')) return false;
  const folder = decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
  try {
    const res = await fetch('/api/proxy/rebuild', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ folder }),
    });
    const data = await res.json();
    if (data.ok) {
      S.hasProxy = true;
      S.proxyFailed = false;
      updateVideoSrc();
      toast('Proxy atualizado', 2000);
      return true;
    }
  } catch { /* ignore */ }
  return false;
}

function wireProxyFallback() {
  let rebuilding = false;
  video.addEventListener('error', () => {
    const rel = video.dataset.rel || '';
    if (rel.includes('final_proxy')) {
      // A copia do final pode estar sendo escrita agora (ela nasce na
      // primeira abertura da aba). Cair no arquivo cheio e o certo: ele
      // ve o video, so mais pesado.
      S.finalProxyFailed = true;
      S.hasFinalProxy = false;
      updateVideoSrc();
      return;
    }
    if (rel.includes('cut_proxy')) {
      S.proxyFailed = true;
      S.hasProxy = false;
      updateVideoSrc();
      toast('Proxy falhou — usando vídeo completo', 2800);
      if (!rebuilding) {
        rebuilding = true;
        rebuildProxy().finally(() => { rebuilding = false; });
      }
      return;
    }
    if (S.tab === 2 && rel && rel !== 'cut.mp4' && !S.finalFailed) {
      S.finalFailed = true;
      video.dataset.src = '';
      updateVideoSrc();
      toast('Não achei o vídeo final — mostrando o corte', 2800);
    }
  });
}

function groupCaptions(caps) {
  // mirror the template: lines of ≤3 words, break on punctuation
  const words = (caps || []).map((w, i) => {
    if (!w || typeof w !== 'object') return null;
    const id = w.tokenId || w.cueId || w.id || w.wordId || null;
    return { ...w, wordIndex: i, tokenId: id };
  }).filter(Boolean);
  const lines = [];
  let cur = [];
  for (const w of words) {
    cur.push(w);
    if (cur.length >= 3 || /[.,!?…]$/.test(w.text || '')) { lines.push(cur); cur = []; }
  }
  if (cur.length) lines.push(cur);
  return lines.map((line) => {
    const t0 = line[0].startMs != null ? line[0].startMs : (Number(line[0].start) || 0) * 1000;
    const t1 = line[line.length - 1].endMs != null ? line[line.length - 1].endMs : (Number(line[line.length - 1].end) || 0) * 1000;
    return {
      text: line.map((w) => String(w.text || '').replace(/[.,!?…]+$/, '')).join(' '),
      start: t0 / 1000,
      end: t1 / 1000,
      wordIndex: line[0].wordIndex,
      tokenId: line[0].tokenId,
      cueId: line[0].cueId || line[0].id || line[0].tokenId || null,
      words: line,
    };
  });
}

/* ---------- caption text correction ----------
 * A transcript slip ("capinha" heard as "carpinha") used to cost a round trip
 * through chat. This records the fix against the caption line the user is
 * looking at and ships it in the save payload; the skill re-runs the caption
 * pipeline, because word-level timings are derived and must not be hand-typed
 * into captions.json. Scope is deliberately text-only: no timing handles.
 */
function openCaptionEditor(i, anchorEl) {
  const c = S.captions[i];
  if (!c) return;
  closeCaptionEditor();
  const cur = S.captionFixes[i] ? S.captionFixes[i].to : c.text;

  const box = el('div', 'cap-editor glass', document.body);
  box.id = 'capEditor';
  const r = anchorEl.getBoundingClientRect();
  box.style.left = `${Math.min(Math.max(8, r.left), window.innerWidth - 330)}px`;
  box.style.top = `${Math.max(8, r.top - 84)}px`;

  // NOTE: this file's el() is el(tag, cls, parent) — it takes no text argument
  // (painel.js has its own 4-arg version). Set textContent explicitly.
  el('div', 'cap-orig', box).textContent = `original: ${c.text}`;
  const input = el('input', 'cap-input', box);
  input.type = 'text';
  input.value = cur;

  const acts = el('div', 'cap-actions', box);
  const reset = el('button', 'btn ghost small', acts);
  reset.textContent = 'desfazer correção';
  reset.style.visibility = S.captionFixes[i] ? 'visible' : 'hidden';
  // Apagar era o buraco: dava para trocar o texto, mas nao para tirar a
  // legenda — e salvar com o campo vazio nao apaga de proposito, senao um
  // campo limpo por engano levaria a legenda junto. Aqui o pedido e explicito,
  // e o undo (pushHistory) cobre o arrependimento.
  const del = el('button', 'btn ghost small', acts);
  del.textContent = 'apagar';
  del.title = 'Tira esta legenda do vídeo';
  el('div', 'spacer', acts);
  const ok = el('button', 'btn primary small', acts);
  ok.textContent = 'aplicar';

  const commit = () => {
    const v = input.value.trim();
    closeCaptionEditor();
    if (!v) {
      // Esvaziar continua DESCARTANDO a correcao pendente, que e o que sempre
      // significou. O que faltava era dizer isso: quem esvaziava esperando
      // apagar a legenda nao via nada acontecer.
      if (S.captionFixes[i]) {
        pushHistory();
        delete S.captionFixes[i];
        toast('Correção descartada — para tirar a legenda, use "apagar"', 3200);
      } else {
        toast('Para tirar a legenda do vídeo, use o botão "apagar"', 3200);
      }
    } else if (v === c.text) {
      if (S.captionFixes[i]) { pushHistory(); delete S.captionFixes[i]; }
    } else if (!S.captionFixes[i] || S.captionFixes[i].to !== v) {
      pushHistory();
      const from = c.text;
      S.captionFixes[i] = { from, to: v, start: c.start, end: c.end };
      c.text = v;
      persistCaptionFix(from, v, {
        start: c.start,
        end: c.end,
        startMs: Math.round((c.start || 0) * 1000),
        endMs: Math.round((c.end || 0) * 1000),
        index: c.wordIndex,
        tokenId: c.tokenId || undefined,
        cueId: c.cueId || undefined,
      }).then((data) => {
        if (data && data.ok === false) {
          c.text = from;
          delete S.captionFixes[i];
          renderAll();
          refreshHeader();
        }
      });
    }
    renderAll(); refreshHeader();
  };
  del.addEventListener('click', () => { closeCaptionEditor(); apagarLegendas([i]); });
  ok.addEventListener('click', commit);
  reset.addEventListener('click', () => {
    closeCaptionEditor();
    if (S.captionFixes[i]) { pushHistory(); delete S.captionFixes[i]; renderAll(); refreshHeader(); }
  });
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();                       // the timeline owns S/space/arrows
    if (e.key === 'Enter') commit();
    if (e.key === 'Escape') closeCaptionEditor();
  });
  input.focus();
  input.select();
}

function closeCaptionEditor() {
  const old = document.getElementById('capEditor');
  if (old) old.remove();
}

function stripAutoInsertsIfLimpa() {
  // Estilo Limpa = quadro cheio. Sem cards de imagem AUTOMÁTICOS por cima.
  // O que o usuário pôs À MÃO (manual) FICA: era varrido junto e o vídeo
  // inserido "sumia da timeline" depois do render (caso real de 02/09).
  const edit = (S.style && S.style.edit) || 'limpa';
  if (String(edit).toLowerCase() !== 'limpa') return false;
  let changed = false;
  if (S.editData && Array.isArray(S.editData.inserts) && S.editData.inserts.length) {
    const manuais = S.editData.inserts.filter((it) => it && it.manual);
    if (manuais.length !== S.editData.inserts.length) {
      S.editData.inserts = manuais;
      changed = true;
    }
  }
  return changed;
}

let fonteDaMarcaOk = '';
function garantirFonteDaMarca() {
  // A fonte PRÓPRIA do usuário (id "arquivo") existia só no render: o
  // preview mostrava a legenda na fonte do template e a final saía em
  // outra. Registra a mesma BrandLocal que o fonts.ts usa, a partir do
  // arquivo que o pipeline copiou para remotion/public/fonts/.
  const rel = S.editData && S.editData.brandFontFile;
  if (!rel || fonteDaMarcaOk === rel || typeof FontFace === 'undefined') return;
  fonteDaMarcaOk = rel;
  const url = mediaHref(`remotion/public/${rel}`);
  const face = new FontFace('BrandLocal', `url(${url})`);
  face.load().then((f) => document.fonts.add(f)).catch(() => {});
}

function buildInsertsDraft() {
  const d = S.editData;
  if (!d) { S.insertsDraft = []; return; }
  stripAutoInsertsIfLimpa();
  const list = [];
  if (d.hook && d.hook.enabled) {
    list.push({ kind: 'hook', label: `Gancho — ${(d.hook.lines || []).join(' / ')}`, start: 0, end: d.hook.endSec || 4 });
  }
  (d.inserts || []).forEach((it, i) => {
    list.push({
      kind: 'insert',
      label: (it.src || it.query || '').split('/').pop() || 'insert',
      start: +it.start,
      end: +it.end,
      ref: i,
      src: it.src || '',
      credit: it.credit || '',
      auto: !!it.auto,
      hint: !!it.hint,
      // Mídia posta À MÃO volta como CAMADA VIVA depois do render (4.61):
      // com a geometria, animações e enquadramento que já valem no vídeo —
      // mover/apagar/reenquadrar continua daqui, sem recomeçar.
      manual: !!it.manual,
      mid: it.mid || null,
      ...(it.x != null ? { x: +it.x } : {}),
      ...(it.y != null ? { y: +it.y } : {}),
      ...(it.w != null ? { w: +it.w } : {}),
      ...(it.h != null ? { h: +it.h } : {}),
      ...(it.size != null ? { size: +it.size } : {}),
      ...(it.entrada ? { entrada: it.entrada } : {}),
      ...(it.saida ? { saida: it.saida } : {}),
      ...(it.fx != null ? { fx: +it.fx } : {}),
      ...(it.fy != null ? { fy: +it.fy } : {}),
      ...(it.zoom != null ? { zoom: +it.zoom } : {}),
      ...(it.srcIn != null ? { srcIn: +it.srcIn } : {}),
      ...(it.camada != null ? { camada: it.camada | 0 } : {}),
    });
  });
  // Emoji e efeito sonoro postos na mao TAMBEM voltam como camada viva
  // depois do render (mesma familia da 4.61): sem isto eles sumiam da
  // timeline — e mover duplicava, apagar ressuscitava (append no pipeline).
  (d.emojis || []).forEach((it) => {
    if (!it || !it.char) return;
    const start = Math.max(0, +it.atSec || 0);
    list.push({
      kind: 'emoji', label: it.char, char: it.char,
      start, end: start + (+it.durSec > 0.05 ? +it.durSec : 1.6),
      manual: true,
      x: it.x != null ? +it.x : 0.5,
      y: it.y != null ? +it.y : 0.34,
      size: it.size != null ? +it.size : 0.22,
    });
  });
  (d.sfxManual || []).forEach((it) => {
    if (!it || !it.src) return;
    const start = Math.max(0, +it.atSec || 0);
    list.push({
      kind: 'sfx', label: (it.src || '').split('/').pop(),
      start, end: start + SFX_BLOCO_S, src: it.src,
      manual: true, volume: it.volume != null ? +it.volume : 0.5,
    });
  });
  // split-layout images (CustomGraphics reads the same array) — they are images
  // like any other insert, so they belong on the image track, not in code
  (d.splitInserts || []).forEach((it, i) => {
    list.push({
      kind: 'split',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  // split-layout VIDEO bands — same seam and geometry as splitInserts, but the
  // band plays a clip (generated b-roll, screen capture). Its own array because
  // the renderer mounts it with a different component; on the timeline it is an
  // image-track element like any other.
  // Selo (lower third) e cartao de capitulo do LONGFORM: eles so existiam
  // queimados no video final — "no visual mostra mas em edicao nao mostra"
  // (02/09). Aqui viram bloco na timeline e cartao vivo no preview da
  // Edicao. O relogio do longform e o proprio cut, entao os tempos valem
  // nas duas abas.
  (d.lowerThirds || []).forEach((it, i) => {
    list.push({
      kind: 'lower', label: `Selo — ${it.name || ''}${it.title ? ' · ' + it.title : ''}`,
      start: +it.start || 0, end: (+it.start || 0) + (+it.dur || 4), ref: i,
    });
  });
  (d.chapters || []).forEach((it, i) => {
    list.push({
      kind: 'chapter', label: `Capítulo — ${it.title || ''}`,
      start: +it.start || 0, end: (+it.start || 0) + (+it.dur || 2.4), ref: i,
    });
  });
  (d.splitVideos || []).forEach((it, i) => {
    list.push({
      kind: 'splitvideo',
      label: it.label || (it.src || '').split('/').pop(),
      start: +it.start, end: +it.end, ref: i,
    });
  });
  (d.behind || []).forEach((b, i) => {
    list.push({ kind: 'behind', label: `BEHIND ${b.kind === 'words' ? (b.words || []).map((w) => w.t).join(' ') : (b.src || '').split('/').pop()}`, start: +b.start, end: +b.start + +b.dur, ref: i });
  });
  // held single words in the caption's own visual language (a keyword the viewer
  // must type, an emphasis beat) — text, so they ride the text track next to the
  // hook rather than the image track
  (d.wordAccents || []).forEach((w, i) => {
    list.push({ kind: 'word', label: w.text, start: +w.start, end: +w.end, ref: i });
  });
  S.insertsDraft = list.map((c) => ({
    ...c,
    orig: { start: c.start, end: c.end },
    // retrato do estado carregado: qualquer mexida num insert manual JA
    // aplicado (geometria, efeito, enquadramento) vira alteracao pendente
    ...(c.manual ? { origGeo: geoDoInsert(c) } : {}),
  }));
  S.manualApagado = false;
}

async function loadWave() {
  try {
    S.wave = await (await fetch(`${BASE}/gen/waveform.json`)).json();
    drawWave();
  } catch (e) { S.wave = null; }
}
async function loadThumbsMeta() {
  try {
    const meta = await (await fetch(`${BASE}/gen/thumbs/meta.json`)).json();
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
const MAX_PPS = 200;
const ZOOM_100_PPS = 40;
const CLIP_TIGHT_PX = 24;

// Zoom keeping `t` (seconds) parked at `anchorX` (px from the panel's left edge).
function applyZoom(pps, t, anchorX) {
  S.pps = Math.min(MAX_PPS, Math.max(S.minPps, pps));
  const span = Math.log(MAX_PPS / S.minPps);
  $('zoom').value = span > 0 ? Math.round((100 * Math.log(S.pps / S.minPps)) / span) : 0;
  renderAll();
  panel.scrollLeft = Math.max(0, LABEL_W + t * S.pps - anchorX);
  drawRuler();
  drawWave();
  positionNeedle();
}

// Trackpad pinch arrives as a wheel event with ctrlKey set. Anchored on the
// pointer (a direct gesture zooms where the fingers are); the slider stays
// anchored on the needle.
panel.addEventListener('wheel', (e) => {
  if (!e.ctrlKey) return; // plain two-finger scrolling stays untouched
  e.preventDefault();
  const pr = panel.getBoundingClientRect();
  const anchorX = e.clientX - pr.left;
  const t = (panel.scrollLeft + anchorX - LABEL_W) / S.pps;
  applyZoom(S.pps * Math.exp(-e.deltaY * 0.01), Math.max(0, t), anchorX);
}, { passive: false });

function setZoom(v) { // slider 0..100 → minPps..200, anchored on the needle
  const t = renderedToDraft(video.currentTime || 0);
  // viewport x of the needle before the zoom; if it is off-screen, pull it to
  // the middle so zooming always lands on the playhead the user is looking at
  const xBefore = LABEL_W + t * S.pps - panel.scrollLeft;
  const visible = xBefore >= LABEL_W && xBefore <= panel.clientWidth;
  const anchor = visible ? xBefore : LABEL_W + (panel.clientWidth - LABEL_W) / 2;
  applyZoom(S.minPps * Math.pow(MAX_PPS / S.minPps, v / 100), t, anchor);
}

function zoomAnchor() {
  const t = renderedToDraft(video.currentTime || 0);
  const xBefore = LABEL_W + t * S.pps - panel.scrollLeft;
  const visible = xBefore >= LABEL_W && xBefore <= panel.clientWidth;
  const anchor = visible ? xBefore : LABEL_W + (panel.clientWidth - LABEL_W) / 2;
  return { t, anchor };
}

function setZoom100() {
  const { t, anchor } = zoomAnchor();
  applyZoom(Math.max(S.minPps, ZOOM_100_PPS), t, anchor);
}

function bumpZoom(factor) {
  const { t, anchor } = zoomAnchor();
  applyZoom(S.pps * factor, t, anchor);
}

// Lanes are clipped at the gutter (and the divider is positioned) by a
// scroll-driven CSS timeline, so both stay pinned to scrollLeft with zero lag.
// All JS has to publish is the scroll RANGE, which only changes on zoom/resize.
function updateScrollRange() {
  const max = Math.max(0, panel.scrollWidth - panel.clientWidth);
  timelineEl.style.setProperty('--max-scroll', `${max}px`);
}

// ---------- rendering ----------
function renderAll() {
  timelineEl.style.width = `${contentWidth()}px`;
  renderClips();
  renderJcutAudio();
  renderChips();
  renderNotes();
  drawRuler();
  drawWave();
  updateScrollRange();
  positionNeedle();
  refreshCapToggle();
}

// ---------- correction markers ----------
function renderNotes() {
  const lane = $('laneNotes');
  lane.innerHTML = '';
  for (const n of S.notes) {
    const chip = el('div', 'note-chip', lane);
    chip.style.left = `${n.start * S.pps}px`;
    chip.style.width = `${Math.max((n.end - n.start) * S.pps, 10)}px`;
    chip.textContent = n.text || '(sem descrição)';
    chip.title = `${fmt(n.start)} → ${fmt(n.end)}\n${n.text || ''}\n\nclique para editar`;
    chip.dataset.id = n.id;
  }
  if (S.pendingIn != null) {
    const p = el('div', 'note-pending', lane);
    p.style.left = `${S.pendingIn * S.pps}px`;
  }
  const btn = $('btnMark');
  btn.classList.toggle('armed', S.pendingIn != null);
  const rotuloMarca = S.pendingIn != null ? 'Até aqui' : 'Marcar';
  $('markText').textContent = rotuloMarca;
  // o botao ficou so com o icone: o estado vai para o `title`
  btn.title = S.pendingIn != null
    ? 'Marcar o FIM do trecho (tecla M)'
    : 'Marcar o começo do trecho a corrigir (tecla M)';
  ajustarBarraNumaLinha();
}

/* ---- a barra cabe sempre numa linha -------------------------------------
 * Ela pede 1175px com todos os rotulos. Abaixo disso o botao da ponta
 * ficava de fora (ou, antes, a barra quebrava em duas fileiras — print do
 * usuario em 29/08). Mede-se SEMPRE no estado largo: tira a classe, olha
 * se cabe, poe de volta se nao couber. Assim nao existe zona de indecisao
 * em que a barra pisca entre os dois estados.
 * Quem e observado e a COLUNA, nao a barra: mexer na classe da barra
 * mudaria o tamanho dela e chamaria o observador de novo, em laco. */
const NIVEIS_DA_BARRA = ['sem-regua', 'apertada', 'sem-zoom', 'so-icone'];

function ajustarBarraNumaLinha() {
  const bar = $('transportBar');
  if (!bar) return;
  bar.classList.remove(...NIVEIS_DA_BARRA);
  for (const nivel of NIVEIS_DA_BARRA) {
    if (bar.scrollWidth <= bar.clientWidth + 1) return;
    bar.classList.add(nivel);
  }
}

if (typeof ResizeObserver !== 'undefined') {
  const alvo = document.getElementById('editorCol');
  if (alvo) new ResizeObserver(() => ajustarBarraNumaLinha()).observe(alvo);
}
window.addEventListener('load', ajustarBarraNumaLinha);

function toggleMark() {
  const t = renderedToDraft(video.currentTime || 0);
  if (S.pendingIn == null) {
    S.pendingIn = t;
    renderNotes();
    toast('Começo marcado — leve a agulha ao fim do trecho e marque de novo', 2600);
    return;
  }
  const start = Math.min(S.pendingIn, t);
  const end = Math.max(S.pendingIn, t);
  if (end - start < 0.05) {
    toast('Trecho curto demais — afaste a agulha do IN', 2200);
    return;
  }
  S.pendingIn = null;
  S.lastMarkRange = { start, end, draftStart: start, draftEnd: end };
  const note = { id: `n${Date.now()}`, start, end, text: '' };
  S.notes.push(note);
  S.notes.sort((a, b) => a.start - b.start);
  renderNotes();
  openNoteEditor(note.id, true);
}

/* Guarda o trecho marcado na Biblioteca, como clipe de b-roll.
 *
 * A 4.31/4.32 fizeram o video de humor USAR os clipes da Biblioteca, em
 * tela cheia — e a unica forma de por um la era recortar arquivo na mao,
 * fora do app. Aqui o acervo nasce do que ele ja filmou: marca com M o
 * comeco e o fim da reacao e guarda.
 *
 * O tempo da nota e do RASCUNHO; quem corta e o arquivo que esta tocando,
 * entao `draftToRendered` faz a conversao — sem isso o clipe sairia
 * deslocado por tudo que foi removido antes dele. */
async function guardarTrechoNaBiblioteca() {
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (!n) return;
  const btn = $('noteBiblioteca');
  const cat = ($('noteCategoria') || {}).value || 'reacao';
  const ini = draftToRendered(n.start);
  const fim = draftToRendered(n.end);
  if (!(fim - ini > 0.4)) {
    toast('Trecho curto demais para guardar (mínimo 0,4s)', 2600);
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Guardando…'; }
  try {
    const r = await fetch(`${BASE}/api/library/trecho`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        arquivo: 'cut.mp4', inicio: ini, fim: fim, categoria: cat,
        // O que ESTA na caixa, nao o que ja foi salvo na nota: quem
        // clica em "Salvar na Biblioteca" acabou de digitar o nome e
        // nunca passou pelo "Aplicar". No teste ao vivo o arquivo saiu
        // como `humor--asset.mp4` — o nome digitado era ignorado.
        nome: (($('noteText') || {}).value || n.text || '').trim().slice(0, 40),
      }),
    });
    const d = await r.json();
    if (!r.ok || d.ok === false) throw new Error(d.error || 'falhou');
    toast(`✓ ${d.arquivo} guardado na Biblioteca (${d.segundos}s)`, 4200);
    // A nota some: ela era a marcacao, nao um pedido de correcao.
    S.notes = S.notes.filter((x) => x.id !== n.id);
    S.editingNote = null;
    $('noteEditor').classList.add('hidden');
    renderNotes();
  } catch (e) {
    toast(e.message || 'Não deu para guardar o trecho', 4000);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Salvar na Biblioteca'; }
  }
}

function openNoteEditor(id, isNew) {
  const n = S.notes.find((x) => x.id === id);
  if (!n) return;
  S.editingNote = id;
  $('noteRange').textContent = `${fmt(n.start)} → ${fmt(n.end)}`;
  $('noteText').value = n.text || '';
  $('noteDelete').classList.toggle('hidden', !!isNew);
  // centred over the timeline (where the user's eyes are), then clamped so a
  // short timeline panel cannot push the editor off-screen
  const ed = $('noteEditor');
  ed.classList.remove('hidden');
  const p = panel.getBoundingClientRect();
  const h = ed.offsetHeight;
  const w = ed.offsetWidth;
  const cy = Math.min(
    Math.max(p.top + p.height / 2, h / 2 + 12),
    window.innerHeight - h / 2 - 12,
  );
  const cx = Math.min(Math.max(p.left + p.width / 2, w / 2 + 12), window.innerWidth - w / 2 - 12);
  ed.style.left = `${cx}px`;
  ed.style.top = `${cy}px`;
  $('noteText').focus();
}

function closeNoteEditor() {
  // a brand-new marker with no text is not worth keeping
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (n && !n.text.trim()) S.notes = S.notes.filter((x) => x.id !== n.id);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
}

// ---------- style setup ----------
const styleName = (group, id) => (STYLE_CATALOG[group].find((o) => o.id === id) || {}).name || '—';
// the accent is a free colour, not a named entry in a list — it names itself
const accentName = (hex) => String(hex || ACCENT_DEFAULT).toUpperCase();
const normHex = (v) => {
  let s = String(v || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(s)) s = s.split('').map((c) => c + c).join(''); // #abc → #aabbcc
  return /^[0-9a-f]{6}$/i.test(s) ? `#${s.toLowerCase()}` : null;
};

/* Which headline styles actually paint the accent. Kept as data because the
 * honest UI note depends on it: with `outline` picked, nothing on screen uses
 * the colour, and saying so beats letting the user wonder why the preview did
 * not move. Mirrors the template — update both together. */
// sombra paints its offset with the accent, sublinhado paints the bar — both
// genuinely consume the pick, so leaving them out would have the Estilo tab
// report "este estilo não usa destaque" while the render plainly used it
const HL_ACCENT_USERS = ['realce', 'misto', 'sombra', 'sublinhado', 'pilula', 'manchete', 'carimbo', 'pergunta',
  'recorte', 'etiqueta', 'marcador', 'linhas', 'riscado', 'caixas', 'quadro'];
const ACCENT_DEFAULT = '#FF0000';

/* Three independent caption colour channels, each painting a different set of
 * styles — splitting these apart (instead of one shared captions.accent) is
 * what lets a project have, say, white legenda text, a red emphasis word, and
 * a green circle all at once:
 *   - "legenda" (captionAccent): the BASE text — karaoke's whole line, the
 *     three static styles (simples/serifada/classica). Stacked's white lines
 *     and scatter's ink-gradient words are NOT this — those two styles keep
 *     their ordinary words fixed and only accent the ONE emphasised element.
 *   - "ênfase" (emphasisAccent): that one accented element — stacked's serif
 *     line, scatter's highlighted word. Karaoke/static have no such element.
 *   - "círculo riscado" (circleAccent): stacked-only, the pencil-circle stroke
 *     around a solo emphasis word — independent from emphasisAccent, so the
 *     serif line and the circle can be two different colours.
 * `nenhuma` uses none of the three (nothing rendered to paint). All three
 * start unpicked (null) rather than forced to ACCENT_DEFAULT — see
 * defaultStyle() — because each has its own natural per-style default colour
 * that a forced value would stomp on. */
const capAccentUsed = () => S.style.captions !== 'nenhuma';
// "bloco" consumes the caption colour too, but paints the SLAB with it rather
// than the text (see SimpleCaptions.tsx) — still a real use of the pick, so it
// belongs here; the note in the Estilo tab is what explains where it lands.
// "recorte" pinta o TEXTO do sticker (o contorno escuro é fixo — é ele que
// garante a leitura); "impacto" usa a cor de ênfase na CAIXA da palavra atual.
// Os cinco de 30/08 tambem consomem a cor: no `metal` ela e a LIGA de que o
// cromado e feito (o degrade sai dela), no `traco` e no `eco` ela pinta o
// texto, na `moldura` a linha e o texto, no `vidro` o texto.
const CAP_BASE_STYLES = ['karaoke', 'simples', 'serifada', 'classica', 'bloco', 'recorte', 'bolha',
  'metal', 'vidro', 'traco', 'moldura', 'eco', 'maquina'];
const CAP_EMPH_STYLES = ['stacked', 'scatter', 'impacto', 'marcador',
  'neon', 'degrade', 'bandeira', 'pilula', 'etiqueta', 'fitadegrade', 'fitadupla', 'etiquetacanto'];
const CAP_CIRCLE_STYLES = ['stacked'];
const legendaAccentUsed = () => capAccentUsed() && CAP_BASE_STYLES.includes(S.style.captions);
const emphasisAccentUsed = () => capAccentUsed() && CAP_EMPH_STYLES.includes(S.style.captions);
const circleAccentUsed = () => capAccentUsed() && CAP_CIRCLE_STYLES.includes(S.style.captions);

// Seletor "Traço da ênfase" (círculo x marca-texto): espelha S.style e
// marca sujo como qualquer knob de estilo.
function wireEmphStyle() {
  const el = $('optEmphStyle');
  // `S.style` so nasce quando o estado carrega, e esta funcao roda no
  // DOMContentLoaded. Marcar `wired` ANTES de ler o estado deixava o
  // seletor vivo na tela e morto por dentro: a linha seguinte estourava,
  // o `setTimeout` de 800ms via `wired` e desistia, e trocar entre
  // "circulo" e "marca-texto" nao mudava nada — calado.
  if (!el || el.dataset.wired || !S.style) return;
  el.dataset.wired = '1';
  el.value = S.style.emphasisStyle === 'marker' ? 'marker' : 'circle';
  el.addEventListener('change', () => {
    S.style.emphasisStyle = el.value === 'marker' ? 'marker' : 'circle';
  });
}
document.addEventListener('DOMContentLoaded', wireEmphStyle);
setTimeout(wireEmphStyle, 800);

function applyAccent() {
  $('styleSetup').style.setProperty('--hl-accent', S.style.accent || ACCENT_DEFAULT);
}

// Unset (not just defaulted) when the user has not picked a caption colour —
// var(--cap-accent, <per-style fallback>) in app.css then falls through to each
// style's own natural colour instead of everything turning ACCENT_DEFAULT.
function applyCaptionAccent() {
  const v = normHex(S.style.captionAccent);
  if (v) $('styleSetup').style.setProperty('--cap-accent', v);
  else $('styleSetup').style.removeProperty('--cap-accent');
}

// Same pattern as applyCaptionAccent, its own CSS variable (--emph-accent).
function applyEmphasisAccent() {
  const v = normHex(S.style.emphasisAccent);
  if (v) $('styleSetup').style.setProperty('--emph-accent', v);
  else $('styleSetup').style.removeProperty('--emph-accent');
}

// No live preview for this one — the mockup's stacked demo does not draw the
// pencil-circle SVG (that lives only in the real Remotion PencilOutline
// component). Nothing to set on #styleSetup; the pick is still tracked in
// S.style.circleAccent and reaches Fase 2 through the save payload like the
// other two. Kept as a function (not skipped) so renderAccentPicker's
// call-apply-on-every-commit contract stays uniform across all three pickers.
function applyCircleAccent() {}

/* One spectral swatch (the OS picker) plus a hex field — no preset row. A grid of
 * canned colours competes with the style cards for attention and still never has
 * the brand colour the user actually wants. Shared builder for both the headline
 * accent and the caption accent — they are independent state, but the same
 * picker widget either way. `allowNone` gives the caption picker a "Padrão" chip
 * that clears back to null (each style's own colour); the headline picker has no
 * such state — realce/misto always paint SOME colour, so there is nothing to
 * clear back to. */
function renderAccentPicker({host, label, get, set, apply, defaultHex, allowNone, onChange}) {
  host.innerHTML = '';
  const raw = get();
  const cur = normHex(raw) || defaultHex;

  if (allowNone) {
    const none = el('label', `swatch none${raw ? '' : ' on'}`, host);
    none.title = 'Padrão do estilo';
    none.innerHTML = NONE_ICON;
    none.addEventListener('click', (e) => {
      e.preventDefault();
      set(null);
      apply();
      // rebuilds the whole widget (the custom swatch/hex field reset to the
      // style's default preview colour too) — this one calls onChange() itself
      renderAccentPicker({host, label, get, set, apply, defaultHex, allowNone, onChange});
    });
  }

  const custom = el('label', 'swatch custom', host);
  custom.title = 'Escolher cor';
  custom.style.setProperty('--swatch-fill', cur);
  const inp = el('input', '', custom);
  inp.type = 'color';
  inp.value = cur;

  const field = el('div', 'hex-field', host);
  el('span', 'hex-hash', field).textContent = '#';
  const hex = el('input', 'hex-input', field);
  hex.type = 'text';
  hex.spellcheck = false;
  hex.maxLength = 7;
  hex.value = cur.slice(1).toUpperCase();
  hex.setAttribute('aria-label', `${label} em hexadecimal`);

  const commit = (v, {fromHexField} = {}) => {
    const n = normHex(v);
    if (!n) return false;
    set(n);
    custom.style.setProperty('--swatch-fill', n);
    inp.value = n;
    if (!fromHexField) hex.value = n.slice(1).toUpperCase();
    apply();   // live — no full rebuild, so dragging the picker stays smooth
    if (allowNone) host.querySelector('.swatch.none')?.classList.remove('on');
    onChange();
    return true;
  };

  inp.addEventListener('input', () => commit(inp.value));
  // typing: accept as soon as it parses, but never fight the user mid-keystroke
  hex.addEventListener('input', () => {
    field.classList.toggle('bad', !normHex(hex.value) && hex.value.trim() !== '');
    commit(hex.value, {fromHexField: true});
  });
  // leaving an unparseable value snaps back rather than silently keeping the old
  // colour behind text that says something else
  hex.addEventListener('blur', () => {
    field.classList.remove('bad');
    hex.value = (normHex(get()) || defaultHex).slice(1).toUpperCase();
  });
  hex.addEventListener('keydown', (e) => { if (e.key === 'Enter') hex.blur(); });

  onChange();
}

const renderAccents = () => renderAccentPicker({
  host: $('optAccent'),
  label: 'Cor da headline',
  get: () => S.style.accent,
  set: (v) => { S.style.accent = v || ACCENT_DEFAULT; }, // no "none" chip on this one
  apply: applyAccent,
  defaultHex: ACCENT_DEFAULT,
  allowNone: false,
  onChange: () => { updateAccentNote(); updateSummary(); },
});

const renderCaptionAccents = () => renderAccentPicker({
  host: $('optCaptionAccent'),
  label: 'Cor da legenda',
  get: () => S.style.captionAccent,
  set: (v) => { S.style.captionAccent = v; },
  apply: applyCaptionAccent,
  defaultHex: ACCENT_DEFAULT,
  allowNone: true,
  onChange: () => { updateCaptionAccentNote(); updateSummary(); },
});

const renderEmphasisAccents = () => renderAccentPicker({
  host: $('optEmphasisAccent'),
  label: 'Cor de ênfase',
  get: () => S.style.emphasisAccent,
  set: (v) => { S.style.emphasisAccent = v; },
  apply: applyEmphasisAccent,
  defaultHex: ACCENT_DEFAULT,
  allowNone: true,
  onChange: () => { updateEmphasisAccentNote(); updateSummary(); },
});

const renderCircleAccents = () => renderAccentPicker({
  host: $('optCircleAccent'),
  label: 'Cor do círculo riscado',
  get: () => S.style.circleAccent,
  set: (v) => { S.style.circleAccent = v; },
  apply: applyCircleAccent,
  defaultHex: '#39E508', // PencilOutline's own default — not ACCENT_DEFAULT
  allowNone: true,
  onChange: () => { updateCircleAccentNote(); updateSummary(); },
});

// Every note below was trimmed to the shortest phrase that still answers
// "does my pick do anything" — these share a row with an all-caps title in a
// card that can be as narrow as ~310px, so a long note was the #1 cause of
// cards in the same row wrapping to different heights.
function updateAccentNote() {
  $('accentNote').textContent = HL_ACCENT_USERS.includes(S.style.headline)
    ? 'aplicada'
    : 'não usada';
}

function updateCaptionAccentNote() {
  if (!capAccentUsed()) {
    $('captionAccentNote').textContent = 'legenda desligada';
  } else if (!legendaAccentUsed()) {
    $('captionAccentNote').textContent = 'ver ênfase';
  } else if (S.style.captionAccent) {
    $('captionAccentNote').textContent = 'aplicada';
  } else {
    $('captionAccentNote').textContent = 'padrão do estilo';
  }
}

function updateEmphasisAccentNote() {
  if (!capAccentUsed()) {
    $('emphasisAccentNote').textContent = 'legenda desligada';
  } else if (!emphasisAccentUsed()) {
    $('emphasisAccentNote').textContent = 'não se aplica';
  } else if (S.style.emphasisAccent) {
    $('emphasisAccentNote').textContent = 'aplicada';
  } else {
    $('emphasisAccentNote').textContent = 'padrão do estilo';
  }
}

function updateCircleAccentNote() {
  if (!capAccentUsed()) {
    $('circleAccentNote').textContent = 'legenda desligada';
  } else if (!circleAccentUsed()) {
    $('circleAccentNote').textContent = 'só no Empilhado';
  } else if (S.style.circleAccent) {
    $('circleAccentNote').textContent = 'aplicada';
  } else {
    $('circleAccentNote').textContent = 'verde padrão';
  }
}

/* Separate from renderSetup so the live colour drag can refresh it without
 * rebuilding every demo. Skipping it there left the footer naming the previous
 * colour while the previews already showed the new one. */
/* ---- previa do layout do video ------------------------------------------
 * O cartao de layout era a unica pista do que ia acontecer: quem escolhia
 * "Vinheta" so via o resultado depois de ~6 min de render. Aqui a mesma
 * tinta do render aparece por cima do preview, como ja acontecia com a
 * legenda e a headline.
 * Os que TRANSFORMAM o video (moldura, barra, desfocado, tela dividida)
 * ficam de fora: imitar o enquadramento deles por CSS mentiria sobre o
 * corte, e mentira aqui e pior que ausencia. */
const LAYOUTS_COM_PREVIA = ['degrade', 'vinheta', 'cinema', 'borda'];

/* Previa do que o usuario acabou de por na mao. Sem ela, descobrir ONDE o
 * emoji caiu custava um render inteiro — e ele pode estar tapando o rosto.
 * So o que foi posto na mao (`isNew`): o insert que a IA colocou esta no
 * relogio do video FINAL e apareceria fora de hora aqui.
 * Som nao entra: nao se ve, e um icone dele so taparia a imagem. */
/* O bloco de mídia da timeline MOSTRA a mídia, não o nome (02/09). Imagem
 * entra como fundo repetido (filmstrip); vídeo ganha UM quadro capturado
 * via canvas, com cache por src — capturar é caro e os chips repintam a
 * toda hora. O nome continua no title (tooltip). */
const MINIATURAS = new Map();   // url -> dataURL, ou lista de callbacks em voo

/* Captura UM quadro de um vídeo (com cache por URL) e entrega por callback.
 * Serve os blocos da timeline E os cartões da Biblioteca — capturar é caro
 * e as duas telas pedem o mesmo quadro. */
function capturarQuadroDeVideo(url, cb) {
  const atual = MINIATURAS.get(url);
  if (typeof atual === 'string' && atual) { cb(atual); return; }
  if (Array.isArray(atual)) { atual.push(cb); return; }
  MINIATURAS.set(url, [cb]);
  const v = document.createElement('video');
  v.muted = true;
  v.preload = 'metadata';
  v.src = url;
  v.addEventListener('loadeddata', () => {
    const d = Number(v.duration) || 0;
    v.currentTime = Math.min(1.0, d * 0.15);
  }, { once: true });
  v.addEventListener('seeked', () => {
    try {
      const cv = document.createElement('canvas');
      const esc = 120 / Math.max(1, v.videoHeight);
      cv.width = Math.max(1, Math.round(v.videoWidth * esc));
      cv.height = 120;
      cv.getContext('2d').drawImage(v, 0, 0, cv.width, cv.height);
      const data = cv.toDataURL('image/jpeg', 0.65);
      const fila = MINIATURAS.get(url);
      MINIATURAS.set(url, data);
      (Array.isArray(fila) ? fila : []).forEach((f) => { try { f(data); } catch { /* segue */ } });
    } catch { MINIATURAS.delete(url); }
    v.removeAttribute('src');
  }, { once: true });
  v.addEventListener('error', () => MINIATURAS.delete(url), { once: true });
}

function miniaturaNoChip(chip, src) {
  chip.classList.add('com-midia');
  const url = mediaHref(`remotion/public/${src}`);
  if (!/\.(mp4|mov|m4v|webm|mkv)$/i.test(String(src))) {
    chip.style.backgroundImage = `url("${url}")`;
    return;
  }
  capturarQuadroDeVideo(url, (data) => {
    document.querySelectorAll(`.chip.insert[data-src="${CSS.escape(src)}"]`)
      .forEach((ch) => { ch.style.backgroundImage = `url("${data}")`; });
    if (chip.isConnected) chip.style.backgroundImage = `url("${data}")`;
  });
}

function desenharMidiaNoPreview() {
  const box = $('midiaOverlay');
  if (!box) return;
  const t = renderedToDraft(video.currentTime || 0);
  // Na aba VISUAL o video e o FINAL, que ja tem a midia aplicada QUEIMADA
  // nele (animando) — desenhar o cartao por cima dava imagem dupla, com "a
  // de tras se mexendo" (print de 02/09). La so entra o que ainda NAO foi
  // aplicado (isNew); na Edicao o video e o cut, sem inserts, entao o
  // cartao representa a camada.
  const naFinal = S.tab === 2 && S.state && S.state.finalVideo && !S.finalFailed;
  const agora = S.insertsDraft.filter(
    (c) => t >= c.start && t < c.end
    && ((c.kind === 'emoji' && (c.isNew || (c.manual && !naFinal)))
      // selo/capitulo do longform: queimados no final; na Edicao (cut cru)
      // o cartao vivo representa o que vai sair
      || ((c.kind === 'lower' || c.kind === 'chapter') && !naFinal)
      || (c.kind === 'insert'
        && (c.isNew || (c.manual && !naFinal)))));
  // mesma ordem de pintura dos motores: camada primeiro (fileira de baixo
  // na timeline = por cima no video), depois quem entra depois fica por cima
  agora.sort((a, b) => ((a.camada | 0) - (b.camada | 0))
    || ((a.start || 0) - (b.start || 0)));
  const chave = agora.map((c) => `${c.kind}:${c.label}:${c.start}:${c.camada | 0}`).join('|');
  if (box.dataset.chave === chave) return;   // sem repintar a cada quadro
  // Caixa ainda sem tamanho (video carregando): pintar agora sairia um
  // cartao de pixels — pinta, mas SEM gravar a chave, para a proxima
  // chamada repintar com a caixa de verdade.
  box.dataset.chave = box.clientWidth > 40 ? chave : '';
  box.innerHTML = '';
  for (const c of agora) {
    if (c.kind === 'lower' || c.kind === 'chapter') {
      // Espelho visual do template/compose do longform: selo embaixo a
      // esquerda (barra + caixa), capitulo com a linha e o titulo grande.
      const accent = (S.editData && S.editData.accent) || '#33e0a3';
      const fonte = S.editData || {};
      const marg = 0.05 * box.clientWidth;
      if (c.kind === 'lower') {
        const it = (fonte.lowerThirds || [])[c.ref] || {};
        const d = el('div', 'lf-previa-selo', box);
        d.style.left = `${marg}px`;
        d.style.bottom = `${marg}px`;
        d.style.setProperty('--accent', accent);
        el('span', 'lf-barra', d);
        const caixa = el('span', 'lf-caixa', d);
        el('b', '', caixa).textContent = it.name || '';
        if (it.title) el('i', '', caixa).textContent = it.title;
      } else {
        const it = (fonte.chapters || [])[c.ref] || {};
        const d = el('div', 'lf-previa-capitulo', box);
        d.style.left = `${marg}px`;
        d.style.bottom = `${marg * 1.4}px`;
        d.style.setProperty('--accent', accent);
        el('span', 'lf-linha', d);
        el('b', '', d).textContent = it.title || '';
      }
      continue;
    }
    if (c.kind === 'emoji') {
      const d = el('div', 'midia-previa-emoji', box);
      d.style.left = `${(c.x ?? 0.5) * 100}%`;
      d.style.top = `${(c.y ?? 0.34) * 100}%`;
      // `size` e fracao da LARGURA, como nos dois motores
      d.style.fontSize = `${(c.size ?? 0.22) * box.clientWidth}px`;
      d.textContent = c.char || '';
      emojiArrastavel(d, c, box);
      continue;
    }
    // PNG/WebP entram como ARTE: inteiros, sem cartao e sem fundo. O
    // retangulo escuro daqui aparecia atras da logo do usuario — e o
    // render nao desenha cartao nenhum nesse caso.
    const arte = /\.(png|webp)$/i.test(String(c.src || ''));
    const card = el('div', `midia-previa-card${arte ? ' arte' : ''}`, box);
    // mesma conta dos dois motores: x/y sao o CENTRO e `size` a largura,
    // ambos em fracao do quadro; a altura segue a proporcao do cartao
    posicionarCartao(card, c, box);
    if (c.src) {
      // Take de VIDEO nao cabe num <img>: saia o icone de imagem quebrada
      // (print de 01/09) e redimensionar "sumia" com o cartao. O render toca
      // o take mudo — o preview mostra o mesmo, rodando em loop.
      if (/\.(mp4|mov|m4v|webm|mkv)$/i.test(String(c.src))) {
        const vid = el('video', '', card);
        vid.src = `${BASE}/media/remotion/public/${c.src}`;
        vid.muted = true;
        vid.loop = true;
        vid.autoplay = true;
        vid.playsInline = true;
        // O primeiro quadro de muito take e PRETO (fade de camera): o
        // cartao parecia uma "tela preta" ate o play andar. Pula para um
        // quadro com conteudo assim que os metadados chegam.
        vid.addEventListener('loadedmetadata', () => {
          const d = Number(vid.duration) || 0;
          const dentro = Math.max(0, +c.srcIn || 0);
          vid.currentTime = dentro || (d > 0.6 ? Math.min(1.0, d * 0.15) : 0);
        }, { once: true });
        // o loop volta ao 0 do ARQUIVO; com in-point, pula de volta para ele
        vid.addEventListener('timeupdate', () => {
          const dentro = Math.max(0, +c.srcIn || 0);
          if (dentro && vid.currentTime < dentro - 0.05) vid.currentTime = dentro;
        });
        vid.play().catch(() => {});
      } else {
        const img = el('img', '', card);
        img.src = `${BASE}/media/remotion/public/${c.src}`;
        img.alt = '';
      }
    }
    // a etiqueta com o nome do arquivo nao entra na arte: ela e uma faixa
    // preta, que e justamente o que a arte nao quer atras dela
    if (!arte) el('div', 'midia-previa-nome', card).textContent = c.label || '';
    // indice para o painel de efeitos achar ESTE cartao (demo do movimento)
    const idx = S.insertsDraft.indexOf(c);
    card.dataset.idx = String(idx);
    aplicarEnquadramento(card, c);
    if (S.enquadrando === idx) card.classList.add('enquadrando');
    // o SELECIONADO fica no topo — a demo da animação nunca roda escondida
    // atrás de outro cartão
    if (S.blocoSel === idx) card.classList.add('sel');
    card.addEventListener('dblclick', (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (c.kind === 'insert') alternarEnquadrar(S.insertsDraft.indexOf(c));
    });
    cartaoArrastavel(card, c, box);
  }
}

/* O usuario pediu (01/09) para ESCOLHER as animacoes do video ou imagem
 * posto na mao — entrada E saida. As mesmas formulas nos dois motores;
 * clicar ja demonstra o movimento no proprio cartao. */
const ENTRADAS_DE_MIDIA = [
  ['nenhum', 'Nenhum', 'Aparece de uma vez, sem animação'],
  ['padrao', 'Suave', 'Sobe e aparece (padrão)'],
  ['pop', 'Pop', 'Cresce com quique'],
  ['deslizar', 'Da esquerda', 'Entra pela esquerda'],
  ['direita', 'Da direita', 'Entra pela direita'],
  ['baixo', 'De baixo', 'Sobe de baixo'],
  ['cima', 'De cima', 'Desce de cima'],
  ['fade', 'Fade', 'Só aparece, sem movimento'],
  ['zoom', 'Zoom', 'Chega de longe (1,25 → 1)'],
  ['girar', 'Girar', 'Gira e assenta'],
  ['quicar', 'Quicar', 'Cai de cima e quica'],
  ['elastico', 'Elástico', 'Estica como mola'],
  ['balancar', 'Balançar', 'Pêndulo que assenta'],
  ['borrao', 'Borrão', 'Chega desfocado'],
  ['virar', 'Virar', 'Abre como uma porta'],
  ['carimbo', 'Carimbo', 'Bate grande e assenta'],
  ['piscar', 'Piscar', 'Pisca ao entrar'],
  ['esticar', 'Esticar', 'Abre na vertical, como persiana'],
];
const SAIDAS_DE_MIDIA = [
  ['nenhum', 'Nenhum', 'Fica até o fim, sem animação'],
  ['suave', 'Suave', 'Some devagar (padrão)'],
  ['encolher', 'Encolher', 'Diminui e some'],
  ['deslizar', 'P/ direita', 'Sai pela direita'],
  ['esquerda', 'P/ esquerda', 'Sai pela esquerda'],
  ['baixo', 'P/ baixo', 'Cai para baixo'],
  ['zoom', 'Zoom', 'Cresce e some'],
  ['girar', 'Girar', 'Gira e some'],
  ['cima', 'P/ cima', 'Sobe e some'],
  ['borrao', 'Borrão', 'Desfoca e some'],
  ['virar', 'Virar', 'Fecha como uma porta'],
  ['piscar', 'Piscar', 'Pisca antes de sumir'],
  ['esticar', 'Esticar', 'Fecha na vertical, como persiana'],
  ['corte', 'Corte', 'Some de uma vez, sem fade'],
];
const DEMOS_DE_MIDIA = [
  ...ENTRADAS_DE_MIDIA.map(([id]) => `ent-demo-${id}`),
  ...SAIDAS_DE_MIDIA.map(([id]) => `sai-demo-${id}`),
];

function _nomeDaAnim(lista, id, padrao) {
  const hit = lista.find(([k]) => k === (id || padrao));
  return hit ? hit[1] : padrao;
}

/* O painel `fx` mora na TIMELINE, nao sobre o video — os botoes em cima do
 * cartao tapavam o conteudo (feedback ao vivo de 01/09). Ele aparece quando
 * um bloco de midia posto na mao esta selecionado (clique no bloco da linha
 * do tempo ou no proprio cartao). */
function renderFxPanel() {
  const painel = $('fxPanel');
  const lane = $('fxLane');
  if (!painel || !lane) return;
  // o dropdown vive no <body> (a lane rola e clipa filhos absolutos) —
  // repintar o painel descarta qualquer dropdown antigo
  document.querySelectorAll('body > .fx-drop').forEach((d) => d.remove());
  const c = S.blocoSel >= 0 ? S.insertsDraft[S.blocoSel] : null;
  const mostrar = !!(c && c.kind === 'insert' && (c.isNew || c.manual));
  painel.classList.toggle('hidden', !mostrar);
  if (!mostrar) { lane.innerHTML = ''; return; }
  lane.innerHTML = '';
  const nome = el('span', 'fx-nome', lane);
  nome.textContent = c.label || 'mídia';
  nome.title = c.label || '';
  // ENQUADRAR: o mesmo modo do duplo clique no cartao, com botao visivel
  const enq = el('button', `ent-btn${S.enquadrando === S.blocoSel ? ' on' : ''}`, lane);
  enq.type = 'button';
  enq.textContent = 'Enquadrar';
  enq.title = 'Escolher que parte da imagem/vídeo aparece no cartão (ou duplo clique no cartão)';
  enq.addEventListener('click', () => alternarEnquadrar(S.blocoSel));
  const demoNoCartao = (prefixo, id) => {
    const card = document.querySelector(
      `.midia-previa-card[data-idx="${S.blocoSel}"]`);
    if (!card) return;
    card.classList.remove(...DEMOS_DE_MIDIA);
    void card.offsetWidth;   // reinicia a animacao CSS
    card.classList.add(`${prefixo}-demo-${id}`);
  };
  // UM botao "Animações" com dropdown (pedido de 02/09): o catalogo cresceu
  // e duas fileiras de botoes nao cabiam mais na faixa.
  const anim = el('button', 'ent-btn fx-anim-btn', lane);
  anim.type = 'button';
  anim.textContent = `Animações: ${_nomeDaAnim(ENTRADAS_DE_MIDIA, c.entrada, 'padrao')}`
    + ` → ${_nomeDaAnim(SAIDAS_DE_MIDIA, c.saida, 'suave')}`;
  anim.title = 'Escolher a animação de entrada e de saída';
  const drop = el('div', 'fx-drop hidden', document.body);
  const montarDrop = () => {
    drop.innerHTML = '';
    const coluna = (rotulo, opcoes, campo, padrao, prefixo) => {
      const col = el('div', 'fx-drop-col', drop);
      el('div', 'fx-drop-titulo', col).textContent = rotulo;
      for (const [id, nomeB, dica] of opcoes) {
        const b = el('button', `fx-opt${(c[campo] || padrao) === id ? ' on' : ''}`, col);
        b.type = 'button';
        b.textContent = nomeB;
        b.title = dica;
        b.addEventListener('click', (e) => {
          e.stopPropagation();
          c[campo] = id === padrao ? null : id;
          demoNoCartao(prefixo, id);
          anim.textContent = `Animações: ${_nomeDaAnim(ENTRADAS_DE_MIDIA, c.entrada, 'padrao')}`
            + ` → ${_nomeDaAnim(SAIDAS_DE_MIDIA, c.saida, 'suave')}`;
          montarDrop();   // re-marca o ativo, mantendo o dropdown aberto
          refreshHeader();
          scheduleAutosave();
        });
      }
    };
    coluna('Entrada', ENTRADAS_DE_MIDIA, 'entrada', 'padrao', 'ent');
    coluna('Saída', SAIDAS_DE_MIDIA, 'saida', 'suave', 'sai');
  };
  anim.addEventListener('click', (e) => {
    e.stopPropagation();
    const abrir = drop.classList.contains('hidden');
    if (abrir) {
      montarDrop();
      const r = anim.getBoundingClientRect();
      drop.style.left = `${Math.max(8, Math.min(window.innerWidth - 280, r.left))}px`;
      drop.style.bottom = `${window.innerHeight - r.top + 6}px`;
    }
    drop.classList.toggle('hidden', !abrir);
  });
}

// clique fora fecha o dropdown de animações — UM listener global (dentro de
// renderFxPanel acumularia um por repintura)
document.addEventListener('click', (e) => {
  document.querySelectorAll('.fx-drop:not(.hidden)').forEach((d) => {
    if (!d.contains(e.target) && !e.target.closest?.('.fx-anim-btn')) {
      d.classList.add('hidden');
    }
  });
});

/* O emoji se arrasta sobre o video e a roda muda o tamanho — o mesmo gesto
 * da manchete e da legenda. Ele nascia no centro-alto e ficava la: tirar do
 * rosto de quem fala exigia mexer no arquivo.
 * A posicao vive no proprio bloco e viaja no salvar; `x`/`y` sao fracao do
 * quadro, que e o que os dois motores desenham. */
/* A roda sobre o bloco do efeito muda o VOLUME. Era fixo em 0,5: som
 * gravado alto entrava alto demais e nao havia como baixar sem editar
 * arquivo. Passo multiplicativo, como no tamanho do emoji. */
/* Tira um bloco posto na mao. Guarda no historico ANTES, para o Ctrl+Z
 * trazer de volta — remover por engano nao pode custar o trabalho todo. */
function removerBlocoDaMao(i) {
  const c = S.insertsDraft[i];
  // emoji e som JA aplicados (manual) tambem saem daqui — a ausencia na
  // lista salva e o que apaga do video (protocolo de substituicao)
  if (!c || !(c.isNew || c.manual)) return;
  pushHistory();
  // manual JA aplicado: a ausencia na lista salva e o que APAGA do video
  if (c.manual && !c.isNew) S.manualApagado = true;
  S.blocoSel = -1;
  S.insertsDraft.splice(i, 1);
  renderAll();
  desenharMidiaNoPreview();
  refreshHeader();
  scheduleAutosave();
  const que = c.kind === 'sfx' ? 'Som' : c.kind === 'emoji' ? 'Emoji' : 'Mídia';
  toast(`${que} tirado — Ctrl+Z traz de volta`, 2600);
}

function somComVolume(chip, c) {
  if (chip.dataset.vol) return;
  chip.dataset.vol = '1';
  chip.addEventListener('wheel', (e) => {
    if (S.applying) return;
    e.preventDefault();
    e.stopPropagation();
    const fator = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const novo = Math.max(0.05, Math.min(1.5, (c.volume ?? 0.5) * fator));
    c.volume = +novo.toFixed(3);
    const pct = Math.round(c.volume * 100);
    chip.textContent = `${c.label} · ${pct}%`;
    chip.title = `${c.label} — ${pct}% de volume (roda do mouse muda)`;
    refreshHeader();
    scheduleAutosave();
  }, { passive: false });
}

/* O cartao de sempre, em fracao do quadro (780x500 a 90px do topo em
 * 1080x1920). E o padrao de quem nao mexeu — igual ao dos dois motores. */
const CARTAO_SIZE_PAD = 780 / 1080;
const CARTAO_Y_PAD = (90 + 250) / 1920;

/* Arrastar e redimensionar a imagem, como o emoji. Ela era um cartao fixo
 * no alto: no video do usuario (30/08) a foto tapava a cena e nao havia
 * como tirar do caminho. */
/* A alca de canto: `aplicar(fracao)` desenha o novo tamanho e `guardar()`
 * grava. Serve para o cartao e para o emoji — o gesto tem de ser o mesmo
 * nos dois, senao cada elemento vira um aprendizado novo. */
function alcaDeTamanho(alvo, box, ler, aplicar, minimo, maximo) {
  const alca = el('div', 'previa-alca', alvo);
  alca.title = 'Arraste para mudar o tamanho';
  let arr = null;
  alca.addEventListener('pointerdown', (e) => {
    if (S.applying || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();      // senao vira ARRASTO do elemento
    arr = { x0: e.clientX, y0: e.clientY, base: ler(),
            larg: box.getBoundingClientRect().width, moveu: false };
    alca.setPointerCapture(e.pointerId);
  });
  alca.addEventListener('pointermove', (e) => {
    if (!arr) return;
    // a diagonal manda: puxar para fora cresce, para dentro encolhe
    const d = ((e.clientX - arr.x0) + (e.clientY - arr.y0)) / 2;
    if (!arr.moveu && Math.abs(d) < 3) return;
    arr.moveu = true;
    const frac = Math.max(minimo, Math.min(maximo, arr.base + (2 * d) / arr.larg));
    aplicar(frac, false);
  });
  const soltar = (e) => {
    if (!arr) return;
    const moveu = arr.moveu;
    arr = null;
    try { alca.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
    if (moveu) aplicar(ler(), true);
  };
  alca.addEventListener('pointerup', soltar);
  alca.addEventListener('pointercancel', soltar);
  return alca;
}

/* Onde o cartao fica na previa. Uma conta so, usada pelo desenho inicial,
 * pelo arrasto e pelas alcas — tres copias divergiriam no primeiro ajuste.
 * Espelha `geometria_do_insert` (motor proprio) e o InsertCard (Remotion). */
function larguraDoCartao(c) {
  return Math.min(1, Math.max(0.08, c.w ?? c.size ?? CARTAO_SIZE_PAD));
}
function alturaDoCartao(c, box) {
  const padrao = (larguraDoCartao(c) * box.clientWidth * (500 / 780))
    / Math.max(1, box.clientHeight);
  return Math.min(1, Math.max(0.05, c.h ?? padrao));
}
function posicionarCartao(card, c, box) {
  // PORCENTAGEM, nao pixel: com pixels o cartao ficava do tamanho que a
  // caixa tinha NA HORA da pintura — redimensionar a janela (ou pintar
  // antes do video assentar) deixava um cartao de 12x7px no canto ("nao da
  // pra ver", print de 01/09). Em %, o cartao acompanha a caixa sozinho.
  const lw = larguraDoCartao(c);
  const lh = alturaDoCartao(c, box);
  card.style.width = `${lw * 100}%`;
  card.style.height = `${lh * 100}%`;
  card.style.left = `${((c.x ?? 0.5) - lw / 2) * 100}%`;
  card.style.top = `${((c.y ?? CARTAO_Y_PAD) - lh / 2) * 100}%`;
}

/* Guias de arrasto (pedido de 02/09): linha de centro que ACENDE quando o
 * cartao trava no meio, e as MEDIDAS de cada lado ("87 img 87") do lado de
 * fora do cartao — em pixels do VIDEO (1080x1920), que e a medida que vale
 * no render. So aparecem enquanto arrasta. */
function _guias(box) {
  let g = box.querySelector('.guias-arrasto');
  if (!g) {
    g = el('div', 'guias-arrasto', box);
    for (const cls of ['guia-centro-v', 'guia-centro-h', 'gm gm-esq',
                       'gm gm-dir', 'gm gm-topo', 'gm gm-baixo']) {
      el('div', `${cls} hidden`, g);
    }
  }
  return g;
}

function atualizarGuias(box, card, nx, ny, snapX, snapY) {
  const g = _guias(box);
  g.querySelector('.guia-centro-v').classList.toggle('hidden', !snapX);
  g.querySelector('.guia-centro-h').classList.toggle('hidden', !snapY);
  const lw = card.offsetWidth / Math.max(1, box.clientWidth);
  const lh = card.offsetHeight / Math.max(1, box.clientHeight);
  const bordas = {
    esq: { v: (nx - lw / 2) * 1080, x: (nx - lw / 2) / 2, y: ny },
    dir: { v: (1 - nx - lw / 2) * 1080, x: (nx + lw / 2 + 1) / 2, y: ny },
    topo: { v: (ny - lh / 2) * 1920, x: nx, y: (ny - lh / 2) / 2 },
    baixo: { v: (1 - ny - lh / 2) * 1920, x: nx, y: (ny + lh / 2 + 1) / 2 },
  };
  for (const [lado, b] of Object.entries(bordas)) {
    const m = g.querySelector(`.gm-${lado}`);
    const px = Math.round(b.v);
    m.classList.toggle('hidden', px < 12);   // colado na borda: sem numero
    m.textContent = String(Math.max(0, px));
    m.style.left = `${b.x * 100}%`;
    m.style.top = `${b.y * 100}%`;
  }
}

function esconderGuias(box) {
  const g = box.querySelector('.guias-arrasto');
  if (g) g.querySelectorAll('div').forEach((n) => n.classList.add('hidden'));
}

/* ENQUADRAR (recorte do que aparece): o cartao corta a imagem/video em
 * `cover`, e fx/fy dizem QUE PARTE fica visivel (0,5 = centro, o padrao) —
 * o mesmo object-position dos dois motores. Duplo clique no cartao entra e
 * sai do modo; no modo, arrastar move o conteudo dentro do quadro. */
function aplicarEnquadramento(card, c) {
  const m = card.querySelector('img, video');
  if (!m) return;
  m.style.objectPosition = `${(c.fx ?? 0.5) * 100}% ${(c.fy ?? 0.5) * 100}%`;
  // `zoom` (>=1) amplia o conteudo ALEM do cover, ancorado no ponto do
  // enquadramento — e o que torna o corte de UM lado verdadeiro mesmo
  // quando o conteudo ja esta justo naquele eixo. Mesma conta nos motores.
  const z = Math.max(1, +(c.zoom ?? 1));
  m.style.transformOrigin = `${(c.fx ?? 0.5) * 100}% ${(c.fy ?? 0.5) * 100}%`;
  m.style.transform = z > 1.0001 ? `scale(${z})` : '';
}

function panDoConteudo(card, c, dx, dy, arr) {
  const m = card.querySelector('img, video');
  if (!m) return;
  const natW = m.naturalWidth || m.videoWidth || 0;
  const natH = m.naturalHeight || m.videoHeight || 0;
  if (!natW || !natH) return;
  const esc = Math.max(card.offsetWidth / natW, card.offsetHeight / natH)
    * Math.max(1, +(c.zoom ?? 1));
  const sobraX = natW * esc - card.offsetWidth;
  const sobraY = natH * esc - card.offsetHeight;
  if (arr.fx0 == null) { arr.fx0 = c.fx ?? 0.5; arr.fy0 = c.fy ?? 0.5; }
  // arrastar para a direita mostra o que esta a ESQUERDA (conteudo acompanha o dedo)
  if (sobraX > 1) c.fx = +Math.min(1, Math.max(0, arr.fx0 - dx / sobraX)).toFixed(4);
  if (sobraY > 1) c.fy = +Math.min(1, Math.max(0, arr.fy0 - dy / sobraY)).toFixed(4);
  aplicarEnquadramento(card, c);
}

function alternarEnquadrar(i) {
  // indice invalido (bloco deselecionado no meio) so pode DESLIGAR o modo
  if (i == null || i < 0 || !S.insertsDraft[i]) {
    S.enquadrando = null;
    document.querySelectorAll('.midia-previa-card.enquadrando')
      .forEach((cd) => cd.classList.remove('enquadrando'));
    return;
  }
  const ligou = S.enquadrando !== i;
  S.enquadrando = ligou ? i : null;
  document.querySelectorAll('.midia-previa-card').forEach((cd) => {
    cd.classList.toggle('enquadrando', ligou && cd.dataset.idx === String(i));
  });
  renderFxPanel();
  toast(ligou
    ? 'Enquadrar: arraste para escolher a parte que aparece — duplo clique para sair'
    : '✓ Enquadramento salvo', 3200);
}

/* Quatro cantos e quatro lados. Cada alca puxa o SEU lado e deixa o oposto
 * parado — puxar a direita cresce para a direita, e nao para os dois lados.
 * Por isso a conta e em bordas e o centro sai delas. */
const ALCAS = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

function alcasDoCartao(card, c, box) {
  /* Divisão de gestos dos editores profissionais (pedido de 02/09):
   * CANTOS redimensionam (a imagem inteira cresce/diminui na proporção,
   * o enquadramento não muda); LADOS cortam DAQUELE lado — o conteúdo
   * que sobra fica parado na tela e só o pedaço arrastado some (o fx/fy
   * é compensado para ancorar o lado oposto). */
  for (const lado of ALCAS) {
    const canto = lado.length === 2;
    const alca = el('div', `previa-alca alca-${lado}`, card);
    alca.title = canto
      ? 'Arraste para redimensionar (mantém a proporção)'
      : 'Arraste para cortar deste lado';
    let arr = null;
    alca.addEventListener('pointerdown', (e) => {
      if (S.applying || e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();          // senao vira ARRASTO do cartao
      const r = box.getBoundingClientRect();
      const lw = larguraDoCartao(c);
      const lh = alturaDoCartao(c, box);
      const cx = c.x ?? 0.5;
      const cy = c.y ?? CARTAO_Y_PAD;
      const m = card.querySelector('img, video');
      arr = { x0: e.clientX, y0: e.clientY, larg: r.width, alt: r.height,
              l: cx - lw / 2, r: cx + lw / 2, t: cy - lh / 2, b: cy + lh / 2,
              w0: lw, h0: lh,
              fx0: c.fx ?? 0.5, fy0: c.fy ?? 0.5,
              natW: (m && (m.naturalWidth || m.videoWidth)) || 0,
              natH: (m && (m.naturalHeight || m.videoHeight)) || 0,
              arte: card.classList.contains('arte'),
              moveu: false };
      alca.setPointerCapture(e.pointerId);
    });
    alca.addEventListener('pointermove', (e) => {
      if (!arr) return;
      const dx = (e.clientX - arr.x0) / arr.larg;
      const dy = (e.clientY - arr.y0) / arr.alt;
      if (!arr.moveu && Math.abs(dx) < 0.005 && Math.abs(dy) < 0.005) return;
      arr.moveu = true;
      let { l, r, t, b } = arr;
      if (canto) {
        // REDIMENSIONA na proporção, com o canto OPOSTO parado
        const kx = (arr.w0 + (lado.includes('e') ? dx : -dx)) / arr.w0;
        const ky = (arr.h0 + (lado.includes('s') ? dy : -dy)) / arr.h0;
        const k = Math.max(0.12, Math.abs(dx) >= Math.abs(dy) ? kx : ky);
        const nw = Math.max(0.08, Math.min(1, arr.w0 * k));
        const nh = Math.max(0.05, Math.min(1, arr.h0 * k));
        if (lado.includes('e')) r = Math.min(1, arr.l + nw); else l = Math.max(0, arr.r - nw);
        if (lado.includes('s')) b = Math.min(1, arr.t + nh); else t = Math.max(0, arr.b - nh);
      } else {
        // CORTA daquele lado: só a borda arrastada se mexe...
        if (lado === 'w') l = Math.min(r - 0.08, Math.max(0, arr.l + dx));
        if (lado === 'e') r = Math.max(l + 0.08, Math.min(1, arr.r + dx));
        if (lado === 'n') t = Math.min(b - 0.05, Math.max(0, arr.t + dy));
        if (lado === 's') b = Math.max(t + 0.05, Math.min(1, arr.b + dy));
        // ...e o CONTEÚDO fica parado: a ESCALA do conteúdo não muda (se o
        // cover re-encaixaria, o `zoom` segura) e o enquadramento é
        // compensado para o lado oposto mostrar exatamente o que mostrava.
        // (arte em `contain` não croppa — não há o que compensar)
        if (!arr.arte && arr.natW > 0 && arr.natH > 0) {
          const W = arr.larg; const H = arr.alt;
          const w0 = arr.w0 * W; const h0 = arr.h0 * H;
          const w1 = (r - l) * W; const h1 = (b - t) * H;
          if (arr.S0 == null) {
            arr.S0 = Math.max(w0 / arr.natW, h0 / arr.natH)
              * Math.max(1, +(c.zoom ?? 1));
          }
          const fit1 = Math.max(w1 / arr.natW, h1 / arr.natH);
          const z1 = Math.min(4, Math.max(1, arr.S0 / fit1));
          c.zoom = +z1.toFixed(4);
          const S1 = fit1 * z1;     // escala real (pode ceder no clamp)
          if (lado === 'e' || lado === 'w') {
            const sobra0 = arr.natW * arr.S0 - w0;
            const sobra1 = arr.natW * S1 - w1;
            if (sobra1 > 0.5) {
              c.fx = +(Math.min(1, Math.max(0, lado === 'e'
                ? (sobra0 * arr.fx0) / sobra1
                : 1 - (sobra0 * (1 - arr.fx0)) / sobra1))).toFixed(4);
            }
          } else {
            const sobra0 = arr.natH * arr.S0 - h0;
            const sobra1 = arr.natH * S1 - h1;
            if (sobra1 > 0.5) {
              c.fy = +(Math.min(1, Math.max(0, lado === 's'
                ? (sobra0 * arr.fy0) / sobra1
                : 1 - (sobra0 * (1 - arr.fy0)) / sobra1))).toFixed(4);
            }
          }
          aplicarEnquadramento(card, c);
        }
      }
      c.w = +(r - l).toFixed(4);
      c.size = c.w;
      c.h = +(b - t).toFixed(4);
      c.x = +((l + r) / 2).toFixed(4);
      c.y = +((t + b) / 2).toFixed(4);
      posicionarCartao(card, c, box);
    });
    const soltar = (e) => {
      if (!arr) return;
      const moveu = arr.moveu;
      arr = null;
      try { alca.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
      if (!moveu) return;
      pushHistory();
      refreshHeader();
      scheduleAutosave();
    };
    alca.addEventListener('pointerup', soltar);
    alca.addEventListener('pointercancel', soltar);
  }
}

function cartaoArrastavel(card, c, box) {
  if (card.dataset.arrasta) return;
  card.dataset.arrasta = '1';
  card.classList.add('movivel');
  let arr = null;

  card.addEventListener('pointerdown', (e) => {
    if (S.applying || e.button !== 0) return;
    const r = box.getBoundingClientRect();
    arr = { x0: e.clientX, y0: e.clientY, cx: c.x ?? 0.5, cy: c.y ?? CARTAO_Y_PAD,
            larg: r.width, alt: r.height, moveu: false };
    card.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  });

  card.addEventListener('pointermove', (e) => {
    if (!arr) return;
    const dx = e.clientX - arr.x0;
    const dy = e.clientY - arr.y0;
    if (!arr.moveu && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;
    arr.moveu = true;
    // Modo ENQUADRAR: o arrasto move o CONTEUDO dentro do cartao (escolhe
    // que parte da imagem/video aparece), nao o cartao. Ver enquadrarCartao.
    if (S.enquadrando === S.insertsDraft.indexOf(c)) {
      panDoConteudo(card, c, dx, dy, arr);
      return;
    }
    card.classList.add('dragging');
    let nx = Math.max(0.02, Math.min(0.98, arr.cx + dx / arr.larg));
    let ny = Math.max(0.02, Math.min(0.98, arr.cy + dy / arr.alt));
    // TRAVA no centro (pedido de 02/09): perto do meio, gruda — e a linha
    // de alinhamento acende. 8px de tela e o iman de sempre dos editores.
    const snapX = Math.abs(nx - 0.5) * arr.larg < 8;
    const snapY = Math.abs(ny - 0.5) * arr.alt < 8;
    if (snapX) nx = 0.5;
    if (snapY) ny = 0.5;
    card.style.left = `${nx * arr.larg - card.offsetWidth / 2}px`;
    card.style.top = `${ny * arr.alt - card.offsetHeight / 2}px`;
    // (a largura/altura nao mudam no arrasto — so o centro)
    card.dataset.nx = String(nx);
    card.dataset.ny = String(ny);
    atualizarGuias(box, card, nx, ny, snapX, snapY);
  });

  const soltar = (e) => {
    if (!arr) return;
    const moveu = arr.moveu;
    arr = null;
    esconderGuias(box);
    card.classList.remove('dragging');
    try { card.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
    if (!moveu) {
      // clique simples SELECIONA o bloco — e o painel de efeitos da
      // timeline (fx) aparece para ele
      const i = S.insertsDraft.indexOf(c);
      if (i >= 0 && S.blocoSel !== i) {
        S.blocoSel = i;
        renderAll();
        refreshHeader();
      }
      return;
    }
    if (S.enquadrando === S.insertsDraft.indexOf(c)) {
      // pan do enquadramento: fx/fy ja foram atualizados durante o arrasto
      refreshHeader();
      scheduleAutosave();
      return;
    }
    pushHistory();
    c.x = +Number(card.dataset.nx || c.x || 0.5).toFixed(4);
    c.y = +Number(card.dataset.ny || c.y || CARTAO_Y_PAD).toFixed(4);
    refreshHeader();
    scheduleAutosave();
    toast('Imagem movida — Salvar para valer no vídeo', 2200);
  };
  card.addEventListener('pointerup', soltar);
  card.addEventListener('pointercancel', soltar);

  const desenhar = (frac, gravar) => {
    // a roda mexe so na largura; a altura acompanha se o usuario nunca a
    // ajustou na mao (senao ela seria "corrigida" a cada giro)
    c.w = +frac.toFixed(4);
    if (c.h == null) c.h = +(c.w * (500 / 780) * (box.clientWidth / Math.max(1, box.clientHeight))).toFixed(4);
    else c.h = +Math.min(1, Math.max(0.05, c.h * (frac / (c.size ?? frac)))).toFixed(4);
    c.size = c.w;
    posicionarCartao(card, c, box);
    if (gravar) {
      refreshHeader();
      scheduleAutosave();
    }
  };
  // Oito alcas: quatro cantos e quatro lados. Uma so, com proporcao
  // travada, nunca cobria a tela.
  alcasDoCartao(card, c, box);
  card.addEventListener('wheel', (e) => {
    if (S.applying) return;
    e.preventDefault();
    const fator = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    desenhar(Math.max(0.12, Math.min(1.0, (c.size ?? CARTAO_SIZE_PAD) * fator)), true);
  }, { passive: false });
}

function emojiArrastavel(d, c, box) {
  if (d.dataset.arrasta) return;
  d.dataset.arrasta = '1';
  d.classList.add('movivel');
  let arr = null;

  d.addEventListener('pointerdown', (e) => {
    if (S.applying || e.button !== 0) return;
    const r = box.getBoundingClientRect();
    arr = { x0: e.clientX, y0: e.clientY, cx: c.x ?? 0.5, cy: c.y ?? 0.34,
            larg: r.width, alt: r.height, moveu: false };
    d.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  });

  d.addEventListener('pointermove', (e) => {
    if (!arr) return;
    const dx = e.clientX - arr.x0;
    const dy = e.clientY - arr.y0;
    if (!arr.moveu && Math.abs(dx) < 4 && Math.abs(dy) < 4) return;  // tremor
    arr.moveu = true;
    d.classList.add('dragging');
    // preso ao quadro: emoji fora da tela e emoji que ninguem ve
    const nx = Math.max(0.02, Math.min(0.98, arr.cx + dx / arr.larg));
    const ny = Math.max(0.02, Math.min(0.98, arr.cy + dy / arr.alt));
    d.style.left = `${nx * 100}%`;
    d.style.top = `${ny * 100}%`;
    d.dataset.nx = String(nx);
    d.dataset.ny = String(ny);
  });

  const soltar = (e) => {
    if (!arr) return;
    const moveu = arr.moveu;
    arr = null;
    d.classList.remove('dragging');
    try { d.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
    if (!moveu) return;
    pushHistory();
    c.x = +Number(d.dataset.nx || c.x || 0.5).toFixed(4);
    c.y = +Number(d.dataset.ny || c.y || 0.34).toFixed(4);
    refreshHeader();
    scheduleAutosave();
    toast('Emoji movido — Salvar para valer no vídeo', 2200);
  };
  d.addEventListener('pointerup', soltar);
  d.addEventListener('pointercancel', soltar);

  const desenharEmoji = (frac, gravar) => {
    c.size = +frac.toFixed(4);
    d.style.fontSize = `${c.size * box.clientWidth}px`;
    if (gravar) {
      refreshHeader();
      scheduleAutosave();
    }
  };
  // mesma alca do cartao: um gesto so para os dois
  alcaDeTamanho(d, box, () => c.size ?? 0.22, desenharEmoji, 0.06, 0.7);
  // roda = tamanho. O passo e multiplicativo para o ajuste ser igual em
  // emoji pequeno e grande.
  d.addEventListener('wheel', (e) => {
    if (S.applying) return;
    e.preventDefault();
    const fator = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    desenharEmoji(Math.max(0.06, Math.min(0.7, (c.size ?? 0.22) * fator)), true);
  }, { passive: false });
}

function aplicarLayoutNoPreview() {
  const box = $('layoutOverlay');
  if (!box) return;
  const nome = String((S.style && S.style.edit) || 'limpa').toLowerCase();
  box.className = 'layout-overlay';
  box.innerHTML = '';
  if (LAYOUTS_COM_PREVIA.indexOf(nome) < 0) return;
  box.classList.add(`layout-${nome}`);
  if (nome !== 'borda') return;
  // 26px de recuo, 6px de traco e canto 28 valem para o quadro de 1080 de
  // largura; no preview tudo isso encolhe junto.
  const esc = box.clientWidth / 1080;
  const linha = el('div', 'layout-borda-linha', box);
  linha.style.inset = `${Math.round(26 * esc)}px`;
  linha.style.borderWidth = `${Math.max(1, 6 * esc).toFixed(1)}px`;
  linha.style.borderRadius = `${Math.round(28 * esc)}px`;
}

if (typeof ResizeObserver !== 'undefined') {
  const palco = document.querySelector('.player-frame');
  if (palco) new ResizeObserver(() => aplicarLayoutNoPreview()).observe(palco);
}

function updateSummary() {
  const on = STYLE_CATALOG.elements.filter((e) => S.style.elements[e.id]);
  const accentBit = HL_ACCENT_USERS.includes(S.style.headline)
    ? ` · destaque ${accentName(S.style.accent)}` : '';
  const capAccentBit = legendaAccentUsed() && S.style.captionAccent
    ? ` (cor ${accentName(S.style.captionAccent)})` : '';
  const emphAccentBit = emphasisAccentUsed() && S.style.emphasisAccent
    ? ` (ênfase ${accentName(S.style.emphasisAccent)})` : '';
  const circleAccentBit = circleAccentUsed() && S.style.circleAccent
    ? ` (círculo ${accentName(S.style.circleAccent)})` : '';
  $('setupSummary').textContent =
    `${styleName('edits', S.style.edit)} · headline ${styleName('headlines', S.style.headline)}` +
    ` · legenda ${styleName('captions', S.style.captions)}${capAccentBit}${emphAccentBit}${circleAccentBit}${accentBit} · ` +
    (on.length ? on.map((e) => e.name).join(', ') : 'sem elementos extras');
}

// The Estilo tab. It sits BETWEEN the phases and is always reachable once the
// catalog applies to this job: changing the caption style after Fase 2 exists,
// or ticking one more element and re-rendering, is normal editing — not a
// decision the user gets exactly one shot at.
let wasShowing = false; // gate was up on the previous render (for the re-fit)

function renderSetup() {
  const show = S.tab === 'style';
  $('styleSetup').classList.toggle('hidden', !show);
  // Layout amplo igual ao Estilos do hub (sidebar) — só no editor, não no embed
  document.body.classList.toggle('styles-wide', show && !HUB_EMBED);
  refreshEndCardCopy();   // follows the "Card final" checkbox
  const hasVideo = S.videoDuration > 0 || !!S.hasCut;
  $('stage').classList.toggle('hidden', show || !hasVideo);
  $('emptyState').classList.toggle('hidden', hasVideo || show);

  if (!show) {
    capAnims = []; // stop stepping demos that are not on screen
    // the timeline was display:none while the tab was up, so its panel had no
    // width to fit against — re-fit once it is back on screen
    if (wasShowing && hasVideo) requestAnimationFrame(() => { fitZoom(); renderAll(); });
    wasShowing = false;
    return;
  }
  if (!wasShowing) $('styleSetup').scrollTop = 0; // open at the top, always
  wasShowing = true;
  renderStyleTemplates();

  $('setupGo').textContent = EDIT_PRESET_ID
    ? 'Salvar preset e voltar'
    : HOUSE_STYLE
    ? 'Salvar padrão e voltar'
    : (S.state.awaitingStyle
      ? 'Confirmar e iniciar a Fase 2'
      : 'Salvar e refazer a Fase 2');
  if (HOUSE_STYLE) {
    // On the house page the primary action IS saving the default — hide the
    // secondary twin so there aren't two "save" buttons doing almost the same.
    $('setupSaveDefault').classList.add('hidden');
  } else {
    $('setupSaveDefault').classList.remove('hidden');
  }

  capAnims = [];
  const radios = (host, group, chosen) => {
    const opts = STYLE_CATALOG[group];
    host.innerHTML = '';
    // Com mais de doze cartoes a lista deixa de ser uma vitrine e vira uma
    // busca: 19 de manchete e 23 de legenda depois de 04/09. O filtro nasce
    // DENTRO do grid (o host e limpo a cada pintura, entao nao duplica) e
    // some sozinho quando o grupo e pequeno.
    let filtro = null;
    if (opts.length > 12) {
      filtro = el('input', 'opt-filtro', host);
      filtro.type = 'search';
      filtro.placeholder = `Filtrar ${opts.length} estilos…`;
      filtro.value = FILTRO_DE_ESTILO[group] || '';
      filtro.oninput = () => {
        const q = filtro.value.trim().toLowerCase();
        FILTRO_DE_ESTILO[group] = filtro.value;
        let vistos = 0;
        for (const c of host.querySelectorAll('.opt')) {
          const nome = (c.querySelector('.opt-name') || {}).textContent || '';
          const bate = !q || nome.toLowerCase().includes(q);
          c.hidden = !bate;
          if (bate) vistos += 1;
        }
        const vazio = host.querySelector('.opt-filtro-vazio');
        if (vazio) vazio.hidden = vistos > 0;
      };
    }
    for (const o of opts) {
      const card = el('div', `opt${o.id === chosen ? ' on' : ''}`, host);
      card.dataset.group = group;
      card.dataset.id = o.id;
      // headline previews are two short lines — they do not need the caption
      // box's height, and with four groups on one screen that height is scarce.
      // "Nenhuma" in the headlines group borrows that same box (hlbox) so it
      // sits level with its siblings; in captions it uses the plain cap box.
      const kind = o.mock ? 'frame' : (o.hl || (o.none && group === 'headlines')) ? 'cap hlbox' : 'cap';
      const prev = el('div', `opt-preview ${kind}`, card);
      if (o.demo) capAnims.push(CAP_BUILDERS[o.demo](prev));
      else if (o.hl) buildHeadlineDemo(prev, o.hl);
      else if (o.stat) {
        const step = buildStaticDemo(prev, o.stat);
        if (step) capAnims.push(step);
      }
      else if (o.none) {
        prev.classList.add('opt-preview-none');
        prev.innerHTML = NONE_ICON;
      }
      else prev.innerHTML = o.mock || '';
      // Todo cartao leva o nome. A regra antiga era "a amostra JA e o
      // rotulo", e com quatro estilos isso bastava; hoje sao 15 headlines e
      // 11 legendas, e sem nome o usuario nao consegue nem PEDIR o que
      // quer — nem achar de novo o que gostou da ultima vez.
      el('div', 'opt-name', card).textContent = o.name;
      el('div', 'opt-mark', card);
    }
    // the ghost only earns its space where there is a single option to explain
    if (opts.length < 2) el('div', 'opt ghost', host).textContent = 'mais estilos em breve';
    if (filtro) {
      const vazio = el('div', 'opt-filtro-vazio', host);
      vazio.textContent = 'Nenhum estilo com esse nome.';
      vazio.hidden = true;
      if (filtro.value.trim()) filtro.oninput();   // reaplica o que ele digitou
    }
  };
  // set BEFORE the demos are built: buildHeadlineDemo/the caption demos read
  // the accents through var(), so the variables have to be in place when the
  // previews first paint
  applyAccent();
  applyCaptionAccent();
  applyEmphasisAccent();
  applyCircleAccent();

  radios($('optEdit'), 'edits', S.style.edit);
  aplicarLayoutNoPreview();
  radios($('optHeadline'), 'headlines', S.style.headline);
  radios($('optCaptions'), 'captions', S.style.captions);
  renderAccents();
  renderCaptionAccents();
  renderEmphasisAccents();
  renderCircleAccents();

  const host = $('optElements');
  host.innerHTML = '';
  for (const e of STYLE_CATALOG.elements) {
    const on = !!S.style.elements[e.id];
    const row = el('div', `chk${on ? ' on' : ''}`, host);
    row.dataset.id = e.id;
    el('div', 'chk-box', row);
    el('div', 'chk-ico', row).innerHTML = e.icon || '';
    el('div', 'chk-name', row).textContent = e.name;
  }

  updateSummary();
}

$('styleSetup').addEventListener('click', (e) => {
  // the accent controls manage themselves (live, no rebuild) — keep the card
  // handler off them, or a click in the hex field would count as a style pick
  if (
    e.target.closest('#optAccent') ||
    e.target.closest('#optCaptionAccent') ||
    e.target.closest('#optEmphasisAccent') ||
    e.target.closest('#optCircleAccent')
  ) return;
  const opt = e.target.closest('.opt:not(.ghost)');
  if (opt) {
    const key = {edits: 'edit', headlines: 'headline', captions: 'captions'}[opt.dataset.group];
    if (S.style[key] === opt.dataset.id) return; // re-clicking the active card isn't an edit
    pushHistory();
    S.style[key] = opt.dataset.id;
    // Limpa = quadro cheio: some cards de imagem do pipeline
    if (key === 'edit' && opt.dataset.id === 'limpa') {
      if (S.editData) S.editData.inserts = [];
      buildInsertsDraft();
    }
    renderSetup();
    return;
  }
  const chk = e.target.closest('.chk');
  // A .chk with no data-id is not an edit element — #fastModeChk wears the
  // same class for the same look and has its OWN handler. Without this guard
  // every click on "Modo rápido" also wrote S.style.elements[undefined]=true,
  // which was then saved into the house preset, spread to every new project
  // through defaultStyle()'s spread, and reached the Fase 2 instructions as an
  // element literally named "undefined". Found it already stored in
  // default-style.json — this had been happening for a while, silently.
  if (chk && chk.dataset.id) {
    pushHistory();
    S.style.elements[chk.dataset.id] = !S.style.elements[chk.dataset.id];
    renderSetup();
  }
});

/* O payload COMPLETO da aba Estilo — extraído do setupGo para o
 * Aplicar da Edição poder salvar o estilo junto (pedido de 02/09:
 * 'mudei em Estilo, apliquei em Editar e o estilo não foi'). */
function montarPayloadDeEstilo() {
  const rerender = !S.state.awaitingStyle;
  return {
    // a save with Fase 2 already on disk is a RE-RENDER request, not a
    // first pick — the skill has to know which of the two it is looking at
    type: 'style-setup',
    rerender,
    edit: S.style.edit,
    editName: styleName('edits', S.style.edit),
    headline: S.style.headline,
    headlineName: styleName('headlines', S.style.headline),
    captions: S.style.captions,
    captionsName: styleName('captions', S.style.captions),
    accent: S.style.accent,
    accentName: accentName(S.style.accent),
    // whether the picked headline style actually paints it — so the skill does
    // not go hunting for an accent in a look that has none
    accentUsed: HL_ACCENT_USERS.includes(S.style.headline),
    // independent from the headline accent above — null means "no pick, keep
    // each caption style's own default colour" (see defaultStyle())
    captionAccent: S.style.captionAccent,
    captionAccentName: S.style.captionAccent ? accentName(S.style.captionAccent) : null,
    captionAccentUsed: legendaAccentUsed() && !!S.style.captionAccent,
    // "ênfase": the one accented element per style (stacked serif line, scatter
    // highlighted word) — independent from captionAccent above (base legenda
    // text) and from accent (headline). null means "keep the style's own
    // default (#ff5200)", same semantics as captionAccent.
    emphasisAccent: S.style.emphasisAccent,
    emphasisAccentName: S.style.emphasisAccent ? accentName(S.style.emphasisAccent) : null,
    emphasisAccentUsed: emphasisAccentUsed() && !!S.style.emphasisAccent,
    // "círculo riscado": stacked-only pencil-circle stroke, independent from
    // emphasisAccent too. null means "keep PencilOutline's own default (green
    // #39E508)".
    circleAccent: S.style.circleAccent,
    circleAccentName: S.style.circleAccent ? accentName(S.style.circleAccent) : null,
    circleAccentUsed: circleAccentUsed() && !!S.style.circleAccent,
    emphasisStyle: S.style.emphasisStyle || 'circle',
    elements: { ...S.style.elements },
    elementNames: STYLE_CATALOG.elements
      .filter((e) => S.style.elements[e.id])
      .map((e) => e.name),
    note: S.style.note,
    fastMode: !!S.fastMode,
    oneClick: !!S.fastMode,
    rhythm: S.style.rhythm || 'dinamico',
    transicao: S.style.transicao || 'flash',
    intensity: S.style.intensity || 'medio',
    speechClean: S.style.speechClean || 'medio',
    videoGoal: S.style.videoGoal || 'reels',
    brollMode: S.style.brollMode || 'quando_necessario',
    captionChunk: S.style.captionChunk || 'frase_curta',
    captionPosition: S.style.captionPosition || 'baixo',
    captionSize: S.style.captionSize || 'm',
    captionFont: S.style.captionFont || null,
    headlineFont: S.style.headlineFont || null,
    emphasisWords: S.style.emphasisWords || null,
    postHashtags: S.style.postHashtags || null,
    postSeo: S.style.postSeo || null,
    postRodape: S.style.postRodape || null,
    headlineDuration: S.style.headlineDuration || 'curta',
    headlinePos: S.style.headlinePos || 'padrao',
    legendaAposHeadline: S.style.legendaAposHeadline || null,
    headlineAnimation: S.style.headlineAnimation || 'padrao',
    exportPreset: S.style.exportPreset || 'reels',
    colorGrade: S.style.colorGrade || 'marca',
    // TIPO DE CONTEUDO e o texto do CARD FINAL iam so no "Salvar como padrao".
    // Quem trocasse o tipo na tela de Estilo e clicasse "Salvar e refazer a
    // Fase 2" mandava tudo MENOS esses dois: o job seguia com o tipo antigo.
    //
    // E o efeito nao para no titulo. `contentType` e um dos knobs congelados
    // em `edl.json.cutStyle`, e o pipeline so REPLANEJA o corte quando um
    // deles muda. Nao chegando, o corte era considerado igual e reaproveitado
    // — dai o "mandei refazer e veio a mesma minutagem".
    //
    // O servidor sempre aceitou os dois: estao em `brand_presets.STYLE_KEYS`,
    // e `preset_from_style_payload` ignora `null`, entao mandar sem escolha
    // nao apaga o que ja havia.
    contentType: S.contentType || $('autoContentType')?.value || null,
    endCardCopy: S.endCardCopy || null,
    // A MARCA escolhida na tela. O servidor grava no job_intent, que e
    // lido a cada render — sem isto, trocar a marca mudava o editor e o
    // video saia com a marca antiga assim mesmo.
    brandId: (S.presetUsed && S.presetUsed.brandId) || null,
    // O PRESET escolhido na linha de cima do editor. Sem ele o editor
    // mudava e o render continuava no preset antigo.
    brandPresetId: (S.presetUsed && S.presetUsed.brandPresetId) || null,
    // MODO DE EDICAO: e ele que decide se a IA planeja o corte. Sem este
    // campo um projeto criado em "Edicao leve" ficava preso no modo para
    // sempre — trocar o estilo e refazer nunca mudava a minutagem.
    // So vai quando o usuario TOCOU no seletor nesta tela: null preserva o
    // que esta gravado, e uma aba antiga nao rebaixa o modo por engano.
    editingIntent: S.editIntentTocado ? ($('autoEditIntent')?.value || null) : null,
  };
}

/* Salva o estilo deste projeto (preview_style.json) sem requeue — o
 * chamador decide quando refazer. É o que faz o Aplicar da Edição levar
 * junto o que foi mexido na aba Estilo. */
async function salvarEstiloDoProjeto() {
  try {
    const res = await fetch(`${BASE}/api/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(montarPayloadDeEstilo()),
    });
    const ok = !!(await res.json().catch(() => ({}))).ok;
    if (ok) S.styleTocado = false;
    return ok;
  } catch {
    return false;
  }
}

// Qualquer mexida na aba Estilo marca o projeto como "estilo tocado": o
// Aplicar da Edição passa a salvar o estilo junto (pedido de 02/09 — ele
// mudava na aba Estilo, aplicava na Edição e o estilo não ia).
(() => {
  const setup = $('styleSetup');
  if (!setup) return;
  setup.addEventListener('change', () => { S.styleTocado = true; refreshHeader(); });
  setup.addEventListener('click', (e) => {
    if (e.target.closest('.opt, .swatch, input, select, textarea')
        || (e.target.closest('button') && !e.target.closest('#setupGo, #setupSaveDefault'))) {
      S.styleTocado = true;
      refreshHeader();
    }
  });
})();

$('setupGo').addEventListener('click', async () => {
  S.style.note = $('setupNote').value.trim();

  if (HOUSE_STYLE) {
    const house = {
      edit: S.style.edit,
      headline: S.style.headline,
      captions: S.style.captions,
      accent: S.style.accent,
      captionAccent: S.style.captionAccent,
      emphasisAccent: S.style.emphasisAccent,
      circleAccent: S.style.circleAccent,
      emphasisStyle: S.style.emphasisStyle || 'circle',
      elements: { ...S.style.elements },
      fastMode: !!S.fastMode,
      oneClick: !!S.fastMode,
      rhythm: S.style.rhythm || 'dinamico',
      transicao: S.style.transicao || 'flash',
      intensity: S.style.intensity || 'medio',
      speechClean: S.style.speechClean || 'medio',
      videoGoal: S.style.videoGoal || 'reels',
      brollMode: S.style.brollMode || 'quando_necessario',
      captionChunk: S.style.captionChunk || 'frase_curta',
      captionPosition: S.style.captionPosition || 'baixo',
      captionSize: S.style.captionSize || 'm',
      captionFont: S.style.captionFont || null,
      headlineFont: S.style.headlineFont || null,
      emphasisWords: S.style.emphasisWords || null,
      postHashtags: S.style.postHashtags || null,
      postSeo: S.style.postSeo || null,
    postRodape: S.style.postRodape || null,
    postHashtags: S.style.postHashtags || null,
    postSeo: S.style.postSeo || null,
    postRodape: S.style.postRodape || null,
    headlineDuration: S.style.headlineDuration || 'curta',
    headlinePos: S.style.headlinePos || 'padrao',
    legendaAposHeadline: S.style.legendaAposHeadline || null,
    headlineAnimation: S.style.headlineAnimation || 'padrao',
      exportPreset: S.style.exportPreset || 'reels',
      colorGrade: S.style.colorGrade || 'marca',
      endCardCopy: S.endCardCopy || null,
      contentType: S.contentType || $('autoContentType')?.value || null,
      note: S.style.note || '',
    };
    // Editando UM preset: grava so nele. O estilo base e os outros
    // presets ficam como estao — era isso que faltava, e por isso o
    // Salvar antigo escrevia sempre no preset padrao.
    if (EDIT_PRESET_ID) {
      const alvo = await fetch('/api/brand-presets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'update',
          brandId: (S.brandPresets && S.brandPresets.brandId) || 'padrao',
          id: EDIT_PRESET_ID,
          style: house,
        }),
      });
      const dado = await alvo.json().catch(() => ({}));
      if (dado && dado.ok !== false && !dado.error) {
        toast('✓ Preset salvo', 2000);
        if (HUB_EMBED) {
          try {
            window.parent.postMessage({ type: 'ativavid-house-style-saved' }, '*');
          } catch { /* ignore */ }
        } else {
          setTimeout(() => { location.href = '/'; }, 450);
        }
      } else {
        toast((dado && dado.error) || 'Erro ao salvar o preset', 4000);
      }
      return;
    }
    // COM EMPRESA, o estilo base e DELA. A tela diz "vale para todos os
    // presets desta empresa", e ate a 5.0.22 este Salvar escrevia no padrao
    // do APP e no preset ativo — a empresa ficava com a copia congelada do
    // modelo por cima, e o que ele salvava nao aparecia no video ("nao fica
    // salvo as cores do preset que ele definiu", 04/09).
    const empresa = (S.brandPresets && S.brandPresets.brandId) || '';
    const res = empresa
      ? await fetch('/api/brands', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'estilo', id: empresa, style: house }),
      })
      : await fetch('/api/default-style', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(house),
      });
    const dadoSalvo = await res.json();
    if (dadoSalvo.ok) {
      SHARED_DEFAULT_STYLE = house;
      const nPresets = dadoSalvo.presetsAtualizados || 0;
      toast(empresa
        ? (nPresets
          ? `✓ Estilo salvo — ${nPresets} ajuste(s) levados aos presets`
          : '✓ Estilo da empresa salvo')
        : '✓ Estilo padrão salvo', 2000);
      // Com embed=1 NÃO navegar o iframe para "/" — isso duplicava a sidebar.
      if (HUB_EMBED) {
        try {
          window.parent.postMessage({ type: 'ativavid-house-style-saved' }, '*');
        } catch { /* ignore */ }
      } else {
        setTimeout(() => { location.href = '/'; }, 450);
      }
    } else {
      toast('Erro ao salvar o padrão', 4000);
    }
    return;
  }

  const payload = montarPayloadDeEstilo();
  const rerender = !!payload.rerender;

  const res = await fetch(`${BASE}/api/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if ((await res.json()).ok) {
    renderSetup();
    // Local desktop: put this project back in the queue with the new style
    if (BASE && BASE.startsWith('/p/')) {
      const folder = decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
      try {
        const rq = await fetch('/api/jobs/requeue-folder', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folder }),
        });
        const body = await rq.json().catch(() => ({}));
        if (rq.ok) {
          toast(rerender
            ? '✓ Estilo salvo — reeditando com o novo visual'
            : '✓ Estilo salvo — editando com essas escolhas', 4500);
          return;
        }
        toast(body.error || 'Estilo salvo — volte em Projetos e toque em Tentar de novo', 5000);
        return;
      } catch {
        toast('Estilo salvo — volte em Projetos e toque em Tentar de novo', 5000);
        return;
      }
    }
    toast(rerender
      ? '✓ Estilo salvo neste projeto'
      : '✓ Estilo confirmado neste projeto', 4000);
  } else {
    toast('Erro ao enviar — o servidor está de pé?', 4000);
  }
});

// Saves the CURRENT picks as the house style — separate button from
// "Confirmar", on purpose: one sends this project's choices to the skill,
// the other changes what every FUTURE project starts on. Doing both in one
// click would mean you can never pick something unusual for just this one
// video without it becoming the new default. Only the core fields defaultStyle()
// actually reads — no names/Used flags, those are preview_style.json's concern.
function refreshFastMode() {
  $('fastModeChk').classList.toggle('on', !!S.fastMode);
}

// The end card's copy belongs to the BRAND, not to one video — so it lives in
// the preset. Without it, fast mode would stop on every single video to ask for
// the same handle, which is exactly what fast mode exists to avoid.
function refreshEndCardCopy() {
  const on = !!(S.style && S.style.elements && S.style.elements.endCard);
  $('endCardCopy').classList.toggle('hidden', !on);
  if (!on) return;
  const c = S.endCardCopy || {};
  // don't fight the user mid-typing
  if (document.activeElement !== $('ecLine1')) $('ecLine1').value = c.line1 || '';
  if (document.activeElement !== $('ecLine2')) $('ecLine2').value = c.line2 || '';
}
['ecLine1', 'ecLine2'].forEach((id) => {
  $(id).addEventListener('input', () => {
    S.endCardCopy = {line1: $('ecLine1').value.trim(), line2: $('ecLine2').value.trim()};
  });
  // the timeline owns S / space / arrows — typing here must not fire them
  $(id).addEventListener('keydown', (e) => e.stopPropagation());
});
$('fastModeChk').addEventListener('click', () => {
  S.fastMode = !S.fastMode;
  refreshFastMode();
  // deliberately NOT saved on click: it only counts once "Salvar como padrão"
  // writes it, so a stray click cannot quietly switch off the approval gate
  toast(S.fastMode
    ? 'Modo 1 clique marcado — clique "Salvar como padrão" para valer'
    : 'Modo 1 clique desmarcado — salve o padrão para valer', 3200);
});

$('setupSaveDefault').addEventListener('click', async () => {
  const payload = {
    edit: S.style.edit,
    headline: S.style.headline,
    captions: S.style.captions,
    accent: S.style.accent,
    captionAccent: S.style.captionAccent,
    emphasisAccent: S.style.emphasisAccent,
    circleAccent: S.style.circleAccent,
    emphasisStyle: S.style.emphasisStyle || 'circle',
    elements: { ...S.style.elements },
    // Policy, not looks — but it belongs with the house preset because it only
    // makes sense WITH one: "fast" means "the recipe is already decided", and
    // without a saved recipe there is nothing to skip the asking for.
    fastMode: !!S.fastMode,
    oneClick: !!S.fastMode,
    rhythm: S.style.rhythm || 'dinamico',
    transicao: S.style.transicao || 'flash',
    intensity: S.style.intensity || 'medio',
    speechClean: S.style.speechClean || 'medio',
    videoGoal: S.style.videoGoal || 'reels',
    brollMode: S.style.brollMode || 'quando_necessario',
    captionChunk: S.style.captionChunk || 'frase_curta',
    captionPosition: S.style.captionPosition || 'baixo',
    captionSize: S.style.captionSize || 'm',
    captionFont: S.style.captionFont || null,
    headlineFont: S.style.headlineFont || null,
    emphasisWords: S.style.emphasisWords || null,
    postHashtags: S.style.postHashtags || null,
    postSeo: S.style.postSeo || null,
    postRodape: S.style.postRodape || null,
    headlineDuration: S.style.headlineDuration || 'curta',
    headlinePos: S.style.headlinePos || 'padrao',
    legendaAposHeadline: S.style.legendaAposHeadline || null,
    headlineAnimation: S.style.headlineAnimation || 'padrao',
    exportPreset: S.style.exportPreset || 'reels',
    colorGrade: S.style.colorGrade || 'marca',
    smartEmphasis: S.style.smartEmphasis !== false,
    endCardCopy: S.endCardCopy || null,
  };
  const res = await fetch(`${BASE}/api/default-style`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if ((await res.json()).ok) {
    SHARED_DEFAULT_STYLE = payload; // takes effect this session too, no reload needed
    toast('✓ Salvo como padrão — todo projeto novo abre assim', 3500);
  } else {
    toast('Erro ao salvar o padrão — o servidor está de pé?', 4000);
  }
});

// Arrastar a borda de um take disparava renderClips() a cada pointermove:
// a lane inteira era destruída e recriada, com TODAS as imagens do filmstrip
// (1 a cada 2s de vídeo), 60x por segundo. Durante o arrasto só a geometria
// muda — o conteúdo do filmstrip vem do corte JÁ RENDERIZADO e não responde
// ao rascunho — então mexer em left/width dos nós existentes basta.
function updateClipGeometry() {
  const dl = draftLayout();
  const nodes = laneVideo.querySelectorAll('.clip');
  for (const node of nodes) {
    const i = Number(node.dataset.i);
    const r = dl[i];
    if (!r) continue;
    node.style.left = `${r.out * S.pps}px`;
    if (!node.classList.contains('removed')) {
      node.style.width = `${Math.max(r.dur * S.pps, 0)}px`;
      node.classList.toggle('dirty', r.start !== r.orig.start || r.end !== r.orig.end);
    }
  }
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
    const c = el('div', 'clip' + (S.takeSel.includes(i) ? ' laco-sel' : ''),
                 laneVideo);
    const px = r.dur * S.pps;
    c.style.left = `${r.out * S.pps}px`;
    c.style.width = `${Math.max(px, 0)}px`;
    c.dataset.i = i;
    if (i === S.selected) c.classList.add('selected');
    if (r.start !== r.orig.start || r.end !== r.orig.end) c.classList.add('dirty');
    if (px > 0 && px < CLIP_TIGHT_PX) {
      c.classList.add('tight');
      el('div', 'clip-body-hit', c);
    }

    // filmstrip from the rendered cut
    if (S.thumbCount > 0 && rl[i]) {
      const strip = el('div', 'thumbs', c);
      const first = Math.floor(rl[i].out / THUMB_EVERY);
      const n = Math.ceil(rl[i].dur / THUMB_EVERY) + 1;
      for (let k = 0; k < n; k++) {
        const idx = first + k + 1; // ffmpeg %04d is 1-based
        if (idx > S.thumbCount) break;
        const img = el('img', '', strip);
        img.src = `${BASE}/gen/thumbs/${String(idx).padStart(4, '0')}.jpg`;
        img.style.width = `${THUMB_EVERY * S.pps}px`;
        img.style.objectFit = 'cover';
      }
    }
    const lab = el('div', 'clip-label', c);
    lab.textContent = `${friendlyBeatLabel(r.beat, r.source)} `;
    if (String(r.beat || '').toUpperCase() === 'HOOK') c.classList.add('hook-beat');
    if (clipIsProtected(r)) {
      c.classList.add('protected');
      const lk = el('div', 'clip-lock', c);
      lk.textContent = '🔒';
      c.title = 'Trecho protegido — a IA não pode cortar este conteúdo';
    }
    const dur = el('div', 'clip-dur', c);
    dur.textContent = `${r.dur.toFixed(2)}s`;

    if (editable) {
      el('div', 'handle l', c).dataset.i = i;
      el('div', 'handle r', c).dataset.i = i;
    }
  });
  for (const span of protectedDraftSpans()) {
    const ov = el('div', 'prot-range', laneVideo);
    ov.style.left = `${span.start * S.pps}px`;
    ov.style.width = `${Math.max((span.end - span.start) * S.pps, 6)}px`;
    ov.title = 'Trecho protegido — a IA não pode cortar este conteúdo';
  }
  refreshTransportActions();
}

/* J-cut audio lanes.
 * The point is legibility, not decoration: on one lane an overlap is invisible,
 * because two blocks that overlap in time just look like one continuous block.
 * Alternating takes across A1/A2 is what makes the "J" readable — exactly how it
 * reads in Premiere. The overlap itself gets a marker on the incoming block, so
 * the user can see how many frames of voice arrive before the picture.
 */
function renderJcutAudio() {
  const t1 = $('trkAudioA1'), t2 = $('trkAudioA2');
  const l1 = $('laneAudioA1'), l2 = $('laneAudioA2');
  const btn = $('jcutToggle');
  l1.innerHTML = ''; l2.innerHTML = '';

  const has = !!(S.jcut && S.jcut.length && S.tab !== 'style');
  // the caret only appears when there is a J-cut to expand; otherwise the chip
  // stays an ordinary track icon
  btn.classList.toggle('disclose', has);
  btn.disabled = !has;
  btn.setAttribute('aria-expanded', String(has && S.jcutOpen));
  btn.title = !has ? 'Áudio (mix)'
    : S.jcutOpen ? 'Áudio (mix) — recolher as faixas do J-cut (A1/A2)'
                 : 'Áudio (mix) — expandir as faixas do J-cut (A1/A2)';

  const on = has && S.jcutOpen;
  t1.classList.toggle('hidden', !on);
  t2.classList.toggle('hidden', !on);
  if (!on) return;

  // drawn off the DRAFT layout so the blocks move with the user's trims
  draftLayout().forEach((r, i) => {
    if (r.removed && r.adur === 0) return;
    const lane = i % 2 === 0 ? l1 : l2;
    const b = el('div', 'ablock', lane);
    b.style.left = `${r.aout * S.pps}px`;
    b.style.width = `${Math.max(r.adur * S.pps, 6)}px`;
    el('div', 'ablock-label', b).textContent = friendlyBeatLabel(r.beat, r.source);

    // the lead: sound already playing while the previous take is still on screen
    if (r.lead > 1e-6) {
      const ov = el('div', 'ablock-lead', b);
      ov.style.width = `${r.lead * S.pps}px`;
    }
    const tf = (S.jcut[i] || {}).tail_trim_frames || 0;
    let tip = `${r.beat || r.source}\náudio ${r.adur.toFixed(2)}s`;
    if (r.lead > 1e-6) {
      tip += `\nJ-cut: ${Math.round(r.lead * S.fps)}f (${Math.round(r.lead * 1000)}ms) `
           + 'de voz antes da imagem';
    }
    if (tf) tip += `\ncauda aparada ${tf}f`;
    b.title = tip;
  });
}

function renderChips() {
  const phase2 = S.tab === 2;
  // The caption track also shows on Fase 1 whenever captions already exist.
  // Without this the fix-before-render loop is broken in half: the WYSIWYG
  // overlay lives on Fase 1, but the chip you click to correct a word lived
  // only on Fase 2 — you could see the wrong word and not reach it.
  const showCaps = phase2 || S.captions.length > 0;
  $('trkCaptions').classList.toggle('hidden', !showCaps);
  // Na Edicao o bloco de faixas so aparece quando ha midia posta na mao —
  // sem isso a faixa nasce vazia e come altura da linha do tempo.
  const temManual = S.insertsDraft.some(
    (c) => c.isNew || c.kind === 'hook' || c.manual
      || c.kind === 'lower' || c.kind === 'chapter');
  insertTracksEl.classList.toggle('hidden', !phase2 && !temManual);
  insertTracksEl.innerHTML = '';
  if (!showCaps) {
    // Sem legenda (estilo sem legenda, ou projeto ainda cru) as faixas de
    // gancho e midia continuam valendo: sair aqui tirava o GANCHO da
    // Edicao justamente de quem nao usa legenda.
    desenharFaixasDeInsert(phase2);
    return;
  }

  laneCaptions.innerHTML = '';
  const edlPending = !!(S.corrections && S.corrections.dirty && S.corrections.dirty.edl);
  if (!edlPending) {
    S.captions.forEach((c, i) => {
      const start = renderedToDraft(c.start);
      const end = renderedToDraft(c.end);
      const fix = S.captionFixes[i];
      const chip = el('div', 'chip caption' + (fix ? ' fixed' : '')
        + (S.capSel.includes(i) ? ' sel' : ''), laneCaptions);
      chip.style.left = `${start * S.pps}px`;
      chip.style.width = `${Math.max((end - start) * S.pps, 6)}px`;
      chip.textContent = fix ? fix.to : c.text;
      chip.title = fix
        ? `“${c.text}” → “${fix.to}” (clique para editar)`
        : `${c.text} — clique para corrigir o texto`;
      chip.dataset.ci = String(i);
    });
  }

  desenharFaixasDeInsert(phase2);
}

/* As faixas do que NAO e legenda: gancho, midia posta na mao e os
 * inserts da IA (so no Visual). Ficava dentro do `renderChips`, depois
 * de um `return` que dispara quando o projeto nao tem legenda — e ai o
 * GANCHO nao aparecia na Edicao de um video sem legenda. */
function desenharFaixasDeInsert(phase2) {
  // Na Visual entram todos os inserts; na Edicao, so os que o usuario poe
  // na mao. Os da IA vem do edit-data no relogio do video FINAL, e desenha-
  // los sobre o corte em edicao os poria no lugar errado. O que e posto na
  // mao ja nasce em tempo de rascunho (`pushInsertFromRef`), que e o
  // relogio desta tela.
  const soManuais = !phase2;
  // Na Edicao entra o que foi posto na mao E o GANCHO. A manchete comeca no
  // segundo 0 nos dois relogios, entao ela nao sofre da ambiguidade que
  // deixa o insert da IA fora daqui — e e clicando nela que se troca o
  // texto (o usuario mandou print em 29/08: "ainda nao edita a headline
  // aqui", estando na Edicao).
  const visiveis = soManuais
    ? S.insertsDraft.map((c, i) => ({ c, i }))
        .filter(({ c }) => c.isNew || c.kind === 'hook' || c.manual
          || c.kind === 'lower' || c.kind === 'chapter')
    : S.insertsDraft.map((c, i) => ({ c, i }));
  if (soManuais && !visiveis.length) return;

  // TEXT and IMAGE get their own tracks — a headline and a photo are different
  // kinds of edit, and mixing them on one lane hid the images entirely.
  const isText = (c) => c.kind === 'hook' || c.kind === 'word' || c.kind === 'emoji'
    || c.kind === 'lower' || c.kind === 'chapter';
  const isSfx = (c) => c.kind === 'sfx';
  const groups = [
    // MIDIA primeiro (logo abaixo do video) e ALTA como o filmstrip — a
    // miniatura de 22px nao dava para ver o que era (pedido de 02/09)
    { icon: 'inserts', cls: 'orange', alto: true,
      items: visiveis.filter(({ c }) => !isText(c) && !isSfx(c)) },
    { icon: 'text', cls: 'teal', items: visiveis.filter(({ c }) => isText(c)) },
    // faixa propria: som e imagem sao coisas diferentes de editar, e
    // misturados numa fileira so o efeito some entre as fotos
    { icon: 'music', cls: 'olive', items: visiveis.filter(({ c }) => isSfx(c)) },
  ];

  for (const g of groups) {
    if (!g.items.length) continue;
    const assign = new Map();
    let fileiras;
    if (g.alto) {
      // MIDIA: a fileira e a CAMADA escolhida pelo usuario (arrasto
      // vertical). Fileira de baixo = pintada por cima no video — a
      // hierarquia de camadas do pedido de 02/09.
      let maxCam = 0;
      for (const { c, i } of g.items) {
        const cam = c.camada | 0;
        assign.set(i, cam);
        if (cam > maxCam) maxCam = cam;
      }
      fileiras = maxCam + 1;
    } else {
      // texto e som: sem camada manual — sobreposicao empilha sozinha
      const order = [...g.items].sort((a, b) => a.c.start - b.c.start || a.c.end - b.c.end);
      const trackEnd = [];
      for (const { c, i } of order) {
        let t = trackEnd.findIndex((end) => c.start >= end - 1e-6);
        if (t < 0) { t = trackEnd.length; trackEnd.push(0); }
        trackEnd[t] = c.end;
        assign.set(i, t);
      }
      fileiras = Math.max(trackEnd.length, 1);
    }
    const lanes = [];
    for (let t = 0; t < fileiras; t++) {
      const trk = el('div', 'track', insertTracksEl);
      const lab = el('div', 'track-label', trk);
      // only the first lane of a group carries the icon; the rest are continuations
      if (t === 0) el('span', `tl-chip ${g.cls}`, lab).innerHTML = ICON[g.icon];
      lanes.push(el('div', g.alto ? 'lane lane-midia' : 'lane', trk));
    }
    for (const { c, i } of g.items) {
      const chip = el('div', `chip insert ${isText(c) ? 'hook' : ''}`, lanes[assign.get(i) ?? 0]);
      chip.style.left = `${c.start * S.pps}px`;
      chip.style.width = `${Math.max((c.end - c.start) * S.pps, 10)}px`;
      const ehSom = c.kind === 'sfx';
      const vol = Math.round((c.volume ?? 0.5) * 100);
      chip.textContent = ehSom ? `${c.label} · ${vol}%` : c.label;
      chip.title = ehSom
        ? `${c.label} — ${vol}% de volume (roda do mouse muda)`
        : c.label;
      if (ehSom) somComVolume(chip, c);
      // Bloco de midia MOSTRA a midia (pedido de 02/09: "o preview vale
      // mais que o nome") — igual a faixa do video principal.
      if (c.kind === 'insert' && c.src) {
        chip.dataset.src = c.src;
        chip.textContent = '';
        miniaturaNoChip(chip, c.src);
      }
      chip.dataset.i = i;
      if (c.start !== c.orig.start || c.end !== c.orig.end) chip.classList.add('dirty');
      el('div', 'handle l', chip).dataset.i = i;
      el('div', 'handle r', chip).dataset.i = i;
      // Selecionado = contorno e o Excluir DE CIMA aceso. Sem ✕ colado no
      // bloco: num bloco de 24px ele comia o proprio bloco, e o usuario ja
      // tem um botao de excluir na barra ("quando clico na imagem deve
      // ativar o delete que temos la em cima", 30/08).
      if (c.isNew && (S.blocoSel === i || S.blocosSel.includes(i))) {
        chip.classList.add('sel');
      }
    }
  }

  // soundtrack → its own track, one chip spanning the whole video. Desde a
  // 4.101 o chip abre um menu (trocar / volume / remover) — antes clicar
  // nele nao fazia nada e a trilha da IA nao tinha como ser trocada.
  const st = S.editData && S.editData.soundtrack;
  if (st && (st.enabled || st.manual === false || S.editData)) {
    const trk = el('div', 'track', insertTracksEl);
    el('span', 'tl-chip olive', el('div', 'track-label', trk)).innerHTML = ICON.music;
    const lane = el('div', 'lane', trk);
    const chip = el('div', 'chip music', lane);
    const dur = S.editData.durationSec || S.videoDuration || draftTotal();
    chip.style.left = '0px';
    chip.style.width = `${Math.max(dur * S.pps, 10)}px`;
    if (st.enabled) {
      const name = st.label || (st.file || 'trilha.mp3').split('/').pop();
      const vol = st.volume != null ? `  ·  vol ${st.volume}` : '';
      chip.textContent = `${name}${vol}`;
    } else {
      chip.textContent = 'sem trilha — clique para escolher uma';
      chip.style.opacity = '.55';
    }
    chip.title = 'Trocar, ajustar o volume ou remover a trilha';
    chip.addEventListener('click', (e) => { e.stopPropagation(); abrirMenuTrilha(e.clientX, e.clientY); });
  }
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
  // TRANSICAO POR CORTE (5.0.37): um losango em cada emenda, na cor do tipo.
  // Escolha propria ganha borda cheia; "nenhuma" e so o contorno. Clicar
  // nele abre o menu — o hit-test mora no pointerdown da regua.
  if (S.draft && S.draft.length) {
    fronteirasDoRascunho().forEach((tb, i) => {
      const x = tb * S.pps - laneX0;
      if (x < -8 || x > w + 8) return;
      const { tipo, proprio } = tipoDaEmenda(i);
      const cy = 9, r = 5;
      ctx.beginPath();
      ctx.moveTo(x, cy - r); ctx.lineTo(x + r, cy); ctx.lineTo(x, cy + r); ctx.lineTo(x - r, cy);
      ctx.closePath();
      const cor = COR_DA_TRANSICAO[tipo] || '#ffd166';
      ctx.fillStyle = tipo === 'nenhuma' ? 'rgba(0,0,0,0)' : cor;
      ctx.fill();
      ctx.lineWidth = proprio ? 2 : 1;
      ctx.strokeStyle = tipo === 'nenhuma' ? 'rgba(139,148,163,0.9)' : cor;
      ctx.stroke();
    });
  }
}

/* Menu da emenda: os tipos vem do MESMO <select> do estilo (autoTransicao),
 * para nao existir um segundo catalogo em JS. */
function abrirMenuDaEmenda(i, clientX, clientY) {
  fecharMenuDaEmenda();
  const sel = $('autoTransicao');
  const tipos = sel ? [...sel.options].map((o) => [o.value, o.textContent]) : [['flash', 'Flash']];
  const atual = tipoDaEmenda(i);
  const menu = el('div', 'menu-emenda', document.body);
  menu.id = 'menuEmenda';
  const titulo = el('div', 'menu-emenda-titulo', menu);
  titulo.textContent = `Transição no corte ${i + 1}`;
  const linhas = [...tipos, ['nenhuma', 'Nenhuma neste corte'], ['', 'Como o estilo manda']];
  for (const [valor, rotulo] of linhas) {
    const b = el('button', 'menu-emenda-item', menu);
    b.type = 'button';
    b.textContent = rotulo;
    const marcado = valor ? (atual.proprio && atual.tipo === valor) : !atual.proprio;
    if (marcado) b.classList.add('on');
    b.onclick = async () => {
      fecharMenuDaEmenda();
      const data = await persistCorrection({ op: 'set_transicao_corte', i, tipo: valor });
      if (data && data.ok) {
        if (!S.editData) S.editData = {};
        S.editData.transicoesPorCorte = data.transicoesPorCorte || {};
        drawRuler();
        toast(valor ? `✓ Corte ${i + 1}: ${rotulo} — aplique em "Salvar e refazer"` : `✓ Corte ${i + 1} volta ao estilo`, 3000);
      }
    };
  }
  menu.style.left = `${Math.min(clientX, window.innerWidth - 240)}px`;
  menu.style.top = `${clientY + 8}px`;
  setTimeout(() => document.addEventListener('pointerdown', fecharMenuDaEmendaFora, { once: true }), 0);
}
function fecharMenuDaEmendaFora(e) {
  if (e.target.closest && e.target.closest('#menuEmenda')) {
    document.addEventListener('pointerdown', fecharMenuDaEmendaFora, { once: true });
    return;
  }
  fecharMenuDaEmenda();
}
function fecharMenuDaEmenda() {
  const m = document.getElementById('menuEmenda');
  if (m) m.remove();
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

// Vertical sources get the split layout (player right, editor left) — stacked,
// a 9:16 clip is tiny above a full-width timeline. Driven off the decoded frame
// size, so it works for cut.mp4 and the Phase-2 render alike.
function applyOrientation() {
  const w = video.videoWidth;
  const h = video.videoHeight;
  if (!w || !h) return;
  const portrait = h > w;
  if (portrait === document.body.classList.contains('portrait')) return;
  document.body.classList.toggle('portrait', portrait);
  // the timeline's width just changed — re-fit after layout settles
  requestAnimationFrame(() => { fitZoom(); renderAll(); });
}
video.addEventListener('loadedmetadata', () => {
  applyOrientation();
  refreshProjectChrome();
});

// ---------- needle / playback sync ----------
/* Leitura de layout do quadro, feita UMA vez no comeco do rafLoop.
 *
 * Ler `panel.scrollLeft` DEPOIS de mexer em qualquer `style` obriga o
 * navegador a refazer o layout da timeline inteira ali, no meio do quadro.
 * Medido nesta pagina (42 chips de legenda, 962 nos): escrever `left`
 * custa 0,001 ms; escrever e ENTAO ler, 1,51 ms. A funcao inteira custava
 * 3,97 ms — 60x por segundo enquanto o video toca, so para mover uma
 * linha de 2px. Um quarto da thread principal, em todo video.
 *
 * Foi o que ele viu: "mesmo sem video na fila nosso player da umas
 * travadas e atrasadas, e no player externo nao trava". */
let quadroEsq = null;
let ultimoNeedleX = null;

function positionNeedle() {
  const tDraft = renderedToDraft(video.currentTime || 0);
  const x = LABEL_W + tDraft * S.pps;
  const esq = quadroEsq != null ? quadroEsq : panel.scrollLeft;
  if (x !== ultimoNeedleX) {
    ultimoNeedleX = x;
    needle.style.left = `${x}px`;
  }
  // Escrever o MESMO valor de novo tambem suja o layout: so escreve o que
  // mudou.
  const oculta = x < esq + LABEL_W ? 'hidden' : '';
  if (needle.style.visibility !== oculta) needle.style.visibility = oculta;
  const agora = $('timeNow');
  const txt = fmt(tDraft);
  if (agora.textContent !== txt) agora.textContent = txt;
  const total = $('timeTotal');
  const txtTotal = fmt(draftTotal() || S.videoDuration);
  if (total.textContent !== txtTotal) total.textContent = txtTotal;
}
/* ---------- WYSIWYG caption layer over the player ----------
 * The expensive loop this kills: render (~2 min on a short reel, more on a
 * long one) → spot a mis-transcribed word → fix → render again. Here the word
 * is on screen before any render, and clicking the chip fixes it.
 *
 * Deliberately a WORDING/FIT check, not a pixel-perfect preview: it reproduces
 * the picked style's family, weight, size and placement, not its animation.
 * Claiming more than that would be a preview that lies, and the Estilo tab is
 * where the real look already gets rendered.
 */
const CAP_OVERLAY_STYLES = {
  karaoke:   {family: "'Poppins',sans-serif", weight: 900, size: 76, bottom: 300, ink: 'accent'},
  stacked:   {family: "'Poppins',sans-serif", weight: 900, size: 74, bottom: 320, ink: 'white', italic: true},
  scatter:   {family: "'Lora',serif",         weight: 400, size: 70, bottom: 330, ink: 'white'},
  impacto:   {family: "'Poppins',sans-serif", weight: 900, size: 72, bottom: 430, ink: 'white', upper: true},
  recorte:   {family: "'Poppins',sans-serif", weight: 800, size: 78, bottom: 430, ink: 'accent', upper: true},
  simples:   {family: "'Poppins',sans-serif", weight: 600, size: 82, bottom: 430, ink: 'accent'},
  serifada:  {family: "'Libre Baskerville',serif", weight: 700, size: 84, bottom: 430, ink: 'accent'},
  classica:  {family: "'Inter',sans-serif",   weight: 500, size: 52, bottom: 430, ink: 'accent'},
  bloco:     {family: "'Poppins',sans-serif", weight: 800, size: 76, bottom: 430, ink: 'slab'},
};

function updateCapOverlay() {
  const box = $('capOverlay');
  const style = S.style && S.style.captions;
  // Fase 2 plays the finished render, which already HAS the captions burned
  // in — drawing a second copy on top would be a lie and a double image.
  const usable = S.capPreviewOn && S.tab !== 2 && style && style !== 'nenhuma' && S.captions.length;
  if (!usable) { box.classList.add('hidden'); return; }

  const t = video.currentTime;
  const cur = S.captions.find((c) => t >= c.start && t < c.end);
  if (!cur) { box.classList.add('hidden'); return; }

  const i = S.captions.indexOf(cur);
  const fix = S.captionFixes[i];
  const text = fix ? fix.to : cur.text;
  const V = CAP_OVERLAY_STYLES[style] || CAP_OVERLAY_STYLES.karaoke;

  // the render is authored at 1080 wide; scale everything to the player
  const s = (video.clientWidth || 1) / 1080;
  const ink = V.ink === 'slab' ? inkOn(S.style.captionAccent || '#111214')
            : V.ink === 'accent' ? (S.style.captionAccent || '#f4f1e9')
            : '#fff';
  // fonte da marca — mesmo catálogo do render (fonts.ts). `arquivo` usa a
  // FontFace registrada por garantirFonteDaMarca(), com Poppins de reserva
  // (o MESMO fallback dos dois motores para glifo que falta).
  const FONT_CSS = {
    poppins: "'Poppins',sans-serif", inter: "'Inter',sans-serif",
    montserrat: "'Montserrat',sans-serif", playfair: "'Playfair Display',serif",
    lora: "'Lora',serif", anton: "'Anton',sans-serif",
    bebas: "'Bebas Neue',sans-serif", archivo: "'Archivo Black',sans-serif",
    oswald: "'Oswald',sans-serif",
    robotocond: "'Roboto Condensed',sans-serif",
    nunito: "'Nunito',sans-serif",
    rubik: "'Rubik',sans-serif",
    spartan: "'League Spartan',sans-serif",
    kanit: "'Kanit',sans-serif",
    barlow: "'Barlow Condensed',sans-serif",
    bangers: "'Bangers',cursive",
    righteous: "'Righteous',cursive",
    titan: "'Titan One',cursive",
    luckiest: "'Luckiest Guy',cursive",
    arquivo: "'BrandLocal','Poppins',sans-serif",
  };
  // posição/tamanho do preset — mesmo mapa do render (_apply_caption_geometry)
  const capPos = S.style.captionPosition || 'baixo';
  const posBottom = capPos === 'centro' ? 900 : capPos === 'alto' ? 1330 : V.bottom;
  // fator de altura por fonte — espelho de _FATOR_ALTURA_CATALOGO no
  // render: a Anton tem caixa alta 21% maior que as outras no mesmo px, e
  // sem isto o preview mostrava uma legenda maior do que a que sai no video.
  const FONT_ALTURA = { anton: 0.83, oswald: 0.877, spartan: 1.076, kanit: 1.092, bangers: 0.947 };
  const fatorFonte = (style !== 'stacked' && FONT_ALTURA[S.style.captionFont]) || 1;
  const capScale = ({ p: 0.85, m: 1, g: 1.18 }[S.style.captionSize] || 1) * fatorFonte;

  box.classList.remove('hidden');
  // Sem ancora livre (familia `simples`) fica o mapa discreto de sempre; com
  // ancora, quem manda e o valor que o motor vai ler.
  if (capAncoraY() == null) {
    box.style.paddingBottom = `${posBottom * s}px`;
    box.style.alignItems = 'flex-end';
  }
  const sig = `${i}|${text}|${style}|${capPos}|${capScale}|${Math.round(s * 100)}`;
  if (box.dataset.sig === sig && box.querySelector('.cap-overlay-line')) {
    highlightCurrentCaption(i);
    return;
  }
  box.dataset.sig = sig;
  box.innerHTML = '';
  const line = el('div', 'cap-overlay-line' + (V.ink === 'slab' ? ' slab' : ''), box);
  line.style.fontFamily = (style !== 'stacked' && FONT_CSS[S.style.captionFont]) || V.family;
  // fonte so-maiusculas (Integral): mesmo uppercase dos dois motores
  line.style.textTransform =
    (style !== 'stacked' && S.style.captionFont === 'arquivo'
     && S.editData && S.editData.brandFontCapsOnly) ? 'uppercase' : '';
  line.style.fontWeight = String(V.weight);
  line.style.fontSize = `${V.size * capScale * s}px`;
  line.style.color = ink;
  if (V.italic) line.style.fontStyle = 'italic';
  if (V.upper) line.style.textTransform = 'uppercase';
  if (V.ink === 'slab') {
    line.style.background = S.style.captionAccent || '#111214';
    line.style.padding = `${V.size * 0.09 * s}px ${V.size * 0.16 * s}px`;
    line.style.borderRadius = `${V.size * 0.16 * s}px`;
  }
  line.textContent = text;
  if (fix) line.classList.add('fixed');
  capArrastavel(line);
  capPosicionar(line);
  highlightCurrentCaption(i);
}



/**
 * Volta a altura ao padrao do estilo. `alvo` e 'headline' ou 'legenda'.
 *
 * Manda `reset` em vez do numero do padrao de hoje: gravar o numero
 * congelaria o projeto se o padrao mudar amanha.
 */
async function voltarAoPadrao(alvo) {
  const op = alvo === 'legenda' ? 'set_caption_pos' : 'set_headline_pos';
  try {
    const data = await persistCorrection({ op, reset: true });
    if (!data || data.ok === false) {
      toast((data && data.error) || 'Não deu para voltar ao padrão');
      return;
    }
    if (S.editData) {
      if (alvo === 'legenda') {
        const caps = { ...(S.editData.captions || {}) };
        for (const k of ['stackedOffsetY', 'scatterOffsetY']) delete caps[k];
        if (capEstilo() === 'impacto') delete caps.paddingBottom;
        S.editData.captions = caps;
      } else {
        const hk = { ...(S.editData.hook || {}) };
        delete hk.paddingTop;
        delete hk.paddingBottom;
        S.editData.hook = hk;
      }
    }
    toast('Voltou para a altura padrão do estilo', 2000);
  } catch (err) {
    toast((err && err.message) || 'Não deu para voltar ao padrão');
  }
}

// ---------- legenda arrastavel --------------------------------------------
// Cada estilo guarda a altura num botao diferente; a tabela vem do MOTOR
// junto com a da headline. A familia `simples` nao aparece la porque
// posiciona por valor DISCRETO — nesses a legenda continua so clicavel.

/** Estilo de legenda em uso neste projeto. */
function capEstilo() {
  const ed = (S.editData && S.editData.captions) || {};
  return String(ed.style || (S.style && S.style.captions) || 'stacked');
}

/** Altura da legenda em pixels do QUADRO, ou null se o estilo nao suporta. */
function capAncoraY() {
  if (!CAP_ANCORAS) return null;
  const a = CAP_ANCORAS[capEstilo()];
  if (!a) return null;
  const salvo = ((S.editData && S.editData.captions) || {})[a.chave];
  const v = salvo == null ? Number(a.padrao) : Number(salvo);
  const H = HL_QUADRO_H;
  // Mesmas formulas de `legenda_valor_para_y` no render_proprio.
  if (a.base === 'centro_meio') return H / 2 + H * v;
  if (a.base === 'centro_frac') return H * v;
  return H - v;                                   // bottom_px
}

/** Coloca a linha da legenda na altura real do quadro. */
function capPosicionar(line) {
  const y = capAncoraY();
  const m = hlMetrica('capOverlay');
  if (y == null || !m || !line) return false;
  const a = CAP_ANCORAS[capEstilo()];
  const box = $('capOverlay');
  box.style.paddingBottom = '0px';
  box.style.alignItems = 'flex-start';
  line.style.position = 'absolute';
  line.style.left = '50%';
  line.style.transform = 'translateX(-50%)';
  const alvo = m.topo + y * m.escala;
  // stacked/scatter marcam o CENTRO do bloco; o impacto marca a BASE.
  line.style.top = Math.round(
    a.base === 'bottom_px' ? alvo - line.offsetHeight : alvo - line.offsetHeight / 2,
  ) + 'px';
  return true;
}

function capArrastavel(line) {
  if (!line || line.dataset.arrasta) return;
  if (capAncoraY() == null) return;      // estilo sem altura livre
  line.dataset.arrasta = '1';
  line.classList.add('movivel');
  let arrasto = null;

  line.addEventListener('pointerdown', (e) => {
    if (S.applying || e.button !== 0) return;
    line.dataset.acabouDeArrastar = '0';   // ver comentario na headline
    const m = hlMetrica('capOverlay');
    if (!m) return;
    arrasto = { y0: e.clientY, topo0: parseFloat(line.style.top) || 0, moveu: false, m };
    line.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  line.addEventListener('pointermove', (e) => {
    if (!arrasto) return;
    const dy = e.clientY - arrasto.y0;
    if (!arrasto.moveu && Math.abs(dy) < 4) return;   // tremor de clique
    arrasto.moveu = true;
    line.classList.add('dragging');
    const m = arrasto.m;
    const min = m.topo;
    const max = m.topo + m.alturaVideo - line.offsetHeight;
    line.style.top = Math.round(Math.max(min, Math.min(max, arrasto.topo0 + dy))) + 'px';
  });

  const soltar = async (e) => {
    if (!arrasto) return;
    const { moveu, m } = arrasto;
    arrasto = null;
    line.classList.remove('dragging');
    try { line.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
    if (!moveu) return;
    line.dataset.acabouDeArrastar = '1';
    const a = CAP_ANCORAS[capEstilo()];
    const topoPx = parseFloat(line.style.top) || 0;
    const alvoTela = a.base === 'bottom_px'
      ? topoPx + line.offsetHeight
      : topoPx + line.offsetHeight / 2;
    const y = Math.round((alvoTela - m.topo) / m.escala);
    try {
      const data = await persistCorrection({ op: 'set_caption_pos', y });
      if (data && data.ok !== false) {
        const caps = (S.editData && S.editData.captions) || {};
        if (data[a.chave] !== undefined) caps[a.chave] = data[a.chave];
        if (S.editData) S.editData.captions = caps;
        toast('Legenda reposicionada — Aplicar alterações para valer no vídeo', 2600);
      } else {
        // mesmo silencio da headline: sem gravacao, a legenda ficava no lugar
        // novo como se tivesse sido salva
        capPosicionar(line);
        if (data && data.error) toast(data.error, 3200);
        else if (!S.applying) toast('Não consegui salvar a posição da legenda', 3200);
      }
    } catch (err) {
      toast((err && err.message) || 'Não deu para salvar a posição');
      capPosicionar(line);
    }
  };
  line.addEventListener('pointerup', soltar);
  line.addEventListener('pointercancel', soltar);
  line.addEventListener('dblclick', (e) => {
    e.stopPropagation();
    voltarAoPadrao('legenda');
  });
  line.title = 'Arraste para mover · toque duplo volta ao padrão · clique edita o texto';
}

// ---------- headline arrastavel -------------------------------------------
// A altura padrao de cada estilo vem do MOTOR (/api/headline-anchors), nao de
// uma copia aqui: a tabela ja vive no template e no render_proprio, e uma
// terceira copia sairia de sincronia no primeiro estilo novo.
let HL_ANCORAS = null;
let CAP_ANCORAS = null;
fetch('/api/headline-anchors', { cache: 'no-store' })
  .then((r) => (r.ok ? r.json() : null))
  .then((d) => {
    if (d && d.anchors) HL_ANCORAS = d.anchors;
    if (d && d.captions) CAP_ANCORAS = d.captions;
  })
  .catch(() => {});

const HL_QUADRO_H = 1920;   // altura do quadro que o motor desenha

/** {base, px} da headline deste projeto: o valor salvo vence o padrao. */
function hlAncora() {
  const hook = (S.editData && S.editData.hook) || {};
  const estilo = String(hook.style || 'outline');
  const padrao = (HL_ANCORAS && HL_ANCORAS[estilo]) || { base: 'top', px: 300 };
  if (hook.paddingBottom != null && padrao.base === 'bottom') {
    return { base: 'bottom', px: Number(hook.paddingBottom) };
  }
  if (hook.paddingTop != null) return { base: 'top', px: Number(hook.paddingTop) };
  return { base: padrao.base, px: Number(padrao.px) };
}

/** Tipografia do estilo em uso, vinda do MOTOR (nao ha copia aqui). */
function hlEstilo() {
  const hook = (S.editData && S.editData.hook) || {};
  const e = (HL_ANCORAS && HL_ANCORAS[String(hook.style || 'outline')]) || {};
  return {
    maiuscula: !!e.maiuscula,
    pesos: e.pesos || [800, 800],
    cap: Number(e.cap) || 92,
    safeWidth: Number(e.safeWidth) || 900,
    lineHeight: Number(e.lineHeight) || 1.02,
    minimo: Number(e.minimo) || 40,
  };
}

let hlMedidor = null;
/** Largura do texto no tamanho/peso pedidos, como `_larg_hl` no motor. */
function hlLargura(txt, tam, peso) {
  if (!hlMedidor) hlMedidor = document.createElement('canvas').getContext('2d');
  hlMedidor.font = `${peso} ${tam}px Poppins, sans-serif`;
  // o motor desenha com letter-spacing -1px (absoluto, nao em em)
  return hlMedidor.measureText(txt).width - Math.max(0, txt.length - 1);
}

/**
 * Quebra em duas linhas e ajusta o tamanho como `_hl_linhas` no motor.
 *
 * O overlay existe para o usuario POSICIONAR a headline; se ele mostra uma
 * caixa de altura diferente da que vai ser desenhada, a posicao escolhida
 * esta errada — e mais ainda na manchete, que se ancora pela base.
 */
function hlLayout(texto, e) {
  const palavras = String(texto || '').trim().split(/\s+/).filter(Boolean);
  let linhas = palavras.length ? [palavras.join(' ')] : [];
  if (palavras.length > 1) {
    let melhor = null, dif = Infinity;
    for (let i = 1; i < palavras.length; i++) {
      const a = palavras.slice(0, i).join(' ');
      const b = palavras.slice(i).join(' ');
      const d = Math.abs(hlLargura(a, 100, e.pesos[0]) - hlLargura(b, 100, e.pesos[1]));
      if (d < dif) { melhor = [a, b]; dif = d; }
    }
    linhas = melhor.filter(Boolean);
  }
  const maisLarga = (t) => Math.max(1, ...linhas.map(
    (l, i) => hlLargura(l, t, e.pesos[Math.min(i, 1)])));
  let tam = Math.floor(e.safeWidth / maisLarga(100) * 100);
  tam = Math.max(e.minimo, Math.min(e.cap, Math.floor(e.safeWidth / maisLarga(tam) * tam)));
  return { linhas, tam };
}

/** Escala e deslocamento do VIDEO dentro da caixa da camada. */
function hlMetrica(boxId) {
  const box = $(boxId || 'hlOverlay');
  if (!box || !video) return null;
  const v = video.getBoundingClientRect();
  const b = box.getBoundingClientRect();
  if (!v.height || !b.height) return null;
  // O video pode estar em caixa-postal dentro da moldura: ancorar na caixa
  // e nao no video colocaria a headline num lugar que o render nao usa.
  return { escala: v.height / HL_QUADRO_H, topo: v.top - b.top, alturaVideo: v.height };
}

/** Coloca a linha na altura real do quadro. */
function hlPosicionar(line) {
  const m = hlMetrica();
  if (!m || !line) return;
  const a = hlAncora();
  line.style.position = 'absolute';
  line.style.left = '50%';
  line.style.transform = 'translateX(-50%)';
  if (a.base === 'bottom') {
    const baseY = m.topo + m.alturaVideo - a.px * m.escala;
    line.style.top = Math.round(baseY - line.offsetHeight) + 'px';
  } else {
    line.style.top = Math.round(m.topo + a.px * m.escala) + 'px';
  }
}

/** Arrastar: converte a posicao na tela de volta para pixels do quadro. */
function hlArrastavel(line) {
  if (!line || line.dataset.arrasta) return;
  line.dataset.arrasta = '1';
  let arrasto = null;

  line.addEventListener('pointerdown', (e) => {
    if (S.applying || line.contentEditable === 'true') return;
    if (e.button !== 0) return;
    // Limpa aqui, no INICIO do gesto: presa ao clique que a consome, a marca
    // sobrevivia a um arrasto que nao emitiu click e comia o clique seguinte.
    line.dataset.acabouDeArrastar = '0';
    const m = hlMetrica();
    if (!m) return;
    arrasto = {
      y0: e.clientY,
      topo0: parseFloat(line.style.top) || 0,
      moveu: false,
      m,
    };
    line.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  line.addEventListener('pointermove', (e) => {
    if (!arrasto) return;
    const dy = e.clientY - arrasto.y0;
    // Limiar: sem ele, um clique com 1px de tremor viraria arrasto e o
    // clique-para-editar (que e o uso mais comum) nunca dispararia.
    if (!arrasto.moveu && Math.abs(dy) < 4) return;
    arrasto.moveu = true;
    line.classList.add('dragging');
    const m = arrasto.m;
    const min = m.topo;
    const max = m.topo + m.alturaVideo - line.offsetHeight;
    line.style.top = Math.round(Math.max(min, Math.min(max, arrasto.topo0 + dy))) + 'px';
  });

  const soltar = async (e) => {
    if (!arrasto) return;
    const moveu = arrasto.moveu;
    const m = arrasto.m;
    arrasto = null;
    line.classList.remove('dragging');
    try { line.releasePointerCapture(e.pointerId); } catch { /* ja solto */ }
    if (!moveu) return;          // foi um clique: deixa o handler de edicao
    line.dataset.acabouDeArrastar = '1';
    const a = hlAncora();
    const topoPx = parseFloat(line.style.top) || 0;
    let corpo;
    if (a.base === 'bottom') {
      const baseY = topoPx + line.offsetHeight;
      corpo = { op: 'set_headline_pos',
                paddingBottom: Math.round((m.topo + m.alturaVideo - baseY) / m.escala) };
    } else {
      corpo = { op: 'set_headline_pos',
                paddingTop: Math.round((topoPx - m.topo) / m.escala) };
    }
    try {
      const data = await persistCorrection(corpo);
      if (data && data.ok !== false) {
        const hook = (S.editData && S.editData.hook) || {};
        if (corpo.paddingTop != null) hook.paddingTop = corpo.paddingTop;
        else hook.paddingBottom = corpo.paddingBottom;
        if (S.editData) S.editData.hook = hook;
        toast('Headline reposicionada — Aplicar alterações para valer no vídeo', 2600);
      } else {
        // `persistCorrection` devolve null sem gravar nada (preview solto, ou
        // um apply em curso). Antes disto nao acontecia NADA: a headline ficava
        // parada no lugar novo e parecia salva. Volta para onde ela esta de
        // verdade e diz o porque.
        hlPosicionar(line);
        if (data && data.error) toast(data.error, 3200);
        else if (!S.applying) toast('Não consegui salvar a posição da headline', 3200);
      }
    } catch (err) {
      toast((err && err.message) || 'Não deu para salvar a posição');
      hlPosicionar(line);
    }
  };
  line.addEventListener('pointerup', soltar);
  line.addEventListener('pointercancel', soltar);
  line.addEventListener('dblclick', (e) => {
    e.stopPropagation();
    voltarAoPadrao('headline');
  });
  line.title = 'Arraste para mover · toque duplo volta ao padrão · clique edita o texto';
}

function updateHlOverlay() {
  const box = $('hlOverlay');
  if (!box) return;
  const lines = headlineLines();
  const hook = (S.editData && S.editData.hook) || {};
  const usable = S.tab !== 2 && lines.length && hook.enabled !== false;
  if (!usable) { box.classList.add('hidden'); return; }
  const end = Number(hook.endSec) || 4;
  const t = video.currentTime || 0;
  const editing = box.querySelector('[contenteditable="true"]') || S.editingHeadline;
  if (!editing && t > end + 0.2) {
    box.classList.add('hidden');
    return;
  }
  box.classList.remove('hidden');
  if (editing) return;
  const showLines = hlAnswerMode() && hlAnswerLines().length ? hlAnswerLines() : lines;
  const e = hlEstilo();
  let texto = showLines.join(' ');
  if (e.maiuscula) texto = texto.toUpperCase();
  const lay = hlLayout(texto, e);
  const want = lay.linhas.join('\n');
  let line = box.querySelector('.hl-overlay-line');
  if (!line) {
    box.innerHTML = '';
    line = el('div', 'hl-overlay-line', box);
  }
  if (line.textContent !== want) line.textContent = want;
  // Tamanho e entrelinha do ESTILO, na escala do video — sem isto a caixa
  // tinha sempre a mesma altura e a posicao escolhida no arrasto nao batia
  // com a desenhada.
  const m = hlMetrica();
  if (m) {
    // So escreve quando MUDA: `style.*` suja o layout, e isto roda a cada
    // quadro do rafLoop enquanto o video toca.
    const tipo = [e.pesos[0], Math.max(9, Math.round(lay.tam * m.escala * 10) / 10),
                  e.lineHeight, Math.round(e.safeWidth * m.escala)].join('|');
    if (line.dataset.tipo !== tipo) {
      line.dataset.tipo = tipo;
      const [peso, tam, lh, larg] = tipo.split('|');
      line.style.fontWeight = peso;
      line.style.fontSize = tam + 'px';
      line.style.lineHeight = lh;
      line.style.maxWidth = larg + 'px';
    }
  }
  hlArrastavel(line);
  hlPosicionar(line);
}

let rafTick = 0;
function rafLoop() {
  rafTick++;
  // Página oculta: nada disso é visível — só mantém o agendamento vivo.
  if (document.hidden) { requestAnimationFrame(rafLoop); return; }
  // Pausado e sem demos de estilo animando, 10Hz basta para manter agulha e
  // overlays em dia com seeks; 60Hz só quando algo se move de verdade.
  const rafActive = (!video.paused && !video.ended) || capAnims.length;
  if (!rafActive && (rafTick % 6)) { requestAnimationFrame(rafLoop); return; }
  // UMA leitura de layout por quadro, AQUI: o layout ainda esta limpo (o
  // navegador acabou de desenhar) e ninguem pagou nada por ela. Quem
  // precisa da rolagem mais abaixo usa este valor em vez de perguntar de
  // novo depois de ja ter escrito estilo — que e o que forcava o
  // recalculo. Ver o comentario em positionNeedle.
  quadroEsq = panel.scrollLeft;
  const larguraPainel = panel.clientWidth;
  updateCapOverlay();
  updateHlOverlay();
  highlightCurrentCaption(currentCaptionIndex());
  if (capAnims.length) {
    const now = performance.now() / 1000;
    for (const step of capAnims) step(now);
  }
  positionNeedle();
  // `!drag`: durante um arrasto a timeline nao pode rolar sozinha. O gesto
  // e ancorado em pixels de tela (drag.x0); se o conteudo desliza no meio,
  // o mesmo pixel passa a valer outro tempo e o trecho APAGADO nao e o que
  // ficou marcado. Desde a 3.22 o proprio arrasto leva a agulha junto,
  // entao ele mesmo disparava a rolagem perto da borda direita.
  if (!drag && !video.paused && !video.ended) {
    // keep needle visible
    const x = LABEL_W + renderedToDraft(video.currentTime) * S.pps;
    const right = quadroEsq + larguraPainel;
    if (x > right - 80) panel.scrollLeft = x - larguraPainel * 0.25;
  }
  quadroEsq = null;   // fora do quadro, quem precisar le por conta propria
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
  // The gutter is chrome, not timeline. Without this guard a pointerdown on a
  // track icon fell through to the scrub branch below, which both yanked the
  // needle to 0 (the gutter is left of t=0, so it computes a negative time) and
  // called setPointerCapture on the panel — retargeting the following click and
  // swallowing it, so a real click on the A1/A2 disclosure never fired while a
  // programmatic .click() did.
  if (e.target.closest('.track-label') || e.target.closest('button')) return;

  if (S.ferramenta === 'laco') {
    // Pegar DENTRO da selecao move o conjunto; pegar fora comeca uma nova.
    const dentro = e.target.closest('.chip.insert, .chip.caption, .clip');
    const iDentro = dentro
      ? (dentro.classList.contains('chip')
        ? (dentro.classList.contains('caption')
          ? S.capSel.includes(+dentro.dataset.ci)
          : S.blocosSel.includes(+dentro.dataset.i))
        : S.takeSel.includes(+dentro.dataset.i))
      : false;
    if (iDentro && S.blocosSel.length) {
      drag = {type: 'laco-mover', x0: e.clientX, dt: 0,
              preSnapshot: snapshotState()};
      try { panel.setPointerCapture(e.pointerId); } catch (err) { /* touch */ }
      e.preventDefault();
      return;
    }
    const r0 = timelineEl.getBoundingClientRect();
    drag = {type: 'laco', x0: e.clientX, y0: e.clientY, ox: r0.left, oy: r0.top};
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* touch */ }
    e.preventDefault();
    return;
  }

  const handle = e.target.closest('.handle');
  const clip = e.target.closest('.clip');
  const chip = e.target.closest('.chip.insert');
  if (!chip && S.blocoSel >= 0) {
    S.blocoSel = -1;      // clicou fora: solta a selecao
    renderChips();
    refreshHeader();
  }

  // caption chips are click-to-edit, not draggable — their timing belongs to
  // the transcript, only the WORDS are the user's to correct here
  const cap = e.target.closest('.chip.caption');
  if (cap) {   // any tab the chips render on — Fase 1 is where fixing pays off
    const ci = +cap.dataset.ci;
    // Ctrl/Cmd marca uma; Shift marca o intervalo. O clique SIMPLES continua
    // abrindo o editor, que e o uso de longe mais comum — a selecao multipla
    // existe para apagar varias de uma vez, nao para atrapalhar o resto.
    if (e.ctrlKey || e.metaKey) {
      S.selected = -1;                 // ver a nota na selecao de take
      const k = S.capSel.indexOf(ci);
      if (k >= 0) S.capSel.splice(k, 1); else S.capSel.push(ci);
      S.capSelAncora = ci;
    } else if (e.shiftKey && S.capSelAncora >= 0) {
      S.selected = -1;
      const a = Math.min(S.capSelAncora, ci), b = Math.max(S.capSelAncora, ci);
      for (let n = a; n <= b; n++) if (!S.capSel.includes(n)) S.capSel.push(n);
    } else {
      // repinta ANTES de abrir: sem isto os chips marcados continuavam
      // brancos na faixa enquanto o editor de outra legenda estava aberto
      const tinhaSel = S.capSel.length > 0;
      S.capSel = [];
      S.capSelAncora = ci;
      if (tinhaSel) renderAll();
      openCaptionEditor(ci, cap);
      e.preventDefault();
      return;
    }
    closeCaptionEditor();
    renderAll();
    if (S.capSel.length) {
      toast(`${S.capSel.length} legenda${S.capSel.length > 1 ? 's' : ''} selecionada${S.capSel.length > 1 ? 's' : ''} · Delete apaga`, 2400);
    }
    e.preventDefault();
    return;
  }

  if (handle && clip && S.tab === 1) {
    const i = +handle.dataset.i;
    drag = { type: 'trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, r: { ...S.draft[i] }, preSnapshot: snapshotState() };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  // O bloco POSTO NA MAO tambem se ajusta na Edicao: ele nasce em tempo de
  // rascunho, que e o relogio daquela tela. So os inserts da IA continuam
  // presos ao Visual, onde o relogio deles bate.
  // `manual` cobre insert, emoji e som ja aplicados — todos voltam como
  // camada viva e continuam ajustaveis
  const daMao = chip && (S.insertsDraft[+chip.dataset.i]?.isNew
    || S.insertsDraft[+chip.dataset.i]?.manual);
  if (handle && chip && (S.tab === 2 || daMao)) {
    const i = +handle.dataset.i;
    drag = { type: 'chip-trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, c: { ...S.insertsDraft[i] }, preSnapshot: snapshotState() };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (chip && (S.tab === 2 || daMao)) {
    const i = +chip.dataset.i;
    if (daMao && S.blocoSel !== i) {
      // selecionar e o primeiro gesto: dai o Excluir de cima tem alvo
      S.blocoSel = i;
      renderChips();
      refreshHeader();
    }
    drag = { type: 'chip-move', i, x0: e.clientX, y0: e.clientY,
             // altura da fileira de midia: arrastar uma fileira inteira na
             // vertical troca o bloco de CAMADA (hierarquia, pedido de 02/09)
             laneH: chip.closest('.track')?.offsetHeight || 60,
             c: { ...S.insertsDraft[i] }, preSnapshot: snapshotState() };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (clip && S.tab === 1) {
    // Undecided yet between "click to select" and "drag to select-and-delete
    // a range" — pointermove below promotes this to the latter only past a
    // few px of real movement, so a plain click keeps working exactly as
    // before. See deleteClipRange().
    //
    // A AGULHA NAO VAI MAIS JUNTO (04/09). Ela andava ao clicar no take
    // desde 27/08, quando a regua era uma tira de ~14px e nao dava para
    // posicionar a agulha depois de um corte. O preco disso era clicar num
    // take, numa imagem ou numa legenda e ver a reproducao pular: "se eu
    // clicar em cima de um video nao e pra mover a agulha... a agulha deve
    // ser movida so na linha da minutagem". A regua ficou mais alta e
    // continua na MESMA coluna de tempo do take, entao posicionar para
    // cortar e um clique logo acima.
    const iClip = +clip.dataset.i;
    drag = { type: 'clip-range', i: iClip, x0: e.clientX, x1: e.clientX, moved: false };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (clip) {
    S.selected = +clip.dataset.i;
    // Uma selecao por vez: com legendas marcadas e um take selecionado, o
    // Delete ia para as legendas e o take nunca era excluido.
    S.capSel = [];
    renderClips();
    return;
  }
  // SO A MINUTAGEM ARRASTA A AGULHA (04/09). Antes, todo pointerdown que
  // nao casasse com um ramo acima caia aqui: clicar num audio, numa imagem
  // ou no fundo de uma faixa movia a agulha. Pior, o `setPointerCapture`
  // daqui retargeta o CLIQUE seguinte para o painel — era isso que engolia
  // o clique do chip da TRILHA, e o menu de trocar trilha nunca abria
  // ("nao da pra clicar na trilha sonora pra adicionar outra"). A mesma
  // armadilha ja tinha mordido o `.track-label`, guardado la em cima.
  if (!e.target.closest('.ruler-track')) return;
  const rect = timelineEl.getBoundingClientRect();
  const t = (e.clientX - rect.left - LABEL_W) / S.pps;
  // Clique num losango de emenda abre o menu da transicao, nao move a
  // agulha (5.0.37). 7px de tolerancia: o losango tem 10.
  const emendas = fronteirasDoRascunho();
  const perto = emendas.findIndex((tb) => Math.abs(tb - t) * S.pps <= 7);
  if (perto >= 0) {
    abrirMenuDaEmenda(perto, e.clientX, e.clientY);
    return;
  }
  drag = { type: 'scrub' };
  seekDraft(t);
  try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
});

panel.addEventListener('pointermove', (e) => {
  if (!drag) return;
  if (drag.type === 'laco') {
    const cx = Math.min(drag.x0, e.clientX);
    const cy = Math.min(drag.y0, e.clientY);
    const cw = Math.abs(e.clientX - drag.x0);
    const ch = Math.abs(e.clientY - drag.y0);
    const box = $('lacoBox');
    box.classList.remove('hidden');
    box.style.left = `${cx - drag.ox}px`;
    box.style.top = `${cy - drag.oy}px`;
    box.style.width = `${cw}px`;
    box.style.height = `${ch}px`;
    marcarPeloRetangulo({left: cx, top: cy, right: cx + cw, bottom: cy + ch});
    renderClips();
    renderChips();      // desenha os blocos E as legendas
    return;
  }
  if (drag.type === 'laco-mover') {
    const dt = (e.clientX - drag.x0) / S.pps;
    moverSelecaoNoTempo(dt - drag.dt);
    drag.dt = dt;
    renderAll();
    desenharMidiaNoPreview();
    return;
  }
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
    // uma atualização por frame de vídeo, não uma por evento do mouse
    if (!drag.raf) {
      drag.raf = requestAnimationFrame(() => {
        drag.raf = 0;
        updateClipGeometry();
        drawWave();
        refreshHeader();
      });
    }
    const d = drag.side === 'l' ? r.start - r.orig.start : r.end - r.orig.end;
    showTooltip(e, `${fmt(r.start)} → ${fmt(r.end)} <span class="delta">(${d >= 0 ? '+' : ''}${d.toFixed(2)}s)</span>`);
  } else if (drag.type === 'chip-trim') {
    const c = S.insertsDraft[drag.i];
    if (drag.side === 'l') {
      c.start = Math.min(Math.max(0, drag.c.start + dt), c.end - 0.15);
      // VIDEO inserido: encurtar pela ESQUERDA corta o COMEÇO do arquivo
      // (in-point), como num editor profissional — o que sobra do take não
      // se mexe na tela. Pedido de 02/09 ("recortar o vídeo ao adicionar").
      if (c.kind === 'insert' && /\.(mp4|mov|m4v|webm|mkv)$/i.test(String(c.src || ''))) {
        c.srcIn = +Math.max(0, (drag.c.srcIn || 0) + (c.start - drag.c.start)).toFixed(3);
        renderChips();
        refreshHeader();
        showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)} · take a partir de ${fmt(c.srcIn)}`);
        return;
      }
    } else c.end = Math.max(drag.c.end + dt, c.start + 0.15);
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}`);
  } else if (drag.type === 'chip-move') {
    const c = S.insertsDraft[drag.i];
    const dur = drag.c.end - drag.c.start;
    c.start = Math.max(0, drag.c.start + dt);
    c.end = c.start + dur;
    // bloco de MIDIA tambem anda na VERTICAL: cada fileira e uma camada
    // (fileira de baixo pinta por cima no video)
    let rotuloCam = '';
    if (c.kind === 'insert' && (c.manual || c.isNew)) {
      const fileiras = Math.round((e.clientY - drag.y0) / drag.laneH);
      const cam = Math.min(4, Math.max(0, (drag.c.camada | 0) + fileiras));
      if (cam !== (c.camada | 0)) {
        if (cam > 0) c.camada = cam; else delete c.camada;
      }
      if ((c.camada | 0) !== (drag.c.camada | 0)) rotuloCam = ` · camada ${(c.camada | 0) + 1}`;
      desenharMidiaNoPreview();
    }
    renderChips();
    refreshHeader();
    showTooltip(e, `${fmt(c.start)} → ${fmt(c.end)}${rotuloCam}`);
  } else if (drag.type === 'clip-range') {
    drag.x1 = e.clientX;
    if (!(S.draft[drag.i] && S.draft[drag.i].removed)) {
      // a agulha segue o dedo, como na regua (menos no fantasma removido)
      seekDraft((e.clientX - timelineEl.getBoundingClientRect().left
                 - LABEL_W) / S.pps);
    }
    if (Math.abs(drag.x1 - drag.x0) > 4) drag.moved = true;
    if (drag.moved) {
      const range = clipRangeFromPixels(drag.i, drag.x0, drag.x1);
      showClipRangeSelection(range);
      if (range) showTooltip(e, `apagar ${fmt(range.tB - range.tA)}s <span class="delta">(solte pra confirmar)</span>`);
    }
  }
});

['pointerup', 'pointercancel'].forEach((ev) =>
  panel.addEventListener(ev, () => {
    // commit ONE history entry per drag gesture (not per pointermove tick),
    // and only if the drag actually moved something — a click-and-release on
    // a handle with no movement shouldn't cost the user an undo step later
    if (drag && drag.type === 'laco') {
      $('lacoBox')?.classList.add('hidden');
      if (temSelecaoMultipla()) {
        toast(`${contarSelecao()} · Delete apaga`
          + (S.blocosSel.length ? ' · arraste para mover' : ''), 3200);
      }
      drag = null;
      return;
    }
    if (drag && drag.type === 'laco-mover') {
      if (drag.dt) {
        pushHistory(drag.preSnapshot);
        scheduleAutosave();
      }
      drag = null;
      return;
    }
    if (drag && drag.preSnapshot) {
      const moved = drag.type === 'trim'
        ? (S.draft[drag.i].start !== drag.r.start || S.draft[drag.i].end !== drag.r.end)
        : (S.insertsDraft[drag.i].start !== drag.c.start || S.insertsDraft[drag.i].end !== drag.c.end
           || (S.insertsDraft[drag.i].camada | 0) !== (drag.c.camada | 0));
      if (moved) {
        pushHistory(drag.preSnapshot);
        if (drag.type === 'trim') persistEdl();
        // Todo arrasto termina em clique: sem esta marca, soltar o bloco do
        // gancho abriria o editor da manchete por cima do que acabou de ser
        // movido (a manchete sobre o video ja usava a mesma guarda).
        if (String(drag.type).startsWith('chip')) {
          const alvo = panel.querySelector(`.chip[data-i="${drag.i}"]`);
          if (alvo) alvo.dataset.acabouDeArrastar = '1';
        }
      }
    }
    if (drag && drag.type === 'clip-range') {
      if (drag.moved) deleteClipRange(drag.i, drag.x0, drag.x1);
      else { S.selected = drag.i; renderClips(); }
      hideClipRangeSelection();
    }
    if (drag && drag.type === 'trim') {
      // solta o frame pendente e assenta a lane de verdade (filmstrip,
      // rótulos e classes voltam a bater com o rascunho final)
      if (drag.raf) cancelAnimationFrame(drag.raf);
      renderClips();
      drawWave();
      refreshHeader();
    }
    drag = null; hideTooltip();
  })
);

// double-click a clip = reset it
laneVideo.addEventListener('dblclick', (e) => {
  const clip = e.target.closest('.clip');
  if (!clip) return;
  const r = S.draft[+clip.dataset.i];
  if (r.start === r.orig.start && r.end === r.orig.end && !r.removed) return; // nothing to undo-log
  pushHistory();
  r.start = r.orig.start; r.end = r.orig.end; r.removed = false;
  renderAll(); refreshHeader();
  persistEdl();
});

// keyboard
document.addEventListener('keydown', (e) => {
  // Esc fecha o painel de IA ANTES da guarda de digitacao: o foco vive no
  // #aiPrompt, e `isTypingContext()` engolia o Esc — era o unico overlay
  // que nao fechava pelo teclado (ajuda, imagens, nota e legenda fecham).
  if (e.key === 'Escape' && !$('aiPanel')?.classList.contains('hidden')) {
    closeAiPanel();
    return;
  }
  if (isTypingContext()) return;
  if (e.key === 'm' || e.key === 'M') {
    e.preventDefault();
    toggleMark();
    return;
  }
  if (e.key === 'Escape' && !$('helpModal').classList.contains('hidden')) {
    toggleHelp(false);
    return;
  }
  if (e.key === '?' || (e.key === '/' && e.shiftKey)) {
    e.preventDefault();
    toggleHelp($('helpModal').classList.contains('hidden'));
    return;
  }
  if (e.key === 'Escape' && S.pendingIn != null) {
    S.pendingIn = null;
    renderNotes();
    toast('IN cancelado', 1600);
    return;
  }
  if (e.code === 'Space') {
    e.preventDefault();
    togglePlay();
  } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && e.altKey && S.selected >= 0 && S.tab === 1) {
    // Alt+arrows nudge the SELECTED take's edge instead of the playhead.
    // A drag cannot land a single frame reliably at any useful zoom — this is
    // the same edit, addressed in the unit the render actually works in.
    // Which edge: Alt = the OUT (right) edge, Alt+Shift = the IN (left) edge,
    // so the common case (tightening a trailing pause) is the shorter chord.
    e.preventDefault();
    nudgeTakeEdge(S.selected, e.shiftKey ? 'l' : 'r', e.key === 'ArrowRight' ? 1 : -1);
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    const step = e.shiftKey ? 1 : 1 / S.fps;
    seekDraft(renderedToDraft(video.currentTime) + (e.key === 'ArrowRight' ? step : -step));
  } else if (e.key === 'Escape' && temSelecaoMultipla()) {
    e.preventDefault();
    limparSelecaoMultipla();
  } else if (e.key === 'Escape' && S.capSel.length) {
    e.preventDefault();
    S.capSel = [];
    S.capSelAncora = -1;
    S.blocoSel = -1;
    renderAll();
  } else if ((e.key === 'Delete' || e.key === 'Backspace')
             && (S.takeSel.length || S.blocosSel.length)) {
    // o laco marcou mais de uma especie: apaga tudo junto
    e.preventDefault();
    apagarSelecaoMultipla();
  } else if ((e.key === 'v' || e.key === 'V') && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    trocarFerramenta(S.ferramenta === 'laco' ? 'agulha' : 'laco');
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.blocoSel >= 0) {
    // o bloco posto na mao vem ANTES do take: e o que esta selecionado
    e.preventDefault();
    const i = S.blocoSel;
    S.blocoSel = -1;
    removerBlocoDaMao(i);
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.capSel.length) {
    e.preventDefault();
    apagarLegendas(S.capSel);
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.selected >= 0 && S.tab === 1) {
    toggleSelectedTake();
  } else if ((e.key === 'q' || e.key === 'Q') && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    apagarAteAAgulha('esq');
  } else if ((e.key === 'w' || e.key === 'W') && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    apagarAteAAgulha('dir');
  } else if ((e.key === 's' || e.key === 'S') && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    splitAtPlayhead();
  } else if ((e.key === 'z' || e.key === 'Z') && (e.ctrlKey || e.metaKey) && !e.shiftKey) {
    e.preventDefault();
    undo();
  } else if (((e.key === 'z' || e.key === 'Z') && (e.ctrlKey || e.metaKey) && e.shiftKey) || ((e.key === 'y' || e.key === 'Y') && (e.ctrlKey || e.metaKey))) {
    e.preventDefault();
    redo();
  }
});

// transport
function togglePlay() {
  if (!video || !video.src) return;
  if (video.paused) video.play().catch(() => {});
  else video.pause();
}
$('btnPlay').innerHTML = ICON.play;
$('btnMute').innerHTML = ICON.vol;
$('btnPlay').addEventListener('click', togglePlay);
// Um ARRASTO termina em `click` no quadro. Sem isto, mover ou
// redimensionar a imagem dava play no fim do gesto — "isso atrapalha
// demais" (30/08).
let andouNoQuadro = null;
document.querySelector('.player-frame')?.addEventListener('pointerdown', (e) => {
  andouNoQuadro = {x: e.clientX, y: e.clientY, longe: false};
});
document.addEventListener('pointermove', (e) => {
  if (!andouNoQuadro) return;
  if (Math.abs(e.clientX - andouNoQuadro.x) > 4
      || Math.abs(e.clientY - andouNoQuadro.y) > 4) andouNoQuadro.longe = true;
});
document.querySelector('.player-frame')?.addEventListener('click', (e) => {
  const arrastou = andouNoQuadro && andouNoQuadro.longe;
  andouNoQuadro = null;
  if (arrastou) return;
  if (isTypingContext()) return;
  // tudo que se PEGA no quadro: legenda, headline, e o que foi posto na mao
  if (e.target.closest('button, .cap-overlay-line, .hl-overlay-line, #capEditor,'
      + ' #hlOverlay, .midia-previa-card, .midia-previa-emoji, .previa-alca')) return;
  togglePlay();
});
video.addEventListener('play', () => { $('btnPlay').innerHTML = ICON.pause; });
video.addEventListener('pause', () => { $('btnPlay').innerHTML = ICON.play; });
video.addEventListener('ended', () => { $('btnPlay').innerHTML = ICON.play; });
$('btnMute').addEventListener('click', () => {
  video.muted = !video.muted;
  $('btnMute').innerHTML = video.muted ? ICON.mute : ICON.vol;
});
$('zoom').addEventListener('input', (e) => setZoom(+e.target.value));

$('btnUndo').innerHTML = ICON.undo;
$('btnRedo').innerHTML = ICON.redo;
$('btnUndo').addEventListener('click', undo);
$('btnRedo').addEventListener('click', redo);
// So o icone: o nome fica no `title`. Devolve barra, que na tela do usuario
// (125% de escala) era o que fazia os rotulos recolherem cedo.
$('btnSplit').innerHTML = ICON.razor;
$('btnSplit').classList.add('icon');
$('btnSplit').addEventListener('click', splitAtPlayhead);
// Apagar da agulha para um lado — o Q e o W do CapCut, tambem no botao:
// atalho sem botao e recurso que so existe para quem leu o changelog.
$('btnCutLeft').innerHTML = ICON.cortarEsq;
$('btnCutRight').innerHTML = ICON.cortarDir;
$('btnCutLeft').addEventListener('click', () => apagarAteAAgulha('esq'));
$('btnCutRight').addEventListener('click', () => apagarAteAAgulha('dir'));
$('btnDeleteTake').innerHTML = ICON.trash;
$('btnDeleteTake').classList.add('icon');
$('btnDeleteTake').addEventListener('click', toggleSelectedTake);
$('coverIcon').innerHTML = ICON.cover;
$('btnCover').addEventListener('click', saveCoverFromPlayhead);
// A ajuda mora no menu (⋯). O botao flutuante saiu de cima do preview: ele
// tapava o canto do video, e o canto de baixo e onde a legenda mora.
if ($('btnHelpMenu')) {
  $('btnHelpMenu').addEventListener('click', () => {
    // `closeHeadMore()`, nunca `#headMore`: aquele e o BOTAO ⋯, e escondelo
    // fazia o menu inteiro sumir do cabecalho depois do primeiro uso — foi
    // exatamente o que o usuario viu ("cade o menu abaixo do minimizar?").
    closeHeadMore();
    toggleHelp(true);
  });
}

if ($('capaChip')) {
  $('capaChip').addEventListener('click', (e) => {
    e.stopPropagation();
    saveCoverFromPlayhead();
  });
}

/* A capa ja escolhida aparece no proprio bloco: sem isso o usuario nao
 * sabe se ja definiu uma, nem qual quadro ficou. */
function mostrarCapaNoBloco() {
  const chip = $('capaChip');
  if (!chip || !BASE) return;
  // (o rotulo so aparece quando NAO ha capa: com a miniatura, texto por
  //  cima e ruido — o `title` continua explicando)
  const img = new Image();
  img.onload = () => {
    chip.style.backgroundImage = `url(${img.src})`;
    chip.classList.add('tem-capa');
  };
  img.src = `${BASE}/media/cover.jpg?v=${Date.now()}`;
}
window.addEventListener('load', mostrarCapaNoBloco);
if ($('appendCtaIcon')) $('appendCtaIcon').innerHTML = ICON.appendCta;
if ($('btnAppendCta')) {
  $('btnAppendCta').addEventListener('click', () => {
    if (!$('appendCtaFile')) return;
    $('appendCtaFile').click();
  });
}
if ($('appendCtaFile')) {
  $('appendCtaFile').addEventListener('change', () => {
    appendCtaFromFile($('appendCtaFile').files && $('appendCtaFile').files[0]);
    $('appendCtaFile').value = '';
  });
}

function projectFolder() {
  if (!BASE || !BASE.startsWith('/p/')) return '';
  return decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
}

function probeLocalDuration(file) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (d) => {
      if (settled) return;
      settled = true;
      resolve(Number.isFinite(d) ? d : 0);
    };
    const timer = setTimeout(() => finish(0), 2500);
    try {
      const url = URL.createObjectURL(file);
      const v = document.createElement('video');
      v.preload = 'metadata';
      v.onloadedmetadata = () => {
        clearTimeout(timer);
        const d = Number(v.duration) || 0;
        URL.revokeObjectURL(url);
        finish(d);
      };
      v.onerror = () => {
        clearTimeout(timer);
        URL.revokeObjectURL(url);
        finish(0);
      };
      v.src = url;
    } catch {
      clearTimeout(timer);
      finish(0);
    }
  });
}

async function appendCtaFromFile(file) {
  if (!file) return;
  const folder = projectFolder();
  if (!folder && !BASE) {
    toast('Abra o vídeo pelo app para importar um take', 2800);
    return;
  }
  const btn = $('btnAppendCta');
  if (btn) btn.disabled = true;
  const ehImagem = /^image\//.test(file.type || '') || /\.(jpe?g|png|webp)$/i.test(file.name || '');
  toast(ehImagem ? 'Transformando a imagem num trecho de 5 s…' : 'Importando o vídeo…', 1600);
  try {
    const duration = ehImagem ? 5 : await probeLocalDuration(file);
    const localPath = String(file.path || '').trim();
    const url = BASE ? `${BASE}/api/append-cta` : '/api/jobs/append-cta';
    let res;
    if (localPath && /^[A-Za-z]:[\\/]/.test(localPath)) {
      res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder, path: localPath, duration }),
      });
    } else {
      const fd = new FormData();
      fd.append('file', file, file.name);
      if (folder) fd.append('folder', folder);
      if (duration) fd.append('duration', String(duration));
      res = await fetch(url, { method: 'POST', body: fd });
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      toast(data.error || data.message || `Não deu para acrescentar esse vídeo (${res.status})`, 4200);
      return;
    }
    const dur = Math.max(0.4, Number(data.duration) || 0);
    pushHistory();
    S.state.sourceDurations = S.state.sourceDurations || {};
    S.state.sourceDurations[data.source] = dur;

    // ONDE a agulha esta. Se ela cai no meio de um take, esse take e
    // dividido e o novo entra entre as duas metades — e assim que se
    // acrescenta um take no meio sem perder nada do que ja havia.
    const t0 = renderedToDraft(video.currentTime || 0);
    const layout = draftLayout();
    let onde = S.draft.length;            // padrao: no fim
    for (let k = 0; k < layout.length; k++) {
      if (S.draft[k].removed) continue;
      const ini = layout[k].out;
      const fim = ini + layout[k].dur;
      if (t0 <= ini + 0.02) { onde = k; break; }          // antes deste take
      if (t0 < fim - 0.02) {                              // dentro: divide
        const r = S.draft[k];
        const corte = draftTimeToSource(k, t0);
        const metadeB = { ...r, start: corte, srcIdx: null,
                          orig: { start: r.start, end: r.end } };
        r.end = corte;
        r.orig = { start: r.start, end: corte };
        S.draft.splice(k + 1, 0, metadeB);
        onde = k + 1;
        break;
      }
    }
    const noFim = onde >= S.draft.length;
    if (noFim) {
      // so quem vai mesmo para o fim vira CTA: um 'CTA' no meio confundiria
      // o planejador do proximo corte
      const last = [...S.draft].reverse().find((r) => !r.removed);
      if (last && String(last.beat || '').toUpperCase() === 'CTA') last.beat = 'KEEP';
    }
    S.draft.splice(onde, 0, {
      source: data.source,
      start: 0,
      end: dur,
      beat: noFim ? 'CTA' : 'KEEP',
      removed: false,
      added: true,
      filePath: data.path,
      srcIdx: null,
      orig: { start: 0, end: dur },
    });
    S.selected = onde;
    renderAll();
    refreshHeader();
    toast(noFim ? 'Take no fim — clique em Salvar para renderizar'
                : 'Take importado na agulha — clique em Salvar para renderizar', 3200);
  } catch (err) {
    toast((err && err.message) || 'Não deu para acrescentar esse vídeo', 3200);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function toggleSelectedTake() {
  if (S.applying) return;
  // Bloco posto na mao vem primeiro: e o que esta selecionado na tela.
  if (S.blocoSel >= 0) {
    const i = S.blocoSel;
    S.blocoSel = -1;
    removerBlocoDaMao(i);
    return;
  }
  if (S.tab !== 1 || S.selected < 0) {
    toast('Selecione um take pra apagar', 1600);
    return;
  }
  const i = S.selected;
  const r = S.draft[i];
  if (!r) return;
  pushHistory();
  r.removed = !r.removed;
  if (r.removed) {
    const next = S.draft.findIndex((x, j) => j > i && !x.removed);
    let prev = -1;
    for (let j = i - 1; j >= 0; j--) {
      if (!S.draft[j].removed) { prev = j; break; }
    }
    S.selected = next >= 0 ? next : prev;
    const keep = S.selected >= 0 ? draftLayout()[S.selected] : null;
    if (keep) seekDraft(keep.out + Math.min(0.05, keep.dur / 2));
  }
  renderAll();
  refreshHeader();
  persistEdl();
}

function refreshTransportActions() {
  renderFxPanel();
  const btn = $('btnDeleteTake');
  if (!btn) return;
  // Bloco posto na mao (imagem, som, emoji) acende o MESMO botao: o usuario
  // clica na imagem e usa o excluir de cima, sem ✕ colado no bloco.
  const bloco = S.blocoSel >= 0 ? S.insertsDraft[S.blocoSel] : null;
  const r = S.selected >= 0 ? S.draft[S.selected] : null;
  const can = !!bloco || (S.tab === 1 && !!r);
  btn.disabled = !can;
  btn.classList.toggle('danger-on', !!(r && r.removed) || !!bloco);
  btn.title = bloco
    ? `Tirar da linha do tempo: ${bloco.label || 'este bloco'} (Delete)`
    : (!can
      ? 'Selecione um take ou um bloco para excluir'
      : (r.removed ? 'Restaurar o take selecionado (Delete)' : 'Excluir o take selecionado (Delete)'));
  // Os cortes valem na Edicao (a aba Visual mostra o video pronto, onde nao
  // ha o que cortar). Botao apagado sem explicacao vira "quebrado": o
  // motivo vai no titulo.
  for (const [id, lado] of [['btnCutLeft', 'ESQUERDA (Q)'],
                            ['btnCutRight', 'DIREITA (W)']]) {
    const b = $(id);
    if (!b) continue;
    const temBloco = blocoTemDuracao(S.insertsDraft[S.blocoSel]);
    b.disabled = S.tab !== 1 && !temBloco;
    b.title = b.disabled
      ? `Apagar da agulha para a ${lado} — abra a aba Edição`
      : (temBloco
        ? `Encurtar o bloco selecionado pela ${lado}`
        : `Apagar da agulha para a ${lado}`);
  }
}

async function saveCoverFromPlayhead() {
  // (o bloco da capa se atualiza no fim desta funcao)
  const btn = $('btnCover');
  if (!btn || btn.disabled) return;
  const t = Number(video.currentTime) || 0;
  btn.disabled = true;
  try {
    const res = await fetch(`${BASE}/api/cover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ t }),
    });
    const data = await res.json();
    if (!data.ok) {
      toast(data.error || 'Não consegui salvar a capa', 3000);
      return;
    }
    const where = data.pack ? ` ao lado da legenda em ${data.pack}` : '';
    toast(`Imagem da capa salva${where} · ${fmtClock(data.t != null ? data.t : t)}`, 3200);
    mostrarCapaNoBloco();      // o bloco passa a mostrar o quadro escolhido
  } catch (e) {
    toast('Não consegui salvar a capa — servidor fora do ar?', 3500);
  } finally {
    btn.disabled = false;
  }
}

function refreshCapToggle() {
  const btn = $('btnCapPreview');
  const style = S.style && S.style.captions;
  // hidden where it cannot help: Fase 2 already has captions in the picture,
  // and a project with no captions has nothing to preview
  const relevant = S.tab !== 2 && style && style !== 'nenhuma' && S.captions.length > 0;
  btn.classList.toggle('hidden', !relevant);
  btn.classList.toggle('on', !!S.capPreviewOn);
  btn.title = S.capPreviewOn
    ? 'Legenda sobreposta — clique num trecho errado na trilha de legenda para corrigir'
    : 'Mostrar a legenda sobre o vídeo, antes de renderizar';
}
$('btnCapPreview').addEventListener('click', () => {
  S.capPreviewOn = !S.capPreviewOn;
  localStorage.setItem('ativa-vid.capPreview', S.capPreviewOn ? '1' : '0');
  refreshCapToggle();
  updateCapOverlay();
});
// Not only from rafLoop: the browser freezes requestAnimationFrame whenever the
// tab is not visible, so a caption that was on screen would stay frozen on the
// wrong line after a background seek. These events fire regardless.
['seeked', 'timeupdate', 'loadedmetadata'].forEach((ev) =>
  video.addEventListener(ev, () => { updateCapOverlay(); desenharMidiaNoPreview(); })
);

$('postCopy').addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText($('postText').textContent);
    toast('Legenda copiada — cole no Instagram');
  } catch (e) { toast('Não consegui copiar'); }
});

// ---------- image picker (Pexels + biblioteca local) ----------
let IMG_TAB = 'pexels';

function projectFolder() {
  if (!BASE) return '';
  try {
    return decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
  } catch {
    return '';
  }
}

function toggleImgPicker(open) {
  $('imgModal').classList.toggle('hidden', !open);
  $('imgBackdrop').classList.toggle('hidden', !open);
  if (open) {
    setImgTab(IMG_TAB);
    if (IMG_TAB === 'pexels') $('imgQuery')?.focus();
  }
}

function setImgTab(tab) {
  IMG_TAB = (tab === 'library' || tab === 'emoji') ? tab : 'pexels';
  const pex = $('imgTabPexels');
  const lib = $('imgTabLibrary');
  const emo = $('imgTabEmoji');
  if (pex) pex.classList.toggle('active', IMG_TAB === 'pexels');
  if (lib) lib.classList.toggle('active', IMG_TAB === 'library');
  if (emo) emo.classList.toggle('active', IMG_TAB === 'emoji');
  $('imgPexelsPane')?.classList.toggle('hidden', IMG_TAB !== 'pexels');
  $('imgLibraryPane')?.classList.toggle('hidden', IMG_TAB === 'pexels');
  $('imgHint').textContent = IMG_TAB === 'library'
    ? 'Arquivos da pasta Biblioteca — clique para inserir na agulha.'
    : IMG_TAB === 'emoji'
      ? 'O emoji entra grande na agulha e fica 1,6s — arraste o bloco para mover.'
      : 'A imagem escolhida entra na trilha de inserts, na posição da agulha.';
  if (IMG_TAB === 'library') loadLibraryResults();
  else if (IMG_TAB === 'emoji') mostrarEmojis();
  else $('imgResults').innerHTML = '';
}

$('btnImage').innerHTML = ICON.imgSearch;
$('btnImage').addEventListener('click', () => {
  // Vale na Edicao tambem: e la que o usuario monta a linha do tempo, e o
  // bloco entra em tempo de rascunho — o relogio daquela tela.
  if (S.tab !== 1 && S.tab !== 2) {
    toast('Abra a Edição ou o Visual para inserir mídia', 2200);
    return;
  }
  toggleImgPicker(true);
});
$('imgClose').addEventListener('click', () => toggleImgPicker(false));
$('imgBackdrop').addEventListener('click', () => toggleImgPicker(false));
$('imgQuery').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); $('imgGo').click(); }
  if (e.key === 'Escape') { e.stopPropagation(); toggleImgPicker(false); }
});
$('imgTabPexels')?.addEventListener('click', () => setImgTab('pexels'));
$('imgTabLibrary')?.addEventListener('click', () => setImgTab('library'));
$('imgTabEmoji')?.addEventListener('click', () => setImgTab('emoji'));

/* Os botoes de somar, na propria linha do tempo. Cada um abre o caminho que
 * ja existia — o que faltava era estar AQUI, onde a atencao esta. */
$('somarMidia')?.addEventListener('click', () => {
  toggleImgPicker(true);
  setImgTab('library');
});
$('somarSom')?.addEventListener('click', () => {
  toggleImgPicker(true);
  setImgTab('library');
  // a Biblioteca lista imagem, clipe e som juntos; o aviso diz onde olhar
  toast('Escolha um som da pasta Efeitos — ▶ ouve antes de pôr', 3200);
});
$('somarEmoji')?.addEventListener('click', () => {
  toggleImgPicker(true);
  setImgTab('emoji');
});
$('somarLegenda')?.addEventListener('click', () => escreverLegendaAqui());
$('imgLibRefresh')?.addEventListener('click', () => loadLibraryResults());
$('imgLibFolder')?.addEventListener('click', async () => {
  try {
    const lib = await (await fetch('/api/library')).json();
    await fetch('/api/open-path', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: lib.root }),
    });
  } catch {
    toast('Não abri a pasta da biblioteca', 2500);
  }
});
async function subirArquivoParaTimeline(file, origemNome) {
  const fd = new FormData();
  fd.append('file', file, file.name || origemNome || 'colado.png');
  const folder = projectFolder();
  // o que sobe pela timeline fica na Biblioteca DESTA empresa (5.0.2)
  const bidProj = (S.presetUsed && S.presetUsed.brandId) || '';
  const qs = folder
    ? `?use=1&folder=${encodeURIComponent(folder)}${bidProj ? `&empresa=${encodeURIComponent(bidProj)}` : ''}`
    : '';
  toast('Enviando…', 1500);
  try {
    const res = await fetch(`/api/library/upload${qs}`, { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'falha no upload');
    if (data.used && data.used.src) {
      pushInsertFromRef(data.used.src, data.name || file.name || origemNome,
        data.used.credit || 'biblioteca');
      toggleImgPicker(false);
      toast('✓ Arquivo na biblioteca e na timeline', 3500);
      return true;
    }
    await loadLibraryResults();
    toast('✓ Salvo na biblioteca — clique para inserir', 3000);
    return false;
  } catch (err) {
    toast(err.message || 'Upload falhou', 3500);
    return false;
  }
}

$('imgLibUpload')?.addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!file) return;
  await subirArquivoParaTimeline(file);
});

/* Ctrl+V direto no editor: imagem (ou video) copiada em qualquer lugar —
 * print, WhatsApp Web, pasta do Windows — cola na timeline NO PONTO DA
 * AGULHA (pedido de 01/09: "se der ctrl c em imagem e ctrl v no editor
 * deve colar a imagem no local da agulha"). O upload ja guarda na
 * Biblioteca e o `pushInsertFromRef` ja usa a agulha. */
document.addEventListener('paste', async (e) => {
  if (!BASE || S.applying || isTypingContext()) return;
  const itens = (e.clipboardData && e.clipboardData.items) || [];
  for (const it of itens) {
    if (it.kind !== 'file') continue;
    const file = it.getAsFile();
    if (!file) continue;
    const tipo = String(file.type || '');
    if (!tipo.startsWith('image/') && !tipo.startsWith('video/')) continue;
    e.preventDefault();
    // Print colado vem sem nome ("image.png") — carimbo para nao sobrescrever
    const nome = file.name && file.name !== 'image.png'
      ? file.name
      : `colado-${Date.now()}.${(tipo.split('/')[1] || 'png').replace('jpeg', 'jpg')}`;
    const arquivo = new File([file], nome, { type: file.type });
    await subirArquivoParaTimeline(arquivo, nome);
    return;
  }
});

/* Emoji nao vem de arquivo: e um caractere. Por isso ele NAO entra como
 * imagem — um insert vira cartao (780x500 no meio da tela) e o emoji
 * ficaria enquadrado. Ele tem contrato proprio (`edit-data.emojis`), que os
 * dois motores desenham solto no quadro.
 * A lista e curta de proposito: um teclado inteiro de emoji vira vitrine,
 * e o que serve num video de loja sao meia duzia deles. */
const EMOJIS = ['🔥', '😱', '😂', '👀', '💰', '✅', '❌', '⚠️', '👉', '🎯',
                '💡', '🚀', '❤️', '👏', '🤔', '📱', '🔧', '⭐', '🎁', '😮'];

function mostrarEmojis() {
  const box = $('imgResults');
  box.innerHTML = '';
  for (const e of EMOJIS) {
    const card = el('button', 'img-card emoji-card', box);
    card.textContent = e;
    card.title = `Inserir ${e} na agulha`;
    card.addEventListener('click', () => {
      pushEmoji(e);
      toggleImgPicker(false);
      toast(`✓ ${e} na agulha — arraste na linha do tempo e Salvar`, 4000);
    });
  }
}

/* Bloco de emoji: o comeco e a duracao valem (ele fica na tela enquanto o
 * bloco durar), diferente do efeito sonoro, onde so o instante importa. */
function pushEmoji(ch) {
  pushHistory();
  const start = Math.max(0, renderedToDraft(video.currentTime));
  const end = start + 1.6;
  S.insertsDraft.push({
    kind: 'emoji', label: ch, char: ch,
    start, end, orig: { start, end },
    isNew: true, x: 0.5, y: 0.34, size: 0.22,
  });
  renderAll(); refreshHeader();
  scheduleAutosave();
}

/* Aba da biblioteca (4.101): imagem, video, som ou trilha. Guardada para
 * quem sempre vai no mesmo tipo. */
let LIB_KIND = 'image';
try { LIB_KIND = localStorage.getItem('ativavid.libKind') || 'image'; } catch { /* ignore */ }
function setLibKind(kind) {
  LIB_KIND = ['image', 'clip', 'sfx', 'track'].includes(kind) ? kind : 'image';
  try { localStorage.setItem('ativavid.libKind', LIB_KIND); } catch { /* ignore */ }
  document.querySelectorAll('.img-subtab').forEach((b) => b.classList.toggle('active', b.dataset.libkind === LIB_KIND));
  const hint = $('imgHint');
  if (hint && IMG_TAB === 'library') hint.textContent = {
    image: 'Clique numa imagem para inserir na agulha.',
    clip: 'Clique num vídeo para inserir na agulha, por cima do principal.',
    sfx: 'Ouça antes (▶) e clique para pôr o efeito na agulha.',
    track: 'Escolha a trilha de fundo do vídeo inteiro — troca a atual.',
  }[LIB_KIND];
}
document.querySelectorAll('.img-subtab').forEach((b) => b.addEventListener('click', () => { setLibKind(b.dataset.libkind); loadLibraryResults(); }));
function kindDoItem(it) {
  if (it.kind === 'clip' || it.kind === 'sfx' || it.kind === 'track') return it.kind;
  return 'image';
}

async function loadLibraryResults() {
  const box = $('imgResults');
  setLibKind(LIB_KIND);
  box.innerHTML = '<div class="img-empty">carregando biblioteca…</div>';
  let data;
  try {
    data = await (await fetch('/api/library')).json();
  } catch {
    box.innerHTML = '<div class="img-empty">falha ao listar biblioteca</div>';
    return;
  }
  // 5.0.2: imagem/video so desta empresa + os comuns (som e de todas)
  const bidProj = (S.presetUsed && S.presetUsed.brandId) || '';
  const items = (data.items || []).filter((it) => kindDoItem(it) === LIB_KIND)
    .filter((it) => !bidProj || !it.empresa || it.empresa === bidProj);
  if (!items.length) {
    box.innerHTML = `<div class="img-empty">${{
      image: 'Nenhuma imagem na biblioteca — use Enviar arquivo ou abra a pasta',
      clip: 'Nenhum vídeo na biblioteca — use Enviar arquivo ou abra a pasta',
      sfx: 'Nenhum efeito sonoro na biblioteca — a pasta Efeitos está vazia',
      track: 'Nenhuma trilha na biblioteca — ponha músicas na pasta Trilhas',
    }[LIB_KIND]}</div>`;
    return;
  }
  box.innerHTML = '';
  items.forEach((it) => {
    if (it.kind === 'track') {
      // Trilha de FUNDO: substitui a do video inteiro (4.101). Antes nem
      // aparecia aqui; a trilha so vinha da IA e nao dava para trocar.
      const card = el('button', 'img-card trilha-card', box);
      card.innerHTML = `<div class="img-clip-ph som">♫</div>`
        + `<button type="button" class="img-ouvir" title="Ouvir">▶</button>`
        + `<span class="img-credit">${it.name}</span>`;
      card.querySelector('.img-ouvir').addEventListener('click', (ev) => {
        ev.stopPropagation();
        ouvirSom(`/api/library/file?rel=${encodeURIComponent(it.rel)}`, ev.currentTarget);
      });
      card.addEventListener('click', () => usarComoTrilha(it));
      return;
    }
    const card = el('button', 'img-card', box);
    const thumb = `/api/library/file?rel=${encodeURIComponent(it.rel)}`;
    if (it.kind === 'clip') {
      // O clipe MOSTRA um quadro do vídeo (pedido de 02/09: "aqui não
      // mostra preview do vídeo") — o ▶ vira selo por cima da miniatura.
      card.innerHTML = `<div class="img-clip-ph">▶</div><span class="img-credit">${it.name}</span>`;
      capturarQuadroDeVideo(thumb, (data) => {
        if (!card.isConnected) return;
        const ph = card.querySelector('.img-clip-ph');
        if (ph) {
          ph.classList.add('com-quadro');
          ph.style.backgroundImage = `url("${data}")`;
        }
      });
    } else if (it.kind === 'sfx') {
      // som nao tem miniatura: o cartao dizia `<img src=...mp3>` e saia quebrado
      card.innerHTML = `<div class="img-clip-ph som">♪</div>`
        + `<button type="button" class="img-ouvir" title="Ouvir">▶</button>`
        + `<span class="img-credit">${it.name}</span>`;
      // Ouvir ANTES de por: o nome do arquivo nao diz como o som e, e sem
      // isto o usuario so descobria que era o errado no video pronto.
      card.querySelector('.img-ouvir').addEventListener('click', (ev) => {
        ev.stopPropagation();
        ouvirSom(`/api/library/file?rel=${encodeURIComponent(it.rel)}`, ev.currentTarget);
      });
    } else {
      card.innerHTML = `<img src="${thumb}" alt=""><span class="img-credit">${it.name}</span>`;
    }
    card.addEventListener('click', () => pickLibraryAsset(it));
  });
}

/* Um som por vez: dois tocando juntos viram barulho e nao da para julgar
 * nenhum dos dois. Clicar de novo no mesmo para. */
let _somOuvindo = null;
function ouvirSom(url, botao) {
  if (_somOuvindo) {
    const igual = _somOuvindo.src.endsWith(url) || _somOuvindo._url === url;
    _somOuvindo.pause();
    if (_somOuvindo._botao) _somOuvindo._botao.textContent = '▶';
    _somOuvindo = null;
    if (igual) return;
  }
  const a = new Audio(url);
  a._url = url;
  a._botao = botao;
  a.volume = 0.8;
  if (botao) botao.textContent = '❚❚';
  a.addEventListener('ended', () => {
    if (botao) botao.textContent = '▶';
    if (_somOuvindo === a) _somOuvindo = null;
  });
  a.play().catch(() => {
    if (botao) botao.textContent = '▶';
    toast('Não consegui tocar esse som', 2400);
  });
  _somOuvindo = a;
}

/* Trilha de fundo pela timeline (4.101): copia a musica da biblioteca para
 * o public/ do projeto e aponta soundtrack.file para ela. O render (rapido
 * e completo) le soundtrack.file de edit-data — nao precisa de nada novo
 * do lado do motor. */
async function usarComoTrilha(it) {
  toast('Colocando a trilha…', 1200);
  const folder = projectFolder();
  let data;
  try {
    data = await (await fetch('/api/library/use', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: it.path, folder }),
    })).json();
  } catch {
    toast('Falha ao copiar a trilha', 3000);
    return;
  }
  if (!data.ok && !data.src) { toast(data.error || 'Falha', 3000); return; }
  definirTrilha(data.src || data.ref, it.name, it.path);
  toggleImgPicker(false);
}

function definirTrilha(src, nome, libraryPath) {
  if (!S.editData) return;
  pushHistory();
  const st = S.editData.soundtrack || {};
  S.editData.soundtrack = {
    ...st, enabled: !!src, file: src || st.file || 'trilha.mp3',
    volume: st.volume != null ? st.volume : 0.12,
    // marca de escolha humana: o pipeline nao troca por outra da IA, e o
    // caminho na Biblioteca faz a escolha sobreviver ao refazer
    manual: !!src, label: nome || '', libraryPath: src ? (libraryPath || '') : '',
  };
  S.editData.soundtrackDirty = true;
  renderAll(); refreshHeader();
  scheduleAutosave();
  toast(src ? `✓ Trilha: ${nome || src.split('/').pop()} — Salvar e Aplicar para ouvir no vídeo` : '✓ Trilha removida — Salvar e Aplicar', 4200);
}

function abrirMenuTrilha(x, y) {
  document.querySelectorAll('.music-menu').forEach((m) => m.remove());
  const menu = el('div', 'music-menu', document.body);
  menu.style.left = `${Math.min(x, innerWidth - 240)}px`;
  menu.style.top = `${Math.min(y, innerHeight - 160)}px`;
  const st = (S.editData && S.editData.soundtrack) || {};
  const vol = Number(st.volume != null ? st.volume : 0.12);
  menu.innerHTML = `
    <button type="button" data-act="trocar">Trocar trilha (biblioteca)</button>
    <button type="button" data-act="mais">Volume + (${vol.toFixed(2)})</button>
    <button type="button" data-act="menos">Volume −</button>
    <button type="button" data-act="remover">Remover trilha</button>`;
  menu.addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    menu.remove();
    if (act === 'trocar') { toggleImgPicker(true); setImgTab('library'); setLibKind('track'); loadLibraryResults(); return; }
    if (act === 'remover') { definirTrilha('', ''); return; }
    if (act === 'mais' || act === 'menos') {
      pushHistory();
      const s = S.editData.soundtrack || {};
      const v = Math.max(0.02, Math.min(1, +(Number(s.volume != null ? s.volume : 0.12) + (act === 'mais' ? 0.04 : -0.04)).toFixed(2)));
      S.editData.soundtrack = { ...s, volume: v };
      renderAll(); scheduleAutosave();
      toast(`Volume da trilha: ${v.toFixed(2)}`, 1600);
    }
  });
  setTimeout(() => document.addEventListener('click', (e) => { if (!e.target.closest('.music-menu')) menu.remove(); }, { once: true }), 0);
}

async function pickLibraryAsset(it) {
  toast('Copiando…', 1200);
  const folder = projectFolder();
  let data;
  try {
    data = await (await fetch('/api/library/use', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: it.path, folder }),
    })).json();
  } catch {
    toast('Falha ao usar arquivo da biblioteca', 3000);
    return;
  }
  if (!data.ok && !data.src) { toast(data.error || 'Falha', 3000); return; }
  if ((data.kind || it.kind) === 'sfx') {
    pushSfxFromRef(data.src || data.ref, it.name);
    toggleImgPicker(false);
    toast('✓ Efeito na agulha — arraste na linha do tempo e Salvar', 4000);
    return;
  }
  pushInsertFromRef(data.src || data.ref, it.name, it.name);
  toggleImgPicker(false);
  toast('✓ Entrou na agulha — arraste na linha do tempo e Salvar', 4000);
}

/* Um efeito e um PONTO, nao um intervalo: ele toca inteiro a partir do
 * instante. O bloco tem largura fixa so para dar onde pegar e arrastar —
 * o que viaja no salvar e o comeco. */
const SFX_BLOCO_S = 0.6;

function pushSfxFromRef(src, label) {
  pushHistory();
  const start = Math.max(0, renderedToDraft(video.currentTime));
  const end = start + SFX_BLOCO_S;
  S.insertsDraft.push({
    kind: 'sfx', label: label || (src || '').split('/').pop(),
    start, end, orig: { start, end },
    isNew: true, src, volume: 0.5,
  });
  renderAll(); refreshHeader();
  desenharMidiaNoPreview();
  scheduleAutosave();
}

/* A camada inicial de um insert novo: a MENOR fileira sem colisao de tempo
 * com o que ja esta na faixa de midia — o bloco novo nao nasce em cima de
 * outro. Depois o usuario arrasta o bloco na VERTICAL para trocar. */
function camadaLivre(start, end) {
  const ocupa = S.insertsDraft.filter(
    (c) => c.kind === 'insert' && (c.manual || c.isNew)
      && c.start < end - 1e-6 && c.end > start + 1e-6);
  for (let cam = 0; cam <= 4; cam++) {
    if (!ocupa.some((c) => (c.camada | 0) === cam)) return cam;
  }
  return 4;
}

function pushInsertFromRef(src, label, credit) {
  pushHistory();
  const start = Math.max(0, renderedToDraft(video.currentTime));
  const end = start + 2.5;
  const camada = camadaLivre(start, end);
  S.insertsDraft.push({
    ...(camada > 0 ? { camada } : {}),
    kind: 'insert', label: label || (src || '').split('/').pop(),
    start, end, orig: { start, end },
    isNew: true, manual: true,
    mid: `m${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`,
    src, credit: credit || '',
  });
  renderAll(); refreshHeader();
  desenharMidiaNoPreview();
  scheduleAutosave();
}

/* De onde a busca online vem (4.96): Pexels fotos, Freepik fotos ou Freepik
 * videos. A escolha fica guardada — quem usa Freepik usa sempre. */
const IMG_FONTE_KEY = 'ativavid.imgFonte';
let IMG_FONTE = { fonte: 'pexels', kind: 'image' };
try {
  const salvo = JSON.parse(localStorage.getItem(IMG_FONTE_KEY) || 'null');
  if (salvo && salvo.fonte) IMG_FONTE = salvo;
} catch { /* ignore */ }
function setImgFonte(fonte, kind) {
  IMG_FONTE = { fonte: fonte === 'freepik' ? 'freepik' : 'pexels', kind: kind === 'video' ? 'video' : 'image' };
  try { localStorage.setItem(IMG_FONTE_KEY, JSON.stringify(IMG_FONTE)); } catch { /* ignore */ }
  document.querySelectorAll('.img-fonte').forEach((b) => {
    b.classList.toggle('active', b.dataset.fonte === IMG_FONTE.fonte && b.dataset.kind === IMG_FONTE.kind);
  });
  const q = $('imgQuery');
  if (q) q.placeholder = IMG_FONTE.kind === 'video'
    ? 'ex.: celular na mão, loja, cliente sorrindo'
    : 'ex.: celular capinha, loja, mãos digitando';
  const hint = $('imgHint');
  if (hint && IMG_TAB === 'pexels') hint.textContent = IMG_FONTE.kind === 'video'
    ? 'Clipes de até 20 s. O vídeo vem em 4K e é convertido para 1080p aqui: o download leva alguns minutos.'
    : 'A imagem escolhida entra na trilha de inserts, na posição da agulha.';
}
document.querySelectorAll('.img-fonte').forEach((b) => {
  b.addEventListener('click', () => {
    setImgFonte(b.dataset.fonte, b.dataset.kind);
    if ($('imgQuery').value.trim()) $('imgGo').click();
  });
});
setImgFonte(IMG_FONTE.fonte, IMG_FONTE.kind);

$('imgGo').addEventListener('click', async () => {
  const q = $('imgQuery').value.trim();
  if (!q) return;
  const box = $('imgResults');
  box.innerHTML = '<div class="img-empty">buscando…</div>';
  let data;
  const extra = IMG_FONTE.fonte === 'freepik'
    ? `&source=freepik&kind=${encodeURIComponent(IMG_FONTE.kind)}` : '';
  try {
    data = await (await fetch(`${BASE}/api/images/search?q=${encodeURIComponent(q)}${extra}`)).json();
  } catch (e) {
    box.innerHTML = '<div class="img-empty">falha na busca — servidor de pé?</div>';
    return;
  }
  if (!data.ok) {
    box.innerHTML = `<div class="img-empty">${data.error || 'busca falhou'}</div>`;
    return;
  }
  if (!data.results.length) {
    box.innerHTML = '<div class="img-empty">nada encontrado — tente outros termos</div>';
    return;
  }
  box.innerHTML = '';
  data.results.forEach((r) => {
    const card = el('button', 'img-card', box);
    const selo = r.kind === 'video'
      ? `<span class="img-selo">▶ ${r.duration || 'vídeo'}</span>` : '';
    const premium = r.premium ? '<span class="img-selo img-selo-premium">premium</span>' : '';
    card.innerHTML = `<img src="${r.thumb}" alt="">${selo}${premium}<span class="img-credit">${r.credit}</span>`;
    if (r.title) card.title = r.title;
    card.addEventListener('click', () => pickImage(q, r, data.source || 'pexels'));
  });
});

async function pickImage(query, r, source) {
  // Video da Freepik so existe no original 4K: baixa e converte para
  // 1080p aqui — minutos, nao segundos. Quem clicou precisa saber.
  if (source === 'freepik' && r.kind === 'video') toast('Baixando o vídeo original (4K) e convertendo para 1080p — pode levar alguns minutos…', 8000);
  else toast('Baixando…', 1500);
  let data;
  const corpo = source === 'freepik'
    ? { source: 'freepik', id: r.id, kind: r.kind || 'image', query, credit: r.credit }
    : { url: r.full, id: r.id, query, credit: r.credit };
  try {
    data = await (await fetch(`${BASE}/api/images/pick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(corpo),
    })).json();
  } catch (e) {
    toast('Falha ao baixar a imagem', 3000);
    return;
  }
  if (!data.ok) { toast(data.error || 'Falha ao baixar', 3000); return; }

  pushInsertFromRef(data.ref, data.ref.split('/').pop(), data.credit);
  toggleImgPicker(false);
  toast(data.kind === 'video'
    ? '✓ Vídeo inserido — arraste pra ajustar, depois Salvar'
    : '✓ Imagem inserida — arraste pra ajustar, depois Salvar', 4000);
}

// header — pasta do projeto, vídeo final, foco e menu •••
const openFolderBtn = $('btnOpenFolder');
if (openFolderBtn) {
  openFolderBtn.addEventListener('click', async () => {
    try {
      const res = await fetch(`${BASE}/api/open-folder`, { method: 'POST' });
      const data = await res.json();
      if (!data.ok) toast('Não consegui abrir a pasta', 3000);
    } catch (e) { toast('Não consegui abrir a pasta — servidor fora do ar?', 3500); }
  });
}
const openFinalBtn = $('btnOpenFinal');
if (openFinalBtn) {
  openFinalBtn.addEventListener('click', async () => {
    if (openFinalBtn.disabled) return;
    const tab2 = document.querySelector('[data-tab="2"]');
    if (tab2 && !tab2.disabled) goToTab(tab2);
    try { video.play().catch(() => {}); } catch { /* ignore */ }
    try {
      const res = await fetch(`${BASE}/api/open-final`, { method: 'POST' });
      const data = await res.json();
      if (!data.ok) toast(data.error || 'Não consegui abrir o vídeo final', 3000);
    } catch (e) { toast('Não consegui abrir o vídeo final', 3500); }
  });
}

function setPostCollapsed(collapsed) {
  const panel = $('postPanel');
  if (!panel) return;
  panel.classList.toggle('collapsed', collapsed);
  $('postToggle')?.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
  try { sessionStorage.setItem('ativavid-post-open', collapsed ? '0' : '1'); } catch { /* ignore */ }
}
try {
  setPostCollapsed(sessionStorage.getItem('ativavid-post-open') === '0');
} catch {
  setPostCollapsed(false);
}
$('postToggle')?.addEventListener('click', () => {
  const panel = $('postPanel');
  if (!panel) return;
  setPostCollapsed(!panel.classList.contains('collapsed'));
});
function setSaiuCollapsed(fechado) {
  const panel = $('saiuPanel');
  if (!panel) return;
  panel.classList.toggle('collapsed', fechado);
  $('saiuToggle')?.setAttribute('aria-expanded', fechado ? 'false' : 'true');
  try {
    sessionStorage.setItem('ativavid-saiu-open', fechado ? '0' : '1');
  } catch { /* ignore */ }
}
// Padrao FECHADO: so abre se o usuario tiver aberto nesta sessao.
try {
  setSaiuCollapsed(sessionStorage.getItem('ativavid-saiu-open') !== '1');
} catch {
  setSaiuCollapsed(true);
}
$('saiuToggle')?.addEventListener('click', () => {
  const panel = $('saiuPanel');
  if (!panel) return;
  setSaiuCollapsed(!panel.classList.contains('collapsed'));
});

/* ---------------------------------------------------------------------
 * O LACO — selecionar varios de uma vez.
 *
 * Com a ferramenta ligada, arrastar no fundo da linha do tempo desenha um
 * retangulo e marca tudo que ele encostar. A selecao e das TRES especies
 * ao mesmo tempo (take, legenda e bloco posto na mao), porque e assim que
 * o usuario ve a linha: uma coisa so.
 * ------------------------------------------------------------------ */
function trocarFerramenta(qual) {
  S.ferramenta = qual === 'laco' ? 'laco' : 'agulha';
  const b = $('btnLaco');
  if (b) {
    b.classList.toggle('ativo', S.ferramenta === 'laco');
    b.setAttribute('aria-pressed', S.ferramenta === 'laco' ? 'true' : 'false');
  }
  panel.classList.toggle('modo-laco', S.ferramenta === 'laco');
  if (S.ferramenta === 'agulha') limparSelecaoMultipla(false);
  toast(S.ferramenta === 'laco'
    ? 'Seleção: arraste um retângulo na linha do tempo · Delete apaga'
    : 'Agulha: clique para posicionar', 2400);
  renderAll();
}

function temSelecaoMultipla() {
  return S.takeSel.length + S.capSel.length + S.blocosSel.length > 0;
}

function limparSelecaoMultipla(repintar = true) {
  S.takeSel = [];
  S.blocosSel = [];
  S.capSel = [];
  S.capSelAncora = -1;
  if (repintar) renderAll();
}

/* Marca tudo que o retangulo encostar. O teste e por INTERSECAO e nao por
 * conter inteiro: num zoom fechado um take ocupa mais que a tela, e exigir
 * envolve-lo inteiro tornaria o laco inutil justamente onde ele mais serve. */
function marcarPeloRetangulo(r) {
  const bate = (el) => {
    const b = el.getBoundingClientRect();
    return !(b.right < r.left || b.left > r.right
             || b.bottom < r.top || b.top > r.bottom);
  };
  S.takeSel = [];
  S.capSel = [];
  S.blocosSel = [];
  for (const el of laneVideo.querySelectorAll('.clip')) {
    const i = +el.dataset.i;
    if (Number.isInteger(i) && !S.draft[i]?.removed && bate(el)) S.takeSel.push(i);
  }
  for (const el of panel.querySelectorAll('.chip.caption')) {
    const i = +el.dataset.ci;
    if (Number.isInteger(i) && bate(el)) S.capSel.push(i);
  }
  for (const el of panel.querySelectorAll('.chip.insert')) {
    const i = +el.dataset.i;
    if (Number.isInteger(i) && S.insertsDraft[i]?.isNew && bate(el)) S.blocosSel.push(i);
  }
  S.selected = -1;
  S.blocoSel = -1;
}

function contarSelecao() {
  const p = [];
  if (S.takeSel.length) p.push(`${S.takeSel.length} take${S.takeSel.length > 1 ? 's' : ''}`);
  if (S.capSel.length) p.push(`${S.capSel.length} legenda${S.capSel.length > 1 ? 's' : ''}`);
  if (S.blocosSel.length) p.push(`${S.blocosSel.length} bloco${S.blocosSel.length > 1 ? 's' : ''}`);
  return p.join(' · ');
}

/* Apaga TUDO que esta marcado, das tres especies, num historico so — o
 * Ctrl+Z tem de desfazer o gesto inteiro, nao um terco dele. */
function apagarSelecaoMultipla() {
  if (!temSelecaoMultipla()) return;
  const quanto = contarSelecao();
  pushHistory();
  for (const i of S.takeSel) if (S.draft[i]) S.draft[i].removed = true;
  // de tras para a frente: apagar por indice muda os indices seguintes
  for (const i of [...S.blocosSel].sort((a, b) => b - a)) {
    const c = S.insertsDraft[i];
    if (c && c.isNew) S.insertsDraft.splice(i, 1);
  }
  if (S.capSel.length) apagarLegendas(S.capSel, true);
  limparSelecaoMultipla(false);
  renderAll();
  refreshHeader();
  desenharMidiaNoPreview();
  persistEdl();
  scheduleAutosave();
  toast(`Apagado: ${quanto}`, 2600);
}

/* Move no TEMPO o que tem tempo PROPRIO: imagem, video, som e emoji postos
 * na mao. As outras duas especies nao se movem, e por motivos diferentes:
 *
 *   take     o corte e uma SEQUENCIA — um take nao flutua sem empurrar os
 *            outros, e arrastar assim daria um resultado que o render nao
 *            respeita;
 *   legenda  o tempo dela e o da FALA. Deslocar a legenda no tempo e
 *            dessincroniza-la da boca de quem fala — o que se corrige numa
 *            legenda e o texto, e isso ja tem editor proprio.
 */
function moverSelecaoNoTempo(dt) {
  const layout = draftLayout();
  const ult = layout[layout.length - 1];
  const fim = ult ? ult.out + ult.dur : 0;
  for (const i of S.blocosSel) {
    const c = S.insertsDraft[i];
    if (!c) continue;
    const dur = c.end - c.start;
    c.start = Math.max(0, Math.min(Math.max(0, fim - dur), c.start + dt));
    c.end = c.start + dur;
  }
}

function closeHeadMore() {
  $('headMoreMenu')?.classList.add('hidden');
  $('btnHeadMore')?.setAttribute('aria-expanded', 'false');
}
function posicionarHeadMore() {
  const menu = $('headMoreMenu');
  const btn = $('btnHeadMore');
  if (!menu || !btn || menu.classList.contains('hidden')) return;
  const r = btn.getBoundingClientRect();
  const larg = menu.offsetWidth || 196;
  // Alinhado a direita do botao, sem sair da janela.
  const left = Math.max(8, Math.min(r.right - larg, window.innerWidth - larg - 8));
  menu.style.left = `${Math.round(left)}px`;
  menu.style.top = `${Math.round(r.bottom + 6)}px`;
}

$('btnHeadMore')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const menu = $('headMoreMenu');
  if (!menu) return;
  // Sai do cabecalho na PRIMEIRA abertura: la dentro ele e recortado pelo
  // `overflow: hidden`, e o `backdrop-filter` do .glass faria o recorte valer
  // ate para `position: fixed`.
  if (menu.parentElement !== document.body) document.body.appendChild(menu);
  const open = menu.classList.contains('hidden');
  menu.classList.toggle('hidden', !open);
  $('btnHeadMore').setAttribute('aria-expanded', open ? 'true' : 'false');
  if (open) posicionarHeadMore();
});
window.addEventListener('resize', posicionarHeadMore);
document.addEventListener('click', (e) => {
  // `#headMore` nao envolve mais o menu (ele foi para o <body>), entao o
  // proprio menu tem de ser reconhecido aqui — senao clicar num item o
  // fecharia antes do handler do item rodar.
  if (e.target.closest?.('#headMore, #headMoreMenu')) return;
  closeHeadMore();
});
// header — light/dark theme (padrão global: localStorage ativavid-theme)
function applyTheme(next) {
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('ativavid-theme', next); } catch { /* ignore */ }
  const btn = $('btnTheme');
  if (btn) {
    btn.title = next === 'light' ? 'Mudar para tema escuro' : 'Mudar para tema claro';
  }
}
const themeBtn = $('btnTheme');
if (themeBtn) {
  themeBtn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    applyTheme(next);
  });
}
window.addEventListener('storage', (e) => {
  if (e.key !== 'ativavid-theme' || !e.newValue) return;
  document.documentElement.setAttribute('data-theme', e.newValue);
});


// ---------- desktop: trecho marcado → aplicar + fila ----------
// Elementos que a nota pode estar mandando mexer. Se ela NOMEIA um deles, e
// instrucao sobre o take, nao ordem de apagar o take: "tira o zoom daqui" quer
// dizer tira o zoom, e a nota antiga apagava o trecho inteiro.
const NOTA_ELEMENTOS =
  /\b(zoom|legenda|legendas|texto|manchete|headline|titulo|título|musica|música|trilha|som|audio|áudio|efeito|efeitos|capa|thumb|cor|filtro|emoji|logo|marca|insert|imagem|foto)\b/;

// Ordem EXPLICITA de remover, com borda de palavra. A versao antiga casava por
// substring: `fora` pegava "fora de foco", `cort` pegava "o corte ficou
// estranho", `tir[ae]` pegava "tira o zoom". Qualquer um desses apagava o
// trecho marcado E jogava fora o texto que o usuario tinha escrito.
const NOTA_REMOVER =
  /\b(corta|corte|cortar|tira|tire|tirar|remove|remova|remover|apaga|apague|apagar|exclui|exclua|excluir|deleta|delete|deletar|descarta|descarte|descartar)\b|\b(joga|jogue|joga)\s+(isso\s+)?fora\b|\bfora\s+daqui\b|\bsem\s+isso\b|\bnao\s+usa\b|\bnão\s+usa\b/;

// `corte` com artigo antes e SUBSTANTIVO, nao ordem: "aqui o corte ficou
// estranho" e comentario, "corte isso" e ordem. Tira essas ocorrencias antes
// de procurar o verbo.
const NOTA_CORTE_SUBSTANTIVO =
  /\b(?:o|a|os|as|um|uma|esse|essa|este|esta|do|da|no|na|nesse|neste)\s+cortes?\b/g;

function noteLooksLikeRemove(text) {
  const s = String(text || '').toLowerCase().replace(NOTA_CORTE_SUBSTANTIVO, ' ');
  if (!NOTA_REMOVER.test(s)) return false;
  // "tira o zoom", "corta a musica": e sobre o que esta DENTRO do trecho.
  if (NOTA_ELEMENTOS.test(s)) return false;
  return true;
}

function removeDraftTimeRange(tStart, tEnd) {
  if (!(tEnd > tStart + 0.04)) return false;
  // A janela marcada esta em tempo de SAIDA, e cada remocao ENCURTA a saida:
  // tudo que vinha depois desliza para dentro da janela. O laco antigo
  // relia o layout a cada volta com `tStart`/`tEnd` fixos e ia comendo o que
  // escorregava para la, ate 64 vezes.
  //
  // Medido com 10 takes de 6s (60s de video): marcar de 10,0s a 12,0s — dois
  // segundos — removia 50 dos 60, tudo da marca ate o fim, em 25 pedacos.
  //
  // Por isso a janela e traduzida para a FONTE de uma vez, antes de mexer em
  // nada; depois os cortes sao aplicados de TRAS PARA FRENTE, para os indices
  // ja coletados continuarem valendo enquanto o array muda.
  const dl = draftLayout();
  const alvos = [];
  for (let i = 0; i < dl.length; i++) {
    const d = dl[i];
    if (d.removed || d.dur <= 0) continue;
    const clipStart = d.out;
    const clipEnd = d.out + d.dur;
    if (tEnd <= clipStart || tStart >= clipEnd) continue;
    const srcA = draftTimeToSource(i, Math.max(tStart, clipStart));
    const srcB = draftTimeToSource(i, Math.min(tEnd, clipEnd));
    if (srcB - srcA < MIN_SEG) continue;
    alvos.push({ i, srcA, srcB });
  }
  if (!alvos.length) return false;
  pushHistory();
  // Sobra menor que isto vira um flash de frames no final — melhor levar
  // junto na remoção do que manter um take que parece corte errado.
  const PIECE_MIN = 0.35;
  for (let k = alvos.length - 1; k >= 0; k--) {
    const { i, srcA, srcB } = alvos[k];
    const r = S.draft[i];
    const pieces = [];
    if (srcA - r.start >= PIECE_MIN) {
      pieces.push({
        source: r.source, start: r.start, end: srcA, beat: r.beat,
        removed: false, srcIdx: null, orig: { start: r.start, end: r.end },
      });
    }
    pieces.push({
      source: r.source, start: srcA, end: srcB, beat: r.beat,
      removed: true, srcIdx: null, orig: { start: r.start, end: r.end },
    });
    if (r.end - srcB >= PIECE_MIN) {
      pieces.push({
        source: r.source, start: srcB, end: r.end, beat: r.beat,
        removed: false, srcIdx: null, orig: { start: r.start, end: r.end },
      });
    }
    S.draft.splice(i, 1, ...pieces);
  }
  S.selected = -1;
  renderAll();
  refreshHeader();
  return true;
}

async function saveEditsAndReturnToQueue() {
  const payload = { type: 'timeline-edits' };
  const extraSources = S.draft.filter((r) => r.added && r.filePath).map((r) => r.filePath);
  if (extraSources.length) payload.extraSources = extraSources;
  if (edlDirty()) {
    payload.edl = {
      ranges: S.draft.filter((r) => !r.removed).map((r) => ({
        source: r.source, start: +r.start.toFixed(3), end: +r.end.toFixed(3), beat: r.beat,
      })),
      removed: S.draft.filter((r) => r.removed).map((r) => ({
        source: r.source, beat: r.beat, start: r.orig.start, end: r.orig.end,
      })),
      changes: S.draft.filter((r) => !r.removed && (r.start !== r.orig.start || r.end !== r.orig.end)).map((r) => ({
        source: r.source, beat: r.beat,
        from: { start: r.orig.start, end: r.orig.end },
        to: { start: +r.start.toFixed(3), end: +r.end.toFixed(3) },
      })),
    };
  }
  if (insertsDirty()) {
    const limpa = (S.style?.edit || 'limpa') === 'limpa';
    // Em limpa: só a mídia manual sobrevive; o automático some.
    // Manual NUNCA entra em `inserts` — vai inteiro em `manualInserts`.
    const keepInsert = (c) => c.kind === 'insert' && !c.isNew && !c.manual && !limpa;
    payload.editData = {
      inserts: S.insertsDraft.filter(keepInsert).map((c) => ({
        ref: c.ref, start: +c.start.toFixed(3), end: +c.end.toFixed(3),
      })),
      // Estado COMPLETO da mídia manual (4.61): o pipeline SUBSTITUI o que
      // há de manual por esta lista — mover/apagar/reenquadrar um insert
      // já aplicado não duplica nem ressuscita. Apagado = ausente daqui.
      manualInserts: S.insertsDraft
        .filter((c) => c.kind === 'insert' && (c.isNew || c.manual))
        .map((c) => ({
          mid: c.mid || `m${Date.now().toString(36)}${Math.floor(Math.random() * 1e4)}`,
          src: c.src, credit: c.credit || '',
          start: +c.start.toFixed(3), end: +c.end.toFixed(3),
          // onde e de que tamanho, quando o usuario mexeu
          ...(c.x != null ? { x: +c.x } : {}),
          ...(c.y != null ? { y: +c.y } : {}),
          ...(c.size != null ? { size: +c.size } : {}),
          ...(c.w != null ? { w: +c.w } : {}),
          ...(c.h != null ? { h: +c.h } : {}),
          // animacoes e enquadramento escolhidos no preview
          ...(c.entrada ? { entrada: c.entrada } : {}),
          ...(c.saida ? { saida: c.saida } : {}),
          ...(c.fx != null ? { fx: +c.fx } : {}),
          ...(c.fy != null ? { fy: +c.fy } : {}),
          ...(c.zoom != null && +c.zoom > 1.0001 ? { zoom: +c.zoom } : {}),
          ...(c.srcIn != null && +c.srcIn > 0.001 ? { srcIn: +c.srcIn } : {}),
          ...((c.camada | 0) > 0 ? { camada: c.camada | 0 } : {}),
        })),
      // Marca do protocolo de SUBSTITUICAO (4.73): estas listas sao o
      // estado COMPLETO de emoji/som — o pipeline troca, nao soma. Um
      // preview velho em cache nao manda a marca e cai no caminho antigo.
      emojiSfxCompleto: true,
      // Emoji: comeco E duracao (ele fica na tela enquanto o bloco durar).
      emojis: S.insertsDraft.filter((c) => c.kind === 'emoji' && c.char).map((c) => ({
        char: c.char, atSec: +c.start.toFixed(3),
        durSec: +(c.end - c.start).toFixed(3),
        x: +(c.x ?? 0.5), y: +(c.y ?? 0.34), size: +(c.size ?? 0.22),
      })),
      // Efeito posto na mao: so o instante importa (o som toca inteiro).
      sfxManual: S.insertsDraft.filter((c) => c.kind === 'sfx' && c.src).map((c) => ({
        src: c.src, atSec: +c.start.toFixed(3), volume: +(c.volume ?? 0.5),
      })),
      splitInserts: limpa ? [] : S.insertsDraft.filter((c) => c.kind === 'split').map((c) => ({
        ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3),
      })),
      splitVideos: limpa ? [] : S.insertsDraft.filter((c) => c.kind === 'splitvideo').map((c) => ({
        ref: c.ref, label: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3),
      })),
      hook: S.insertsDraft.filter((c) => c.kind === 'hook').map((c) => ({ endSec: +c.end.toFixed(3) }))[0] || null,
      behind: limpa ? [] : S.insertsDraft.filter((c) => c.kind === 'behind').map((c) => ({
        ref: c.ref, start: +c.start.toFixed(3), dur: +(c.end - c.start).toFixed(3),
      })),
      wordAccents: S.insertsDraft.filter((c) => c.kind === 'word').map((c) => ({
        ref: c.ref, text: c.label, start: +c.start.toFixed(3), end: +c.end.toFixed(3),
      })),
    };
  }
  if (S.notes.length) {
    payload.notes = S.notes.map((n) => ({
      start: +n.start.toFixed(3),
      end: +n.end.toFixed(3),
      renderedStart: +draftToRendered(n.start).toFixed(3),
      renderedEnd: +draftToRendered(n.end).toFixed(3),
      phase: S.tab === 2 ? 2 : 1,
      text: n.text,
    }));
  }
  const capFixes = Object.values(S.captionFixes);
  const capApagar = (S.capApagadas || []).map((f) => ({
    from: f.from, to: '', delete: true,
    renderedStart: +f.start.toFixed(3),
    renderedEnd: +f.end.toFixed(3),
  }));
  if (capFixes.length || capApagar.length) {
    payload.captionFixes = capFixes.map((f) => ({
      from: f.from, to: f.to,
      renderedStart: +f.start.toFixed(3),
      renderedEnd: +f.end.toFixed(3),
    })).concat(capApagar);
  }
  // O que foi mexido na aba ESTILO vai JUNTO: sem isto, mudar o estilo e
  // aplicar pela Edição levava só a timeline — headline e card final saíam
  // velhos (caso real de 02/09, nos filhos do Multiplicador).
  const tinhaEstilo = !!S.styleTocado;
  const estiloSalvo = tinhaEstilo ? await salvarEstiloDoProjeto() : false;
  if (tinhaEstilo && !estiloSalvo) {
    toast('Não consegui salvar o estilo — tente de novo', 4000);
    return false;
  }
  const algoNaTimeline = !!(payload.edl || payload.editData || payload.notes
    || payload.captionFixes || payload.extraSources);
  if (!algoNaTimeline && !estiloSalvo) {
    toast('Nada para salvar', 2000);
    return false;
  }
  let data = {};
  if (algoNaTimeline) {
    const res = await fetch(`${BASE}/api/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      toast('Erro ao salvar — o servidor está de pé?', 4000);
      return false;
    }
  }
  // O servidor agora diz se a correcao de legenda pegou. Antes ele respondia
  // ok sempre e esta linha jogava fora o pedido do usuario mesmo quando nada
  // tinha sido trocado: a palavra continuava errada e a tela dizia que nao.
  const capFalhou = !!(data.captionFix && data.captionFix.ok === false);
  S.savedPending = true;
  S.notes = [];
  if (!capFalhou) { S.captionFixes = {}; S.capApagadas = []; }
  S.pendingIn = null;
  S.draft.forEach((r) => {
    r.orig = { start: r.start, end: r.end };
    r.added = false;
    if (r.removed) r.hardRemoved = true;
  });
  S.draft = S.draft.filter((r) => !r.removed);
  S.insertsDraft.forEach((c) => {
    c.orig = { start: c.start, end: c.end };
    if (c.manual) c.origGeo = geoDoInsert(c);
  });
  S.manualApagado = false;
  S.history = [];
  S.future = [];
  refreshUndoRedoButtons();
  renderAll();
  refreshHeader();

  const captionOnly = !!(payload.captionFixes && !payload.edl && !payload.editData && !payload.extraSources) && !estiloSalvo;
  // Refazer o vídeo do zero (re-analisar, re-transcrever, re-cortar) só é
  // necessário quando entra material NOVO ou muda algo que a IA precisa
  // reler. Ajuste de corte, legenda e headline vai pelo Aplicar rápido, que
  // reaproveita o que já está pronto: minutos em vez de uma hora.
  // estilo mexido = Fase 2 refeita por inteiro (o quick apply não veste
  // estilo novo)
  const needsFullRerun = !!(payload.extraSources || payload.editData || estiloSalvo);
  if (BASE && BASE.startsWith('/p/') && !captionOnly && !needsFullRerun) {
    if (payload.edl) {
      const ok = await persistCorrection({ op: 'set_edl', ranges: payload.edl.ranges });
      if (!ok || ok.ok === false) {
        toast('Não consegui salvar o corte — nada foi alterado', 4000);
        return false;
      }
    }
    const applied = await persistCorrection({ op: 'apply' });
    if (applied && applied.ok !== false) {
      toast('✓ Atualizando o vídeo com suas mudanças', 2800);
      setTimeout(() => { location.href = '/?view=fila'; }, 500);
      return true;
    }
    // Se o atalho recusar, cai no reprocesso completo (nunca fica sem saída)
  }
  if (BASE && BASE.startsWith('/p/') && !captionOnly) {
    const folder = projectFolder() || decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
    // `fetch` NAO levanta em 4xx/5xx, e este endpoint recusa em tres casos
    // reais: 403 (licenca sem direito), 400 (pasta invalida) e 404 (projeto
    // fora da fila). Antes os tres viravam "Enviado a fila" e o usuario ia
    // esperar na Fila um video que nunca comecou. A chamada irma da aba
    // Estilo (mais acima, no mesmo arquivo) ja tratava assim.
    try {
      const rq = await fetch('/api/jobs/requeue-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder, extraSources }),
      });
      if (!rq.ok) {
        const body = await rq.json().catch(() => ({}));
        toast(body.error || 'Não deu para enviar à fila — tente de novo em Projetos', 5000);
        return false;
      }
    } catch {
      toast('Não deu para enviar à fila — verifique se o ATIVAVID está aberto', 5000);
      return false;
    }
    toast('✓ Enviado à fila de edição', 2800);
    setTimeout(() => { location.href = '/?view=fila'; }, 500);
    return true;
  }
  if (captionOnly) {
    if (capFalhou) {
      toast(data.captionFix.error || 'Nao consegui corrigir essa legenda', 4200);
      return false;
    }
    try {
      const r = await fetch(`${BASE}/media/${S.state.captions || 'remotion/public/captions.json'}?v=${Date.now()}`);
      if (r.ok) {
        const caps = await r.json();
        if (Array.isArray(caps) && caps.length) S.captions = groupCaptions(caps);
      }
    } catch { /* chips já mostram o fix */ }
    renderAll();
    toast('✓ Legenda corrigida', 2800);
    return true;
  }
  toast('✓ Ajustes salvos neste projeto', 4000);
  return true;
}

// ---------- correction markers: button, chips, editor ----------
$('markIcon').innerHTML = ICON.flag;
$('btnLaco').innerHTML = ICON.laco;
$('btnLaco').addEventListener('click', () => trocarFerramenta(
  S.ferramenta === 'laco' ? 'agulha' : 'laco'));
$('btnMark').addEventListener('click', toggleMark);
$('laneNotes').addEventListener('click', (e) => {
  const chip = e.target.closest('.note-chip');
  if (chip) openNoteEditor(chip.dataset.id, false);
});
$('noteOk').addEventListener('click', async () => {
  const n = S.notes.find((x) => x.id === S.editingNote);
  if (!n) return;
  n.text = $('noteText').value.trim();
  if (!n.text) { toast('Escreva o ajuste desejado', 2000); return; }
  const start = n.start;
  const end = n.end;
  const text = n.text;
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  // Pedidos de corte/remoção: aplica já na timeline (desktop 1-clique)
  if (noteLooksLikeRemove(text)) {
    // So descarta a nota se o corte aconteceu de verdade. Se a marca nao
    // pegou nenhum take (fora do video, ou menor que o minimo), a nota
    // sumia levando junto o texto que o usuario escreveu.
    if (removeDraftTimeRange(start, end)) {
      S.notes = S.notes.filter((x) => x.id !== n.id);
    } else {
      toast('Não achei trecho para remover aí — a nota foi mantida', 3500);
    }
  }
  renderNotes();
  refreshHeader();
  // Confirmar = salvar + voltar à fila (não só rascunho local)
  await saveEditsAndReturnToQueue();
});
$('noteBiblioteca')?.addEventListener('click', () => {
  guardarTrechoNaBiblioteca().catch(() => {});
});

$('noteDelete').addEventListener('click', () => {
  S.notes = S.notes.filter((x) => x.id !== S.editingNote);
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  renderNotes();
  refreshHeader();
});
$('noteClose').addEventListener('click', closeNoteEditor);

// ---------- help modal ----------
function toggleHelp(open) {
  if (open && (S.tab === 'style' || HUB_EMBED || HOUSE_STYLE)) return;
  $('helpModal').classList.toggle('hidden', !open);
  $('helpBackdrop').classList.toggle('hidden', !open);
}

$('helpClose').addEventListener('click', () => toggleHelp(false));
$('helpBackdrop').addEventListener('click', () => toggleHelp(false));
$('noteText').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeNoteEditor(); }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('noteOk').click(); }
});
$('btnFit').innerHTML = ICON.fit;
$('btnFit').addEventListener('click', () => { fitZoom(); renderAll(); });
if ($('btnZoomOut')) $('btnZoomOut').addEventListener('click', () => bumpZoom(1 / 1.4));
$('btnZoom100').addEventListener('click', () => setZoom100());
$('btnZoomIn').addEventListener('click', () => bumpZoom(1.4));
/* Rolar redesenha a onda e a regua — e `drawWave` custa 7,8 ms medidos.
 * Uma rolagem so dispara varios eventos `scroll`, e cada um agendava o seu
 * proprio quadro: o mesmo desenho refeito 3-4 vezes seguidas. Um agendado
 * por vez basta; o ultimo estado e o que vale. */
let redesenhoPendente = false;
panel.addEventListener('scroll', () => {
  if (redesenhoPendente) return;
  redesenhoPendente = true;
  requestAnimationFrame(() => {
    redesenhoPendente = false;
    drawRuler(); drawWave(); positionNeedle();
  });
});
// renderSetup too: the caption demos bake their scale from the box width, so a
// resize (or the short-pane media query kicking in) has to rebuild them
window.addEventListener('resize', () => { fitZoom(); renderAll(); renderSetup(); });

// tabs
function goToTab(tab) {
  if (tab.disabled) return;
  if (HOUSE_STYLE && tab.dataset.tab !== 'style') return;
  document.querySelectorAll('.tab').forEach((t) => {
    const on = t === tab;
    t.classList.toggle('active', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  S.tab = tab.dataset.tab === 'style' ? 'style' : +tab.dataset.tab;
  S.selected = -1;
  // O laco marca coisas da Edicao. Levar a marca para outra aba deixaria o
  // Delete apagando take de onde nao se ve o take — o ramo do laco nao
  // pergunta a aba, de proposito (ele apaga as tres especies juntas).
  limparSelecaoMultipla(false);
  const path = HOUSE_STYLE ? '/estilo-padrao' : (BASE + TAB_TO_PATH[S.tab]);
  const search = HUB_EMBED ? '?embed=1' : '';
  // a real nav here (not applyState's replaceState) — a click is a place the
  // user meant to go, so back/forward should be able to return to it
  if (location.pathname !== path || (HUB_EMBED && location.search.indexOf('embed=1') < 0)) {
    history.pushState(null, '', path + search);
  }
  // Ao ENTRAR na Visual pergunta de novo pela copia leve: na primeira
  // abertura ela ainda nao existe (o servidor manda fazer ao ser
  // perguntado), e sem perguntar de novo o editor tocaria o arquivo cheio
  // pelo resto da sessao mesmo com a copia ja pronta.
  if (S.tab === 2 && !S.hasFinalProxy && !S.finalProxyFailed) {
    esperarCopiaDoFinal();
  }
  updateVideoSrc(); // Fase 2 plays the Phase-2 render when available
  renderAll();
  renderSetup();
  loadPostCaption();
  renderSaiuPanel();
}
document.querySelectorAll('.tab').forEach((tab) => tab.addEventListener('click', () => goToTab(tab)));
// back/forward, or a link straight to someone's /estilo
window.addEventListener('popstate', () => {
  const wantTab = tabFromPath();
  const el = document.querySelector(`[data-tab="${wantTab}"]`);
  if (el && !el.disabled) goToTab(el);
});

// ---------- save / discard ----------
$('btnSave').addEventListener('click', async () => {
  await saveEditsAndReturnToQueue();
});

if ($('btnApply')) {
  $('btnApply').addEventListener('click', async () => {
    if (S.applying || pendingList().length === 0) return;
    // O que esta so na sessao (video/imagem/som posto na mao, corte, nota,
    // conserto de legenda) vai pelo MESMO caminho do salvar — que ja grava,
    // decide entre Aplicar rapido e fila, e leva para a Fila. Um clique faz
    // tudo. Antes, quem adicionava um video via o Aplicar apagado e tinha
    // de achar o salvar dentro do "Mais…".
    const temSessao = edlDirty() || insertsDirty() || S.styleTocado
      || S.notes.length
      || Object.keys(S.captionFixes).length || (S.capApagadas || []).length;
    if (temSessao) {
      await saveEditsAndReturnToQueue();
      return;
    }
    S.applying = true;
    document.body.classList.add('applying-corrections');
    refreshHeader();
    const data = await persistCorrection({ op: 'apply' });
    if (!data || data.ok === false) {
      S.applying = false;
      document.body.classList.remove('applying-corrections');
      toast(
        (data && (data.message || data.error)) ||
        'Não foi possível aplicar as alterações. Seu vídeo anterior foi mantido.',
        5000
      );
      refreshHeader();
      return;
    }
    if (data.noop) {
      S.applying = false;
      document.body.classList.remove('applying-corrections');
      refreshHeader();
      toast('Nada para aplicar', 2000);
      return;
    }
    applyApplyStatus(data.applyStatus || {
      running: !!data.started,
      ok: data.ok === true && !data.started ? true : null,
      message: data.message || 'Aplicando edição...',
      at: data.started ? '' : 'local',
    }, data.applyTask);
  });
}

/* O bloco GANCHO da linha do tempo abre o mesmo editor da manchete que o
 * clique sobre o video. Ele ja mostrava o texto e o intervalo (0:00 ->
 * 0:04) e nao fazia nada — o usuario tinha de achar a manchete no quadro
 * certo do video para poder troca-la. */
panel.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip.insert');
  if (!chip || chip.dataset.i == null) return;
  if (chip.dataset.acabouDeArrastar === '1') {
    chip.dataset.acabouDeArrastar = '0';
    return;
  }
  const c = S.insertsDraft[+chip.dataset.i];
  if (!c || c.kind !== 'hook') return;
  e.stopPropagation();
  editarManchetePelaLinhaDoTempo();
});

/* A janela para quem esta na linha do tempo. O editor de dentro do quadro
 * (`beginHeadlineEdit`) continua valendo para quem clica na manchete SOBRE
 * o video — la se ajusta letra a letra, com o resultado a vista. */
async function editarManchetePelaLinhaDoTempo() {
  if (S.applying) {
    toast('Estou aplicando as alterações. Espere terminar para editar.', 2400);
    return;
  }
  const atual = headlineLines().join(' ');
  const novo = await pedirTexto('Texto da manchete', atual, 'Salvar');
  if (novo == null) return;
  const limpo = String(novo).trim();
  if (!limpo || limpo === atual) return;
  // UMA linha: os dois motores reequilibram em duas pela largura medida.
  const r = await persistHeadline([limpo]);
  if (r && r.ok === false) {
    toast(r.erro || r.error || 'Não consegui salvar a manchete', 3600);
    return;
  }
  if (S.editData && S.editData.hook) {
    S.editData.hook.lines = [limpo];
    S.editData.hook.text = limpo;
  }
  buildInsertsDraft();
  renderAll();
  refreshHeader();
  toast('Manchete trocada', 2000);
}

if ($('hlOverlay')) {
  $('hlOverlay').addEventListener('click', (e) => {
    e.stopPropagation();
    // Um arrasto termina com click; sem esta guarda, soltar a headline
    // abriria o editor de texto por cima do que acabou de ser movido.
    const line = e.target.closest('.hl-overlay-line');
    if (line && line.dataset.acabouDeArrastar === '1') {
      line.dataset.acabouDeArrastar = '0';
      return;
    }
    beginHeadlineEdit(e);
  });
}
if ($('capOverlay')) {
  $('capOverlay').addEventListener('click', (e) => {
    e.stopPropagation();
    // Um arrasto termina com click: sem esta guarda, soltar a legenda abriria
    // o editor de texto por cima do que acabou de ser movido.
    const l = e.target.closest('.cap-overlay-line');
    if (l && l.dataset.acabouDeArrastar === '1') {
      l.dataset.acabouDeArrastar = '0';
      return;
    }
    const i = currentCaptionIndex();
    if (i >= 0) openCaptionEditor(i, l || e.target);
  });
}
if ($('hlChip')) {
  $('hlChip').addEventListener('click', (e) => {
    e.stopPropagation();
    beginHeadlineEdit();
  });
}
if ($('capNow')) {
  $('capNow').addEventListener('click', (e) => {
    e.stopPropagation();
    const i = currentCaptionIndex();
    if (i >= 0) openCaptionEditor(i, e.currentTarget);
    else escreverLegendaAqui();
  });
}

$('btnDiscard').addEventListener('click', async () => {
  const data = await persistCorrection({ op: 'discard' });
  if (data && data.ok && data.restored) {
    toast('Correções desfeitas', 2000);
    location.reload();
    return;
  }
  S.draft = S.rendered.map((r, srcIdx) => ({ ...r, removed: false, srcIdx, orig: { start: r.start, end: r.end } }));
  buildInsertsDraft();
  S.notes = [];
  S.captionFixes = {};
  S.capApagadas = [];
  S.capSel = [];
  closeCaptionEditor();
  S.pendingIn = null;
  S.editingNote = null;
  $('noteEditor').classList.add('hidden');
  S.selected = -1;
  S.history = []; S.future = []; refreshUndoRedoButtons();
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
/* O aviso mora no topo, mas AQUI o cabecalho e alto (barra de 72px + a
 * faixa das abas Edicao/Estilo/Visual): medido em 27/08, o toast a 52px
 * cobria justamente as abas. Ele desce para logo abaixo do cabecalho de
 * verdade — e como o cabecalho quebra em telas estreitas, a conta e feita
 * na hora de mostrar, nao fixada no CSS. */
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  const cab = document.querySelector('header.glass');
  if (cab) {
    const base = Math.round(cab.getBoundingClientRect().bottom) + 12;
    if (base > 0) t.style.top = base + 'px';
  }
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}


// ---------- automação / safe zone / IA edit / score ----------
function refreshAutoControls() {
  const st = S.style || {};
  const map = [
    ['autoRhythm', 'rhythm', 'dinamico'],
    ['autoTransicao', 'transicao', 'flash'],
    ['autoIntensity', 'intensity', 'medio'],
    ['autoColorGrade', 'colorGrade', 'marca'],
    ['autoSpeech', 'speechClean', 'medio'],
    ['autoGoal', 'videoGoal', 'reels'],
    ['autoBroll', 'brollMode', 'quando_necessario'],
    ['autoExport', 'exportPreset', 'reels'],
    ['autoCaptionChunk', 'captionChunk', 'frase_curta'],
    ['autoCapPosition', 'captionPosition', 'baixo'],
    ['autoCapSize', 'captionSize', 'm'],
    ['autoCapFont', 'captionFont', ''],
    ['autoHlFont', 'headlineFont', ''],
    ['autoEmphWords', 'emphasisWords', ''],
    ['autoPostTags', 'postHashtags', ''],
    ['autoPostSeo', 'postSeo', ''],
    ['autoPostRodape', 'postRodape', ''],
    ['autoHlDuration', 'headlineDuration', 'curta'],
    ['autoHlSeconds', 'headlineSeconds', ''],
    ['autoHlAnim', 'headlineAnimation', 'padrao'],
    ['autoHlPos', 'headlinePos', 'padrao'],
    ['autoLegendaApos', 'legendaAposHeadline', ''],
    ['autoContentType', 'contentType', 'informational'],
  ];
  for (const [id, key, def] of map) {
    const el = $(id);
    if (!el) continue;
    let v = st[key] || (SHARED_DEFAULT_STYLE && SHARED_DEFAULT_STYLE[key]) || def;
    if (key === 'videoGoal' && v === 'tutorial') v = 'educativo';
    if (key === 'contentType') v = S.contentType || v;
    el.value = v;
  }
}

/* ---------- galeria de modelos: combinações completas com nome ------------
 * Cada modelo é só dados sobre o catálogo existente — aplicar = assinar os
 * campos no estilo atual (mesma semântica de clicar card a card) e o usuário
 * ajusta/salva como sempre. Nada aqui cria caminho novo de render. */
const _tplElems = (o) => ({ tracking: false, zoomAuto: true, zoomCuts: true, flashCut: true, musicAI: true, endCard: false, ...(o || {}) });
const STYLE_TEMPLATES = [
  { id: 'abertura_cheia', name: 'Abertura em cheio', desc: 'Headline no centro nos 4s iniciais; legenda entra depois',
    style: { edit: 'limpa', headline: 'realce', captions: 'stacked', accent: null, emphasisAccent: null, captionAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'viral', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', headlineDuration: 'curta', headlinePos: 'centro', legendaAposHeadline: '1', elements: _tplElems() } },
  { id: 'venda_agressiva', name: 'Venda agressiva', desc: 'Impacto na palavra, corte rápido, urgência',
    style: { edit: 'limpa', headline: 'realce', captions: 'impacto', accent: '#e30004', emphasisAccent: '#ffd400', captionAccent: null, rhythm: 'rapido', intensity: 'forte', speechClean: 'agressivo', contentType: 'sales', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'g', elements: _tplElems() } },
  { id: 'educativo_clean', name: 'Educativo clean', desc: 'Pílula de contexto, legenda limpa, ritmo calmo',
    style: { edit: 'limpa', headline: 'pilula', captions: 'simples', accent: '#33e0a3', captionAccent: '#ffffff', emphasisAccent: null, rhythm: 'calmo', intensity: 'sutil', speechClean: 'leve', contentType: 'educational', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'humor_caotico', name: 'Humor caótico', desc: 'Carimbo, legenda empilhada, energia total',
    style: { edit: 'limpa', headline: 'carimbo', captions: 'stacked', accent: '#ff5200', emphasisAccent: '#ffd400', circleAccent: '#39E508', rhythm: 'rapido', intensity: 'forte', speechClean: 'medio', contentType: 'humor', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'noticia_urgente', name: 'Notícia urgente', desc: 'Manchete na base, legenda em bloco',
    style: { edit: 'limpa', headline: 'manchete', captions: 'bloco', accent: '#e30004', captionAccent: '#ffffff', emphasisAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'informational', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'sticker_capcut', name: 'Sticker CapCut', desc: 'Sombra dura + recorte com contorno grosso',
    style: { edit: 'limpa', headline: 'sombra', captions: 'recorte', accent: '#ffd400', captionAccent: '#ffffff', emphasisAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'humor', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'review_direto', name: 'Review direto', desc: 'Sublinhado, karaokê, tom de análise',
    style: { edit: 'limpa', headline: 'sublinhado', captions: 'karaoke', accent: '#4da3ff', captionAccent: '#ffffff', emphasisAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'review', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'minimalista', name: 'Minimalista', desc: 'Sem headline, legenda clássica, zero efeitos',
    style: { edit: 'limpa', headline: 'nenhuma', captions: 'classica', accent: null, captionAccent: '#f4f1e9', emphasisAccent: null, rhythm: 'calmo', intensity: 'sutil', speechClean: 'leve', contentType: 'institutional', captionChunk: 'frase_longa', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems({ zoomAuto: false, zoomCuts: false, flashCut: false, musicAI: false }) } },
  { id: 'institucional', name: 'Institucional', desc: 'Cartão sóbrio, legenda serifada, calmo',
    style: { edit: 'limpa', headline: 'card', captions: 'serifada', accent: null, captionAccent: '#f4f1e9', emphasisAccent: null, rhythm: 'calmo', intensity: 'sutil', speechClean: 'leve', contentType: 'institutional', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems({ flashCut: false }) } },
  { id: 'impacto_total', name: 'Impacto total', desc: 'Contorno + caixa na palavra, legenda grande',
    style: { edit: 'limpa', headline: 'outline', captions: 'impacto', accent: null, emphasisAccent: '#e30004', captionAccent: null, rhythm: 'rapido', intensity: 'forte', speechClean: 'agressivo', contentType: 'sales', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'g', elements: _tplElems() } },
  { id: 'depoimento', name: 'Depoimento', desc: 'Misto discreto, palavras dispersas, suave',
    style: { edit: 'limpa', headline: 'misto', captions: 'scatter', accent: '#ff5200', emphasisAccent: '#ff5200', captionAccent: null, rhythm: 'calmo', intensity: 'sutil', speechClean: 'leve', contentType: 'institutional', videoGoal: 'depoimento', captionChunk: 'frase_curta', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems({ flashCut: false }) } },
  { id: 'tutorial_pratico', name: 'Tutorial prático', desc: 'Pílula no topo, karaokê palavra a palavra',
    style: { edit: 'limpa', headline: 'pilula', captions: 'karaoke', accent: '#7c5cff', captionAccent: '#ffffff', emphasisAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'educational', captionChunk: 'palavra', captionPosition: 'baixo', captionSize: 'm', elements: _tplElems() } },
  { id: 'clipe_podcast', name: 'Clipe de podcast', desc: 'Cartão no gancho, karaokê amarelo clássico',
    style: { edit: 'limpa', headline: 'card', captions: 'karaoke', accent: null, captionAccent: '#ffd400', emphasisAccent: null, rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio', contentType: 'informational', captionChunk: 'frase_curta', captionPosition: 'centro', captionSize: 'm', elements: _tplElems({ zoomCuts: false }) } },
];

function applyStyleTemplate(t) {
  if (!S.style) S.style = defaultStyle();
  Object.assign(S.style, JSON.parse(JSON.stringify(t.style)));
  if (t.style.contentType) {
    S.contentType = t.style.contentType;
    persistIntent();
  }
  refreshAutoControls();
  renderSetup();
  toast(`Modelo "${t.name}" aplicado — ajuste o que quiser e salve`);
}

function renderStyleTemplates() {
  const host = $('styleTemplates');
  if (!host) return;
  if (!host.dataset.built) {
    host.dataset.built = '1';
    for (const t of STYLE_TEMPLATES) {
      const card = el('button', 'tpl-card', host);
      card.type = 'button';
      const dots = el('span', 'tpl-dots', card);
      for (const c of [t.style.accent, t.style.emphasisAccent, t.style.captionAccent]) {
        if (!c) continue;
        const d = el('span', 'tpl-dot', dots);
        d.style.background = c;
      }
      el('span', 'tpl-name', card).textContent = t.name;
      el('span', 'tpl-desc', card).textContent = t.desc;
      card.addEventListener('click', () => applyStyleTemplate(t));
    }
  }
}

const RHYTHM_PRESETS = {
  natural: { rhythm: 'calmo', intensity: 'sutil', speechClean: 'leve' },
  dinamico: { rhythm: 'dinamico', intensity: 'medio', speechClean: 'medio' },
  intenso: { rhythm: 'rapido', intensity: 'forte', speechClean: 'agressivo' },
  // Um corte por frase, zero pausas — o ritmo de retenção máxima
  cirurgico: { rhythm: 'cirurgico', intensity: 'forte', speechClean: 'agressivo',
    elements: { zoomCuts: true, flashCut: true } },
  // Storytelling: blocos longos, sem flash/zoom quebrando a imersão
  narrativa: { rhythm: 'narrativa', intensity: 'sutil', speechClean: 'leve',
    elements: { flashCut: false, zoomCuts: false } },
  // O mais agressivo do catálogo — cenas ≤2s, tudo ligado
  turbo: { rhythm: 'muito_rapido', intensity: 'forte', speechClean: 'agressivo',
    elements: { zoomCuts: true, flashCut: true, zoomAuto: true } },
  // Ritmo de anúncio: comercial no corte, forte nos efeitos
  comercial: { rhythm: 'dinamico', intensity: 'forte', speechClean: 'medio',
    elements: { flashCut: true, zoomCuts: true } },
};

function applyRhythmPreset(id) {
  const p = RHYTHM_PRESETS[id];
  if (!p) return;
  if (!S.style) S.style = defaultStyle();
  const { elements, ...fields } = p;
  Object.assign(S.style, fields);
  if (elements) {
    // merge — um preset de ritmo ajusta zoom/flash sem apagar trilha/endCard
    S.style.elements = { ...(S.style.elements || {}), ...elements };
  }
  refreshAutoControls();
  renderSetup();
  document.querySelectorAll('.rhythm-preset').forEach((b) => {
    b.classList.toggle('on', b.dataset.preset === id);
  });
}

function wireAutoControls() {
  const map = [
    ['autoRhythm', 'rhythm'],
    ['autoTransicao', 'transicao'],
    ['autoIntensity', 'intensity'],
    ['autoColorGrade', 'colorGrade'],
    ['autoSpeech', 'speechClean'],
    ['autoGoal', 'videoGoal'],
    ['autoBroll', 'brollMode'],
    ['autoExport', 'exportPreset'],
    ['autoCaptionChunk', 'captionChunk'],
    ['autoCapPosition', 'captionPosition'],
    ['autoCapSize', 'captionSize'],
    ['autoCapFont', 'captionFont'],
    ['autoHlFont', 'headlineFont'],
    ['autoEmphWords', 'emphasisWords'],
    ['autoPostTags', 'postHashtags'],
    ['autoPostSeo', 'postSeo'],
    ['autoPostRodape', 'postRodape'],
    ['autoHlDuration', 'headlineDuration'],
    ['autoHlSeconds', 'headlineSeconds'],
    ['autoHlPos', 'headlinePos'],
    ['autoLegendaApos', 'legendaAposHeadline'],
    ['autoHlAnim', 'headlineAnimation'],
    ['autoContentType', 'contentType'],
  ];
  for (const [id, key] of map) {
    const el = $(id);
    if (!el) continue;
    el.addEventListener('change', () => {
      if (!S.style) S.style = defaultStyle();
      S.style[key] = el.value;
      if (key === 'contentType') {
        S.contentType = el.value;
        persistIntent();
      }
    });
  }
  document.querySelectorAll('.rhythm-preset').forEach((b) => {
    b.addEventListener('click', () => applyRhythmPreset(b.dataset.preset));
  });
  const custom = $('btnAutoCustomize');
  const grid = $('autoControls');
  if (custom && grid) {
    grid.classList.add('is-collapsed');
    custom.addEventListener('click', () => {
      grid.classList.toggle('is-collapsed');
      custom.textContent = grid.classList.contains('is-collapsed') ? 'Personalizar' : 'Ocultar detalhes';
    });
  }
}

function refreshSafeZone() {
  const on = localStorage.getItem('ativa-vid.safeZone') === '1';
  const sz = $('safeZone');
  const btn = $('btnSafeZone');
  if (sz) sz.classList.toggle('hidden', !on);
  if (btn) btn.classList.toggle('on', on);
}

/* Na PRIMEIRA vez que ele abre a Visual de um projeto a copia leve ainda
 * nao existe: o servidor comeca a fazer quando e perguntado e leva de 10 a
 * 30 s. Sem voltar a perguntar, a sessao inteira tocaria o arquivo cheio
 * mesmo com a copia pronta ha um minuto. Quatro perguntas, 15 s entre
 * elas, e para — nem enxurrada, nem uma pergunta so. */
let esperaDaCopia = null;
function esperarCopiaDoFinal(tentativas = 4) {
  if (esperaDaCopia) return;
  const passo = async () => {
    esperaDaCopia = null;
    if (S.tab !== 2 || S.hasFinalProxy || S.finalProxyFailed) return;
    await detectProxy().catch(() => {});
    if (S.hasFinalProxy) { updateVideoSrc(); return; }
    if (--tentativas > 0) esperaDaCopia = setTimeout(passo, 15000);
  };
  esperaDaCopia = setTimeout(passo, 1500);
}

async function detectProxy() {
  try {
    const r = await fetch(`${BASE}/media/cut_proxy.mp4`, { method: 'HEAD' });
    S.hasProxy = r.ok;
    if (r.ok) S.proxyFailed = false;
  } catch { S.hasProxy = false; }
  // A copia do video pronto responde 404 enquanto nao existe (e o servidor
  // manda fazer ao ser perguntado). Perguntar de novo ao trocar de aba e o
  // que faz a copia entrar em uso assim que fica pronta, sem recarregar.
  try {
    const r = await fetch(`${BASE}/media/final_proxy.mp4`, { method: 'HEAD' });
    S.hasFinalProxy = r.ok;
    if (r.ok) S.finalProxyFailed = false;
  } catch { S.hasFinalProxy = false; }
}

const AI_UNDO = [];
const AI_CONFIRM_EXACT = new Set([
  'ok', 'sim', 'isso', 'vai', 'pode', 'blz', 'beleza', 'fechou',
  'aplica', 'aplicar', 'faz', 'faz isso', 'manda ver',
  'ok pode aplicar', 'pode aplicar', 'ok aplicar', 'ok aplica',
  'pode mandar', 'pode fazer', 'pode sim', 'confirma', 'confirmar',
  'aplica isso', 'aplicar isso',
]);
const AI_CONFIRM_RE = /^(ok|sim|blz|beleza|fechou)?\s*(pode\s+)?(aplicar|aplica|fazer|faz(\s+isso)?|mandar|manda\s+ver|confirmar|confirma)(\s+isso)?\s*$/i;

function isAiConfirm(text) {
  const t = String(text || '').trim().toLowerCase().replace(/[.!,…]+$/, '').replace(/\s+/g, ' ');
  if (!t) return false;
  return AI_CONFIRM_EXACT.has(t) || AI_CONFIRM_RE.test(t);
}

function pendingKey() {
  return `ativa-vid.pendingEdit:${projectId()}`;
}

function projectId() {
  return projectFolder() || BASE || 'house';
}

function edlFingerprint(list) {
  const rows = (list || S.draft || []).map((r) => ([
    String(r.source || ''),
    Number((+r.start || 0).toFixed(3)),
    Number((+r.end || 0).toFixed(3)),
    !!r.removed,
  ]));
  return JSON.stringify(rows);
}

function pendingOpCount(p) {
  if (!p) return 0;
  const ops = p.operations || [];
  if (ops.length) return ops.length;
  return (p.actions || []).filter((a) => a && a.action && a.action !== 'noop').length;
}

function hasPendingOps() {
  return pendingOpCount(S.pendingEdit) > 0;
}

function pendingIsStale(p) {
  if (!p || pendingOpCount(p) === 0) return false;
  if (String(p.projectId || '') !== String(projectId())) return true;
  if (p.edlFingerprint && p.edlFingerprint !== edlFingerprint()) return true;
  return false;
}

function setPendingEdit(p) {
  S.pendingEdit = p && pendingOpCount(p) > 0 ? p : null;
  try {
    if (S.pendingEdit) localStorage.setItem(pendingKey(), JSON.stringify(S.pendingEdit));
    else localStorage.removeItem(pendingKey());
  } catch { /* quota */ }
  refreshAiApplyBtn();
}

function loadPendingEdit() {
  try {
    const raw = localStorage.getItem(pendingKey());
    if (!raw) return;
    const p = JSON.parse(raw);
    if (p && pendingOpCount(p) > 0 && String(p.projectId || '') === String(projectId())) {
      S.pendingEdit = p;
    } else {
      S.pendingEdit = null;
    }
  } catch { S.pendingEdit = null; }
  refreshAiApplyBtn();
}

function refreshAiApplyBtn() {
  const btn = $('aiGo');
  const banner = $('aiPending');
  const n = pendingOpCount(S.pendingEdit);
  if (banner) banner.classList.toggle('hidden', n === 0);
  if (!btn) return;
  btn.disabled = false;
  btn.textContent = n ? `Aplicar (${n})` : 'Aplicar';
}

function sourceDurationSec() {
  const durs = S.state.sourceDurations || {};
  const vals = Object.values(durs).map(Number).filter((n) => n > 0);
  if (vals.length) return Math.max(...vals);
  const ends = (S.draft || []).map((r) => Number(r.end) || 0);
  const origEnds = (S.draft || []).map((r) => Number(r.orig && r.orig.end) || 0);
  const maxEnd = Math.max(0, ...ends, ...origEnds);
  return maxEnd || S.videoDuration || null;
}

function primarySource() {
  if (S.draft && S.draft[0] && S.draft[0].source) return S.draft[0].source;
  const keys = Object.keys(S.state.sourceDurations || {});
  return keys[0] || 'SRC';
}

function aiAppendMsg(text, kind = 'bot') {
  const thread = $('aiThread');
  if (!thread || !text) return null;
  const bubble = document.createElement('div');
  bubble.className = `ai-msg ai-msg-${kind}`;
  bubble.textContent = text;
  thread.appendChild(bubble);
  thread.scrollTop = thread.scrollHeight;
  return bubble;
}

function openAiPanel() {
  const panel = $('aiPanel');
  if (!panel) return;
  panel.classList.add('solid-float');
  panel.classList.remove('hidden');
  loadPendingEdit();
  $('aiPrompt')?.focus();
}
function closeAiPanel() {
  $('aiPanel')?.classList.add('hidden');
}

function applyRestoreRange(start, end) {
  const src = primarySource();
  const srcDur = sourceDurationSec();
  const a = Math.max(0, +start);
  const b = Math.min(+end, srcDur || +end);
  if (!(b > a + 0.04)) return false;
  const span = b - a;
  const full = !srcDur || span >= 0.9 * srcDur;
  if (full) {
    const orig = (S.draft[0] && S.draft[0].orig) || { start: a, end: b };
    S.draft = [{
      source: src, start: a, end: b, beat: 'KEEP',
      removed: false, srcIdx: S.draft[0] ? S.draft[0].srcIdx : 0, orig,
    }];
    return true;
  }
  let touched = false;
  for (const r of S.draft) {
    if (r.source !== src) continue;
    if (r.start < b && r.end > a) {
      if (r.removed) { r.removed = false; touched = true; }
      const ns = Math.min(r.start, a);
      const ne = Math.max(r.end, b);
      if (ns !== r.start || ne !== r.end) {
        r.start = ns;
        r.end = ne;
        touched = true;
      }
    }
  }
  const covered = S.draft.some((r) => (
    !r.removed && r.source === src && r.start <= a + 0.05 && r.end >= b - 0.05
  ));
  if (!covered) {
    S.draft.push({
      source: src, start: a, end: b, beat: 'KEEP',
      removed: false, srcIdx: null, orig: { start: a, end: b },
    });
    S.draft.sort((x, y) => x.start - y.start);
    touched = true;
  }
  return touched;
}

function applyTimelineOps(ops) {
  if (!Array.isArray(ops) || !ops.length) return;
  for (const op of ops) {
    if (!op || !op.op) continue;
    if (op.op === 'remove_range') {
      removeDraftTimeRange(+op.start, +op.end);
    } else if (op.op === 'restore_range') {
      applyRestoreRange(+op.start, +op.end);
    } else if (op.op === 'trim_range') {
      // remove before start, then after end (draft timeline seconds)
      const total = draftTotal();
      if (+op.start > 0.05) removeDraftTimeRange(0, +op.start);
      if (+op.end < total - 0.05) removeDraftTimeRange(+op.end, total + 1);
    } else if (op.op === 'set_duration_max') {
      const total = draftTotal();
      const maxSec = +op.maxSec;
      if (maxSec > 0.5 && maxSec < total - 0.05) removeDraftTimeRange(maxSec, total + 1);
    } else if (op.op === 'regenerate_hook' || op.op === 'mark_hook') {
      if (op.lines && S.editData) {
        S.editData.hook = { ...(S.editData.hook || {}), enabled: true, lines: op.lines };
      }
      if (op.op === 'mark_hook' && S.editData) {
        const end = Math.max(1.5, (+op.end || 3) - (+op.start || 0));
        S.editData.hook = { ...(S.editData.hook || {}), enabled: true, endSec: end };
      }
      buildInsertsDraft();
    } else if (op.op === 'fix_captions') {
      applyCaptionReplacements(op.replacements || []);
    }
  }
}

function _capFold(s) {
  return String(s || '').normalize('NFD').replace(/\p{M}/gu, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
}

function _fixHookLines(from, to) {
  const hook = S.editData && S.editData.hook;
  if (!hook || !from || !to) return;
  const lines = hook.lines || hook.text;
  if (!Array.isArray(lines)) return;
  const re = new RegExp(from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig');
  const nxt = lines.map((ln) => String(ln || '').replace(re, to));
  if (nxt.some((ln, i) => ln !== String(lines[i] || ''))) {
    S.editData.hook = { ...hook, lines: nxt };
  }
}

function applyCaptionReplacements(reps) {
  for (const rep of reps || []) {
    const from = String(rep.from || '').trim();
    const to = String(rep.to || '').trim();
    if (!from || !to) continue;
    _fixHookLines(from, to);
    const needle = _capFold(from);
    S.captions.forEach((c, i) => {
      const hay = _capFold(c.text);
      if (!hay || !needle) return;
      if (hay === needle || hay.includes(needle) || needle.includes(hay)) {
        const next = c.text.replace(new RegExp(from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), to);
        const toText = next === c.text ? to : next;
        S.captionFixes[i] = { from: c.text, to: toText, start: c.start, end: c.end };
        c.text = toText;
      }
    });
  }
}

function logAiApply(ops) {
  const n = (ops || []).length;
  console.log(`AI_EDIT_APPLY operations=${n}`);
  const lines = [`AI_EDIT_APPLY operations=${n}`];
  for (const op of ops || []) {
    const kind = String(op.op || op.type || op.action || '?').toUpperCase();
    let line = kind;
    if (op.start != null && op.end != null) {
      line = `${kind} ${Number(op.start).toFixed(2)}-${Number(op.end).toFixed(2)}`;
    }
    console.log(line);
    lines.push(line);
  }
  aiAppendMsg(lines.join('\n'), 'status');
  return lines;
}

function applyPendingPatch(patch) {
  const beforeInsertKeys = new Set(
    ((S.editData && S.editData.inserts) || [])
      .map((it) => `${it.src || ''}|${Number(it.start) || 0}`)
  );
  if (patch.style) {
    S.style = { ...S.style, ...patch.style, elements: { ...S.style.elements, ...(patch.style.elements || {}) } };
  }
  if (patch.editData) S.editData = { ...(S.editData || {}), ...patch.editData };
  if (Array.isArray(patch.notes)) S.notes = patch.notes;
  applyTimelineOps(patch.timelineOps || []);
  buildInsertsDraft();
  for (const c of S.insertsDraft) {
    if (c.kind === 'insert' && c.src && !beforeInsertKeys.has(`${c.src}|${c.start}`)) {
      c.isNew = true;
    }
  }
  renderSetup();
  renderClips();
  renderNotes();
  renderAll();
  refreshHeader();
  if (typeof updateVideoSrc === 'function') updateVideoSrc();
  scheduleAutosave();
}

async function applyPendingEdit(via) {
  const pending = S.pendingEdit;
  const ops = (pending && pending.operations) || [];
  if (!pending || !ops.length) {
    toast('Nenhuma alteração pendente');
    aiAppendMsg('Nenhuma alteração pendente; mantendo o projeto no estado atual.', 'bot');
    return false;
  }
  if (pendingIsStale(pending)) {
    console.log('PENDING_EDIT_STALE');
    aiAppendMsg('O vídeo foi alterado desde essa sugestão. Peça à IA para recalcular a edição.', 'bot');
    toast('O vídeo foi alterado desde essa sugestão. Peça à IA para recalcular a edição.');
    setPendingEdit(null);
    return false;
  }
  const before = snapshotState();
  const edlSnapshot = structuredClone(S.draft);
  const rangesBefore = (S.draft || []).map((r) => ({
    source: r.source, start: r.start, end: r.end, removed: !!r.removed,
  }));
  const filtered = filterProtectedOps(ops);
  if (filtered.blocked.length) {
    console.log(filtered.blocked.map((op) => {
      const a = Number(op.start ?? op.maxSec ?? 0);
      const b = Number(op.end ?? a);
      return `PROTECTED_RANGE_BLOCKED ${String(op.op || op.action || '?').toUpperCase()} ${a.toFixed(2)}-${b.toFixed(2)}`;
    }).join('\n'));
  }
  if (!filtered.kept.length) {
    toast('Esse trecho está protegido');
    aiAppendMsg('Esse trecho está protegido. Desproteja para a IA poder alterar.', 'bot');
    return false;
  }
  pushHistory();
  AI_UNDO.push({ ...before, edlSnapshot });
  applyPendingPatch({ ...(pending.patch || {}), timelineOps: filtered.kept });
  logAiApply(filtered.kept);
  snapshotVersion('ai', 'Editar com IA');
  try {
    await fetch('/api/ai-edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: 'apply',
        operations: filtered.kept,
        pendingEdit: pending,
        currentRanges: rangesBefore,
        folder: projectFolder(),
        protectedRanges: S.protectedRanges,
      }),
    });
  } catch { /* log local já saiu */ }
  setPendingEdit(null);
  $('aiUndo').disabled = AI_UNDO.length === 0;
  if (filtered.kept.some((op) => op && op.op === 'fix_captions')) {
    try {
      const r = await fetch(`${BASE}/media/${S.state.captions || 'remotion/public/captions.json'}?v=${Date.now()}`);
      if (r.ok) {
        const caps = await r.json();
        if (Array.isArray(caps) && caps.length) S.captions = groupCaptions(caps);
      }
    } catch { /* overlay já usou o texto novo */ }
    renderAll();
    updateCapOverlay();
  }
  const done = pending.summary
    ? `Pronto. ${pending.summary.replace(/^vou\s+/i, '')}`
    : 'Pronto. A alteração foi aplicada.';
  aiAppendMsg(done, 'bot');
  toast('Alteração da IA aplicada');
  return true;
}

async function planAiEdit(prompt) {
  $('aiGo').disabled = true;
  const errBox = $('aiErr');
  if (errBox) errBox.classList.add('hidden');
  aiAppendMsg(prompt, 'user');
  $('aiPrompt').value = '';
  const status = aiAppendMsg('Pensando…', 'status');
  try {
    const body = {
      mode: 'plan',
      prompt,
      durationSec: S.videoDuration || draftTotal() || null,
      sourceDurationSec: sourceDurationSec(),
      currentRanges: (S.draft || []).map((r) => ({
        source: r.source, start: r.start, end: r.end, removed: !!r.removed,
      })),
      style: S.style,
      editData: S.editData,
      notes: S.notes,
      folder: projectFolder(),
      protectedRanges: S.protectedRanges,
    };
    const res = await fetch('/api/ai-edit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || 'Falha na IA');
    if (data.confirm && hasPendingOps()) {
      if (status) status.remove();
      return applyPendingEdit('confirm');
    }
    const ops = data.operations || (data.patch && data.patch.timelineOps) || [];
    const pending = {
      ...(data.pendingEdit || {}),
      hasPendingEdit: Boolean(ops.length || data.hasPendingEdit),
      projectId: (data.pendingEdit && data.pendingEdit.projectId) || projectId(),
      edlRevision: (data.pendingEdit && data.pendingEdit.edlRevision) || '',
      edlFingerprint: edlFingerprint(),
      timestamp: (data.pendingEdit && data.pendingEdit.timestamp) || Date.now(),
      operations: ops,
      actions: data.actions || [],
      patch: data.patch || {},
      summary: data.summary || 'Alteração planejada',
    };
    if (status) status.remove();
    if (pendingOpCount(pending) === 0) {
      aiAppendMsg(data.summary || 'Não consegui preparar essa alteração. Tente descrever de outra forma.', 'bot');
      toast('Nenhuma operação gerada');
      return false;
    }
    setPendingEdit(pending);
    const n = pendingOpCount(pending);
    aiAppendMsg(
      `${pending.summary}\n${n} operação(ões) pronta(s) — clique em Aplicar ou escreva “ok pode aplicar”.`,
      'bot',
    );
    toast('Alteração pronta — clique em Aplicar');
    return true;
  } catch (e) {
    const msg = e.message || 'erro';
    if (status) status.remove();
    if (errBox && $('aiErrText')) {
      $('aiErrText').textContent = msg;
      errBox.classList.remove('hidden');
    } else {
      aiAppendMsg(msg, 'bot');
    }
    toast(msg.length > 80 ? 'Sessão IA incompleta — veja Chaves & IA' : msg);
    return false;
  } finally {
    $('aiGo').disabled = false;
    refreshAiApplyBtn();
  }
}

async function runAiEdit() {
  const prompt = ($('aiPrompt').value || '').trim();
  if (isAiConfirm(prompt) && hasPendingOps()) {
    $('aiPrompt').value = '';
    aiAppendMsg(prompt, 'user');
    await applyPendingEdit('confirm');
    return;
  }
  if (!prompt && hasPendingOps()) {
    await applyPendingEdit('button');
    return;
  }
  if (prompt.length < 3) { toast('Escreva o que mudar'); return; }
  await planAiEdit(prompt);
}

function undoAiEdit() {
  const snap = AI_UNDO.pop();
  if (!snap) return;
  pushHistory();
  S.draft = structuredClone(snap.edlSnapshot || snap.draft);
  S.insertsDraft = snap.insertsDraft;
  S.notes = snap.notes;
  S.style = snap.style;
  S.captionFixes = snap.captionFixes || {};
  renderSetup();
  renderClips();
  renderAll();
  refreshHeader();
  $('aiUndo').disabled = AI_UNDO.length === 0;
  toast('Desfeito');
}

function overlapsSec(a0, a1, b0, b1) {
  return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0)) >= 0.08;
}

function protectedDraftSpans() {
  const out = [];
  for (const pr of S.protectedRanges || []) {
    if (pr.draftStart != null && pr.draftEnd != null) {
      out.push({ start: +pr.draftStart, end: +pr.draftEnd });
      continue;
    }
    draftLayout().forEach((r) => {
      if (r.removed) return;
      const a = Math.max(r.start, +pr.start || 0);
      const b = Math.min(r.end, +pr.end || 0);
      if (b > a) out.push({ start: r.out + (a - r.start), end: r.out + (b - r.start) });
    });
  }
  return out;
}

function clipIsProtected(r) {
  if (!r || r.removed) return false;
  for (const pr of S.protectedRanges || []) {
    const a0 = pr.draftStart != null ? +pr.draftStart : +pr.start;
    const a1 = pr.draftEnd != null ? +pr.draftEnd : +pr.end;
    const b0 = r.out != null ? r.out : r.start;
    const b1 = r.out != null ? r.out + r.dur : r.end;
    if (overlapsSec(a0, a1, b0, b1) || overlapsSec(+pr.start || 0, +pr.end || 0, r.start, r.end)) {
      return true;
    }
  }
  return false;
}

function filterProtectedOps(ops) {
  const kept = [];
  const blocked = [];
  const spans = protectedDraftSpans();
  for (const op of ops || []) {
    const kind = String(op.op || op.action || '');
    if (kind === 'restore_range') { kept.push(op); continue; }
    let a0; let a1;
    if (kind === 'set_duration_max' && op.maxSec != null) {
      a0 = +op.maxSec; a1 = 1e9;
    } else if (op.start != null && op.end != null) {
      a0 = +op.start; a1 = +op.end;
    } else {
      kept.push(op);
      continue;
    }
    const hit = spans.some((s) => overlapsSec(a0, a1, s.start, s.end));
    if (hit) blocked.push({ ...op, reason: 'PROTECTED_RANGE_BLOCKED' });
    else kept.push(op);
  }
  return { kept, blocked };
}

async function persistIntent(extra) {
  try {
    await fetch(`${BASE}/api/intent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        protectedRanges: S.protectedRanges,
        contentType: S.contentType || undefined,
        ...(extra || {}),
      }),
    });
  } catch { /* persistência local já cobre reload curto */ }
}

function currentProtectSpan() {
  if (S.pendingIn != null) {
    const t = renderedToDraft(video.currentTime || 0);
    const a = Math.min(S.pendingIn, t);
    const b = Math.max(S.pendingIn, t);
    if (b - a >= 0.08) return { start: a, end: b, draftStart: a, draftEnd: b, label: 'seleção' };
  }
  if (S.lastMarkRange && S.lastMarkRange.end > S.lastMarkRange.start) {
    return { ...S.lastMarkRange, label: S.lastMarkRange.label || 'seleção' };
  }
  if (S.selected >= 0) {
    const r = draftLayout()[S.selected];
    if (r && !r.removed) {
      return {
        start: r.start, end: r.end, draftStart: r.out, draftEnd: r.out + r.dur,
        source: r.source, label: r.beat || 'take',
      };
    }
  }
  return null;
}

function beatProtectSpan(beat) {
  const want = String(beat || '').toUpperCase();
  const items = draftLayout().filter((r) => !r.removed && String(r.beat || '').toUpperCase() === want);
  const all = draftLayout().filter((r) => !r.removed);
  const pick = (want === 'CTA' ? items[items.length - 1] : items[0])
    || (want === 'CTA' ? all[all.length - 1] : all[0]);
  if (!pick) return null;
  return {
    start: pick.start, end: pick.end,
    draftStart: pick.out, draftEnd: pick.out + pick.dur,
    source: pick.source, label: beat,
  };
}

async function applyProtectAction(kind) {
  if (kind === 'clear') {
    const span = currentProtectSpan();
    if (!span) { toast('Marque um trecho ou selecione um take'); return; }
    S.protectedRanges = (S.protectedRanges || []).filter((pr) => {
      const a0 = pr.draftStart != null ? +pr.draftStart : +pr.start;
      const a1 = pr.draftEnd != null ? +pr.draftEnd : +pr.end;
      return !overlapsSec(a0, a1, span.draftStart ?? span.start, span.draftEnd ?? span.end);
    });
    await persistIntent();
    renderClips();
    toast('Trecho desprotegido');
    return;
  }
  const span = kind === 'hook' ? beatProtectSpan('HOOK')
    : kind === 'cta' ? beatProtectSpan('CTA')
    : currentProtectSpan();
  if (!span) {
    toast(kind === 'selection' ? 'Marque um trecho ou selecione um take' : 'Não achei esse trecho');
    return;
  }
  S.protectedRanges = [...(S.protectedRanges || []), {
    start: +span.start.toFixed(3),
    end: +span.end.toFixed(3),
    draftStart: +(span.draftStart ?? span.start).toFixed(3),
    draftEnd: +(span.draftEnd ?? span.end).toFixed(3),
    source: span.source || '',
    label: span.label || kind,
  }];
  await persistIntent();
  renderClips();
  toast('Trecho protegido — a IA não corta este conteúdo');
}

function wireProtect() {
  const btn = $('btnProtect');
  const menu = $('protectMenu');
  const ico = $('protectIcon');
  if (ico) ico.innerHTML = ICON.lock;
  if (!btn || !menu) return;
  btn.onclick = (e) => {
    e.stopPropagation();
    menu.classList.toggle('hidden');
    btn.setAttribute('aria-expanded', String(!menu.classList.contains('hidden')));
  };
  menu.querySelectorAll('[data-protect]').forEach((b) => {
    b.onclick = () => {
      menu.classList.add('hidden');
      applyProtectAction(b.dataset.protect);
    };
  });
  document.addEventListener('click', () => menu.classList.add('hidden'));
}

async function snapshotVersion(origin, description, extra) {
  if (HOUSE_STYLE) return;
  try {
    await fetch(`${BASE}/api/versions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        origin,
        description,
        extra: extra || {
          edl: { ranges: (S.draft || []).filter((r) => !r.removed).map((r) => ({
            source: r.source, start: r.start, end: r.end, beat: r.beat,
          })) },
          intent: { protectedRanges: S.protectedRanges, contentType: S.contentType },
        },
      }),
    });
  } catch { /* histórico é auxiliar */ }
}

async function ensureInitialVersion() {
  if (HOUSE_STYLE) return;
  try {
    const r = await fetch(`${BASE}/api/versions`);
    const data = await r.json();
    if ((data.versions || []).length) return;
    await snapshotVersion('auto', 'Edição automática');
  } catch { /* ignore */ }
}

function applyRestoredEdl(edl) {
  const ranges = (edl && edl.ranges) || [];
  if (!ranges.length) return;
  pushHistory();
  S.draft = ranges.map((r, srcIdx) => ({
    source: r.source, start: +r.start, end: +r.end, beat: r.beat || '',
    removed: false, srcIdx, orig: { start: +r.start, end: +r.end },
  }));
  renderAll();
  refreshHeader();
}

async function openVersionsPanel() {
  let panel = $('versionsPanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'versionsPanel';
    panel.className = 'versions-panel solid-float';
    document.body.appendChild(panel);
  }
  let items = [];
  try {
    const r = await fetch(`${BASE}/api/versions`);
    const data = await r.json();
    items = data.versions || [];
  } catch { items = []; }
  panel.innerHTML = `
    <div class="score-head"><strong>Versões</strong>
      <button type="button" class="btn ghost small" id="verClose">✕</button></div>
    ${items.length ? items.slice().reverse().map((v) => `
      <div class="ver-item">
        <div>
          <p>v${v.n} · ${v.description || v.origin || ''}</p>
          <span>${v.at || ''} · ${v.origin || ''}</span>
        </div>
        <button type="button" class="btn ghost small" data-restore="${v.id}">Restaurar esta versão</button>
      </div>`).join('') : '<p class="hint">Ainda não há versões neste projeto.</p>'}`;
  panel.classList.remove('hidden');
  const c = $('verClose');
  if (c) c.onclick = () => panel.classList.add('hidden');
  panel.querySelectorAll('[data-restore]').forEach((b) => {
    b.onclick = async () => {
      try {
        const res = await fetch(`${BASE}/api/versions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'restore', id: b.dataset.restore }),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || 'Falha ao restaurar');
        if (data.edl) applyRestoredEdl(data.edl);
        if (data.intent && Array.isArray(data.intent.protectedRanges)) {
          S.protectedRanges = data.intent.protectedRanges;
        }
        if (data.corrections) S.corrections = data.corrections;
        toast('Versão restaurada — clique em Aplicar alterações para atualizar o vídeo');
        panel.classList.add('hidden');
        location.reload();
      } catch (e) {
        toast(e.message || 'Não restaurei');
      }
    };
  });
}

function currentStyleSnapshot() {
  return {
    edit: S.style?.edit,
    headline: S.style?.headline,
    captions: S.style?.captions,
    accent: S.style?.accent,
    captionAccent: S.style?.captionAccent,
    emphasisAccent: S.style?.emphasisAccent,
    circleAccent: S.style?.circleAccent,
    elements: { ...(S.style?.elements || {}) },
    rhythm: S.style?.rhythm,
    intensity: S.style?.intensity,
    speechClean: S.style?.speechClean,
    videoGoal: S.style?.videoGoal,
    brollMode: S.style?.brollMode,
    captionChunk: S.style?.captionChunk,
    captionPosition: S.style?.captionPosition,
    captionSize: S.style?.captionSize,
    captionFont: S.style?.captionFont,
    headlineFont: S.style?.headlineFont,
    emphasisWords: S.style?.emphasisWords,
    headlineDuration: S.style?.headlineDuration,
    headlineAnimation: S.style?.headlineAnimation,
    exportPreset: S.style?.exportPreset,
    colorGrade: S.style?.colorGrade,
    endCardCopy: S.endCardCopy || null,
    fastMode: !!S.fastMode,
    oneClick: !!S.fastMode,
    contentType: S.contentType || $('autoContentType')?.value || null,
  };
}

/* PRESET DO VIDEO. Ele decide as cores, a legenda e o texto do cartao
 * final, e a tela nao dizia qual era: em 29/08 um video saiu com o verde e
 * o "Segue @Ativacrm" porque a identidade ativa NO MOMENTO DA IMPORTACAO
 * era outra — e so dava para descobrir depois de renderizar.
 *
 * Ate a 4.28 esta linha listava MARCAS, conceito que saiu do app na 4.19
 * ("nao aparece os presets reais ali, no lugar de marca, que a gente nao
 * usa mais"). A mecanica e a mesma; a unidade e que mudou. */
async function carregarPresetDoVideo() {
  const caixa = document.getElementById('presetDoVideo');
  const sel = document.getElementById('presetVideoSelect');
  const dica = document.getElementById('presetVideoDica');
  if (!caixa || !sel || HOUSE_STYLE || HUB_EMBED) return;
  let pack = {};
  try {
    const r = await fetch('/api/brand-presets');
    if (!r.ok) throw new Error('sem presets');
    pack = await r.json();
  } catch {
    caixa.hidden = true;        // preview solto (skill): nao ha presets
    return;
  }
  const presets = pack.presets || [];
  if (!presets.length) { caixa.hidden = true; return; }
  const atual = String(
    (S.presetUsed && (S.presetUsed.brandPresetId || S.presetUsed.presetId))
    || pack.activeId || ''
  ).trim();
  S.presetsDoVideo = presets;
  S.presetBrandId = pack.brandId || '';
  sel.innerHTML = presets.map((p) =>
    `<option value="${p.id}"${p.id === atual ? ' selected' : ''}>${p.name || p.id}</option>`
  ).join('');
  caixa.hidden = false;
  S.presetOriginal = sel.value;
  if (dica) dica.textContent = '';
  sel.onchange = () => trocarPresetDoVideo(sel.value);

  // "Voltar ao preset": o estilo ajustado NESTE video (preview_style.json)
  // e a camada mais forte da cadeia — mais forte que a empresa e que o
  // preset. Um video editado antes de acertar a cor da empresa ficava com
  // a cor velha congelada, e nem trocar o preset o tirava de la, porque
  // trocar para o MESMO preset nao dispara `change`. Este botao repoe o
  // estilo do preset escolhido e o Salvar grava isso no projeto (04/09).
  const voltar = document.getElementById('btnUsarPreset');
  if (voltar && !voltar.dataset.wired) {
    voltar.dataset.wired = '1';
    voltar.onclick = async () => {
      const alvo = (S.presetsDoVideo || []).find((x) => x.id === sel.value);
      if (!alvo) return;
      if (!await pedirConfirmacao(
        'Voltar ao estilo do preset?',
        'Os ajustes de estilo feitos neste vídeo (cor, legenda, manchete) '
        + 'são trocados pelos do preset. O corte e a linha do tempo ficam '
        + 'como estão. Vale depois de "Salvar e refazer a Fase 2".',
        'Voltar ao preset')) return;
      trocarPresetDoVideo(alvo.id);
      if (dica) {
        dica.textContent = 'aplique em "Salvar e refazer a Fase 2" '
          + 'para o vídeo sair assim';
      }
      toast('Estilo do preset carregado — falta salvar e refazer', 4000);
    };
  }
}

function trocarPresetDoVideo(id) {
  const p = (S.presetsDoVideo || []).find((x) => x.id === id);
  const dica = document.getElementById('presetVideoDica');
  if (!p) return;
  // O estilo do preset entra no editor. `endCardCopy` faz parte do
  // retrato (STYLE_KEYS), senao o video trocaria de cor e continuaria com
  // o CTA antigo — que foi exatamente o caso de 29/08.
  //
  // `resolved` e o estilo CHEIO desse preset (padrao do app + empresa +
  // preset). Sem ele, escolher um preset vazio — o "Padrao" que nasce com
  // toda empresa — nao mudava nada na tela, e o Salvar congelava a cor do
  // video anterior no projeto: o vermelho voltando sempre (04/09).
  const est = p.resolved || p.style || {};
  applyPresetToUi({ ...p, style: est });
  const cta = est.endCardCopy;
  if (cta && typeof cta === 'object') {
    S.endCardCopy = { ...cta };
    const l1 = document.getElementById('ecLine1');
    const l2 = document.getElementById('ecLine2');
    if (l1) l1.value = S.endCardCopy.line1 || '';
    if (l2) l2.value = S.endCardCopy.line2 || '';
  }
  S.presetUsed = { ...(S.presetUsed || {}) };
  S.presetUsed.brandPresetId = p.id;
  S.presetUsed.presetName = p.name || p.id;
  if (S.presetBrandId) S.presetUsed.brandId = S.presetBrandId;
  if (dica) {
    dica.textContent = (id === S.presetOriginal)
      ? ''
      : 'aplique em "Salvar e refazer a Fase 2" para o vídeo sair assim';
  }
  loadBrandPresets({ applyActive: false }).catch(() => {});
}

/* As fontes da pasta ~/ATIVAVID/Fontes, com o NOME de cada uma.
 *
 * "cade a fonte Integral que pedi pra voce instalar?" (30/08) — ela estava
 * instalada desde 29/08. A lista e que nao dizia: a unica opcao se chamava
 * "Sua fonte (pasta Fontes)", e o pipeline pegava a primeira em ordem
 * alfabetica sem dizer qual. Agora cada fonte tem sua linha.
 *
 * Falhar aqui deixa a opcao generica de antes, que continua funcionando. */
async function carregarFontesDoUsuario() {
  let fontes = [];
  try {
    const r = await fetch('/api/fontes');
    fontes = (await r.json()).fontes || [];
  } catch { return; }
  if (!fontes.length) return;
  FONTES_DO_USUARIO = fontes;
  for (const id of ['autoCapFont', 'autoHlFont']) {
    const sel = document.getElementById(id);
    if (!sel) continue;
    const antigo = sel.value;
    const generica = sel.querySelector('option[value="arquivo"]');
    if (!generica) continue;
    const pai = generica.parentNode;
    generica.remove();
    fontes.forEach((f, i) => {
      const o = document.createElement('option');
      // A PRIMEIRA responde pelo id antigo `arquivo`: estilo salvo antes
      // desta versao tem de cair exatamente na mesma fonte.
      o.value = i === 0 ? 'arquivo' : `arquivo:${f.arquivo}`;
      o.textContent = f.nome;
      pai.appendChild(o);
    });
    if (antigo) sel.value = antigo;
    sel.addEventListener('change', () => avisoDaFonte(sel));
    avisoDaFonte(sel);
  }
}

let FONTES_DO_USUARIO = [];

/* Fonte que nao desenha acento avisa NA HORA DE ESCOLHER.
 *
 * A checagem existe desde 29/08, mas so falava na ficha do video pronto
 * — com "N[DEMO]O" ja gravado. A demo da Integral CF carimba "DEMO" em
 * todo acento e no "!", e o estilo base dele esta nela: todo video sai
 * assim ate alguem olhar a ficha. */
function avisoDaFonte(sel) {
  const id = String(sel.value || '');
  const label = sel.closest('label') || sel.parentElement;
  if (!label) return;
  let box = label.querySelector('.fonte-aviso');
  const f = id.startsWith('arquivo')
    ? (id.includes(':')
        ? FONTES_DO_USUARIO.find((x) => `arquivo:${x.arquivo}` === id)
        : FONTES_DO_USUARIO[0])
    : null;
  const faltam = (f && f.faltam) || '';
  if (!faltam) {
    if (box) box.remove();
    return;
  }
  if (!box) {
    box = document.createElement('p');
    box.className = 'fonte-aviso';
    label.appendChild(box);
  }
  box.textContent = `Esta fonte não desenha ${faltam.slice(0, 12)} — `
    + 'nessas letras o vídeo sai com o símbolo da fonte. É a versão de '
    + 'demonstração; use a completa ou outra fonte.';
}

async function loadBrandPresets(opts) {
  const applyActive = !!(opts && opts.applyActive);
  const sel = $('presetSelect');
  if (!sel) return;
  const projectBrand = String(
    (S.presetUsed && (S.presetUsed.brandId || S.presetUsed.brandName))
    || (S.state && S.state.style && S.state.style.brandId)
    || ''
  ).trim();
  const qsBrand = new URLSearchParams(location.search).get('brandId') || '';
  let brandId = '';
  if (HOUSE_STYLE || HUB_EMBED) {
    brandId = qsBrand;
  } else {
    brandId = (S.presetUsed && S.presetUsed.brandId) || (S.state && S.state.style && S.state.style.brandId) || '';
  }
  // Projeto real: nunca cair no active.json global (loja-teste dos testes).
  if (!HOUSE_STYLE && !HUB_EMBED && !brandId) {
    const label = (S.presetUsed && S.presetUsed.brandName) || 'Deste vídeo';
    sel.innerHTML = `<option value="">${label}</option>`;
    S.brandPresets = { brandId: '', presets: [], activeId: '' };
    return;
  }
  try {
    const q = brandId ? `?brandId=${encodeURIComponent(brandId)}` : '';
    const r = await fetch('/api/brand-presets' + q);
    const pack = await r.json();
    const presets = pack.presets || [];
    S.brandPresets = pack;
    // Num projeto a barra comeca no preset DESTE VIDEO. Antes ela ficava
    // sem selecao e o navegador mostrava o PRIMEIRO da lista: dois campos
    // de preset na mesma tela apontando para presets diferentes ("porque 2
    // campos de preset ai?", 04/09) — e pior, Renomear/Excluir/Definir
    // como padrao agiam no que a barra mostrava, nao no do video.
    const doVideo = String(
      (S.presetUsed && (S.presetUsed.brandPresetId || S.presetUsed.presetId)) || ''
    ).trim();
    const wantId = (!HOUSE_STYLE && !HUB_EMBED)
      ? (presets.some((p) => p.id === doVideo) ? doVideo : (pack.activeId || ''))
      : (pack.activeId || '');
    sel.innerHTML = presets.map((p) =>
      `<option value="${p.id}" ${p.id === wantId ? 'selected' : ''}>${p.name || p.id}</option>`
    ).join('');
    if (!sel.innerHTML) {
      sel.innerHTML = `<option value="">${projectBrand || 'Deste vídeo'}</option>`;
    }
    if (EDIT_PRESET_ID) {
      const alvo = presets.find((p) => p.id === EDIT_PRESET_ID);
      if (alvo) {
        sel.value = alvo.id;
        applyPresetToUi(alvo);
      }
    } else if (applyActive) {
      applyPresetToUi(presets.find((p) => p.id === sel.value) || pack.active);
    }
  } catch { /* hub sem rota em preview isolado */ }
}

function applyPresetToUi(preset) {
  if (!preset) return;
  const st = preset.style || {};
  if (S.style) Object.assign(S.style, st);
  if (preset.contentType) {
    S.contentType = preset.contentType;
    const ct = $('autoContentType');
    if (ct) ct.value = preset.contentType;
  }
  if (typeof renderSetup === 'function') renderSetup();
  refreshAutoControls();
}


/* ---- Janelas do APP, no lugar das do navegador ---------------------------
 * `prompt()` e `confirm()` abrem a caixa do Chrome, com o "127.0.0.1:4850
 * diz" em cima e os botoes do sistema — dentro de um app escuro isso parece
 * outro programa (o usuario mandou print em 29/08: "esse tipo de janela feia
 * nao quero"). Estas usam <dialog>, herdam o tema e devolvem Promise. */
function _escDlg(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[c]);
}

function _dlgApp(html, aoAbrir) {
  return new Promise((resolve) => {
    const d = document.createElement('dialog');
    d.className = 'dlg dlg-app';
    d.innerHTML = html;
    document.body.appendChild(d);
    const fechar = (v) => {
      resolve(v);
      d.close();
      d.remove();
    };
    d.addEventListener('cancel', (e) => { e.preventDefault(); fechar(null); });
    d.querySelector('[data-nao]')?.addEventListener('click', () => fechar(null));
    if (aoAbrir) aoAbrir(d, fechar);
    d.showModal();
  });
}

/** Pergunta um texto. Devolve a string ou null (cancelou). */
function pedirTexto(titulo, valor, rotuloOk) {
  return _dlgApp(
    `<h3>${_escDlg(titulo)}</h3>
     <input type="text" class="dlg-input" id="_dlgTxt" value="${_escDlg(valor || '')}" autocomplete="off">
     <div class="dlg-actions">
       <button type="button" class="ghost-btn" data-nao>Cancelar</button>
       <button type="button" class="export-btn" data-sim>${_escDlg(rotuloOk || 'Salvar')}</button>
     </div>`,
    (d, fechar) => {
      const campo = d.querySelector('#_dlgTxt');
      const ok = () => {
        const v = (campo.value || '').trim();
        fechar(v || null);
      };
      d.querySelector('[data-sim]').addEventListener('click', ok);
      campo.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); ok(); }
      });
      setTimeout(() => { campo.focus(); campo.select(); }, 30);
    },
  );
}

/** Pergunta sim/nao. `perigo` deixa o botao de confirmar vermelho. */
function pedirConfirmacao(titulo, detalhe, rotuloOk, perigo) {
  return _dlgApp(
    `<h3>${_escDlg(titulo)}</h3>
     ${detalhe ? `<p class="hint">${_escDlg(detalhe)}</p>` : ''}
     <div class="dlg-actions">
       <button type="button" class="ghost-btn" data-nao>Agora não</button>
       <button type="button" class="${perigo ? 'danger-btn' : 'export-btn'}" data-sim>${_escDlg(rotuloOk || 'Confirmar')}</button>
     </div>`,
    (d, fechar) => {
      d.querySelector('[data-sim]').addEventListener('click', () => fechar(true));
    },
  ).then((v) => v === true);
}

async function presetAction(action) {
  const sel = $('presetSelect');
  const pack = S.brandPresets || {};
  const brandId = pack.brandId || 'padrao';
  const id = sel?.value;
  let name = '';
  if (action === 'create' || action === 'duplicate' || action === 'rename') {
    name = await pedirTexto(
      action === 'rename' ? 'Novo nome do preset' : 'Nome do preset', '',
      action === 'rename' ? 'Renomear' : 'Criar') || '';
    if (!name.trim()) return;
  }
  try {
    const r = await fetch('/api/brand-presets', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: action === 'create' ? 'create' : action,
        brandId,
        id,
        name,
        style: currentStyleSnapshot(),
        contentType: S.contentType || $('autoContentType')?.value,
      }),
    });
    const data = await r.json();
    if (!r.ok || data.error) throw new Error(data.error || 'Falha no preset');
    S.brandPresets = data;
    await loadBrandPresets({ applyActive: !!(HOUSE_STYLE || HUB_EMBED) });
    toast(action === 'delete' ? 'Preset excluído' : 'Preset atualizado');
  } catch (e) {
    toast(e.message || 'Não deu para alterar o preset');
  }
}

function wirePresets() {
  const bar = $('presetBar');
  if (!bar) return;
  loadBrandPresets({ applyActive: !!(HOUSE_STYLE || HUB_EMBED) });
  carregarFontesDoUsuario().catch(() => {});
  const sel = $('presetSelect');
  if (sel) {
    sel.onchange = () => {
      const p = (S.brandPresets?.presets || []).find((x) => x.id === sel.value);
      applyPresetToUi(p);
    };
  }
  const map = {
    btnPresetNew: 'create',
    btnPresetDup: 'duplicate',
    btnPresetRename: 'rename',
    btnPresetDel: 'delete',
    btnPresetDefault: 'default',
  };
  for (const [id, action] of Object.entries(map)) {
    const b = $(id);
    if (b) b.onclick = () => presetAction(action);
  }
  wirePresetShare();
}

// Exportar grava um .json em ~/ATIVAVID/presets-exportados (via servidor —
// download direto não é confiável no WebView2); Importar lê o arquivo no
// cliente e aplica como um modelo (mesma semântica da galeria).
const PRESET_SHARE_KEYS = [
  'edit', 'headline', 'captions', 'accent', 'captionAccent', 'emphasisAccent',
  'circleAccent', 'elements', 'rhythm', 'intensity', 'speechClean', 'videoGoal',
  'brollMode', 'captionChunk', 'exportPreset', 'colorGrade', 'endCardCopy',
  'contentType', 'captionPosition', 'captionSize', 'captionFont',
  'headlineFont', 'emphasisWords',
];

function wirePresetShare() {
  const exp = $('btnPresetExport');
  if (exp) exp.onclick = async () => {
    const style = {};
    for (const k of PRESET_SHARE_KEYS) {
      if (S.style && S.style[k] != null) style[k] = S.style[k];
    }
    const sel = $('presetSelect');
    const name = (sel && sel.selectedOptions[0]?.textContent) || 'preset';
    try {
      const r = await fetch(`${BASE}/api/style-export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, style }),
      });
      const data = await r.json();
      if (data.ok) toast(`Preset exportado: ${data.path}`);
      else toast(data.error || 'Não deu para exportar');
    } catch {
      toast('Não deu para exportar o preset');
    }
  };
  const imp = $('btnPresetImport');
  const file = $('presetImportFile');
  if (imp && file) {
    imp.onclick = () => file.click();
    file.onchange = () => {
      const f = file.files && file.files[0];
      if (!f) return;
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const data = JSON.parse(String(reader.result || '{}'));
          const style = data.style || data; // aceita o arquivo cru também
          const clean = {};
          for (const k of PRESET_SHARE_KEYS) {
            if (style[k] != null) clean[k] = style[k];
          }
          if (!Object.keys(clean).length) { toast('Arquivo sem estilo válido'); return; }
          if (!S.style) S.style = defaultStyle();
          Object.assign(S.style, clean);
          if (clean.contentType) { S.contentType = clean.contentType; persistIntent(); }
          refreshAutoControls();
          renderSetup();
          toast(`Preset "${data.name || f.name}" aplicado — ajuste e salve`);
        } catch {
          toast('Arquivo de preset inválido');
        }
      };
      reader.readAsText(f);
      file.value = '';
    };
  }
}

function wireAiAndSafe() {
  const aiBtn = $('btnAiEdit');
  if (aiBtn) aiBtn.onclick = openAiPanel;
  const aiClose = $('aiClose');
  if (aiClose) aiClose.onclick = closeAiPanel;
  const aiGo = $('aiGo');
  if (aiGo) aiGo.onclick = () => runAiEdit();
  const aiUndo = $('aiUndo');
  if (aiUndo) aiUndo.onclick = undoAiEdit;
  const aiPrompt = $('aiPrompt');
  if (aiPrompt) {
    aiPrompt.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        runAiEdit();
      }
    });
  }
  loadPendingEdit();
  wireProtect();
  wirePresets();
  const btnVer = $('btnVersions');
  if (btnVer) btnVer.onclick = () => openVersionsPanel();
  const sz = $('btnSafeZone');
  if (sz) {
    sz.onclick = () => {
      const on = localStorage.getItem('ativa-vid.safeZone') !== '1';
      localStorage.setItem('ativa-vid.safeZone', on ? '1' : '0');
      refreshSafeZone();
    };
  }
  refreshSafeZone();
  wireAutoControls();
}


// ---------- score panel + autosave ----------
async function refreshScorePill() {
  const pill = $('scorePill');
  if (!pill) return;
  try {
    const r = await fetch(`${BASE}/media/score.json?v=${Date.now()}`);
    if (!r.ok) { pill.classList.add('hidden'); return; }
    const s = await r.json();
    S.lastScore = s;
    $('scoreVal').textContent = s.overall != null ? s.overall : '—';
    pill.title = (s.disclaimer || '') + (s.tips && s.tips[0] ? ' · ' + s.tips[0] : '');
    pill.classList.remove('hidden');
    pill.onclick = () => openScorePanel();
  } catch {
    pill.classList.add('hidden');
  }
}

function openScorePanel() {
  const s = S.lastScore;
  if (!s) return;
  let panel = $('scorePanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'scorePanel';
    panel.className = 'score-panel solid-float';
    document.body.appendChild(panel);
  }
  panel.classList.add('solid-float');
  const tip = (s.tips || []).map((x) => `<li>${x}</li>`).join('') || '<li>Sem alertas.</li>';
  const band = (n) => {
    const v = Number(n);
    if (!Number.isFinite(v)) return '';
    if (v >= 85) return 'forte';
    if (v >= 70) return 'boa';
    if (v >= 55) return 'ok';
    return 'fraca';
  };
  const row = (label, val) => val == null
    ? ''
    : `<div><span>${label}</span><b>${band(val) || val}</b></div>`;
  panel.innerHTML = `
    <div class="score-head"><strong>Análise do vídeo</strong>
      <button type="button" class="btn ghost small" id="scoreClose">✕</button></div>
    <p class="score-disc">${s.disclaimer || ''}</p>
    <div class="score-grid">
      ${s.overall != null ? `<div><span>Geral</span><b>${s.overall}</b></div>` : ''}
      ${row('Gancho', s.hook)}
      ${row('Clareza', s.clarity)}
      ${row('Ritmo', s.rhythm)}
      ${row('CTA', s.cta)}
    </div>
    <ul class="score-tips">${tip}</ul>`;
  panel.classList.remove('hidden');
  const c = $('scoreClose');
  if (c) c.onclick = () => panel.classList.add('hidden');
}

let _autosaveTimer = null;
function scheduleAutosave() {
  clearTimeout(_autosaveTimer);
  _autosaveTimer = setTimeout(() => {
    try {
      const key = `ativavid-autosave:${BASE || 'house'}`;
      const payload = {
        at: Date.now(),
        draft: S.draft,
        insertsDraft: S.insertsDraft,
        notes: S.notes,
        style: S.style,
        captionFixes: S.captionFixes,
        protectedRanges: S.protectedRanges,
        contentType: S.contentType,
      };
      localStorage.setItem(key, JSON.stringify(payload));
    } catch { /* quota */ }
  }, 1200);
}

function autosaveKey() {
  return `ativavid-autosave:${BASE || 'house'}`;
}

function clearAutosave() {
  try { localStorage.removeItem(autosaveKey()); } catch { /* ignore */ }
}

function applyAutosaveData(data) {
  pushHistory();
  S.draft = data.draft;
  S.insertsDraft = data.insertsDraft || [];
  S.notes = data.notes || [];
  if (data.style) S.style = data.style;
  S.captionFixes = data.captionFixes || {};
  if (Array.isArray(data.protectedRanges)) S.protectedRanges = data.protectedRanges;
  if (data.contentType) S.contentType = data.contentType;
  if ((S.style?.edit || 'limpa') === 'limpa') {
    S.insertsDraft = (S.insertsDraft || []).filter((c) => c.kind !== 'insert');
    if (S.editData) S.editData.inserts = [];
  }
  renderAll();
  refreshHeader();
  toast('Rascunho restaurado', 2500);
}

function restoreAutosave() {
  try {
    const raw = localStorage.getItem(autosaveKey());
    if (!raw) return false;
    const data = JSON.parse(raw);
    if (!data || !Array.isArray(data.draft) || !data.draft.length) {
      clearAutosave();
      return false;
    }
    if (Date.now() - (data.at || 0) > 1000 * 60 * 60 * 48) {
      clearAutosave();
      return false;
    }
    // Concluído = pronto. Não interrompe com rascunho velho nem confirm() do Windows.
    if (hasFinalVideo()) {
      clearAutosave();
      return false;
    }
    const dlg = $('dlgAutosave');
    if (!dlg || typeof dlg.showModal !== 'function') {
      clearAutosave();
      return false;
    }
    const restoreBtn = $('btnAutosaveRestore');
    const discardBtn = $('btnAutosaveDiscard');
    if (restoreBtn) {
      restoreBtn.onclick = () => {
        try { dlg.close(); } catch { /* ignore */ }
        applyAutosaveData(data);
      };
    }
    if (discardBtn) {
      discardBtn.onclick = () => {
        clearAutosave();
        try { dlg.close(); } catch { /* ignore */ }
      };
    }
    if (!dlg.open) dlg.showModal();
    return true;
  } catch { return false; }
}

// ---------- boot ----------
document.querySelectorAll('.tl-chip[data-icon]').forEach((c) => {
  c.innerHTML = ICON[c.dataset.icon] || '';
});

// A1/A2 accordion, folded into the audio track
$('jcutToggle').addEventListener('click', () => {
  if (!(S.jcut && S.jcut.length)) return;
  S.jcutOpen = !S.jcutOpen;
  localStorage.setItem('ativa-vid.jcutOpen', S.jcutOpen ? '1' : '0');
  renderJcutAudio();
  updateScrollRange();
  positionNeedle();
});

wireAiAndSafe();
wireProxyFallback();
loadSharedDefaultStyle().then(async () => {
  await detectProxy();
  await refreshScorePill();
  poll();
  setTimeout(() => restoreAutosave(), 800);
});
// autosave on edits
const _pushHistory = pushHistory;
pushHistory = function(snap) {
  _pushHistory(snap);
  scheduleAutosave();
}; // wait for it once — a flash of the wrong default is worse than a beat of delay
rafLoop();
// the headline fit is MEASURED, so it is wrong until Poppins is actually
// loaded — rebuild once the fonts land
if (document.fonts && document.fonts.ready) {
  document.fonts.ready.then(() => { if (S.style) renderSetup(); });
}

// --- "Identidade visual" do hub: parar na seção certa ---------------------
//
// Os quadros da tela de Marca prometiam "abrem já na seção certa" e não
// cumpriam: eram `data-view="estilo"` sem destino nenhum, então os três caíam
// no topo do editor. O hub agora manda o destino por `postMessage` (não pelo
// `src`, que recarregaria o editor e perderia ajuste não salvo).
const IR_ALVOS = {
  accent: '#optAccent',
  fontes: '#autoCapFont',
  cartao: '#optElements',
};

function irParaSecao(alvo, tentativa = 0) {
  const sel = IR_ALVOS[alvo];
  if (!sel) return;
  const el = document.querySelector(sel);
  // O editor monta os controles depois de ler o estado; na primeira abertura
  // a mensagem chega antes disso. Tenta de novo por até ~3s e então desiste.
  if (!el || !el.offsetParent) {
    if (tentativa < 12) setTimeout(() => irParaSecao(alvo, tentativa + 1), 250);
    return;
  }
  // Os grupos vivem dentro de <details>; num fechado o alvo tem altura 0 e a
  // rolagem para no lugar errado.
  for (let d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) {
    d.open = true;
  }
  // O MAIS PRÓXIMO dos dois, não `.setup-group` primeiro: o seletor de fonte
  // fica dentro do grupo "Tipo de conteúdo e formato", que ocupa vários
  // milhares de pixels — realçá-lo não aponta nada, e centralizá-lo joga o
  // campo para fora da tela. Foi o que aconteceu no primeiro teste.
  const caixa = el.closest('.auto-field, .setup-group') || el;
  // SEM `behavior: 'smooth'`: medido neste iframe, o suave nao rola nada —
  // o instantaneo leva o `main` a 2142 e o suave o deixa em 0. O app roda em
  // Edge WebView2, entao seria um botao que nao faz nada, calado. O realce
  // abaixo e o que explica o salto.
  caixa.scrollIntoView({ block: 'center' });
  caixa.classList.add('ir-piscou');
  setTimeout(() => caixa.classList.remove('ir-piscou'), 1800);
}

window.addEventListener('message', (e) => {
  if (!e.data || e.data.type !== 'ativavid-ir-para') return;
  irParaSecao(String(e.data.alvo || ''));
});
