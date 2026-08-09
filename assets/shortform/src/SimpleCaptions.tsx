/**
 * SimpleCaptions — the three STATIC caption styles.
 *
 *   "simples"  Poppins semibold, squeezed, off-white, ONE line, up to 3 words
 *   "serifada" the same rules in a classic serif (Libre Baskerville)
 *   "classica" classic subtitle: small sans (Inter), TWO lines, low on frame
 *
 * No animation anywhere — a cue simply replaces the previous one on the frame
 * the word starts. That is the whole point of these three: they are what you
 * reach for when the footage, not the typography, should carry the motion.
 *
 * Lines are grouped by MEASURED WIDTH, not by word count. "inteligência" and
 * "de" cannot share a rule: the long word takes its own line and the short ones
 * ride together, which is exactly what a fixed 3-words-per-line would get wrong.
 *
 * Data: public/captions.json (word level) — no extra generation step.
 */
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont as loadPoppins} from '@remotion/google-fonts/Poppins';
import {loadFont as loadBaskerville} from '@remotion/google-fonts/LibreBaskerville';
import {loadFont as loadInter} from '@remotion/google-fonts/Inter';
import {measureText} from '@remotion/layout-utils';
import captions from '../public/captions.json';
import editData from '../public/edit-data.json';

const POPPINS = loadPoppins('normal', {weights: ['600']}).fontFamily;
const BASKERVILLE = loadBaskerville('normal', {weights: ['700']}).fontFamily;
const INTER = loadInter('normal', {weights: ['500']}).fontFamily;

const OFFWHITE = '#f4f1e9';

type Word = {text: string; startMs: number; endMs: number};
type Variant = {
  family: string;
  weight: number;
  size: number;
  maxWords: number;
  lines: 1 | 2;
  squeeze: number; // horizontal scale — Poppins ships no condensed cut
  squeezeY: number; // vertical scale — squat the letterforms, does NOT regroup
  tracking: number;
  bottom: number;
  maxW: number;
  // "bloco": each line sits on a solid slab instead of floating over the
  // footage. For THIS variant the picked caption colour paints the SLAB and
  // the text is always white — coloured text over a shop wall full of
  // coloured product is the case a text-shadow cannot rescue.
  block?: boolean;
};

const C = (editData as any).captions ?? {};
export const SIMPLE_VARIANTS: Record<string, Variant> = {
  simples: {
    family: POPPINS,
    weight: 600,
    size: 82,
    maxWords: 3,
    lines: 1,
    squeeze: 0.9,
    squeezeY: 0.9,
    tracking: -3,
    bottom: 430,
    maxW: 860,
  },
  serifada: {
    family: BASKERVILLE,
    weight: 700,
    size: 84,
    maxWords: 3,
    lines: 1,
    squeeze: 1,
    squeezeY: 1,
    tracking: -1,
    bottom: 430,
    maxW: 860,
  },
  classica: {
    family: INTER,
    weight: 500,
    size: 52,
    maxWords: 14,
    lines: 2,
    squeeze: 1,
    squeezeY: 1,
    tracking: 0,
    bottom: 430, // same height as the other two — low on frame it read as an afterthought
    maxW: 840,
  },
  bloco: {
    family: POPPINS,
    weight: 800,
    size: 76,
    maxWords: 3,
    lines: 1,
    squeeze: 1,
    squeezeY: 1,
    tracking: -2,
    bottom: 430,
    // narrower than the others: the slab adds padding on both sides, so
    // fitting to their 860 would run the block past the safe area
    maxW: 760,
    block: true,
  },
};

/* Text colour for the "bloco" slab, decided from the slab's own brightness.
 * Hardcoding white text broke the moment the picked caption colour was light:
 * this project picks #FFFFFF, which rendered a white slab with white text —
 * invisible. Relative luminance (sRGB coefficients) is the cheap correct test;
 * the 0.6 threshold sits above mid-grey because white text on a mid tone reads
 * worse than black does. */
function inkOn(bg: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(bg.trim());
  if (!m) return '#fff';
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return lum > 0.6 ? '#111214' : '#fff';
}

const clean = (t: string) => t.replace(/[.,!?…]+$/, '');
const isBreak = (t: string) => /[.,!?…]$/.test(t);

const widthOf = (words: Word[], V: Variant) =>
  measureText({
    text: words.map((w) => clean(w.text)).join(' '),
    fontFamily: V.family,
    fontSize: V.size,
    fontWeight: V.weight,
    letterSpacing: `${V.tracking}px`,
  }).width * V.squeeze;

