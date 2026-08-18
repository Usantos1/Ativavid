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
  flag: '<svg viewBox="0 0 16 16"><rect x="1.9" y="1.4" width="1.6" height="13.2" rx=".8"/><path d="M5 2.7h7.6a.6.6 0 0 1 .47.97L11.36 6l1.71 2.33a.6.6 0 0 1-.47.97H5V2.7z"/></svg>',
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
    {id: 'simples', name: 'Simples', stat: 'simples'},
    {id: 'serifada', name: 'Serifada', stat: 'serifada'},
    {id: 'classica', name: 'Clássica', stat: 'classica'},
    {id: 'bloco', name: 'Bloco', stat: 'bloco'},
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
  const upperHl = styleId === 'card' || styleId === 'manchete' || styleId === 'carimbo';
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
  if (styleId === 'realce') {
    for (const l of lines) {
      if (!l) continue;
      const b = el('div', 'hl-block', box);
      b.style.fontSize = `${size}px`;
      b.style.borderRadius = `${12 * s}px`;
      b.textContent = l;
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
};
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
  const wOf = (ws) => measureType(
    (V.sticker ? ws.join(' ').toUpperCase() : ws.join(' ')),
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
  captions: [], // grouped caption lines [{text,start,end}] (rendered space)
  editData: null, // edit-data.json content (phase 2)
  insertsDraft: [], // editable inserts [{kind,label,start,end,ref,orig}]
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
  toast(`${side === 'l' ? 'IN' : 'OUT'} ${fmt(side === 'l' ? r.start : r.end)}  ` +
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
function splitAtPlayhead() {
  if (S.applying) return;
  if (S.tab !== 1) { toast('Corte só na aba Edição', 1600); return; }
  if (S.selected < 0) { toast('Selecione um take pra cortar', 1600); return; }
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
  S.draft = snap.draft;
  S.insertsDraft = snap.insertsDraft;
  S.notes = snap.notes;
  if (snap.style) S.style = snap.style;
  S.captionFixes = snap.captionFixes || {};
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
function insertsDirty() {
  // isNew: added from the image picker this session, so there is no orig to
  // diff against — it is dirty by existing at all
  return S.insertsDraft.some((c) => c.isNew || c.start !== c.orig.start || c.end !== c.orig.end);
}
function dirtyCount() {
  let n = S.draft.filter((r) => r.added || r.removed || r.start !== r.orig.start || r.end !== r.orig.end).length;
  n += S.insertsDraft.filter((c) => c.isNew || c.start !== c.orig.start || c.end !== c.orig.end).length;
  n += S.notes.length; // each correction marker is an unsaved adjustment too
  n += Object.keys(S.captionFixes).length; // and each caption text fix
  return n;
}
function pendingFlags() {
  const d = (S.corrections && S.corrections.dirty) || {};
  return {
    headline: !!d.headline,
    captions: !!d.captions || Object.keys(S.captionFixes).length > 0,
    edl: !!d.edl || edlDirty(),
    style: !!d.style,
  };
}
function pendingList() {
  const f = pendingFlags();
  const labels = { headline: 'headline', captions: 'legenda', edl: 'corte', style: 'estilo' };
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
  const hint = $('applyHint');
  if (hint) {
    hint.classList.add('hidden');
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

async function persistCaptionFix(from, to, extra) {
  const data = await persistCorrection({ op: 'fix_caption', from, to, ...(extra || {}) });
  if (data && data.ok === false) {
    toast(data.error || 'Essa palavra aparece mais de uma vez. Clique na legenda certa.', 3600);
    return data;
  }
  if (data && Array.isArray(data.captionWords) && data.captionWords.length) {
    S.captions = groupCaptions(data.captionWords);
    S.captionFixes = {};
  }
  return data;
}

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

function beginHeadlineEdit() {
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
    const range = document.createRange();
    range.selectNodeContents(line);
    const sel = window.getSelection();
    sel.removeAllRanges();
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
  const next = window.prompt(
    answerMode ? 'Resposta desta headline' : 'Headline deste vídeo', cur);
  if (next != null) commitHeadline(next, answerMode);
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
    const text = c ? (fix ? fix.to : c.text) : '—';
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
  if (title && file && title.toLowerCase() !== file.toLowerCase()) {
    pn.textContent = title;
    if (meta) {
      meta.textContent = bits.filter(Boolean).join(' · ');
      meta.classList.toggle('hidden', bits.filter(Boolean).length === 0);
    }
  } else {
    pn.textContent = file || 'ATIVAVID';
    if (meta) {
      const extra = bits.slice(1);
      meta.textContent = extra.join(' · ');
      meta.classList.toggle('hidden', extra.length === 0);
    }
  }
}

// ---------- data loading ----------
async function poll() {
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
  setTimeout(poll, S.applying ? 700 : 2000);
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
  if (data.intent) {
    S.protectedRanges = Array.isArray(data.intent.protectedRanges) ? data.intent.protectedRanges : [];
    S.contentType = data.intent.contentType || S.contentType;
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
  S.captionsSigBefore = JSON.stringify((S.captions || []).map((c) => c.text));

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
      } catch (e) { /* absent yet */ }
    }
    if (S.state.editData) {
      try {
        S.editData = await (await fetch(`${mediaHref(S.state.editData)}?v=${Date.now()}`)).json();
        buildInsertsDraft();
      } catch (e) { /* absent yet */ }
    }
  }

  // see S.captionsSigBefore above: only discard pending caption fixes when the
  // caption lines themselves actually changed under us
  if (JSON.stringify(S.captions.map((c) => c.text)) !== S.captionsSigBefore) {
    S.captionFixes = {};
    closeCaptionEditor();
  }

  fitZoom();
  renderAll();
  renderSetup();
  refreshHeader();
  loadPostCaption(); // picks up a caption written between polls
  loadBrandPresets({ applyActive: !!(HOUSE_STYLE || HUB_EMBED) });
}

// Fase 1 plays the clean cut; Fase 2 plays the Phase-2 render (state.finalVideo)
// when it exists, so captions/inserts are visible. Keeps the playback position.
function updateVideoSrc() {
  const wantFinal = S.tab === 2 && S.state.finalVideo && !S.finalFailed;
  let rel = wantFinal ? S.state.finalVideo : (S.state.video || 'cut.mp4');
  // proxy leve no corte (Fase 1) quando existir — scrub mais fluido
  if (S.tab !== 2 && S.hasProxy && !S.proxyFailed && rel === 'cut.mp4') rel = 'cut_proxy.mp4';
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
  el('div', 'spacer', acts);
  const ok = el('button', 'btn primary small', acts);
  ok.textContent = 'aplicar';

  const commit = () => {
    const v = input.value.trim();
    closeCaptionEditor();
    if (!v || v === c.text) {
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
  // Estilo Limpa = quadro cheio. Sem cards de imagem por cima — só o que o
  // usuário colocar à mão depois (isNew no draft). Pipeline/IA não deixam inserts.
  const edit = (S.style && S.style.edit) || 'limpa';
  if (String(edit).toLowerCase() !== 'limpa') return false;
  let changed = false;
  if (S.editData && Array.isArray(S.editData.inserts) && S.editData.inserts.length) {
    S.editData.inserts = [];
    changed = true;
  }
  return changed;
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
  S.insertsDraft = list.map((c) => ({ ...c, orig: { start: c.start, end: c.end } }));
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
  $('markText').textContent = S.pendingIn != null ? 'OUT' : 'IN';
}

function toggleMark() {
  const t = renderedToDraft(video.currentTime || 0);
  if (S.pendingIn == null) {
    S.pendingIn = t;
    renderNotes();
    toast('IN marcado — leve a agulha ao fim do trecho e marque o OUT', 2600);
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
const HL_ACCENT_USERS = ['realce', 'misto', 'sombra', 'sublinhado', 'pilula', 'manchete', 'carimbo', 'pergunta'];
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
const CAP_BASE_STYLES = ['karaoke', 'simples', 'serifada', 'classica', 'bloco', 'recorte'];
const CAP_EMPH_STYLES = ['stacked', 'scatter', 'impacto'];
const CAP_CIRCLE_STYLES = ['stacked'];
const legendaAccentUsed = () => capAccentUsed() && CAP_BASE_STYLES.includes(S.style.captions);
const emphasisAccentUsed = () => capAccentUsed() && CAP_EMPH_STYLES.includes(S.style.captions);
const circleAccentUsed = () => capAccentUsed() && CAP_CIRCLE_STYLES.includes(S.style.captions);

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
  // Ajuda é da timeline — some na aba Estilos / embed do hub
  const help = $('btnHelp');
  if (help) help.classList.toggle('hidden', show || HUB_EMBED || HOUSE_STYLE);

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

  $('setupGo').textContent = HOUSE_STYLE
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
      // Only the abstract mockups get a title — a card that renders the real
      // caption or headline is already labelled by itself. "Nenhuma" renders
      // nothing to read, so it needs the label just as much as a mockup does.
      if (o.mock || o.none) el('div', 'opt-name', card).textContent = o.name;
      el('div', 'opt-mark', card);
    }
    // the ghost only earns its space where there is a single option to explain
    if (opts.length < 2) el('div', 'opt ghost', host).textContent = 'mais estilos em breve';
  };
  // set BEFORE the demos are built: buildHeadlineDemo/the caption demos read
  // the accents through var(), so the variables have to be in place when the
  // previews first paint
  applyAccent();
  applyCaptionAccent();
  applyEmphasisAccent();
  applyCircleAccent();

  radios($('optEdit'), 'edits', S.style.edit);
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
      elements: { ...S.style.elements },
      fastMode: !!S.fastMode,
      oneClick: !!S.fastMode,
      rhythm: S.style.rhythm || 'dinamico',
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
    headlineDuration: S.style.headlineDuration || 'curta',
    headlineAnimation: S.style.headlineAnimation || 'padrao',
      headlineDuration: S.style.headlineDuration || 'curta',
    headlineAnimation: S.style.headlineAnimation || 'padrao',
      headlineAnimation: S.style.headlineAnimation || 'padrao',
      exportPreset: S.style.exportPreset || 'reels',
      colorGrade: S.style.colorGrade || 'marca',
      endCardCopy: S.endCardCopy || null,
      contentType: S.contentType || $('autoContentType')?.value || null,
      note: S.style.note || '',
    };
    const res = await fetch('/api/default-style', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(house),
    });
    if ((await res.json()).ok) {
      SHARED_DEFAULT_STYLE = house;
      if (S.brandPresets && S.brandPresets.activeId) {
        fetch('/api/brand-presets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action: 'update',
            brandId: S.brandPresets.brandId || 'padrao',
            id: S.brandPresets.activeId,
            style: house,
          }),
        }).catch(() => {});
      }
      toast('✓ Estilo padrão salvo', 2000);
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

  const rerender = !S.state.awaitingStyle;
  const payload = {
    // a save with Fase 2 already on disk is a RE-RENDER request, not a first
    // pick — the skill has to know which of the two it is looking at
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
    elements: { ...S.style.elements },
    elementNames: STYLE_CATALOG.elements
      .filter((e) => S.style.elements[e.id])
      .map((e) => e.name),
    note: S.style.note,
    fastMode: !!S.fastMode,
    oneClick: !!S.fastMode,
    rhythm: S.style.rhythm || 'dinamico',
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
    headlineDuration: S.style.headlineDuration || 'curta',
    headlineAnimation: S.style.headlineAnimation || 'padrao',
    exportPreset: S.style.exportPreset || 'reels',
    colorGrade: S.style.colorGrade || 'marca',
  };
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
    elements: { ...S.style.elements },
    // Policy, not looks — but it belongs with the house preset because it only
    // makes sense WITH one: "fast" means "the recipe is already decided", and
    // without a saved recipe there is nothing to skip the asking for.
    fastMode: !!S.fastMode,
    oneClick: !!S.fastMode,
    rhythm: S.style.rhythm || 'dinamico',
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
    headlineDuration: S.style.headlineDuration || 'curta',
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
    const c = el('div', 'clip', laneVideo);
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
  insertTracksEl.classList.toggle('hidden', !phase2);
  insertTracksEl.innerHTML = '';
  if (!showCaps) return;

  laneCaptions.innerHTML = '';
  const edlPending = !!(S.corrections && S.corrections.dirty && S.corrections.dirty.edl);
  if (!edlPending) {
    S.captions.forEach((c, i) => {
      const start = renderedToDraft(c.start);
      const end = renderedToDraft(c.end);
      const fix = S.captionFixes[i];
      const chip = el('div', 'chip caption' + (fix ? ' fixed' : ''), laneCaptions);
      chip.style.left = `${start * S.pps}px`;
      chip.style.width = `${Math.max((end - start) * S.pps, 6)}px`;
      chip.textContent = fix ? fix.to : c.text;
      chip.title = fix
        ? `“${c.text}” → “${fix.to}” (clique para editar)`
        : `${c.text} — clique para corrigir o texto`;
      chip.dataset.ci = String(i);
    });
  }

  // Inserts stay Fase-2 only: they describe the Phase-2 render, and on the
  // Fase-1 cut there is nothing for them to sit against.
  if (!phase2) return;

  // TEXT and IMAGE get their own tracks — a headline and a photo are different
  // kinds of edit, and mixing them on one lane hid the images entirely.
  const isText = (c) => c.kind === 'hook' || c.kind === 'word';
  const groups = [
    { icon: 'text', cls: 'teal', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => isText(c)) },
    { icon: 'inserts', cls: 'orange', items: S.insertsDraft.map((c, i) => ({ c, i })).filter(({ c }) => !isText(c)) },
  ];

  for (const g of groups) {
    if (!g.items.length) continue;
    // overlapping elements stack onto extra lanes within the same group
    const order = [...g.items].sort((a, b) => a.c.start - b.c.start || a.c.end - b.c.end);
    const trackEnd = [];
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
      const lab = el('div', 'track-label', trk);
      // only the first lane of a group carries the icon; the rest are continuations
      if (t === 0) el('span', `tl-chip ${g.cls}`, lab).innerHTML = ICON[g.icon];
      lanes.push(el('div', 'lane', trk));
    }
    for (const { c, i } of g.items) {
      const chip = el('div', `chip insert ${isText(c) ? 'hook' : ''}`, lanes[assign.get(i) ?? 0]);
      chip.style.left = `${c.start * S.pps}px`;
      chip.style.width = `${Math.max((c.end - c.start) * S.pps, 10)}px`;
      chip.textContent = c.label;
      chip.title = c.label;
      chip.dataset.i = i;
      if (c.start !== c.orig.start || c.end !== c.orig.end) chip.classList.add('dirty');
      el('div', 'handle l', chip).dataset.i = i;
      el('div', 'handle r', chip).dataset.i = i;
    }
  }

  // soundtrack → its own read-only track, one chip spanning the whole video
  const st = S.editData && S.editData.soundtrack;
  if (st && st.enabled) {
    const trk = el('div', 'track', insertTracksEl);
    el('span', 'tl-chip olive', el('div', 'track-label', trk)).innerHTML = ICON.music;
    const lane = el('div', 'lane', trk);
    const chip = el('div', 'chip music', lane);
    const dur = S.editData.durationSec || S.videoDuration || draftTotal();
    chip.style.left = '0px';
    chip.style.width = `${Math.max(dur * S.pps, 10)}px`;
    const name = (st.file || 'trilha.mp3').split('/').pop();
    const vol = st.volume != null ? `  ·  vol ${st.volume}` : '';
    chip.textContent = `${name}${vol}`;
    chip.title = chip.textContent;
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
function positionNeedle() {
  const tDraft = renderedToDraft(video.currentTime || 0);
  const x = LABEL_W + tDraft * S.pps;
  needle.style.left = `${x}px`;
  needle.style.visibility = x < panel.scrollLeft + LABEL_W ? 'hidden' : '';
  $('timeNow').textContent = fmt(tDraft);
  $('timeTotal').textContent = fmt(draftTotal() || S.videoDuration);
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
  // fonte da marca — mesmo catálogo do render (fonts.ts)
  const FONT_CSS = {
    poppins: "'Poppins',sans-serif", inter: "'Inter',sans-serif",
    montserrat: "'Montserrat',sans-serif", playfair: "'Playfair Display',serif",
    lora: "'Lora',serif", anton: "'Anton',sans-serif",
    bebas: "'Bebas Neue',sans-serif", archivo: "'Archivo Black',sans-serif",
  };
  // posição/tamanho do preset — mesmo mapa do render (_apply_caption_geometry)
  const capPos = S.style.captionPosition || 'baixo';
  const posBottom = capPos === 'centro' ? 900 : capPos === 'alto' ? 1330 : V.bottom;
  const capScale = { p: 0.85, m: 1, g: 1.18 }[S.style.captionSize] || 1;

  box.classList.remove('hidden');
  box.style.paddingBottom = `${posBottom * s}px`;
  const sig = `${i}|${text}|${style}|${capPos}|${capScale}|${Math.round(s * 100)}`;
  if (box.dataset.sig === sig && box.querySelector('.cap-overlay-line')) {
    highlightCurrentCaption(i);
    return;
  }
  box.dataset.sig = sig;
  box.innerHTML = '';
  const line = el('div', 'cap-overlay-line' + (V.ink === 'slab' ? ' slab' : ''), box);
  line.style.fontFamily = (style !== 'stacked' && FONT_CSS[S.style.captionFont]) || V.family;
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
  highlightCurrentCaption(i);
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
  const want = showLines.join('\n');
  let line = box.querySelector('.hl-overlay-line');
  if (!line) {
    box.innerHTML = '';
    line = el('div', 'hl-overlay-line', box);
  }
  if (line.textContent !== want) line.textContent = want;
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
  updateCapOverlay();
  updateHlOverlay();
  highlightCurrentCaption(currentCaptionIndex());
  if (capAnims.length) {
    const now = performance.now() / 1000;
    for (const step of capAnims) step(now);
  }
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
  // The gutter is chrome, not timeline. Without this guard a pointerdown on a
  // track icon fell through to the scrub branch below, which both yanked the
  // needle to 0 (the gutter is left of t=0, so it computes a negative time) and
  // called setPointerCapture on the panel — retargeting the following click and
  // swallowing it, so a real click on the A1/A2 disclosure never fired while a
  // programmatic .click() did.
  if (e.target.closest('.track-label') || e.target.closest('button')) return;

  const handle = e.target.closest('.handle');
  const clip = e.target.closest('.clip');
  const chip = e.target.closest('.chip.insert');

  // caption chips are click-to-edit, not draggable — their timing belongs to
  // the transcript, only the WORDS are the user's to correct here
  const cap = e.target.closest('.chip.caption');
  if (cap) {   // any tab the chips render on — Fase 1 is where fixing pays off
    openCaptionEditor(+cap.dataset.ci, cap);
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
  if (handle && chip && S.tab === 2) {
    const i = +handle.dataset.i;
    drag = { type: 'chip-trim', i, side: handle.classList.contains('l') ? 'l' : 'r', x0: e.clientX, c: { ...S.insertsDraft[i] }, preSnapshot: snapshotState() };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (chip && S.tab === 2) {
    const i = +chip.dataset.i;
    drag = { type: 'chip-move', i, x0: e.clientX, c: { ...S.insertsDraft[i] }, preSnapshot: snapshotState() };
    try { panel.setPointerCapture(e.pointerId); } catch (err) { /* synthetic/touch */ }
    e.preventDefault();
    return;
  }
  if (clip && S.tab === 1) {
    // Undecided yet between "click to select" and "drag to select-and-delete
    // a range" — pointermove below promotes this to the latter only past a
    // few px of real movement, so a plain click keeps working exactly as
    // before. See deleteClipRange().
    drag = { type: 'clip-range', i: +clip.dataset.i, x0: e.clientX, x1: e.clientX, moved: false };
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
  } else if (drag.type === 'clip-range') {
    drag.x1 = e.clientX;
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
    if (drag && drag.preSnapshot) {
      const moved = drag.type === 'trim'
        ? (S.draft[drag.i].start !== drag.r.start || S.draft[drag.i].end !== drag.r.end)
        : (S.insertsDraft[drag.i].start !== drag.c.start || S.insertsDraft[drag.i].end !== drag.c.end);
      if (moved) {
        pushHistory(drag.preSnapshot);
        if (drag.type === 'trim') persistEdl();
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
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && S.selected >= 0 && S.tab === 1) {
    toggleSelectedTake();
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
document.querySelector('.player-frame')?.addEventListener('click', (e) => {
  if (isTypingContext()) return;
  if (e.target.closest('button, .cap-overlay-line, .hl-overlay-line, #capEditor, #hlOverlay')) return;
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
$('btnSplit').innerHTML = `${ICON.razor}<span>Cortar</span>`;
$('btnSplit').addEventListener('click', splitAtPlayhead);
$('btnDeleteTake').innerHTML = `${ICON.trash}<span>Excluir</span>`;
$('btnDeleteTake').addEventListener('click', toggleSelectedTake);
$('coverIcon').innerHTML = ICON.cover;
$('btnCover').addEventListener('click', saveCoverFromPlayhead);
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
    toast('Abra o vídeo pelo app para acrescentar um take no fim', 2800);
    return;
  }
  const btn = $('btnAppendCta');
  if (btn) btn.disabled = true;
  toast('Colocando o vídeo no fim…', 1600);
  try {
    const duration = await probeLocalDuration(file);
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
    const last = [...S.draft].reverse().find((r) => !r.removed);
    if (last && String(last.beat || '').toUpperCase() === 'CTA') {
      last.beat = 'KEEP';
    }
    S.state.sourceDurations = S.state.sourceDurations || {};
    S.state.sourceDurations[data.source] = dur;
    S.draft.push({
      source: data.source,
      start: 0,
      end: dur,
      beat: 'CTA',
      removed: false,
      added: true,
      filePath: data.path,
      srcIdx: null,
      orig: { start: 0, end: dur },
    });
    S.selected = S.draft.length - 1;
    renderAll();
    refreshHeader();
    toast('CTA no fim — clique em Salvar para renderizar', 3200);
  } catch (err) {
    toast((err && err.message) || 'Não deu para acrescentar esse vídeo', 3200);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function toggleSelectedTake() {
  if (S.applying) return;
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
  const btn = $('btnDeleteTake');
  if (!btn) return;
  const r = S.selected >= 0 ? S.draft[S.selected] : null;
  const can = S.tab === 1 && !!r;
  btn.disabled = !can;
  btn.classList.toggle('danger-on', !!(r && r.removed));
  btn.title = !can
    ? 'Selecione um take para excluir'
    : (r.removed ? 'Restaurar o take selecionado (Delete)' : 'Excluir o take selecionado (Delete)');
}

async function saveCoverFromPlayhead() {
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
  video.addEventListener(ev, updateCapOverlay)
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
  IMG_TAB = tab === 'library' ? 'library' : 'pexels';
  const pex = $('imgTabPexels');
  const lib = $('imgTabLibrary');
  if (pex) pex.classList.toggle('active', IMG_TAB === 'pexels');
  if (lib) lib.classList.toggle('active', IMG_TAB === 'library');
  $('imgPexelsPane')?.classList.toggle('hidden', IMG_TAB !== 'pexels');
  $('imgLibraryPane')?.classList.toggle('hidden', IMG_TAB !== 'library');
  $('imgHint').textContent = IMG_TAB === 'library'
    ? 'Arquivos da pasta Biblioteca — clique para inserir na agulha.'
    : 'A imagem escolhida entra na trilha de inserts, na posição da agulha.';
  if (IMG_TAB === 'library') loadLibraryResults();
  else $('imgResults').innerHTML = '';
}

$('btnImage').innerHTML = ICON.imgSearch;
$('btnImage').addEventListener('click', () => {
  if (S.tab !== 2) { toast('A busca de imagem é da aba Final (Visual)', 2200); return; }
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
$('imgLibUpload')?.addEventListener('change', async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file, file.name);
  const folder = projectFolder();
  const qs = folder ? `?use=1&folder=${encodeURIComponent(folder)}` : '';
  toast('Enviando…', 1500);
  try {
    const res = await fetch(`/api/library/upload${qs}`, { method: 'POST', body: fd });
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.error || 'falha no upload');
    if (data.used && data.used.src) {
      pushInsertFromRef(data.used.src, data.name || file.name, data.used.credit || 'biblioteca');
      toggleImgPicker(false);
      toast('✓ Arquivo na biblioteca e na timeline', 3500);
    } else {
      await loadLibraryResults();
      toast('✓ Salvo na biblioteca — clique para inserir', 3000);
    }
  } catch (err) {
    toast(err.message || 'Upload falhou', 3500);
  }
});

async function loadLibraryResults() {
  const box = $('imgResults');
  box.innerHTML = '<div class="img-empty">carregando biblioteca…</div>';
  let data;
  try {
    data = await (await fetch('/api/library')).json();
  } catch {
    box.innerHTML = '<div class="img-empty">falha ao listar biblioteca</div>';
    return;
  }
  const items = data.items || [];
  if (!items.length) {
    box.innerHTML = '<div class="img-empty">Biblioteca vazia — use Enviar arquivo ou abra a pasta</div>';
    return;
  }
  box.innerHTML = '';
  items.forEach((it) => {
    const card = el('button', 'img-card', box);
    const thumb = `/api/library/file?rel=${encodeURIComponent(it.rel)}`;
    if (it.kind === 'clip') {
      card.innerHTML = `<div class="img-clip-ph">▶</div><span class="img-credit">${it.name}</span>`;
    } else {
      card.innerHTML = `<img src="${thumb}" alt=""><span class="img-credit">${it.name}</span>`;
    }
    card.addEventListener('click', () => pickLibraryAsset(it));
  });
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
  pushInsertFromRef(data.src || data.ref, it.name, it.name);
  toggleImgPicker(false);
  toast('✓ Inserido da biblioteca — arraste e Salvar', 4000);
}

function pushInsertFromRef(src, label, credit) {
  pushHistory();
  const start = Math.max(0, renderedToDraft(video.currentTime));
  const end = start + 2.5;
  S.insertsDraft.push({
    kind: 'insert', label: label || (src || '').split('/').pop(),
    start, end, orig: { start, end },
    isNew: true, src, credit: credit || '',
  });
  renderAll(); refreshHeader();
  scheduleAutosave();
}

$('imgGo').addEventListener('click', async () => {
  const q = $('imgQuery').value.trim();
  if (!q) return;
  const box = $('imgResults');
  box.innerHTML = '<div class="img-empty">buscando…</div>';
  let data;
  try {
    data = await (await fetch(`${BASE}/api/images/search?q=${encodeURIComponent(q)}`)).json();
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
    card.innerHTML = `<img src="${r.thumb}" alt=""><span class="img-credit">${r.credit}</span>`;
    card.addEventListener('click', () => pickImage(q, r));
  });
});

async function pickImage(query, r) {
  toast('Baixando…', 1500);
  let data;
  try {
    data = await (await fetch(`${BASE}/api/images/pick`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: r.full, id: r.id, query, credit: r.credit }),
    })).json();
  } catch (e) {
    toast('Falha ao baixar a imagem', 3000);
    return;
  }
  if (!data.ok) { toast(data.error || 'Falha ao baixar', 3000); return; }

  pushInsertFromRef(data.ref, data.ref.split('/').pop(), data.credit);
  toggleImgPicker(false);
  toast('✓ Imagem inserida — arraste pra ajustar, depois Salvar', 4000);
}

// header — pasta do projeto, vídeo final, foco e menu •••
const openFolderBtn = $('btnOpenFolder');
const openFolderIcon = $('openFolderIcon');
if (openFolderIcon && typeof ICON !== 'undefined' && ICON.folder) {
  openFolderIcon.innerHTML = ICON.folder;
}
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

function closeHeadMore() {
  $('headMoreMenu')?.classList.add('hidden');
  $('btnHeadMore')?.setAttribute('aria-expanded', 'false');
}
$('btnHeadMore')?.addEventListener('click', (e) => {
  e.stopPropagation();
  const menu = $('headMoreMenu');
  if (!menu) return;
  const open = menu.classList.contains('hidden');
  menu.classList.toggle('hidden', !open);
  $('btnHeadMore').setAttribute('aria-expanded', open ? 'true' : 'false');
});
document.addEventListener('click', (e) => {
  if (e.target.closest?.('#headMore')) return;
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


// ---------- desktop: marcação IN/OUT → aplicar + fila ----------
function noteLooksLikeRemove(text) {
  const s = String(text || '').toLowerCase();
  return /remov|apag|cort|tir[ae]|exclu|deleta|fora|tira isso|corta isso|sem isso/.test(s);
}

function removeDraftTimeRange(tStart, tEnd) {
  if (!(tEnd > tStart + 0.04)) return false;
  pushHistory();
  let changed = false;
  // iterate by index while draft mutates — always re-layout
  let guard = 0;
  while (guard++ < 64) {
    const dl = draftLayout();
    let hit = -1;
    let srcA = 0;
    let srcB = 0;
    for (let i = 0; i < dl.length; i++) {
      const d = dl[i];
      if (d.removed || d.dur <= 0) continue;
      const clipStart = d.out;
      const clipEnd = d.out + d.dur;
      if (tEnd <= clipStart || tStart >= clipEnd) continue;
      const overlapA = Math.max(tStart, clipStart);
      const overlapB = Math.min(tEnd, clipEnd);
      srcA = draftTimeToSource(i, overlapA);
      srcB = draftTimeToSource(i, overlapB);
      if (srcB - srcA < MIN_SEG) continue;
      hit = i;
      break;
    }
    if (hit < 0) break;
    const r = S.draft[hit];
    const pieces = [];
    if (srcA - r.start >= MIN_SEG) {
      pieces.push({
        source: r.source, start: r.start, end: srcA, beat: r.beat,
        removed: false, srcIdx: null, orig: { start: r.start, end: r.end },
      });
    }
    pieces.push({
      source: r.source, start: srcA, end: srcB, beat: r.beat,
      removed: true, srcIdx: null, orig: { start: r.start, end: r.end },
    });
    if (r.end - srcB >= MIN_SEG) {
      pieces.push({
        source: r.source, start: srcB, end: r.end, beat: r.beat,
        removed: false, srcIdx: null, orig: { start: r.start, end: r.end },
      });
    }
    S.draft.splice(hit, 1, ...pieces);
    changed = true;
  }
  if (changed) {
    S.selected = -1;
    renderAll();
    refreshHeader();
  }
  return changed;
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
    // Em limpa: só inserts que o usuário acabou de criar à mão (isNew).
    const keepInsert = (c) => c.kind === 'insert' && !c.isNew && !limpa;
    const keepNew = (c) => c.kind === 'insert' && c.isNew;
    payload.editData = {
      inserts: S.insertsDraft.filter(keepInsert).map((c) => ({
        ref: c.ref, start: +c.start.toFixed(3), end: +c.end.toFixed(3),
      })),
      newInserts: S.insertsDraft.filter(keepNew).map((c) => ({
        src: c.src, credit: c.credit || '', start: +c.start.toFixed(3), end: +c.end.toFixed(3),
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
  if (capFixes.length) {
    payload.captionFixes = capFixes.map((f) => ({
      from: f.from, to: f.to,
      renderedStart: +f.start.toFixed(3),
      renderedEnd: +f.end.toFixed(3),
    }));
  }
  if (!payload.edl && !payload.editData && !payload.notes && !payload.captionFixes && !payload.extraSources) {
    toast('Nada para salvar', 2000);
    return false;
  }
  const res = await fetch(`${BASE}/api/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    toast('Erro ao salvar — o servidor está de pé?', 4000);
    return false;
  }
  S.savedPending = true;
  S.notes = [];
  S.captionFixes = {};
  S.pendingIn = null;
  S.draft.forEach((r) => {
    r.orig = { start: r.start, end: r.end };
    r.added = false;
    if (r.removed) r.hardRemoved = true;
  });
  S.draft = S.draft.filter((r) => !r.removed);
  S.insertsDraft.forEach((c) => { c.orig = { start: c.start, end: c.end }; });
  S.history = [];
  S.future = [];
  refreshUndoRedoButtons();
  renderAll();
  refreshHeader();

  const captionOnly = !!(payload.captionFixes && !payload.edl && !payload.editData && !payload.extraSources);
  if (BASE && BASE.startsWith('/p/') && !captionOnly) {
    const folder = projectFolder() || decodeURIComponent(BASE.slice('/p/'.length).split('/')[0]);
    try {
      await fetch('/api/jobs/requeue-folder', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder, extraSources }),
      });
    } catch { /* ignore */ }
    toast('✓ Enviado à fila de edição', 2800);
    setTimeout(() => { location.href = '/?view=fila'; }, 500);
    return true;
  }
  if (captionOnly) {
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
    removeDraftTimeRange(start, end);
    S.notes = S.notes.filter((x) => x.id !== n.id);
  }
  renderNotes();
  refreshHeader();
  // Confirmar = salvar + voltar à fila (não só rascunho local)
  await saveEditsAndReturnToQueue();
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
$('btnHelp').addEventListener('click', () => toggleHelp($('helpModal').classList.contains('hidden')));
$('helpClose').addEventListener('click', () => toggleHelp(false));
$('helpBackdrop').addEventListener('click', () => toggleHelp(false));
$('noteText').addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.stopPropagation(); closeNoteEditor(); }
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); $('noteOk').click(); }
});
$('btnFit').addEventListener('click', () => { fitZoom(); renderAll(); });
if ($('btnZoomOut')) $('btnZoomOut').addEventListener('click', () => bumpZoom(1 / 1.4));
$('btnZoom100').addEventListener('click', () => setZoom100());
$('btnZoomIn').addEventListener('click', () => bumpZoom(1.4));
panel.addEventListener('scroll', () => requestAnimationFrame(() => { drawRuler(); drawWave(); positionNeedle(); }));
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
  const path = HOUSE_STYLE ? '/estilo-padrao' : (BASE + TAB_TO_PATH[S.tab]);
  const search = HUB_EMBED ? '?embed=1' : '';
  // a real nav here (not applyState's replaceState) — a click is a place the
  // user meant to go, so back/forward should be able to return to it
  if (location.pathname !== path || (HUB_EMBED && location.search.indexOf('embed=1') < 0)) {
    history.pushState(null, '', path + search);
  }
  updateVideoSrc(); // Fase 2 plays the Phase-2 render when available
  renderAll();
  renderSetup();
  loadPostCaption();
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

if ($('hlOverlay')) {
  $('hlOverlay').addEventListener('click', (e) => {
    e.stopPropagation();
    beginHeadlineEdit();
  });
}
if ($('capOverlay')) {
  $('capOverlay').addEventListener('click', (e) => {
    e.stopPropagation();
    const i = currentCaptionIndex();
    if (i >= 0) openCaptionEditor(i, e.target.closest('.cap-overlay-line') || e.target);
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
    else toast('Avance o vídeo até aparecer a legenda', 1800);
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
function toast(msg, ms) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms || 3000);
}


// ---------- automação / safe zone / IA edit / score ----------
function refreshAutoControls() {
  const st = S.style || {};
  const map = [
    ['autoRhythm', 'rhythm', 'dinamico'],
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
    ['autoHlDuration', 'headlineDuration', 'curta'],
    ['autoHlAnim', 'headlineAnimation', 'padrao'],
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
};

function applyRhythmPreset(id) {
  const p = RHYTHM_PRESETS[id];
  if (!p) return;
  if (!S.style) S.style = defaultStyle();
  Object.assign(S.style, p);
  refreshAutoControls();
  document.querySelectorAll('.rhythm-preset').forEach((b) => {
    b.classList.toggle('on', b.dataset.preset === id);
  });
}

function wireAutoControls() {
  const map = [
    ['autoRhythm', 'rhythm'],
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
    ['autoHlDuration', 'headlineDuration'],
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

async function detectProxy() {
  try {
    const r = await fetch(`${BASE}/media/cut_proxy.mp4`, { method: 'HEAD' });
    S.hasProxy = r.ok;
    if (r.ok) S.proxyFailed = false;
  } catch { S.hasProxy = false; }
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
    if (!span) { toast('Marque IN/OUT ou selecione um take'); return; }
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
    toast(kind === 'selection' ? 'Marque IN/OUT ou selecione um take' : 'Não achei esse trecho');
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
    const wantId = (!HOUSE_STYLE && !HUB_EMBED)
      ? ''
      : (pack.activeId || '');
    sel.innerHTML = presets.map((p) =>
      `<option value="${p.id}" ${p.id === wantId ? 'selected' : ''}>${p.name || p.id}</option>`
    ).join('');
    if (!sel.innerHTML) {
      sel.innerHTML = `<option value="">${projectBrand || 'Deste vídeo'}</option>`;
    }
    if (applyActive) {
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

async function presetAction(action) {
  const sel = $('presetSelect');
  const pack = S.brandPresets || {};
  const brandId = pack.brandId || 'padrao';
  const id = sel?.value;
  let name = '';
  if (action === 'create' || action === 'duplicate' || action === 'rename') {
    name = window.prompt(action === 'rename' ? 'Novo nome do preset' : 'Nome do preset', '') || '';
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
