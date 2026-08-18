/**
 * SHORT-FORM composition (Reels/TikTok/Shorts) — DATA-DRIVEN. DO NOT EDIT.
 *
 * All per-video values live in ../public/edit-data.json (schema in README.md):
 * camera zooms, hook headline, captions config, image inserts,
 * behind-the-subject windows, soundtrack. Machine-generated data files in
 * public/: captions.json (captions_for_remotion.py), track.json
 * (face_track.py), segments.json (EDL output-timeline boundaries).
 *
 * The ONE editable file is CustomGraphics.tsx — bespoke motion graphics only.
 *
 * Audio: keep layers low (whoosh ~0.09, pop ~0.12, music ~0.12) and always run
 * a final loudnorm pass on the render — voice + music + SFX summed will clip.
 */
import {
  AbsoluteFill,
  Audio,
  Img,
  OffthreadVideo,
  Sequence,
  staticFile,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import track from '../public/track.json';
import segData from '../public/segments.json';
import editData from '../public/edit-data.json';
import {CustomGraphics} from './CustomGraphics';
import {StackedCaptions} from './StackedCaptions';
import {ScatterCaptions} from './ScatterCaptions';
import {SimpleCaptions, SIMPLE_VARIANTS} from './SimpleCaptions';
import {ImpactCaptions} from './ImpactCaptions';

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});

// ============ TYPES + DATA ====================================================
type Caption = {text: string; startMs: number; endMs: number};
type Insert = {src: string; start: number; end: number};
type BehindImage = {kind: 'image'; src: string; matte: string; start: number; dur: number};
type BehindWords = {kind: 'words'; words: {t: string; at: number}[]; matte: string; start: number; dur: number};
type Behind = BehindImage | BehindWords;

export type EditData = {
  width: number;
  height: number;
  fps: number;
  durationSec: number;
  camera: {enabled: boolean; zooms: number[]; pushIn: number; targetX: number; targetY: number};
  hook: {
    enabled: boolean; endSec: number; lines: string[]; logo: string | null; sign: string | null;
    // `text` is preferred over `lines`: the headline is ALWAYS re-broken into
    // exactly two balanced lines and the size fitted to them (see twoLines /
    // fitHeadline). Anything in `lines` is joined back into one string first.
    text?: string;
    // "outline" (default): white text + thick black stroke, no card — the
    //   MrBeast/TikTok headline.
    // "card": Poppins Black on a dark rounded card, UPPERCASE, optional logo row.
    // "realce": each line on its own solid orange marker block.
    // "misto": line 1 light white, line 2 heavy orange.
    // "sombra": white text with a hard un-blurred offset in the accent.
    // "sublinhado": white text over a thick accent bar under each line.
    style?: 'outline' | 'card' | 'realce' | 'misto' | 'sombra' | 'sublinhado'
      | 'pilula' | 'manchete' | 'carimbo';
    accent?: string;        // realce/misto marker + text colour (default #ff5200)
    fontSizePx?: number;   // auto-fit CEILING (alias of maxFontPx, kept for compat)
    maxFontPx?: number;    // auto-fit ceiling (per-style default)
    safeWidth?: number;    // auto-fit width budget (per-style default)
    strokePx?: number;     // outline: black stroke width (default 12)
    paddingTop?: number;   // distance from top (per-style default)
    paddingBottom?: number; // manchete only: distance from the base (default 140)
    lineHeight?: number;
  };
  captions: {
    enabled: boolean;
    fontSize: number;
    maxWords: number;
    safeWidth: number;
    paddingBottom: number;
    // "Posição da legenda" do preset: baixo (default de cada estilo), centro,
    // alto. karaoke posiciona por paddingBottom; os estáticos e o impacto leem
    // este campo; stacked/scatter recebem seus offsets próprios já mapeados.
    position?: 'baixo' | 'centro' | 'alto';
    // "Tamanho da legenda" (P/M/G → 0.85/1/1.18) — os estáticos e o impacto
    // multiplicam a fonte por ele; karaoke/stacked/scatter recebem os knobs
    // próprios (fontSize/fontScale/scatterFontSize) já escalados.
    sizeScale?: number;
    // "Legenda" colour — the BASE text: karaoke's whole line, and the three
    // static styles (simples/serifada/classica). Stacked's white lines and
    // scatter's ink-gradient words are deliberately NOT tied to this — they
    // have their own separate accent below, since those two styles draw a
    // distinction between ordinary text and an emphasised word/line.
    accent?: string;
    // "Ênfase/destaque" colour — the ONE accented element per style: stacked's
    // serif line, scatter's highlighted word. Independent from `accent` above
    // (a project can want white body text and a red emphasis) and from
    // hook.accent (headline). Defaults to #ff5200 when unset, same as accent's
    // default, but the two are picked separately.
    emphasisAccent?: string;
    // Stacked-only: the hand-drawn pencil-circle stroke around a solo emphasis
    // word (see StackedCaptions.tsx / PencilOutline.tsx). Independent from
    // emphasisAccent — a project can circle in green while the serif line
    // reads red. Defaults to PencilOutline's own #39E508 when unset.
    circleAccent?: string;
    // ranges (seconds) where the caption sits somewhere else — used by the
    // "tela dividida" style to park it on the seam between image and video
    windows?: {start: number; end: number; paddingBottom: number}[];
    // "karaoke" (default, single line), "stacked" (multi-font stack + pencil
    // outline + click/scratch SFX, reads public/caption-cues.json) or "scatter"
    // (serif, lowercase, scattered word-by-word — reads captions.json alone).
    // The STATIC ones ("simples", "serifada", "classica", "bloco", "recorte")
    // live in SimpleCaptions.tsx and take no tunables — they ARE the tuning.
    // "impacto" (ImpactCaptions.tsx) boxes the spoken word in emphasisAccent.
    style?: 'karaoke' | 'stacked' | 'scatter' | 'impacto'
      | 'simples' | 'serifada' | 'classica' | 'bloco' | 'recorte';
    scatterOffsetY?: number;   // scatter: block centre, fraction of height
    scatterFontSize?: number;  // scatter: ordinary word size (default 74)
    scatterSafeWidth?: number; // scatter: layout width budget (default 940)
    stackedOffsetY?: number;
    fontScale?: number;
    sfx?: {enabled?: boolean; clickVolume?: number; scratchVolume?: number};
  };
  inserts: Insert[];
  behind: Behind[];
  soundtrack: {enabled: boolean; file: string; volume: number};
  // Brand sign-off over the last seconds. Optional: omit the key entirely and
  // nothing renders, so every project that predates this keeps working.
  endCard?: {
    enabled: boolean;
    // How long it holds, counted back from the END of the video. Expressed as
    // a duration rather than a start time on purpose: the cut's length changes
    // every time a take is trimmed, and a hardcoded startSec silently drifts
    // off the end. Default 2.5s.
    lastSec?: number;
    lines?: string[];        // e.g. ["@primecamp", "link na bio"]
    logo?: string | null;    // staticFile path, drawn above the lines
    accent?: string;         // first line's colour (default: hook.accent)
    // How much of the video shows through behind it. 1 = solid black card,
    // 0 = text straight over the footage. Default 0.82.
    dim?: number;
  };
};

