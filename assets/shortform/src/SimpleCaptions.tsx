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
import {capFamily, capTransform, capWeight} from './fonts';

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
  modo?: 'metal' | 'vidro' | 'traco' | 'moldura' | 'eco'
    | 'neon' | 'degrade' | 'bandeira' | 'maquina'
    | 'pilula' | 'etiqueta' | 'fitadegrade' | 'marcador'
    | 'fitadupla' | 'etiquetacanto';
};

// Quem desenha em CAIXA ALTA. Muda a MEDIDA das linhas, entao os tres
// motores (este, o render_proprio e a previa) tem de concordar.
const MAIUSCULA = new Set(['metal', 'moldura', 'eco', 'degrade', 'bandeira', 'fitadegrade', 'fitadupla']);

// Opacidades do Vidro e do Metálico — os MESMOS números do render_proprio
// (VIDRO_OPACO / VIDRO_FIO / METAL_OPACO). Um 0,32 que vira 0,30 aqui sai
// como outra legenda e ninguém percebe.
const VIDRO_OPACO = 0.32;
const VIDRO_FIO = 0.92;
const METAL_OPACO = 0.88;

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
    family: POPPINS, weight: 600, size: 72, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -1, bottom: 430, maxW: 840,
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
  // ---- os quatro de 04/09 ------------------------------------------------
  neon: {
    family: POPPINS, weight: 800, size: 74, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -1, bottom: 430, maxW: 800,
    modo: 'neon',
  },
  degrade: {
    family: POPPINS, weight: 800, size: 78, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -2, bottom: 430, maxW: 800,
    modo: 'degrade',
  },
  bandeira: {
    family: POPPINS, weight: 800, size: 62, maxWords: 4, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 760,
    modo: 'bandeira',
  },
  maquina: {
    family: INTER, weight: 600, size: 56, maxWords: 8, lines: 2,
    squeeze: 1, squeezeY: 1, tracking: 1, bottom: 430, maxW: 840,
    modo: 'maquina',
  },
  // ---- os quatro de fundo colorido (04/09) -------------------------------
  pilula: {
    family: POPPINS, weight: 800, size: 66, maxWords: 4, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 720,
    modo: 'pilula',
  },
  etiqueta: {
    family: INTER, weight: 600, size: 52, maxWords: 8, lines: 2,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 780,
    modo: 'etiqueta',
  },
  fitadegrade: {
    family: POPPINS, weight: 800, size: 62, maxWords: 4, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 760,
    modo: 'fitadegrade',
  },
  // ---- os dois de 05/09 ---------------------------------------------------
  fitadupla: {
    family: POPPINS, weight: 800, size: 62, maxWords: 4, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 760,
    modo: 'fitadupla',
  },
  etiquetacanto: {
    family: INTER, weight: 600, size: 52, maxWords: 8, lines: 2,
    squeeze: 1, squeezeY: 1, tracking: 0, bottom: 430, maxW: 780,
    modo: 'etiquetacanto',
  },
  marcador: {
    family: POPPINS, weight: 800, size: 74, maxWords: 3, lines: 1,
    squeeze: 1, squeezeY: 1, tracking: -1, bottom: 430, maxW: 800,
    modo: 'marcador',
  },
};

