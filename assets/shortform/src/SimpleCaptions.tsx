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
import {capFamily, capWeight} from './fonts';

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
  // "recorte": CapCut-style sticker — UPPERCASE white glyphs cut out by a
  // thick near-black outline. The outline is what guarantees legibility, so
  // the picked caption colour tints the TEXT (accent over dark edge always
  // reads); the outline itself is never user-coloured.
  sticker?: boolean;
  // Os cinco de 30/08. `modo` decide o RAMO de desenho; `bloco`/`sticker`
  // continuam como flags proprias porque ja estavam no contrato.
  modo?: 'metal' | 'vidro' | 'traco' | 'moldura' | 'eco';
};

// Quem desenha em CAIXA ALTA. Muda a MEDIDA das linhas, entao os tres
// motores (este, o render_proprio e a previa) tem de concordar.
const MAIUSCULA = new Set(['metal', 'moldura', 'eco']);

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
  recorte: {
    family: POPPINS,
    weight: 800,
    size: 78,
    maxWords: 3,
    lines: 1,
    squeeze: 1,
    squeezeY: 1,
    tracking: -1,
    bottom: 430,
    // the outline eats ~8px each side; keep the sticker inside the safe area
    maxW: 800,
    sticker: true,
  },
  // ---- os cinco de 30/08 -------------------------------------------------
  metal: {
    family: POPPINS, weight: 800, size: 76, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -1, bottom: 430, maxW: 800,
    modo: 'metal',
  },
  vidro: {
    family: INTER, weight: 500, size: 50, maxWords: 12, lines: 2,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 700,
    modo: 'vidro',
  },
  traco: {
    family: POPPINS, weight: 800, size: 74, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -1, bottom: 430, maxW: 820,
    modo: 'traco',
  },
  moldura: {
    family: INTER, weight: 600, size: 44, maxWords: 6, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: 6, bottom: 430, maxW: 700,
    modo: 'moldura',
  },
  eco: {
    family: POPPINS, weight: 800, size: 78, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -2, bottom: 430, maxW: 800,
    modo: 'eco',
  },
};

/* As cinco paradas do cromado, tiradas DA COR escolhida. `f > 1` clareia
 * em direcao ao branco, `f < 1` escurece. A parada escura em 50% com o
 * estalo de luz logo abaixo e o que o olho le como metal — um degrade
 * suave de claro para escuro parece papel. */
function degradeMetal(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  const n = m ? parseInt(m[1], 16) : 0xe8edf3;
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const paradas: [number, number][] = [
    [0, 1.45], [34, 0.55], [50, 0.38], [56, 1.6], [100, 0.72],
  ];
  return paradas
    .map(([pos, f]) => {
      const rgb = c.map((v) =>
        Math.round(f > 1 ? v + (255 - v) * Math.min(1, f - 1) : v * f));
      return `rgb(${rgb.join(',')}) ${pos}%`;
    })
    .join(', ');
}

/* Contorno por sombras em 8 direcoes — nao `-webkit-text-stroke`, que come
 * metade da espessura para dentro do glifo. */
function contornoCss(r: number, cor: string): string[] {
  const d = (0.7071 * r).toFixed(1);
  return [
    `${r}px 0 0 ${cor}`, `-${r}px 0 0 ${cor}`,
    `0 ${r}px 0 ${cor}`, `0 -${r}px 0 ${cor}`,
    `${d}px ${d}px 0 ${cor}`, `-${d}px ${d}px 0 ${cor}`,
    `${d}px -${d}px 0 ${cor}`, `-${d}px -${d}px 0 ${cor}`,
  ];
}

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
    // recorte renders UPPERCASE — measuring the lowercase form would group
    // lines ~10% too wide and run the sticker past the safe area
    text: words
      .map((w) => (V.sticker || MAIUSCULA.has(V.modo ?? '')
        ? clean(w.text).toUpperCase()
        : clean(w.text)))
      .join(' '),
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

// Posição/tamanho do preset: "baixo" mantém o bottom de cada variante;
// centro/alto usam a mesma altura visual do karaokê. O tamanho escala a fonte
// ANTES do agrupamento — a quebra de linha é medida no tamanho final.
const POS_BOTTOM: Record<string, number> = {centro: 900, alto: 1330};
const CAP_SCALE: number = (C as any).sizeScale ?? 1;

