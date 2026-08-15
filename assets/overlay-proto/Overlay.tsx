/**
 * Composição EXPERIMENTAL — só gráfica, sem cut.mp4 / OffthreadVideo.
 * Não faz parte do caminho FULL. O proto copia este arquivo para um
 * remotion de trabalho; o template shipped (Main/Root) não muda.
 */
import {AbsoluteFill} from 'remotion';
import {CustomGraphics} from './CustomGraphics';
import {StackedCaptions} from './StackedCaptions';
import {ScatterCaptions} from './ScatterCaptions';
import {SimpleCaptions, SIMPLE_VARIANTS} from './SimpleCaptions';
import {EndCard, HookIntro, Inserts, Karaoke} from './Main';
import editData from '../public/edit-data.json';

const D = editData as {
  hook?: {enabled?: boolean};
  captions?: {enabled?: boolean; style?: string};
  endCard?: {enabled?: boolean};
};

export const Overlay: React.FC = () => {
  return (
    <AbsoluteFill style={{backgroundColor: 'transparent'}}>
      <Inserts />
      <CustomGraphics />
      {D.hook?.enabled ? <HookIntro /> : null}
      {D.captions?.enabled
        ? D.captions.style === 'stacked'
          ? <StackedCaptions />
          : D.captions.style === 'scatter'
            ? <ScatterCaptions />
            : SIMPLE_VARIANTS[D.captions.style as string]
              ? <SimpleCaptions variant={D.captions.style as string} />
              : <Karaoke />
        : null}
      {D.endCard?.enabled ? <EndCard /> : null}
    </AbsoluteFill>
  );
};
