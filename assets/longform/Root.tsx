import {Composition} from 'remotion';
import {Main} from './Main';

// LONGFORM (YouTube 16:9). Set width/height/fps/durationInFrames to MATCH cut.mp4
// exactly (e.g. 1920×1080 @ 30, or 3840×2160 @ 24). durationInFrames = round(durationSec * fps).
export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Longform"
      component={Main}
      durationInFrames={9000}
      fps={30}
      width={1920}
      height={1080}
    />
  );
};
