/**
 * REFERENCE short-form composition (Reels/TikTok/Shorts) — see README.md.
 * Adapt per video: captions.json/track.json/segments.json in public/, INSERTS[]
 * timings, ZOOMS[] per-cut levels. TimelineGraphic/ScriptGraphic are examples of
 * "custom motion graphic instead of a stock photo". Audio: SFX pack in
 * public/sfx/ (whoosh on appearances, pop on shapes) + Soundtrack (Treblo AI
 * track or local file) as public/trilha.mp3. Keep audio layers low and run a
 * final loudnorm pass on the render (voice+music+SFX can clip). Style carries
 * over unchanged; just re-time.
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

// SFX played at an appearance (whoosh) or a pop for shapes
const Sfx: React.FC<{src: string; volume?: number}> = ({src, volume = 0.09}) => (
  <Audio src={staticFile(`sfx/${src}`)} volume={volume} />
);
import {loadFont} from '@remotion/google-fonts/Poppins';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import track from '../public/track.json';
import segData from '../public/segments.json';

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});

type Caption = {text: string; startMs: number; endMs: number};
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const clamp01 = (v: number) => clamp(v, 0, 1);

// ============ DYNAMIC CAMERA (hard zoom on cuts + push-in + eye tracking) ======
const ZOOMS = [1.14, 1.2, 1.12, 1.22, 1.16, 1.1, 1.18]; // per cut segment
const PUSH_IN = 0.04; // slow growth within each segment
const TARGET_X = 0.5;
const TARGET_Y = 0.4; // keep eyes on the upper third

// src defaults to the base cut. frameOffset lets a windowed layer (e.g. a person
// matte inside a <Sequence>) use the GLOBAL frame for the camera math so it stays
// aligned with the base. transparent enables ProRes/WebM alpha (person matte).
// children render inside the same transformed space.
const DynamicVideo: React.FC<{src?: string; frameOffset?: number; transparent?: boolean; children?: React.ReactNode}> = ({
  src = 'cut.mp4',
  frameOffset = 0,
  transparent = false,
  children,
}) => {
  const frame = useCurrentFrame() + frameOffset;
  const {width, height, fps} = useVideoConfig();

  // which cut segment is this frame in?
  const segs = segData.segments;
  let idx = 0;
  for (let i = 0; i < segs.length; i++) {
    if (frame >= Math.round(segs[i].start * fps)) idx = i;
  }
  const segFrom = Math.round(segs[idx].start * fps);
  const segLen = Math.max(1, Math.round(segs[idx].dur * fps));
  const base = ZOOMS[idx % ZOOMS.length];
  const push = PUSH_IN * clamp01((frame - segFrom) / segLen);
  const S = base + push;

  const pts = track.points;
  const [cx, cy] = pts[Math.min(frame, pts.length - 1)] ?? [0.5, 0.4];
  let tx = TARGET_X * width - cx * width * S;
  let ty = TARGET_Y * height - cy * height * S;
  tx = clamp(tx, width - width * S, 0); // never reveal an edge
  ty = clamp(ty, height - height * S, 0);

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
// person_matte.py (see SKILL.md 5d), one file per window, frame 0 = window start.
type BehindImage = {kind: 'image'; src: string; matte: string; start: number; dur: number};
type BehindWords = {kind: 'words'; words: {t: string; at: number}[]; matte: string; start: number; dur: number};
type Behind = BehindImage | BehindWords;
const BEHIND: Behind[] = [
  // {kind: 'image', src: 'ill/x.jpg', matte: 'fg_x.mov', start: 4.15, dur: 1.65},
  // {kind: 'words', matte: 'fg_w.mov', start: 19.55, dur: 1.5,
  //   words: [{t: 'MAS', at: 19.55}, {t: 'POR', at: 19.9}, {t: 'QUE', at: 20.26}]},
];

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
      {BEHIND.map((b, i) => {
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
const MAX_WORDS = 3;
const FONT_SIZE = 76;
const LETTER_SPACING = -1;
const SAFE_WIDTH = 720; // ~180px each side on 1080 — clears the platform right-side action rail (like/comment/share)
const PADDING_BOTTOM = 420;
const cleanW = (t: string) => t.replace(/[.,!?…]+$/, '');
const isBreak = (t: string) => /[.,!?…]$/.test(t);

function buildLines(caps: Caption[]): Caption[][] {
  const lines: Caption[][] = [];
  let cur: Caption[] = [];
  for (const w of caps) {
    cur.push(w);
    if (cur.length >= MAX_WORDS || isBreak(w.text)) {
      lines.push(cur);
      cur = [];
    }
  }
  if (cur.length) lines.push(cur);
  return lines;
}
const LINES = buildLines(captions as Caption[]);

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
          fontSize: FONT_SIZE,
          fontWeight: 900,
          letterSpacing: `${LETTER_SPACING}px`,
        });
        const fit = Math.min(1, SAFE_WIDTH / width);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: PADDING_BOTTOM}}>
              <div
                style={{
                  fontFamily,
                  fontWeight: 900,
                  fontSize: FONT_SIZE,
                  color: 'white',
                  lineHeight: 1,
                  letterSpacing: LETTER_SPACING,
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

// ============ ILLUSTRATIVE IMAGE INSERTS (rounded card + shadow) ================
type Insert = {src: string; start: number; end: number};
const INSERTS: Insert[] = [
  {src: 'ai.jpg', start: 1.95, end: 3.35},
  {src: 'car.jpg', start: 6.85, end: 9.5},
  {src: 'social.jpg', start: 15.05, end: 16.5},
  {src: 'youtube.jpg', start: 16.6, end: 18.1},
  {src: 'podcast.jpg', start: 19.45, end: 20.85},
];
const CARD_W = 780;
const CARD_H = 500;
const CARD_TOP = 90;

const InsertCard: React.FC<{src: string; totalFrames: number}> = ({src, totalFrames}) => {
  const frame = useCurrentFrame();
  const enter = interpolate(frame, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(frame, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const opacity = Math.min(enter, exit);
  // dynamic zoom: the image itself grows slowly while on screen
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
      {INSERTS.map((it, i) => {
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

// ============ MOTION GRAPHIC for "animações" (~13.0s) ===========================
const GREEN = '#33e0a3';
const Shape: React.FC<{i: number; color: string; round: number}> = ({i, color, round}) => {
  const frame = useCurrentFrame();
  const appear = interpolate(frame, [i * 3, i * 3 + 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.6))});
  const pulse = 1 + 0.16 * Math.sin((frame + i * 6) * 0.28);
  const rot = Math.sin((frame + i * 8) * 0.12) * 22;
  return (
    <div
      style={{
        width: 92,
        height: 92,
        background: color,
        borderRadius: round,
        opacity: appear,
        scale: String(appear * pulse),
        rotate: `${rot}deg`,
        boxShadow: '0 10px 30px rgba(0,0,0,0.35)',
      }}
    />
  );
};

const AnimacoesGraphic: React.FC = () => {
  const {fps} = useVideoConfig();
  const from = Math.round(12.85 * fps);
  const duration = Math.round((14.15 - 12.85) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <AnimInner totalFrames={duration} />
    </Sequence>
  );
};

const AnimInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(frame, [0, 8], [24, 0], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="pop.mp3" volume={0.12} />
      <div style={{marginTop: 210, display: 'flex', gap: 34, opacity: exit, translate: `0px ${rise}px`}}>
        <Shape i={0} color="white" round={46} />
        <Shape i={1} color={GREEN} round={20} />
        <Shape i={2} color="white" round={8} />
      </div>
    </AbsoluteFill>
  );
};

// ============ MOTION GRAPHIC: editing timeline being cut + caption tracks =======
// for "Os cortes, as legendas e as animações"
const TL_W = 800;
const TL_H = 378;
const PAD = 46;
const INNER = TL_W - PAD * 2;

const TimelineInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(appear, [0, 1], [26, 0]);

  // "cortes" ~ local 0–16: playhead sweeps, bar splits into 3
  const gap = interpolate(f, [6, 16], [0, 16], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pieceW = (INNER - gap * 2) / 3;
  const playX = interpolate(f, [0, 16], [0, INNER], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const playOp = interpolate(f, [0, 2, 15, 19], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: TL_W, height: TL_H, marginTop: 105, borderRadius: 28, background: '#15171c', border: '1px solid #262a31', boxShadow: '0 18px 50px rgba(0,0,0,0.5)', opacity: appear * exit, scale: String(interpolate(appear, [0, 1], [0.93, 1])), translate: `0px ${rise}px`, padding: PAD, boxSizing: 'border-box', position: 'relative', fontFamily}}>
        {/* window dots */}
        <div style={{display: 'flex', gap: 12}}>
          {['#ff5f57', '#febc2e', '#28c840'].map((c) => (<div key={c} style={{width: 16, height: 16, borderRadius: 999, background: c}} />))}
        </div>

        {/* VIDEO track — being cut */}
        <div style={{position: 'absolute', left: PAD, top: 92, width: INNER, height: 62}}>
          {[0, 1, 2].map((i) => (
            <div key={i} style={{position: 'absolute', left: i * (pieceW + gap), width: pieceW, height: 62, borderRadius: 10, background: 'linear-gradient(180deg,#5b8dff,#3f6fe0)', boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.15)'}} />
          ))}
          <div style={{position: 'absolute', left: playX, top: -8, width: 3, height: 78, background: 'white', opacity: playOp, boxShadow: '0 0 8px rgba(255,255,255,0.8)'}} />
        </div>

        {/* LEGENDAS track — caption chips appear */}
        <div style={{position: 'absolute', left: PAD, top: 188, width: INNER, height: 46}}>
          {[0, 1, 2, 3].map((k) => {
            const ap = interpolate(f, [16 + k * 5, 24 + k * 5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.5))});
            return (
              <div key={k} style={{position: 'absolute', left: k * (INNER / 4), width: INNER / 4 - 14, height: 46, borderRadius: 9, background: '#33e0a3', opacity: Math.min(1, ap), scale: String(Math.max(0.01, ap)), display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6, padding: '0 12px', boxSizing: 'border-box'}}>
                <div style={{height: 6, width: '80%', borderRadius: 4, background: 'rgba(0,0,0,0.55)'}} />
                <div style={{height: 6, width: '55%', borderRadius: 4, background: 'rgba(0,0,0,0.4)'}} />
              </div>
            );
          })}
        </div>

        {/* ANIMAÇÕES track — shapes pop */}
        <div style={{position: 'absolute', left: PAD, top: 270, width: INNER, height: 60, display: 'flex', gap: 20, alignItems: 'center'}}>
          {[0, 1, 2, 3].map((k) => {
            const ap = interpolate(f, [34 + k * 4, 42 + k * 4], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.8))});
            const rot = Math.sin((f + k * 7) * 0.2) * 20;
            const colors = ['#ffffff', '#ffd23f', '#ff5f9e', '#5b8dff'];
            const rounds = [999, 12, 6, 999];
            return (<div key={k} style={{width: 52, height: 52, background: colors[k], borderRadius: rounds[k], opacity: Math.min(1, ap), scale: String(Math.max(0.01, ap)), rotate: `${rot}deg`}} />);
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const TimelineGraphic: React.FC = () => {
  const {fps} = useVideoConfig();
  const from = Math.round(3.3 * fps);
  const duration = Math.round((5.6 - 3.3) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <TimelineInner totalFrames={duration} />
    </Sequence>
  );
};

