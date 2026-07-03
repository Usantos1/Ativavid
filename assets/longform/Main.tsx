/**
 * LONGFORM reference composition (YouTube 16:9). Produced-but-not-saturated:
 * the frame is mostly the talker or a B-roll cutaway; graphics PUNCTUATE.
 * Layers (all optional, driven by the data arrays below):
 *   - base cut (full-frame)         - B-roll cutaways (image Ken-Burns / video)
 *   - lower-thirds (name/title)     - chapter cards (title at each chapter)
 *   - callouts (emphasis boxes)     - soundtrack bed
 * Captions are NOT here — longform ships a .srt for YouTube CC (captions_srt.py).
 * Set the composition size/fps in Root.tsx to match cut.mp4. Reuse the shortform
 * dynamic camera / behind-subject sparingly if a moment calls for it.
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

const {fontFamily} = loadFont('normal', {weights: ['400', '600', '900']});
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const ACCENT = '#33e0a3'; // rebrand here
const MARGIN = 96; // 16:9 safe margin

const Sfx: React.FC<{src: string; volume?: number}> = ({src, volume = 0.08}) => (
  <Audio src={staticFile(`sfx/${src}`)} volume={volume} />
);

// ============ BASE ============
const Base: React.FC = () => {
  const {width, height} = useVideoConfig();
  return <OffthreadVideo src={staticFile('cut.mp4')} style={{width, height}} />;
};

// ============ B-ROLL CUTAWAYS (cover the talker over narration) ================
type Broll = {kind: 'image' | 'video'; src: string; start: number; dur: number};
const BROLL: Broll[] = [
  // {kind: 'image', src: 'broll/x.jpg', start: 12, dur: 4},
  // {kind: 'video', src: 'broll/y.mp4', start: 40, dur: 6},
];

const BrollEl: React.FC<{item: Broll; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const inn = interpolate(f, [0, 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const out = interpolate(f, [totalFrames - 10, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(inn, out);
  const grow = interpolate(f, [0, totalFrames], [1, 1.06], {extrapolateRight: 'clamp'}); // Ken-Burns
  return (
    <AbsoluteFill style={{opacity: op}}>
      <Sfx src="whoosh.mp3" />
      {item.kind === 'image' ? (
        <Img src={staticFile(item.src)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${grow})`}} />
      ) : (
        <OffthreadVideo src={staticFile(item.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      )}
    </AbsoluteFill>
  );
};

// ============ LOWER-THIRDS (name / title) =====================================
type Lower = {name: string; title?: string; start: number; dur: number};
const LOWER_THIRDS: Lower[] = [
  // {name: 'Fill Rocha', title: 'Criador · Edvid', start: 6, dur: 4},
];

const LowerThird: React.FC<{item: Lower; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const inn = interpolate(f, [0, 12], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [totalFrames - 10, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(inn, out);
  const x = interpolate(inn, [0, 1], [-40, 0]);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: MARGIN}}>
      <div style={{opacity: op, transform: `translateX(${x}px)`, display: 'flex', alignItems: 'stretch', gap: 16, fontFamily}}>
        <div style={{width: 8, borderRadius: 4, background: ACCENT}} />
        <div style={{background: 'rgba(20,22,26,0.86)', borderRadius: 12, padding: '14px 22px', boxShadow: '0 12px 34px rgba(0,0,0,0.4)'}}>
          <div style={{color: '#fff', fontWeight: 900, fontSize: 40, lineHeight: 1.05}}>{item.name}</div>
          {item.title ? <div style={{color: ACCENT, fontWeight: 600, fontSize: 24, marginTop: 4}}>{item.title}</div> : null}
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ============ CHAPTER CARDS (title at each chapter start) ======================
type Chapter = {title: string; start: number; dur?: number};
const CHAPTERS: Chapter[] = [
  // {title: 'O que é isso', start: 14},
];

const ChapterCard: React.FC<{title: string; totalFrames: number}> = ({title, totalFrames}) => {
  const f = useCurrentFrame();
  const inn = interpolate(f, [0, 14], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic)});
  const out = interpolate(f, [totalFrames - 12, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(inn, out);
  const y = interpolate(inn, [0, 1], [30, 0]);
  const lineW = interpolate(inn, [0, 1], [0, 120]);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'flex-start', padding: MARGIN, paddingBottom: MARGIN + 40}}>
      <Sfx src="whoosh.mp3" />
      <div style={{opacity: op, transform: `translateY(${y}px)`, fontFamily}}>
        <div style={{height: 6, width: lineW, background: ACCENT, borderRadius: 3, marginBottom: 16}} />
        <div style={{color: '#fff', fontWeight: 900, fontSize: 76, letterSpacing: -1, lineHeight: 1, textShadow: '0 4px 24px rgba(0,0,0,0.6)'}}>{title}</div>
      </div>
    </AbsoluteFill>
  );
};

// ============ CALLOUTS (emphasis box / keyword) ================================
type Callout = {text: string; start: number; dur: number; x?: number; y?: number};
const CALLOUTS: Callout[] = [
  // {text: '2x mais rápido', start: 33, dur: 3, x: 0.62, y: 0.28},
];

const CalloutEl: React.FC<{item: Callout; totalFrames: number}> = ({item, totalFrames}) => {
  const f = useCurrentFrame();
  const pop = interpolate(f, [0, 8], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.back(1.6))});
  const out = interpolate(f, [totalFrames - 8, totalFrames], [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const op = Math.min(interpolate(f, [0, 5], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}), out);
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill>
      <Sfx src="pop.mp3" volume={0.1} />
      <div style={{position: 'absolute', left: (item.x ?? 0.5) * width, top: (item.y ?? 0.3) * height, transform: `translate(-50%,-50%) scale(${clamp(pop, 0.01, 1)})`, opacity: op, fontFamily, fontWeight: 900, fontSize: 44, color: '#0c0d10', background: ACCENT, padding: '10px 22px', borderRadius: 12, boxShadow: '0 10px 30px rgba(0,0,0,0.4)', whiteSpace: 'nowrap'}}>
        {item.text}
      </div>
    </AbsoluteFill>
  );
};

// ============ SOUNDTRACK (bed) ================================================
const Soundtrack: React.FC = () => {
  const {durationInFrames} = useVideoConfig();
  return (
    <Audio
      src={staticFile('trilha.mp3')}
      volume={(f) => interpolate(f, [0, 20, durationInFrames - 40, durationInFrames], [0, 0.1, 0.1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}
    />
  );
};

// ============ helper: map a timed list to sequences ===========================
function Timed<T extends {start: number; dur?: number}>(
  items: T[], defaultDur: number, render: (item: T, totalFrames: number) => React.ReactNode,
) {
  const {fps} = useVideoConfig();
  return (
    <>
      {items.map((it, i) => {
        const from = Math.round(it.start * fps);
        const duration = Math.round((it.dur ?? defaultDur) * fps);
        return (
          <Sequence key={i} from={from} durationInFrames={duration} layout="none">
            {render(it, duration)}
          </Sequence>
        );
      })}
    </>
  );
}

// ============ MAIN ============
export const Main: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: 'black'}}>
      <Soundtrack />
      <Base />
      {Timed(BROLL, 4, (it, d) => <BrollEl item={it} totalFrames={d} />)}
      {Timed(CHAPTERS, 2.4, (it, d) => <ChapterCard title={it.title} totalFrames={d} />)}
      {Timed(LOWER_THIRDS, 4, (it, d) => <LowerThird item={it} totalFrames={d} />)}
      {Timed(CALLOUTS, 3, (it, d) => <CalloutEl item={it} totalFrames={d} />)}
    </AbsoluteFill>
  );
};