// Neon: cor do brilho quando a marca nao escolheu; degrade/bandeira: a
// cor de baixo / da fita. Os MESMOS padroes do render_proprio.
const NEON_PADRAO = '#4de1ff';
const DEGRADE_PADRAO = '#ff6a00';
const BANDEIRA_PADRAO = '#ff6a00';
const BANDEIRA_SKEW = 8;      // graus; o motor proprio usa tan(8deg)
// Os quatro de fundo colorido. A barra da etiqueta e a faixa do marca-texto
// tem medidas fixas — os tres motores leem ESTES numeros.
const ETIQUETA_FUNDO = 'rgba(11,13,16,0.86)';
const ETIQUETA_BARRA = 10;    // px da barra colorida na borda esquerda
const FITA_ESCURO = 0.55;     // fator da cor no PE do degrade da fita
const FITA_DUPLA_DY = 10;     // a segunda fita, px abaixo
const FITA_DUPLA_ESCURO = 0.45; // fator da cor da segunda fita
const MARCADOR_PADRAO = '#ffd400';
// A faixa e o FUNDO da linha com folga em volta — nao uma listra por dentro
// dela. A listra de 26%-96% (5.0.19) cortava a letra: com line-height 1,16 a
// Poppins ocupa de -10,6% a 110,6% da caixa de linha (asc+desc = 104px num
// corpo de 74), entao pe de "p" e ponta de "d" ficavam de fora. 0,14 do
// corpo de cada lado cobre a caixa do glifo inteira com folga.
const MARCADOR_PADY = 0.14;
const MARCADOR_PADX = 0.16;
// Maquina de escrever: uma letra a cada VEL quadros, no maximo 2 quadros por
// letra, e o cue inteiro digitado em 55% do tempo dele.
export function velocidadeMaquina(durFrames: number, nChars: number): number {
  return Math.min(2, (0.55 * durFrames) / Math.max(1, nChars));
}

/* As cinco paradas do cromado, tiradas DA COR escolhida. `f > 1` clareia
 * em direcao ao branco, `f < 1` escurece. A parada escura em 50% com o
 * estalo de luz logo abaixo e o que o olho le como metal — um degrade
 * suave de claro para escuro parece papel. */
