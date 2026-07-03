import {Composition} from 'remotion';
import {Main} from './Main';

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Reels"
      component={Main}
      durationInFrames={635}
      fps={24}
      width={1080}
      height={1920}
    />
  );
};
