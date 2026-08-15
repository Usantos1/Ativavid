import {Composition} from 'remotion';
import {Main} from './Main';
import {Overlay} from './Overlay';
import editData from '../public/edit-data.json';

const frames = Math.max(1, Math.round(editData.durationSec * editData.fps));

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Reels"
        component={Main}
        durationInFrames={frames}
        fps={editData.fps}
        width={editData.width}
        height={editData.height}
      />
      <Composition
        id="Overlay"
        component={Overlay}
        durationInFrames={frames}
        fps={editData.fps}
        width={editData.width}
        height={editData.height}
      />
    </>
  );
};
