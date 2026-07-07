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
  hook: {enabled: boolean; endSec: number; lines: string[]; logo: string | null; sign: string | null};
  captions: {
    enabled: boolean;
    fontSize: number;
    maxWords: number;
    safeWidth: number;
    paddingBottom: number;
    // "karaoke" (default, single line) or "stacked" (multi-font stack + pencil
    // outline + click/scratch SFX). Stacked reads public/caption-cues.json.
    style?: 'karaoke' | 'stacked';
    stackedOffsetY?: number;
    fontScale?: number;
    sfx?: {enabled?: boolean; clickVolume?: number; scratchVolume?: number};
  };
  inserts: Insert[];
  behind: Behind[];
  soundtrack: {enabled: boolean; file: string; volume: number};
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
    for (let i = 0; i < segs.length; i++) {
      if (frame >= Math.round(segs[i].start * fps)) idx = i;
    }
    const segFrom = Math.round(segs[idx].start * fps);
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
            <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: C.paddingBottom}}>
              <div
                style={{
                  fontFamily,
                  fontWeight: 900,
                  fontSize: C.fontSize,
                  color: 'white',
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
            </AbsoluteFill>
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

// ============ SOUNDTRACK (Treblo AI track or a local file) — background bed ====
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

// ============ VISUAL HOOK (static headline in the first ~4s — always on) =======
// Copy comes from edit-data.json `hook.lines` — written like a copywriting/
// virality specialist from the cut transcript (curiosity gap · high stakes ·
// specificity · urgency). Design is THE locked standard: Poppins Black, white,
// UPPERCASE, dark-gray rounded card, ALL LINES ONE SIZE, static (fade only),
// optional logo + symbol row above.
const HookInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const H = D.hook;
  const enter = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 9, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [24, 0]);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: 120}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{opacity: op, translate: `0px ${y}px`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28}}>
          {H.logo || H.sign ? (
            <div style={{display: 'flex', alignItems: 'center', gap: 34}}>
              {H.logo ? <Img src={staticFile(H.logo)} style={{width: 300, borderRadius: 18, boxShadow: '0 12px 34px rgba(0,0,0,0.4)'}} /> : null}
              {H.sign ? <Img src={staticFile(H.sign)} style={{width: 128, filter: 'drop-shadow(0 8px 20px rgba(0,0,0,0.45))'}} /> : null}
            </div>
          ) : null}
          {/* headline card — caption-style text, ALL LINES ONE SIZE */}
          <div style={{background: '#232326', borderRadius: 24, padding: '28px 46px', textAlign: 'center', fontFamily, fontWeight: 900, fontSize: 54, color: '#fff', lineHeight: 1.08, letterSpacing: -1, textShadow: '0 4px 20px rgba(0,0,0,0.55)', boxShadow: '0 18px 50px rgba(0,0,0,0.45)'}}>
            {H.lines.map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
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
          : <Karaoke />
        : null}
    </AbsoluteFill>
  );
};
