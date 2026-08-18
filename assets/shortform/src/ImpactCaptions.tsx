/**
 * ImpactCaptions — caption style "impacto".
 *
 * The dominant sales-Reels look: short UPPERCASE cues, and the word being
 * SPOKEN right now sits in a solid rounded box that pops in. Everything else
 * is plain white — the box is the style, so only one word ever has it.
 *
 * The box colour is the picked emphasisAccent (same role as the highlighted
 * word in scatter / the serif line in stacked: the ONE accented element of the
 * style). Text inside the box flips black/white by the box's own luminance —
 * hardcoding white broke the bloco style once already (see SimpleCaptions).
 *
 * Data: public/captions.json (word level, same file karaoke reads).
 * No extra generation step, no Math.random(): frames must agree.
 */
import {
  AbsoluteFill,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import editData from '../public/edit-data.json';

const {fontFamily} = loadFont('normal', {weights: ['800', '900']});

type Word = {text: string; startMs: number; endMs: number};

const C = (editData as any).captions ?? {};
const SIZE = Math.round(72 * (C.sizeScale ?? 1)); // captionSize do preset
const MAX_W = 820;
const MAX_WORDS = 3;
const BOTTOM = C.paddingBottom ?? 430; // captionPosition entra por aqui (900/1330)
const BOX = C.emphasisAccent || '#ffd400';
const POP = 5; // frames — the box lands fast; slower reads as lag, not punch

// same luminance rule as SimpleCaptions.inkOn — the box colour is user-picked,
// so the ink inside it cannot be hardcoded
function inkOn(bg: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(bg.trim());
  if (!m) return '#111214';
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.6 ? '#111214' : '#fff';
}

const INK = inkOn(BOX);
const clean = (t: string) => t.replace(/[.,!?…]+$/, '').toUpperCase();
const isBreak = (t: string) => /[.,!?…]$/.test(t);

const widthOf = (words: Word[]) =>
  measureText({
    text: words.map((w) => clean(w.text)).join(' '),
    fontFamily,
    fontSize: SIZE,
    fontWeight: 900,
  }).width;

// One line per cue, grouped by measured width first, count second, breath
// (punctuation / 450ms gap) last — the same grouping contract the static
// styles follow, so switching styles never regroups the speech differently.
function buildCues(words: Word[]): Word[][] {
  const cues: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    const trial = [...cur, w];
    if (cur.length && (trial.length > MAX_WORDS || widthOf(trial) > MAX_W)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
    const next = words[i + 1];
    const gap = next ? next.startMs - w.endMs : 0;
    if (cur.length && (isBreak(w.text) || gap > 450)) {
      cues.push(cur);
      cur = [];
    }
  });
  if (cur.length) cues.push(cur);
  return cues;
}

const CUES = buildCues(captions as Word[]);

export const ImpactCaptions: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  let idx = -1;
  for (let i = 0; i < CUES.length; i++) {
    if (frame >= Math.round((CUES[i][0].startMs / 1000) * fps)) idx = i;
  }
  if (idx < 0) return null;
  const cue = CUES[idx];
  const next = CUES[idx + 1];
  const end = next
    ? Math.round((next[0].startMs / 1000) * fps)
    : Math.min(durationInFrames, Math.round((cue[cue.length - 1].endMs / 1000) * fps) + fps);
  if (frame >= end) return null;

  // the word being spoken NOW — the last one whose start has passed
  let hot = 0;
  for (let i = 0; i < cue.length; i++) {
    if (frame >= Math.round((cue[i].startMs / 1000) * fps)) hot = i;
  }

  const pad = Math.round(SIZE * 0.18);
  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: BOTTOM}}>
      <div
        style={{
          display: 'flex',
          gap: Math.round(SIZE * 0.22),
          alignItems: 'center',
          fontFamily,
          fontWeight: 900,
          fontSize: SIZE,
          lineHeight: 1.08,
          whiteSpace: 'pre',
        }}
      >
        {cue.map((w, i) => {
          const isHot = i === hot;
          const start = Math.round((w.startMs / 1000) * fps);
          // pop: the box overshoots slightly and settles — on the BOX only,
          // plain words never move (motion on every word is motion on nothing)
          const t = interpolate(frame, [start, start + POP], [0, 1], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.out(Easing.back(2.2)),
          });
          if (!isHot) {
            return (
              <span key={i} style={{color: '#fff', textShadow: '0 4px 18px rgba(0,0,0,0.6)'}}>
                {clean(w.text)}
              </span>
            );
          }
          return (
            <span
              key={i}
              style={{
                color: INK,
                background: BOX,
                borderRadius: Math.round(SIZE * 0.18),
                padding: `${Math.round(pad * 0.35)}px ${pad}px ${Math.round(pad * 0.5)}px`,
                transform: `scale(${(0.7 + 0.3 * t).toFixed(3)})`,
                boxShadow: '0 10px 26px rgba(0,0,0,0.45)',
                display: 'inline-block',
              }}
            >
              {clean(w.text)}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