const D = editData as unknown as EditData;

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const clamp01 = (v: number) => clamp(v, 0, 1);

// SFX played at an appearance (whoosh) or a pop for shapes
export const Sfx: React.FC<{src: string; volume?: number}> = ({src, volume = 0.09}) => (
  <Audio src={staticFile(`sfx/${src}`)} volume={volume} />
);

// ============ DYNAMIC CAMERA (hard zoom on cuts + push-in + eye tracking) ======
// src defaults to the base cut. frameOffset lets a windowed layer (e.g. a person
// matte inside a <Sequence>) use the GLOBAL frame for the camera math so it stays
// aligned with the base. transparent enables ProRes alpha (person matte).
// children render inside the same transformed space.
export const DynamicVideo: React.FC<{src?: string; frameOffset?: number; transparent?: boolean; children?: React.ReactNode}> = ({
  src = 'cut.mp4',
  frameOffset = 0,
  transparent = false,
  children,
}) => {
  const frame = useCurrentFrame() + frameOffset;
  const {width, height, fps} = useVideoConfig();
  const cam = D.camera;

  let S = 1;
  let tx = 0;
  let ty = 0;
  if (cam.enabled) {
    // which cut segment is this frame in?
    const segs = segData.segments;
    let idx = 0;
    // -1: OffthreadVideo draws the source frame at or before frame/fps, which on an
    // exact boundary lands a frame late. Without this the hard zoom steps one frame
    // BEFORE the picture cuts (same lag CustomGraphics compensates with VIDEO_LAG).
    for (let i = 0; i < segs.length; i++) {
      if (frame - 1 >= Math.round(segs[i].start * fps)) idx = i;
    }
    const segFrom = Math.round(segs[idx].start * fps) + 1;
    const segLen = Math.max(1, Math.round(segs[idx].dur * fps));
    const base = cam.zooms[idx % cam.zooms.length] ?? 1.14;
    const push = cam.pushIn * clamp01((frame - segFrom) / segLen);
    S = base + push;

    const pts = track.points as [number, number][];
    const [cx, cy] = pts[Math.min(frame, pts.length - 1)] ?? [0.5, 0.4];
    tx = cam.targetX * width - cx * width * S;
    ty = cam.targetY * height - cy * height * S;
    tx = clamp(tx, width - width * S, 0); // never reveal an edge
    ty = clamp(ty, height - height * S, 0);
  }

  return (
    <AbsoluteFill>
      <div
        style={{
          width,
          height,
          transformOrigin: '0 0',
          transform: `translate(${tx.toFixed(2)}px, ${ty.toFixed(2)}px) scale(${S.toFixed(4)})`,
        }}
      >
        <OffthreadVideo src={staticFile(src)} transparent={transparent} style={{width, height}} />
        {children}
      </div>
    </AbsoluteFill>
  );
};

