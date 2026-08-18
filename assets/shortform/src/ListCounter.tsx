/**
 * ListCounter — badge "1º / 2º / 3º" sincronizado com a enumeração falada.
 *
 * Data-driven: lê editData.listMarkers ([{n, atSec}]), gerado pelo pipeline
 * a partir das legendas (app/list_counter.py). Sem marcadores, não renderiza
 * nada — projetos antigos seguem intactos.
 *
 * O badge vive no canto superior direito (fora do caminho da headline
 * central e da pílula), troca com um pop no frame exato de cada ordinal e
 * fica até o próximo. Pinta com o accent da headline — é o mesmo "one
 * accented element" que o resto do template segue.
 */
import {AbsoluteFill, interpolate, Easing, useCurrentFrame, useVideoConfig} from 'remotion';
import {loadFont} from '@remotion/google-fonts/Poppins';
import editData from '../public/edit-data.json';
import {hookFamily, hookWeight} from './fonts';

const {fontFamily: _poppins} = loadFont('normal', {weights: ['900']});
const FF = hookFamily(_poppins);

type Marker = {n: number; atSec: number};
const ED = editData as any;
const MARKERS: Marker[] = Array.isArray(ED.listMarkers) ? ED.listMarkers : [];
const ACCENT: string = ED?.hook?.accent ?? '#ff5200';

function inkOn(bg: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(bg).trim());
  if (!m) return '#fff';
  const n = parseInt(m[1], 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6 ? '#111214' : '#fff';
}

const INK = inkOn(ACCENT);

export const ListCounter: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  if (!MARKERS.length) return null;

  let idx = -1;
  for (let i = 0; i < MARKERS.length; i++) {
    if (frame >= Math.round(MARKERS[i].atSec * fps)) idx = i;
  }
  if (idx < 0) return null;
  const cur = MARKERS[idx];
  const from = Math.round(cur.atSec * fps);
  const pop = interpolate(frame, [from, from + 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.back(2.2)),
  });

  return (
    <AbsoluteFill style={{alignItems: 'flex-end', justifyContent: 'flex-start', paddingTop: 150, paddingRight: 54}}>
      <div
        style={{
          background: ACCENT,
          color: INK,
          fontFamily: FF,
          fontWeight: hookWeight(900),
          fontSize: 64,
          lineHeight: 1,
          padding: '18px 26px 22px',
          borderRadius: 20,
          transform: `rotate(4deg) scale(${(0.6 + 0.4 * pop).toFixed(3)})`,
          opacity: Math.min(1, pop * 1.4),
          boxShadow: '0 12px 32px rgba(0,0,0,0.4)',
        }}
      >
        {cur.n}º
      </div>
    </AbsoluteFill>
  );
};