// Group by width first, word count second. A cue also ends on punctuation or on
// a speech gap, so the text breaks where the speaker breathes.
function buildCues(words: Word[], V: Variant): Word[][] {
  const budget = V.maxW * V.lines;
  const cues: Word[][] = [];
  let cur: Word[] = [];
  words.forEach((w, i) => {
    const trial = [...cur, w];
    if (cur.length && (trial.length > V.maxWords || widthOf(trial, V) > budget)) {
      cues.push(cur);
      cur = [w];
    } else {
      cur = trial;
    }
    const prev = words[i];
    const next = words[i + 1];
    const gap = next ? next.startMs - prev.endMs : 0;
    if (cur.length && (isBreak(prev.text) || gap > 450)) {
      cues.push(cur);
      cur = [];
    }
  });
  if (cur.length) cues.push(cur);
  return cues;
}

// Two-line styles split where the halves come out closest in width — but a pure
// width balance happily ends a line on "o" or "de", which is the one thing a
// classic subtitle never does. Breaking after a short function word carries a
// penalty worth ~200px of imbalance, so it only wins when nothing else is close.
const ORPHAN = /^(o|a|os|as|e|é|de|do|da|em|no|na|um|uma|que|se|ao|à|por|com)$/i;

function splitTwo(words: Word[], V: Variant): Word[][] {
  if (V.lines === 1 || words.length < 2) return [words];
  let best = 0;
  let bestScore = Infinity;
  for (let i = 1; i < words.length; i++) {
    const diff = Math.abs(widthOf(words.slice(0, i), V) - widthOf(words.slice(i), V));
    const tail = clean(words[i - 1].text);
    const score = diff + (ORPHAN.test(tail) ? 200 : 0);
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  return [words.slice(0, best), words.slice(best)];
}

export const SimpleCaptions: React.FC<{variant: string}> = ({variant}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const V = SIMPLE_VARIANTS[variant] ?? SIMPLE_VARIANTS.simples;
  const cues = buildCues(captions as Word[], V);

  let idx = -1;
  for (let i = 0; i < cues.length; i++) {
    if (frame >= Math.round((cues[i][0].startMs / 1000) * fps)) idx = i;
  }
  if (idx < 0) return null;
  const next = cues[idx + 1];
  const end = next
    ? Math.round((next[0].startMs / 1000) * fps)
    : Math.min(durationInFrames, Math.round((cues[idx][cues[idx].length - 1].endMs / 1000) * fps) + fps);
  if (frame >= end) return null;

  const lines = splitTwo(cues[idx], V);

  if (V.block) {
    const pad = Math.round(V.size * 0.16);
    const slab = C.accent ?? '#111214';
    const ink = inkOn(slab);
    return (
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: V.bottom}}>
        <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: Math.round(V.size * 0.14)}}>
          {lines.map((ln, i) => (
            <div
              key={i}
              style={{
                fontFamily: V.family,
                fontWeight: V.weight,
                fontSize: V.size,
                letterSpacing: V.tracking,
                lineHeight: 1.06,
                color: ink,
                whiteSpace: 'pre',
                background: slab,
                padding: `${Math.round(pad * 0.55)}px ${pad}px ${Math.round(pad * 0.75)}px`,
                borderRadius: Math.round(V.size * 0.16),
                boxShadow: '0 12px 30px rgba(0,0,0,0.45)',
              }}
            >
              {ln.map((w) => clean(w.text)).join(' ')}
            </div>
          ))}
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: V.bottom}}>
      <div
        style={{
          textAlign: 'center',
          fontFamily: V.family,
          fontWeight: V.weight,
          fontSize: V.size,
          letterSpacing: V.tracking,
          lineHeight: 1.18,
          color: C.accent ?? OFFWHITE,
          whiteSpace: 'pre',
          // scaleY only squats the glyphs — the line grouping is measured on
          // WIDTH, so unlike the horizontal squeeze this changes no line breaks
          transform:
            V.squeeze === 1 && V.squeezeY === 1
              ? undefined
              : `scale(${V.squeeze}, ${V.squeezeY})`,
          textShadow: '0 4px 18px rgba(0,0,0,0.55)',
        }}
      >
        {lines.map((ln, i) => (
          <div key={i}>{ln.map((w) => clean(w.text)).join(' ')}</div>
        ))}
      </div>
    </AbsoluteFill>
  );
};