// ============ BEHIND-THE-SUBJECT (element between person and background) ========
// Layer: base cut (bg+person) → element → person matte on top (person redrawn,
// so the element sits behind it). The matte is a ProRes 4444 alpha .mov from
// person_matte.py, one file per window, frame 0 = window start. Elements anchor
// to the TOP of the frame (a centered element hides behind the torso).
const BehindImageEl: React.FC<{src: string; totalFrames: number}> = ({src, totalFrames}) => {
  const f = useCurrentFrame();
  const enter = interpolate(f, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 8, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(enter, exit);
  const grow = interpolate(f, [0, totalFrames], [1, 1.08], {extrapolateRight: 'clamp'});
  const scale = interpolate(enter, [0, 1], [0.94, 1]) * grow;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      {/* top-weighted so the image frames the head instead of hiding behind the torso */}
      <div style={{width: 1000, height: 1250, marginTop: 40, borderRadius: 30, overflow: 'hidden', opacity: op, scale: String(scale), boxShadow: '0 24px 70px rgba(0,0,0,0.55)'}}>
        <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </div>
    </AbsoluteFill>
  );
};

const BehindWordsEl: React.FC<{words: {t: string; at: number}[]; startSec: number; totalFrames: number}> = ({words, startSec, totalFrames}) => {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const scrim = interpolate(f, [0, 8, totalFrames - 8, totalFrames], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: 180}}>
      <AbsoluteFill style={{background: 'rgba(0,0,0,0.26)', opacity: scrim}} />
      {words.map((w, i) => {
        const from = Math.round((w.at - startSec) * fps);
        const to = i + 1 < words.length ? Math.round((words[i + 1].at - startSec) * fps) : totalFrames;
        if (f < from || f >= to) return null;
        const local = f - from;
        const pop = interpolate(local, [0, 6], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.7))});
        const op = interpolate(local, [0, 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
        return (
          <div key={i} style={{position: 'absolute', fontFamily, fontWeight: 900, fontSize: 360, color: '#fff', opacity: op, scale: String(0.72 + 0.28 * pop), letterSpacing: -12, textShadow: '0 6px 30px rgba(0,0,0,0.5)'}}>
            {w.t}
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

const BehindSubject: React.FC = () => {
  const {fps} = useVideoConfig();
  return (
    <>
      {D.behind.map((b, i) => {
        const from = Math.round(b.start * fps);
        const duration = Math.round(b.dur * fps);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            {b.kind === 'image' ? (
              <BehindImageEl src={b.src} totalFrames={duration} />
            ) : (
              <BehindWordsEl words={b.words} startSec={b.start} totalFrames={duration} />
            )}
            <DynamicVideo src={b.matte} frameOffset={from} transparent />
          </Sequence>
        );
      })}
    </>
  );
};

// ============ KARAOKE CAPTIONS (1 line, ≤3 words, rise up, safe-margin fit) =====
const cleanW = (t: string) => t.replace(/[.,!?…]+$/, '');
const isBreak = (t: string) => /[.,!?…]$/.test(t);

function buildLines(caps: Caption[], maxWords: number): Caption[][] {
  const lines: Caption[][] = [];
  let cur: Caption[] = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= maxWords || isBreak(w.text)) {
      lines.push(cur);
      cur = [];
    }
  }
  if (cur.length) lines.push(cur);
  return lines;
}
const LINES = buildLines(captions as Caption[], D.captions.maxWords);

