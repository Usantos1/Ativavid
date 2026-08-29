import React from 'react';
import {interpolate, Easing} from 'remotion';

/**
 * Hand-drawn "pencil" ellipse that draws itself around a word.
 * `progress` 0..1 controls how much of the loop is inked.
 * Part of the STACKED caption style (see StackedCaptions.tsx).
 */
export const PencilOutline: React.FC<{progress: number; color?: string}> = ({
  progress,
  color = '#39E508',
}) => {
  const p = interpolate(progress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.4, 0, 0.2, 1),
  });

  // Loose, slightly wavy ellipse with a small overshoot tail — like a scribble.
  const d =
    'M 30 78 C 26 40, 120 20, 190 24 C 262 28, 300 52, 288 82 ' +
    'C 276 114, 150 132, 78 122 C 28 114, 8 92, 34 66 ' +
    'C 50 50, 96 40, 150 42';

  return (
    <svg
      viewBox="0 0 312 150"
      preserveAspectRatio="none"
      style={{
        position: 'absolute',
        left: '-10%',
        top: '-22%',
        width: '120%',
        height: '150%',
        overflow: 'visible',
        pointerEvents: 'none',
      }}
    >
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={9}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
        pathLength={1}
        // Enquanto anima, o tracejado desenha o laco aos poucos. Quando
        // termina, ele SAI: com `non-scaling-stroke` o Chrome mede o
        // tracejado na tela ja esticada, e `strokeDasharray={1}` acabava
        // antes do fim do caminho — o laco ficava com um buraco no arco de
        // baixo e nunca fechava (medido em 29/08: o preview desenhava so de
        // 0 a 0,42 e de 0,78 a 1,00 do caminho). O video final, que sai do
        // renderizador proprio, sempre fechou o laco: era o preview que
        // mostrava outra coisa.
        strokeDasharray={p >= 1 ? undefined : 1}
        strokeDashoffset={p >= 1 ? undefined : 1 - p}
        style={{filter: 'drop-shadow(0 3px 8px rgba(0,0,0,0.45))'}}
      />
    </svg>
  );
};