export const SimpleCaptions: React.FC<{variant: string}> = ({variant}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const base = SIMPLE_VARIANTS[variant] ?? SIMPLE_VARIANTS.simples;
  const V: Variant = {
    ...base,
    // fonte da marca (fonts.ts) — a medição de largura usa a MESMA família
    // e peso efetivos, então as quebras de linha acompanham a troca
    family: capFamily(base.family),
    weight: capWeight(base.weight),
    size: Math.round(base.size * CAP_SCALE),
    bottom: POS_BOTTOM[(C as any).position as string] ?? base.bottom,
  };
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

  if (V.modo) {
    const CAIXA = MAIUSCULA.has(V.modo);
    const txt = (ln: Word[]) =>
      ln.map((w) => (CAIXA ? clean(w.text).toUpperCase() : clean(w.text))).join(' ');
    const LH: Record<string, number> = {
      metal: 1.1, vidro: 1.34, traco: 1.16, moldura: 1.2, eco: 1.14,
    };
    const tipo = {
      fontFamily: V.family,
      fontWeight: V.weight,
      fontSize: V.size,
      letterSpacing: V.tracking,
      lineHeight: LH[V.modo],
      whiteSpace: 'pre' as const,
      textAlign: 'center' as const,
    };
    const fora = {
      justifyContent: 'flex-end' as const,
      alignItems: 'center' as const,
      paddingBottom: V.bottom,
    };

    if (V.modo === 'metal') {
      // Duas copias: a de baixo so o contorno (fill transparente — a sombra
      // sai do GLIFO, nao do preenchimento), a de cima o cromado. Uma copia
      // so nao serve: com `background-clip: text` o fundo e pintado antes
      // das sombras, e o contorno taparia o degrade.
      const R = Math.max(2, Math.round(V.size * 0.035));
      const borda = contornoCss(R, '#0e1013').join(', ');
      const corpo = lines.map((ln, i) => <div key={i}>{txt(ln)}</div>);
      return (
        <AbsoluteFill style={fora}>
          <div style={{position: 'relative'}}>
            <div style={{...tipo, color: 'transparent',
                         textShadow: `${borda}, 0 10px 24px rgba(0,0,0,0.5)`}}>
              {corpo}
            </div>
            <div
              style={{
                ...tipo,
                position: 'absolute',
                left: 0,
                top: 0,
                width: '100%',
                backgroundImage: `linear-gradient(180deg, ${degradeMetal(C.accent ?? '#e8edf3')})`,
                WebkitBackgroundClip: 'text',
                backgroundClip: 'text',
                color: 'transparent',
                WebkitTextFillColor: 'transparent',
              }}
            >
              {corpo}
            </div>
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'traco') {
      // o Recorte com contorno FINO: 3px em vez dos 7px dele
      const R = Math.max(2, Math.round(V.size * 0.035));
      return (
        <AbsoluteFill style={fora}>
          <div style={{...tipo, color: C.accent ?? '#fff',
                       textShadow: [...contornoCss(R, '#101215'),
                                    '0 8px 20px rgba(0,0,0,0.4)'].join(', ')}}>
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'eco') {
      // As sombras do CSS pintam na ordem INVERSA da lista: a primeira fica
      // por cima. Ciano em cima, magenta embaixo, o texto sobre os dois.
      const d = Math.max(3, Math.round(V.size * 0.085));
      return (
        <AbsoluteFill style={fora}>
          <div style={{...tipo, color: C.accent ?? '#fff',
                       textShadow: [`${-d}px ${-d}px 0 #28e0d8`,
                                    `${d}px ${d}px 0 #ff2e88`,
                                    '0 10px 26px rgba(0,0,0,0.45)'].join(', ')}}>
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    // vidro e moldura: UM painel em volta do cue inteiro (o bloco da uma
    // lapide por linha — aqui a caixa e uma so, com as duas dentro)
    const vidro = V.modo === 'vidro';
    const padX = Math.round(V.size * (vidro ? 0.62 : 0.72));
    const padY = Math.round(V.size * (vidro ? 0.44 : 0.4));
    return (
      <AbsoluteFill style={fora}>
        <div
          style={{
            ...tipo,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: Math.round(V.size * 0.16),
            padding: `${padY}px ${padX}px`,
            borderRadius: vidro ? Math.round(V.size * 0.6) : 4,
            // Vidro FUMADO: o take fica escuro atras da letra em vez de
            // desfocado. O motor rapido desenha um overlay, SEM o take
            // embaixo — um desfoque de verdade so existiria num dos dois.
            background: vidro
              ? 'linear-gradient(180deg, rgba(255,255,255,0.16), rgba(255,255,255,0.02)), rgba(13,15,20,0.46)'
              : 'rgba(11,13,16,0.30)',
            border: vidro
              ? '2px solid rgba(255,255,255,0.34)'
              : `2px solid ${C.accent ?? '#ffffff'}d9`,
            color: C.accent ?? (vidro ? '#f7f9fc' : '#ffffff'),
            boxShadow: '0 18px 40px rgba(0,0,0,0.45)',
          }}
        >
          {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
        </div>
      </AbsoluteFill>
    );
  }

  if (V.sticker) {
    // Thick outline via layered shadows in 8 directions — NOT WebkitTextStroke:
    // a centered stroke eats half its width out of the glyph, and paint-order
    // support for HTML text varies across headless Chrome builds. Shadows
    // always render behind the fill, on every build.
    const R = Math.max(5, Math.round(V.size * 0.09));
    const D = 0.7071 * R;
    const edge = '#141518';
    const outline = [
      `${R}px 0 0 ${edge}`, `-${R}px 0 0 ${edge}`,
      `0 ${R}px 0 ${edge}`, `0 -${R}px 0 ${edge}`,
      `${D.toFixed(1)}px ${D.toFixed(1)}px 0 ${edge}`,
      `-${D.toFixed(1)}px ${D.toFixed(1)}px 0 ${edge}`,
      `${D.toFixed(1)}px -${D.toFixed(1)}px 0 ${edge}`,
      `-${D.toFixed(1)}px -${D.toFixed(1)}px 0 ${edge}`,
      '0 14px 30px rgba(0,0,0,0.5)',
    ].join(', ');
    return (
      <AbsoluteFill style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: V.bottom}}>
        <div
          style={{
            textAlign: 'center',
            fontFamily: V.family,
            fontWeight: V.weight,
            fontSize: V.size,
            letterSpacing: V.tracking,
            lineHeight: 1.16,
            color: C.accent ?? '#fff',
            whiteSpace: 'pre',
            textShadow: outline,
          }}
        >
          {lines.map((ln, i) => (
            <div key={i}>{ln.map((w) => clean(w.text).toUpperCase()).join(' ')}</div>
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