function degradeMetal(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  const n = m ? parseInt(m[1], 16) : 0xe8edf3;
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  // PRATA LISO — sem a faixa escura no meio, que o usuário leu (com razão)
  // como um risco atravessando a letra.
  const paradas: [number, number][] = [[0, 1.38], [42, 1.06], [100, 0.74]];
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
/* A cor multiplicada por `f` (0-1): o pe do degrade da fita. Mesma conta do
 * `_escurecer` no motor proprio. */
function escurecer(hex: string, f: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  const rgb = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    .map((v) => Math.round(v * f));
  return `rgb(${rgb.join(',')})`;
}

/* A cor que pinta a SUPERFICIE de um estilo (brilho, degrade, fita,
 * capsula, barra). Vem da ENFASE; cai na cor da legenda so para preset
 * antigo que nao tem enfase, e por fim no padrao do estilo. */
function corDaSuperficie(padrao: string): string {
  return (C.emphasisAccent as string) || (C.accent as string) || padrao;
}

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
    textTransform: capTransform(),
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
    textTransform: capTransform(),
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
      metal: 1.1, vidro: 1.16, traco: 1.16, moldura: 1.2, eco: 1.14,
      neon: 1.16, degrade: 1.14, bandeira: 1.2, maquina: 1.3,
      pilula: 1.2, etiqueta: 1.25, fitadegrade: 1.2, marcador: 1.16,
      fitadupla: 1.2, etiquetacanto: 1.25,
    };
    const tipo = {
      fontFamily: V.family,
    textTransform: capTransform(),
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
                // a prata deixa o take pulsar por baixo; a borda (na cópia
                // de baixo) fica opaca e é ela que segura a leitura
                opacity: METAL_OPACO,
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

    if (V.modo === 'neon') {
      // Letra branca, brilho na cor da marca em tres raios (8/22/46px) e a
      // sombra escura de sempre por baixo, para ler sobre imagem clara.
      // A cor vem da ENFASE: a da legenda e quase sempre branca, e brilho
      // branco em letra branca e brilho nenhum (04/09).
      const g = corDaSuperficie(NEON_PADRAO);
      return (
        <AbsoluteFill style={fora}>
          <div style={{...tipo, color: '#ffffff',
                       textShadow: [`0 0 8px ${g}`, `0 0 22px ${g}`, `0 0 46px ${g}`,
                                    '0 8px 20px rgba(0,0,0,0.5)'].join(', ')}}>
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'degrade') {
      // Como o metal: copia de baixo so com o contorno, copia de cima com o
      // degrade (branco em cima, cor da marca embaixo) recortado na letra.
      const R = Math.max(2, Math.round(V.size * 0.03));
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
                backgroundImage: `linear-gradient(180deg, #ffffff 0%, ${corDaSuperficie(DEGRADE_PADRAO)} 100%)`,
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

    if (V.modo === 'pilula') {
      // Capsula: raio = metade da altura, entao as pontas sao semicirculos.
      const fundo = corDaSuperficie('#ffffff');
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.30);
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: `${padY}px ${padX}px`,
              background: fundo,
              color: inkOn(fundo),
              borderRadius: 9999,
              boxShadow: '0 12px 30px rgba(0,0,0,0.45)',
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'etiqueta') {
      // Painel escuro com uma barra da cor da marca na borda esquerda.
      const barra = corDaSuperficie('#ffffff');
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.34);
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: `${padY}px ${padX}px`,
              background: ETIQUETA_FUNDO,
              borderLeft: `${ETIQUETA_BARRA}px solid ${barra}`,
              borderRadius: 6,
              color: '#ffffff',
              boxShadow: '0 16px 36px rgba(0,0,0,0.45)',
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'fitadupla') {
      // A fita degrade com uma segunda fita escura por baixo: um box-shadow
      // DURO (0 10px 0) na cor do pe, mais a sombra macia de sempre.
      const topo = corDaSuperficie('#ff6a00');
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.30);
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: `${padY}px ${padX}px`,
              backgroundImage: `linear-gradient(180deg, ${topo} 0%, ${escurecer(topo, FITA_ESCURO)} 100%)`,
              color: inkOn(topo),
              borderRadius: Math.round(V.size * 0.14),
              boxShadow: `0 ${FITA_DUPLA_DY}px 0 ${escurecer(topo, FITA_DUPLA_ESCURO)}, 0 20px 32px rgba(0,0,0,0.45)`,
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }
    if (V.modo === 'etiquetacanto') {
      // A etiqueta com o canto superior direito cortado. O clip-path cortaria
      // o box-shadow junto, entao a sombra e um drop-shadow no ELEMENTO DE
      // FORA, que ve a forma ja recortada.
      const barra = corDaSuperficie('#ffffff');
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.34);
      const canto = Math.round(V.size * 0.5);
      return (
        <AbsoluteFill style={fora}>
          <div style={{filter: 'drop-shadow(0 16px 36px rgba(0,0,0,0.45))'}}>
            <div
              style={{
                ...tipo,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                padding: `${padY}px ${padX}px`,
                background: ETIQUETA_FUNDO,
                borderLeft: `${ETIQUETA_BARRA}px solid ${barra}`,
                borderRadius: 6,
                color: '#ffffff',
                clipPath: `polygon(0 0, calc(100% - ${canto}px) 0, 100% ${canto}px, 100% 100%, 0 100%)`,
              }}
            >
              {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
            </div>
          </div>
        </AbsoluteFill>
      );
    }
    if (V.modo === 'fitadegrade') {
      // A fita da bandeira, sem inclinacao e com o fundo em degrade.
      const topo = corDaSuperficie('#ff6a00');
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.30);
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: `${padY}px ${padX}px`,
              backgroundImage: `linear-gradient(180deg, ${topo} 0%, ${escurecer(topo, FITA_ESCURO)} 100%)`,
              color: inkOn(topo),
              borderRadius: Math.round(V.size * 0.14),
              boxShadow: '0 14px 32px rgba(0,0,0,0.45)',
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'marcador') {
      // Faixa de caneta marca-texto: o fundo da LINHA, com folga em volta,
      // de ponta reta. A cor e a de ENFASE (amarela por padrao).
      const faixa = C.emphasisAccent || MARCADOR_PADRAO;
      const padX = Math.round(V.size * MARCADOR_PADX);
      const padY = Math.round(V.size * MARCADOR_PADY);
      return (
        <AbsoluteFill style={fora}>
          <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center'}}>
            {lines.map((ln, i) => (
              <div
                key={i}
                style={{
                  ...tipo,
                  padding: `${padY}px ${padX}px`,
                  background: faixa,
                  color: inkOn(faixa),
                  textShadow: '0 4px 14px rgba(0,0,0,0.35)',
                }}
              >
                {txt(ln)}
              </div>
            ))}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'bandeira') {
      // Uma fita na cor da marca, inclinada (skewX), texto em caixa alta na
      // tinta que a luminancia da fita pede. A fita inclina o texto junto —
      // e o adesivo do CapCut, nao uma placa.
      const fita = corDaSuperficie(BANDEIRA_PADRAO);
      const padX = Math.round(V.size * 0.55);
      const padY = Math.round(V.size * 0.28);
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              padding: `${padY}px ${padX}px`,
              background: fita,
              color: inkOn(fita),
              transform: `skewX(-${BANDEIRA_SKEW}deg)`,
              boxShadow: '0 12px 30px rgba(0,0,0,0.45)',
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    if (V.modo === 'maquina') {
      // As letras aparecem uma a uma, a esquerda de cada linha fixa (a linha
      // nao "anda" enquanto cresce). Cada letra e um span: o navegador nao
      // faz kerning entre spans, e o motor proprio desenha letra a letra —
      // os dois medem igual.
      const ini = Math.round((cues[idx][0].startMs / 1000) * fps);
      const dur = Math.max(1, end - ini);
      const textos = lines.map((ln) => txt(ln));
      const total = textos.reduce((s, tx) => s + tx.length, 0);
      const vel = velocidadeMaquina(dur, total);
      let vistos = frame < ini ? 0 : Math.floor((frame - ini) / vel) + 1;
      const cor = C.accent ?? '#f4f1e9';
      return (
        <AbsoluteFill style={fora}>
          <div style={{...tipo, color: cor, display: 'flex', flexDirection: 'column',
                       alignItems: 'center', textShadow: '0 4px 18px rgba(0,0,0,0.55)'}}>
            {textos.map((tx, i) => {
              const w = widthOf(lines[i], V);
              const daqui = Math.max(0, Math.min(tx.length, vistos));
              vistos -= tx.length;
              return (
                <div key={i} style={{width: Math.ceil(w), textAlign: 'left', whiteSpace: 'pre'}}>
                  {Array.from(tx).map((ch, k) => (
                    <span key={k} style={{visibility: k < daqui ? 'visible' : 'hidden'}}>{ch}</span>
                  ))}
                </div>
              );
            })}
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

    if (V.modo === 'vidro') {
      // A LETRA é de vidro: 32% de branco, então o take aparece ATRAVÉS
      // dela. O fio de luz de 2px é o que garante a leitura sobre qualquer
      // imagem — sem ele isto vira texto apagado.
      //
      // `-webkit-text-stroke` é um traço CENTRADO (metade para dentro,
      // metade para fora); o motor próprio reproduz isso com dilata−corrói.
      const R = Math.max(1, Math.round(V.size * 0.028));
      const cor = C.accent ?? '#ffffff';
      return (
        <AbsoluteFill style={fora}>
          <div
            style={{
              ...tipo,
              color: cor,
              opacity: VIDRO_OPACO,
              filter: 'drop-shadow(0 8px 22px rgba(0,0,0,0.55))',
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
          <div
            style={{
              ...tipo,
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: V.bottom,
              color: 'transparent',
              WebkitTextStrokeWidth: `${R * 2}px`,
              WebkitTextStrokeColor: cor,
              opacity: VIDRO_FIO,
            }}
          >
            {lines.map((ln, i) => <div key={i}>{txt(ln)}</div>)}
          </div>
        </AbsoluteFill>
      );
    }

    // moldura: UM painel em volta do cue inteiro (o bloco da uma lápide por
    // linha — aqui a caixa é uma só, com as duas dentro)
    const vidro = false;
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
    textTransform: capTransform(),
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
    textTransform: capTransform(),
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