const Word: React.FC<{caption: Caption; lineFromFrame: number}> = ({caption, lineFromFrame}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const startLocal = (caption.startMs / 1000) * fps - lineFromFrame;
  const p = interpolate(frame, [startLocal, startLocal + 7], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return (
    <span
      style={{
        display: 'inline-block',
        opacity: p,
        translate: `0px ${interpolate(p, [0, 1], [34, 0])}px`,
        marginRight: 18,
      }}
    >
      {cleanW(caption.text)}
    </span>
  );
};

// captions.windows lets the caption sit somewhere else for part of the video —
// the "tela dividida" style parks it on the seam between image and video. It is
// resolved PER FRAME, not per line: a line that starts before a window and runs
// into it has to move mid-line, otherwise it stays stuck at the bottom.
const CaptionShell: React.FC<{fromFrame: number; children: React.ReactNode}> = ({fromFrame, children}) => {
  const {fps} = useVideoConfig();
  const local = useCurrentFrame();
  const C = D.captions;
  // Compared in FRAMES, never seconds: window bounds are rounded in the JSON, and
  // an epsilon comparison there lands a frame off. +1 is the same video lag the
  // split layout compensates for (see VIDEO_LAG in CustomGraphics).
  const f = fromFrame + local;
  const w = (C.windows || []).find(
    (x) => f >= Math.round(x.start * fps) + 1 && f < Math.round(x.end * fps) + 1,
  );
  return (
    <AbsoluteFill
      style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: w ? w.paddingBottom : C.paddingBottom}}
    >
      {children}
    </AbsoluteFill>
  );
};

const Karaoke: React.FC = () => {
  const {fps, durationInFrames} = useVideoConfig();
  const C = D.captions;
  return (
    <>
      {LINES.map((line, i) => {
        const from = Math.round((line[0].startMs / 1000) * fps);
        const nextFrom =
          i + 1 < LINES.length ? Math.round((LINES[i + 1][0].startMs / 1000) * fps) : durationInFrames;
        const duration = Math.max(1, nextFrom - from);
        const lineText = line.map((w) => cleanW(w.text)).join(' ');
        const {width} = measureText({
          text: lineText,
          fontFamily,
          fontSize: C.fontSize,
          fontWeight: 900,
          letterSpacing: '-1px',
        });
        // safe-margin fit: scale down so the line clears the platform action rail
        const fit = Math.min(1, C.safeWidth / width);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            <CaptionShell fromFrame={from}>
              <div
                style={{
                  fontFamily,
                  fontWeight: 900,
                  fontSize: C.fontSize,
                  color: C.accent ?? 'white',
                  lineHeight: 1,
                  letterSpacing: -1,
                  whiteSpace: 'nowrap',
                  scale: String(fit),
                  textShadow: '0 4px 20px rgba(0,0,0,0.55)',
                }}
              >
                {line.map((w, j) => (
                  <Word key={j} caption={w} lineFromFrame={from} />
                ))}
              </div>
            </CaptionShell>
          </Sequence>
        );
      })}
    </>
  );
};

// ============ ILLUSTRATIVE IMAGE INSERTS (rounded card + shadow, upper zone) ====
const CARD_W = 780;
const CARD_H = 500;
const CARD_TOP = 90;

const InsertCard: React.FC<{src: string; totalFrames: number}> = ({src, totalFrames}) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(frame, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(enter, exit);
  // dynamic zoom: the image itself grows slowly while on screen (Ken-Burns)
  const grow = interpolate(frame, [0, totalFrames], [1, 1.08], {extrapolateRight: 'clamp'});
  const scale = interpolate(enter, [0, 1], [0.92, 1]) * grow;
  const y = interpolate(enter, [0, 1], [26, 0]);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: CARD_W, height: CARD_H, marginTop: CARD_TOP, borderRadius: 28, overflow: 'hidden', opacity, scale: String(scale), translate: `0px ${y}px`, boxShadow: '0 18px 50px rgba(0,0,0,0.45)'}}>
        <Img src={staticFile(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </div>
    </AbsoluteFill>
  );
};

const Inserts: React.FC = () => {
  const {fps} = useVideoConfig();
  return (
    <>
      {D.inserts.map((it, i) => {
        const from = Math.round(it.start * fps);
        const duration = Math.round((it.end - it.start) * fps);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            <InsertCard src={it.src} totalFrames={duration} />
          </Sequence>
        );
      })}
    </>
  );
};

