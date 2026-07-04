/**
 * CustomGraphics — the ONE file you edit in Phase 2, and ONLY when a spoken
 * word calls for a bespoke motion graphic instead of a stock image (e.g.
 * "animações" → animated shapes, "roteiro" → a typewriter script sheet,
 * "gráfico" → a growing chart). Everything else is data in edit-data.json.
 *
 * Default: renders nothing. To add graphics, build components here (worked
 * examples below — same upper-zone card motif as the image inserts) and mount
 * them in <CustomGraphics/> with their own <Sequence from/durationInFrames>.
 *
 * Timings: get the payoff word's timestamp from the cut transcript and land
 * the animation on it. Keep 0.5–2s per accent; whoosh on entry, pop on shapes.
 */
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {Sfx} from './Main';

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

// ============ MOUNT POINT (edit this) ==========================================
export const CustomGraphics: React.FC = () => {
  return null;
  // Example — mount worked examples (or your own) with per-video timings:
  // return (
  //   <>
  //     <TimelineGraphic startSec={3.3} endSec={5.6} />
  //     <ScriptGraphic startSec={9.9} endSec={11.9} lines={['Esse vídeo foi 100%', 'editado com IA.']} />
  //     <ShapesGraphic startSec={12.85} endSec={14.15} />
  //   </>
  // );
};

// ============ WORKED EXAMPLE 1: editing timeline being cut + caption tracks =====
// For "os cortes, as legendas e as animações" — a mini editor UI: playhead
// sweeps and splits the video track, caption chips pop in, shapes pop last.
const TL_W = 800;
const TL_H = 378;
const PAD = 46;
const INNER = TL_W - PAD * 2;

const TimelineInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 9], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(appear, [0, 1], [26, 0]);

  // playhead sweeps, bar splits into 3
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

export const TimelineGraphic: React.FC<{startSec: number; endSec: number}> = ({startSec, endSec}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <TimelineInner totalFrames={duration} />
    </Sequence>
  );
};

// ============ WORKED EXAMPLE 2: script sheet with typewriter text ===============
// For "ela leu o roteiro" — a tilted paper card, lines typing in with a cursor.
const ScriptInner: React.FC<{totalFrames: number; lines: string[]}> = ({totalFrames, lines}) => {
  const f = useCurrentFrame();
  const appear = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const exit = interpolate(f, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const cps = 1.7; // chars per frame

  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="whoosh.mp3" />
      <div style={{width: 640, height: 420, marginTop: 100, borderRadius: 16, background: '#f4f1e8', boxShadow: '0 22px 55px rgba(0,0,0,0.5)', opacity: appear * exit, scale: String(interpolate(appear, [0, 1], [0.94, 1])), rotate: '-2deg', translate: `0px ${interpolate(appear, [0, 1], [26, 0])}px`, padding: 46, boxSizing: 'border-box', fontFamily}}>
        <div style={{fontWeight: 900, fontSize: 26, letterSpacing: 3, color: '#c2492b'}}>ROTEIRO</div>
        <div style={{height: 4, width: 90, background: '#c2492b', borderRadius: 3, marginTop: 10, marginBottom: 30}} />
        {lines.map((line, i) => {
          const startLocal = 10 + i * 12;
          const shown = clamp(Math.floor((f - startLocal) * cps), 0, line.length);
          const isTyping = shown > 0 && shown < line.length;
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

export const ScriptGraphic: React.FC<{startSec: number; endSec: number; lines: string[]}> = ({startSec, endSec, lines}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <ScriptInner totalFrames={duration} lines={lines} />
    </Sequence>
  );
};

// ============ WORKED EXAMPLE 3: playful shapes pop (for "animações") ============
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

const ShapesInner: React.FC<{totalFrames: number}> = ({totalFrames}) => {
  const frame = useCurrentFrame();
  const exit = interpolate(frame, [totalFrames - 7, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const rise = interpolate(frame, [0, 8], [24, 0], {extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  return (
    <AbsoluteFill style={{justifyContent: 'flex-start', alignItems: 'center'}}>
      <Sfx src="pop.mp3" volume={0.12} />
      <div style={{marginTop: 210, display: 'flex', gap: 34, opacity: exit, translate: `0px ${rise}px`}}>
        <Shape i={0} color="white" round={46} />
        <Shape i={1} color="#33e0a3" round={20} />
        <Shape i={2} color="white" round={8} />
      </div>
    </AbsoluteFill>
  );
};

export const ShapesGraphic: React.FC<{startSec: number; endSec: number}> = ({startSec, endSec}) => {
  const {fps} = useVideoConfig();
  const from = Math.round(startSec * fps);
  const duration = Math.round((endSec - startSec) * fps);
  return (
    <Sequence from={from} durationInFrames={duration} layout="none">
      <ShapesInner totalFrames={duration} />
    </Sequence>
  );
};
