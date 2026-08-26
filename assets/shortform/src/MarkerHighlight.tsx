import React from 'react';
import {interpolate, Easing} from 'remotion';

/**
 * Highlighter ("marca-texto") band that paints itself behind a word,
 * left to right — the sibling of PencilOutline for the STACKED style.
 * Same viewBox and progress contract as PencilOutline so the engines
 * (Remotion and render_proprio) share one geometry.
 * `progress` 0..1 controls how much of the band is inked.
 */
export const MarkerHighlight: React.FC<{progress: number; color?: string}> = ({
  progress,
  color = '#FFE94A',
}) => {
  const p = interpolate(progress, [0, 1], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.4, 0, 0.2, 1),
  });

  // A single thick stroke with a slight tilt and wobble — like one confident
  // swipe of a marker. Drawn in the same 312x150 box as the pencil ellipse.
  const d = 'M 8 84 C 90 82, 210 80, 304 76';

  return (
    <svg
      viewBox="0 0 312 150"
      preserveAspectRatio="none"
      style={{
        position: 'absolute',
        left: '-7%',
        top: '-16%',
        width: '114%',
        height: '138%',
        overflow: 'visible',
        pointerEvents: 'none',
      }}
    >
      <path
        d={d}
        fill="none"
        stroke={color}
        strokeWidth={92}
        strokeLinecap="round"
        pathLength={1}
        strokeDasharray={1}
        strokeDashoffset={1 - p}
        style={{opacity: 0.85}}
      />
    </svg>
  );
};