// ============ SOUNDTRACK (ElevenLabs AI track or a local file) — background bed ====
const Soundtrack: React.FC = () => {
  const {durationInFrames} = useVideoConfig();
  const S = D.soundtrack;
  return (
    <Audio
      src={staticFile(S.file)}
      volume={(f) =>
        interpolate(f, [0, 10, durationInFrames - 24, durationInFrames], [0, S.volume, S.volume, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      }
    />
  );
};

// ============ END CARD (brand sign-off over the last seconds) =================
// Anchored to the END of the composition, not to a start time: the cut's length
// moves every time a take is trimmed, and a hardcoded start would drift off the
// tail. It dims rather than cuts to black so the last frames of the video still
// play underneath — a hard cut to a static card reads as "the video stopped",
// which is exactly when people swipe.
const EndCardInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const frame = useCurrentFrame();
  const {fps, width} = useVideoConfig();
  const E = D.endCard!;
  const lines = (E.lines || []).filter(Boolean);
  const dim = E.dim ?? 0.82;
  const accent = E.accent || D.hook.accent || '#ff5200';

  const fadeF = Math.min(Math.round(0.35 * fps), Math.floor(totalFrames / 2));
  const inK = clamp01(frame / Math.max(1, fadeF));
  // no fade-out: the card is the last thing on screen, and fading it before
  // the final frame just gives the viewer an empty beat to swipe on
  const eased = Easing.out(Easing.cubic)(inK);
  const rise = interpolate(eased, [0, 1], [26, 0]);

  // FIT to a safe width, never a fixed size. Shipped with a fixed 0.072*width
  // and it bled off both edges the first time a real handle went in
  // ("Segue @lojaprimecamp" at 900 weight is far wider than 1080px). The
  // headline solved this long ago by measuring; the end card has to as well.
  // 0.84 stopped the bleed but replaced it with a different problem: any handle
  // long enough to hit the budget renders AT the budget, so "Segue
  // @lojaprimecamp" came out edge to edge, headline-sized, on a card that is
  // supposed to read as a sign-off. The fit is doing its job — the target was
  // too generous. 0.70 leaves a real margin, and the smaller base means short
  // handles shrink too instead of only long ones being clamped.
  const safeW = width * 0.70;          // 15% breathing room each side
  const base = Math.round(width * 0.058);
  const weightOf = (i: number) => (i === 0 ? 900 : 600);
  const scaleOf = (i: number) => (i === 0 ? 1 : 0.62);
  const widthAt = (t: string, px: number, w: number) =>
    t ? measureText({text: t, fontFamily, fontSize: px, fontWeight: w, letterSpacing: '-1px'}).width : 0;
  // one shrink factor for the whole block, so the lines keep their relative
  // sizes instead of the longest one collapsing on its own
  let fit = 1;
  lines.forEach((t, i) => {
    const w = widthAt(t, base * scaleOf(i), weightOf(i));
    if (w > safeW) fit = Math.min(fit, safeW / w);
  });
  const size = Math.max(28, Math.round(base * fit));

  return (
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
      <AbsoluteFill style={{backgroundColor: '#000', opacity: dim * eased}} />
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: Math.round(size * 0.34),
          opacity: eased,
          transform: `translateY(${rise}px)`,
        }}
      >
        {E.logo ? (
          <Img
            src={staticFile(E.logo)}
            style={{width: Math.round(width * 0.44), objectFit: 'contain'}}
          />
        ) : null}
        {lines.map((t, i) => (
          <div
            key={i}
            style={{
              fontFamily,
              fontWeight: i === 0 ? 900 : 600,
              fontSize: i === 0 ? size : Math.round(size * 0.62),
              letterSpacing: '-1px',
              color: i === 0 ? accent : '#fff',
              textAlign: 'center',
              // belt and braces on top of the measured fit: if a face ever
              // measures differently than it renders, this wraps instead of
              // bleeding off frame — a wrapped CTA is readable, a clipped one
              // is the bug that was just reported.
              maxWidth: safeW,
              textShadow: '0 4px 24px rgba(0,0,0,.6)',
            }}
          >
            {t}
          </div>
        ))}
      </div>
    </AbsoluteFill>
  );
};

const EndCard: React.FC = () => {
  const {fps, durationInFrames} = useVideoConfig();
  const hold = Math.round((D.endCard?.lastSec ?? 2.5) * fps);
  const dur = clamp(hold, 1, durationInFrames);
  return (
    <Sequence from={durationInFrames - dur} durationInFrames={dur} layout="none">
      <EndCardInner totalFrames={dur} />
    </Sequence>
  );
};

// ============ VISUAL HOOK (static headline in the first ~4s — always on) =======
// Copy comes from edit-data.json `hook.lines` — written like a copywriting/
// virality specialist from the cut transcript (curiosity gap · high stakes ·
// specificity · urgency). Four styles via `hook.style`, ALL of them two lines
// with the size fitted to the text:
//   "outline" (default): white + thick black stroke, no card, sentence-case,
//     sits lower (paddingTop~330, may overlap the top of the head) — TikTok.
//   "card": Poppins Black on a dark-gray rounded card, UPPERCASE, optional
//     logo + symbol row above.
//   "realce": each line on its own solid orange marker block.
//   "misto": line 1 light white, line 2 heavy orange.
// All static (fade + rise only) with a soft whoosh on entry. Tunables:
// fontSizePx / maxFontPx (ceiling for the fit — NOT a fixed size), safeWidth,
// strokePx, paddingTop, lineHeight.
// ---- ALWAYS two lines, size fitted to them ----------------------------------
// The headline has one job: be read in a glance. A third line shrinks the type
// and costs exactly that, so whatever comes in is re-broken into TWO balanced
// lines and the size is fitted to the widest one. Author `hook.text` as a plain
// sentence and let this do the breaking — hand-broken `lines` get rejoined.
const HL_MIN = 40;