// ============ MOTION GRAPHIC: a script sheet with text being written ============
// for "Ela leu o roteiro"
const SCRIPT_LINES = ['Esse vídeo foi 100%', 'editado com IA.', 'Cortes, legendas...'];
const ScriptInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cps = 1.7; // chars per frame

  let typingLine = 0;
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: 640, height: 420, marginTop: 100, borderRadius: 16, background: '#f4f1e8', boxShadow: '0 22px 55px rgba(0,0,0,0.5)', opacity: appear * exit, scale: String(interpolate(appear, [0, 1], [0.94, 1])), rotate: '-2deg', translate: `0px ${interpolate(appear, [0, 1], [26, 0])}px`, padding: 46, boxSizing: 'border-box', fontFamily}}>
        <div style={{fontWeight: 900, fontSize: 26, letterSpacing: 3, color: '#c2492b'}}>ROTEIRO</div>
        <div style={{height: 4, width: 90, background: '#c2492b', borderRadius: 3, marginTop: 10, marginBottom: 30}} />
        {SCRIPT_LINES.map((line, i) => {
          const startLocal = 10 + i * 12;
          const shown = clamp(Math.floor((f - startLocal) * cps), 0, line.length);
          const isTyping = shown > 0 && shown < line.length;
          if (shown > 0 && shown < line.length) typingLine = i;
          const cursor = isTyping && Math.floor(f / 6) % 2 === 0 ? '|' : '';
          return (
            <div key={i} style={{fontWeight: 400, fontSize: 32, color: '#2b2b2b', lineHeight: 1.5, minHeight: 40}}>
              {line.slice(0, shown)}
              <span style={{color: '#c2492b'}}>{cursor}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

const ScriptGraphic: React.FC = () => {
  const {fps} = useVideoConfig();
  const from = Math.round(9.9 * fps);
  const duration = Math.round((11.9 - 9.9) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <ScriptInner totalFrames={duration} />
    </Sequence>
  );
};

// ============ SOUNDTRACK (Treblo AI track or a local file) — background bed ====
const Soundtrack: React.FC = () => {
  const {durationInFrames} = useVideoConfig();
  return (
    <Audio
      src={staticFile('trilha.mp3')}
      volume={(f) =>
        interpolate(f, [0, 10, durationInFrames - 24, durationInFrames], [0, 0.12, 0.12, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        })
      }
    />
  );
};

// ============ VISUAL HOOK (static headline in the first ~4s — always on) =======
// Write HEADLINE_LINES like a copywriting/virality specialist from the cut
// transcript (curiosity gap · high stakes · specificity · urgency). Rules:
//   • caption-style text: Poppins Black, white, UPPERCASE, on a dark-gray rounded
//     card for contrast. ALL lines the SAME font size — never mix sizes.
//   • static: no per-word animation, just a clean fade in/out.
//   • pair with a logo/symbol when it sharpens the angle. Drop real brand assets
//     in public/ (logo card + a hazard/transparent sign) and swap the <Img> srcs.
const HOOK_END = 4.0;
const HOOK_BG = '#232326'; // dark-gray card behind the headline
const HEADLINE_LINES = ['A IA MAIS', 'PERIGOSA DO MUNDO', 'ACABOU DE SER LIBERADA']; // ← rewrite per video
const HOOK_LOGO = 'brand/logo.webp'; // ← brand logo card (or remove the <Img>)
const HOOK_SIGN = 'brand/warning.webp'; // ← hazard/angle symbol (transparent)

const HookInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const enter = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 9, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(enter, exit);
  const y = interpolate(enter, [0, 1], [24, 0]);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center', paddingTop: 120}}>
        <Sfx src="whoosh.mp3" volume={0.1} />
        <div style={{opacity: op, translate: `0px ${y}px`, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 34}}>
            <Img src={staticFile(HOOK_LOGO)} style={{width: 300, borderRadius: 18, boxShadow: '0 12px 34px rgba(0,0,0,0.4)'}} />
            <Img src={staticFile(HOOK_SIGN)} style={{width: 128, filter: 'drop-shadow(0 8px 20px rgba(0,0,0,0.45))'}} />
          </div>
          {/* headline card — caption-style text, ALL LINES ONE SIZE */}
          <div style={{background: HOOK_BG, borderRadius: 24, padding: '28px 46px', textAlign: 'center', fontFamily, fontWeight: 900, fontSize: 54, color: '#fff', lineHeight: 1.08, letterSpacing: -1, textShadow: '0 4px 20px rgba(0,0,0,0.55)', boxShadow: '0 18px 50px rgba(0,0,0,0.45)'}}>
            {HEADLINE_LINES.map((l, i) => (<div key={i}>{l}</div>))}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const HookIntro: React.FC = () => {
  const {fps} = useVideoConfig();
  const dur = Math.round(HOOK_END * fps);
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
      <Soundtrack />
      <DynamicVideo />
      <BehindSubject />
      <Inserts />
      <TimelineGraphic />
      <ScriptGraphic />
      <AnimacoesGraphic />
      <HookIntro />
      <Karaoke />
    </AbsoluteFill>
  );
};
