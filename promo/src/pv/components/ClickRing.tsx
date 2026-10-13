import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { HOTSPOTS, type HotspotName } from "../meta/hotspots";

const SIZE = 46;

const Ring: React.FC<{ size: number; scale: number; opacity: number }> = ({
  size,
  scale,
  opacity,
}) => (
  <div
    style={{
      position: "absolute",
      left: -size / 2,
      top: -size / 2,
      width: size,
      height: size,
      borderRadius: "50%",
      // A white ring with a thin ink edge: a click aim lands on a navy button as often as on
      // the light surface, and either single colour vanishes on one of the two.
      border: "3px solid #ffffff",
      boxShadow: "0 0 0 1.5px rgba(24, 24, 27, 0.55)",
      opacity,
      transform: `scale(${scale})`,
    }}
  />
);

/**
 * The recorded OS cursor is already in the footage, so this never invents one. It sits at a
 * measured click aim inside the camera layer, which means it magnifies and flattens with the
 * plane for free and cannot drift out of register with the button it names.
 */
export const ClickRing: React.FC<{ aim: HotspotName }> = ({ aim }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const [x, y] = HOTSPOTS[aim].center;
  const grow = spring({ frame, fps, config: { damping: 16, stiffness: 190, mass: 0.7 } });
  const hold = interpolate(frame, [0, 9], [1, 1], { extrapolateRight: "clamp" });
  const fade = interpolate(frame, [9, 34], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ position: "absolute", left: x, top: y, width: 0, height: 0 }}>
      <Ring size={SIZE} scale={1 + grow * 0.85} opacity={0.95 * hold * fade} />
      <Ring size={SIZE * 1.7} scale={0.55 + grow * 0.6} opacity={0.5 * hold * fade} />
    </div>
  );
};