type HlStyle = {weights: [number, number]; cap: number; safeW: number; lh: number; top: number};
const HL_STYLES: Record<string, HlStyle> = {
  outline: {weights: [800, 800], cap: 92, safeW: 900, lh: 1.02, top: 330},
  card: {weights: [900, 900], cap: 82, safeW: 820, lh: 1.06, top: 120},
  realce: {weights: [900, 900], cap: 86, safeW: 830, lh: 1.04, top: 300},
  misto: {weights: [400, 900], cap: 98, safeW: 900, lh: 0.98, top: 300},
  // safeW is tighter than outline's: the hard offset adds real width to the
  // right of the glyphs, so fitting to the full 900 would push it off-frame.
  sombra: {weights: [900, 900], cap: 92, safeW: 860, lh: 1.02, top: 310},
  // gap between lines is generous (the bar lives in it), so the cap is lower
  // to keep two lines + two bars inside the same band as the other styles.
  sublinhado: {weights: [900, 900], cap: 84, safeW: 850, lh: 1.0, top: 305},
  // "pilula": ONE-line context pill pinned high; the pipeline stretches
  // hook.endSec to the whole video for this style — it is a context bar,
  // not an opening moment.
  pilula: {weights: [700, 700], cap: 44, safeW: 780, lh: 1.1, top: 130},
  // "manchete": news band at the BASE (flex-end; `top` unused). safeW leaves
  // room for the band's own margins + accent bar inside the 1080 frame.
  manchete: {weights: [800, 800], cap: 54, safeW: 780, lh: 1.14, top: 0},
  carimbo: {weights: [900, 900], cap: 80, safeW: 720, lh: 1.05, top: 300},
};

const hlWidth = (text: string, size: number, weight: number) =>
  text
    ? measureText({text, fontFamily, fontSize: size, fontWeight: weight, letterSpacing: '-1px'}).width
    : 0;

// Balance by MEASURED width, not word count: "É assim que vai" and "ficar a sua
// headline" are 4 words and 3 words but nearly the same width — counting words
// would break it in the wrong place.
function twoLines(text: string, weights: [number, number]): [string, string] {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return [words[0] ?? '', ''];
  let best: [string, string] = [words[0], words.slice(1).join(' ')];
  let bestDiff = Infinity;
  for (let i = 1; i < words.length; i++) {
    const a = words.slice(0, i).join(' ');
    const b = words.slice(i).join(' ');
    const d = Math.abs(hlWidth(a, 100, weights[0]) - hlWidth(b, 100, weights[1]));
    if (d < bestDiff) {
      bestDiff = d;
      best = [a, b];
    }
  }
  return best;
}

// Width scales with size, but letterSpacing (-1px per gap) does NOT — so the
// first estimate is off by a few px on long lines. One refinement pass at the
// estimated size fixes that; iterating further buys nothing.
function fitHeadline(lines: [string, string], s: HlStyle): number {
  const widest = (size: number) =>
    Math.max(hlWidth(lines[0], size, s.weights[0]), hlWidth(lines[1], size, s.weights[1]));
  let size = Math.floor((s.safeW / Math.max(1, widest(100))) * 100);
  size = clamp(Math.floor((s.safeW / Math.max(1, widest(size))) * size), HL_MIN, s.cap);
  return size;
}

const HookInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const H = D.hook;
  const enter = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 9, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [24, 0]);

  const styleId = H.style ?? 'outline';
  const S = HL_STYLES[styleId] ?? HL_STYLES.outline;
  const raw = (H.text ?? (H.lines || []).join(' ')).trim();
  const isUpper = styleId === 'card' || styleId === 'manchete' || styleId === 'carimbo';
  const lines = twoLines(isUpper ? raw.toUpperCase() : raw, S.weights);
  // fontSizePx is a CEILING, never a fixed size. As a hard override it silently
  // defeats the whole point: at a size the text cannot fit in, the line wraps and
  // the headline becomes three lines again — which is exactly what happened with
  // the uppercase "card" style at the project's inherited fontSizePx of 66.
  const cap = H.fontSizePx ?? H.maxFontPx ?? S.cap;
  const size = fitHeadline(lines, {...S, cap, safeW: H.safeWidth ?? S.safeW});
  const lh = H.lineHeight ?? S.lh;
  const top = H.paddingTop ?? S.top;
  const shell: React.CSSProperties = {
    opacity: op,
    translate: `0px ${y}px`,
    textAlign: 'center',
    fontFamily,
    lineHeight: lh,
    letterSpacing: -1,
    // the two-line promise is structural: if a fit is ever off, this overflows
    // visibly instead of quietly wrapping into a third line
    whiteSpace: 'nowrap',
  };

  // "pilula": one compact line in a dark pill with an accent dot, pinned high
  // and PERSISTENT (endSec = whole video, set by the pipeline). No Sfx — a
  // context bar has no "moment"; a whoosh would announce one.
  if (styleId === 'pilula') {
    const one = raw;
    const sz = fitHeadline([one, ''], {...S, cap, safeW: H.safeWidth ?? S.safeW});
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <div
          style={{
            opacity: op,
            translate: `0px ${y}px`,
            display: 'flex',
            alignItems: 'center',
            gap: Math.round(sz * 0.35),
            background: 'rgba(17,18,20,0.78)',
            borderRadius: 999,
            padding: `${Math.round(sz * 0.3)}px ${Math.round(sz * 0.6)}px`,
            boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
          }}
        >
          <div
            style={{
              width: Math.round(sz * 0.3),
              height: Math.round(sz * 0.3),
              borderRadius: '50%',
              background: H.accent ?? '#ff5200',
              flex: '0 0 auto',
            }}
          />
          <div style={{fontFamily, fontWeight: 700, fontSize: sz, color: '#fff', letterSpacing: -0.5, whiteSpace: 'nowrap', lineHeight: 1.1}}>
            {one}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  // "manchete": breaking-news band at the base — dark slab, accent bar on the
  // left, UPPERCASE left-aligned lines. Sits BELOW the caption band (430), so
  // the two never collide.
  if (styleId === 'manchete') {
    return (
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: H.paddingBottom ?? 140}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div
          style={{
            opacity: op,
            translate: `0px ${(-y).toFixed(1)}px`,
            display: 'flex',
            alignItems: 'stretch',
            gap: 26,
            background: 'rgba(12,13,15,0.86)',
            padding: '26px 44px',
            borderRadius: 18,
            boxShadow: '0 14px 40px rgba(0,0,0,0.45)',
            maxWidth: 1000,
          }}
        >
          <div style={{width: 12, borderRadius: 6, background: H.accent ?? '#ff5200', flex: '0 0 auto'}} />
          <div style={{fontFamily, fontWeight: 800, fontSize: size, color: '#fff', lineHeight: lh, letterSpacing: -1, textAlign: 'left', whiteSpace: 'nowrap'}}>
            {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  // "carimbo": accent-coloured stamp — thick border, slight rotation, and a
  // slam entrance (starts big and transparent, lands fast). The slam replaces
  // the shared fade+rise; the exit fade is shared.
  if (styleId === 'carimbo') {
    const slam = interpolate(f, [0, 7], [0, 1], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.cubic),
    });
    const acc = H.accent ?? '#ff5200';
    const bw = Math.max(6, Math.round(size * 0.09));
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.12} />
        <div
          style={{
            opacity: Math.min(slam, exit),
            transform: `rotate(-6deg) scale(${(1.9 - 0.9 * slam).toFixed(3)})`,
            border: `${bw}px solid ${acc}`,
            borderRadius: 18,
            padding: `${Math.round(size * 0.18)}px ${Math.round(size * 0.4)}px`,
            background: 'rgba(10,10,12,0.25)',
          }}
        >
          <div style={{...shell, opacity: 1, translate: '0px 0px', fontWeight: 900, fontSize: size, color: acc, textShadow: '0 4px 14px rgba(0,0,0,0.45)'}}>
            {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  if (styleId === 'realce') {
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{...shell, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10}}>
          {lines.filter(Boolean).map((l, i) => (
            <div
              key={i}
              style={{
                background: H.accent ?? '#ff5200',
                color: '#fff',
                fontWeight: 900,
                fontSize: size,
                padding: '0.08em 0.3em 0.16em',
                borderRadius: 12,
                boxShadow: '0 10px 28px rgba(0,0,0,0.45)',
              }}
            >
              {l}
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  if (styleId === 'misto') {
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{...shell, filter: 'drop-shadow(0 6px 16px rgba(0,0,0,0.55))'}}>
          <div style={{fontWeight: 400, fontSize: size, color: '#fff'}}>{lines[0]}</div>
          <div style={{fontWeight: 900, fontSize: size, color: H.accent ?? '#ff5200'}}>{lines[1]}</div>
        </div>
      </AbsoluteFill>
    );
  }

  if (styleId === 'card') {
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{opacity: op, translate: `0px ${y}px`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28}}>
          {H.logo || H.sign ? (
            <div style={{display: 'flex', alignItems: 'center', gap: 34}}>
              {H.logo ? <Img src={staticFile(H.logo)} style={{width: 300, borderRadius: 18, boxShadow: '0 12px 34px rgba(0,0,0,0.4)'}} /> : null}
              {H.sign ? <Img src={staticFile(H.sign)} style={{width: 128, filter: 'drop-shadow(0 8px 20px rgba(0,0,0,0.45))'}} /> : null}
            </div>
          ) : null}
          <div style={{background: '#232326', borderRadius: 24, padding: '28px 46px', textAlign: 'center', fontFamily, fontWeight: 900, fontSize: size, color: '#fff', lineHeight: lh, letterSpacing: -1, textShadow: '0 4px 20px rgba(0,0,0,0.55)', boxShadow: '0 18px 50px rgba(0,0,0,0.45)'}}>
            {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
    );
  }

  // "sombra": white text with a hard, un-blurred offset in the accent. Reads as
  // a sticker/pop print rather than a lit object — the opposite of `outline`'s
  // stroke, which sits tight to the glyph. Offset scales with the type so it
  // holds at any fitted size instead of vanishing on small headlines.
  if (styleId === 'sombra') {
    const off = Math.max(4, Math.round(size * 0.07));
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div
          style={{
            ...shell,
            fontWeight: 900,
            fontSize: size,
            color: '#fff',
            padding: '0 60px',
            // two shadows: the accent offset, then a soft black to lift the
            // whole thing off busy footage (a shelf wall eats flat white)
            textShadow: `${off}px ${off}px 0 ${H.accent ?? '#ff5200'}, 0 6px 18px rgba(0,0,0,0.5)`,
          }}
        >
          {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
        </div>
      </AbsoluteFill>
    );
  }

  // "sublinhado": text stays white and readable; the accent is a thick bar
  // UNDER each line. The marker sits behind the descenders on purpose — a bar
  // clear of them reads as a separate rule rather than a highlight.
  if (styleId === 'sublinhado') {
    // 0.13 rendered as a hairline rule that competed with busy footage instead
    // of anchoring the text; 0.19 reads as a marker stroke at the sizes the
    // headline actually fits to.
    const barH = Math.max(8, Math.round(size * 0.19));
    return (
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{...shell, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: Math.round(size * 0.16)}}>
          {lines.filter(Boolean).map((l, i) => (
            <div key={i} style={{position: 'relative', display: 'inline-block'}}>
              <div
                style={{
                  position: 'absolute',
                  left: '-0.06em',
                  right: '-0.06em',
                  bottom: Math.round(size * 0.06),
                  height: barH,
                  borderRadius: barH / 2,
                  background: H.accent ?? '#ff5200',
                }}
              />
              <div
                style={{
                  position: 'relative',
                  fontWeight: 900,
                  fontSize: size,
                  color: '#fff',
                  textShadow: '0 4px 16px rgba(0,0,0,0.55)',
                }}
              >
                {l}
              </div>
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  const stroke = H.strokePx ?? 12;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: top}}>
      <Sfx src="whoosh.mp3" volume={0.1} />
      <div
        style={{
          ...shell,
          fontWeight: 800,
          fontSize: size,
          color: '#fff',
          WebkitTextStroke: `${stroke}px #000`,
          paintOrder: 'stroke fill',
          filter: 'drop-shadow(0 6px 14px rgba(0,0,0,0.45))',
          padding: '0 60px',
        }}
      >
        {lines.filter(Boolean).map((l, i) => (<div key={i}>{l}</div>))}
      </div>
    </AbsoluteFill>
  );
};

const HookIntro: React.FC = () => {
  const {fps} = useVideoConfig();
  const dur = Math.round(D.hook.endSec * fps);
  return (
    <Sequence from={0} durationInFrames={dur} layout="none">
      <HookInner totalFrames={dur} />
    </Sequence>
  );
};

// ============ MAIN ============
export const Main: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      {D.soundtrack.enabled ? <Soundtrack /> : null}
      <DynamicVideo />
      <BehindSubject />
      <Inserts />
      <CustomGraphics />
      {D.hook.enabled ? <HookIntro /> : null}
      {D.captions.enabled
        ? D.captions.style === 'stacked'
          ? <StackedCaptions />
          : D.captions.style === 'scatter'
            ? <ScatterCaptions />
            : D.captions.style === 'impacto'
              ? <ImpactCaptions />
              : SIMPLE_VARIANTS[D.captions.style as string]
                ? <SimpleCaptions variant={D.captions.style as string} />
                : <Karaoke />
        : null}
      {/* last: the sign-off covers the captions too, not just the footage */}
      {D.endCard?.enabled ? <EndCard /> : null}
    </AbsoluteFill>
  );
};
