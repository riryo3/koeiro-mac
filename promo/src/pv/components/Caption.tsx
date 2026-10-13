import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { COLOR, FONT } from "../constants";
import type { Caption as CaptionData } from "../meta/beats";

const MUTE = "rgba(255, 255, 255, 0.86)";

/** A caption that simply appears has no weight; 12 frames of settle says it arrived to be read. */
const settle = (frame: number) => ({
  opacity: interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" }),
  transform: `translateY(${interpolate(frame, [0, 12], [14, 0], { extrapolateRight: "clamp" })}px)`,
});

export const Caption: React.FC<{
  data?: CaptionData;
  /** Beats whose label changes on a cue (the voice A/B) rather than on the cut. */
  chips?: { at: number; label: string }[];
}> = ({ data, chips }) => {
  const frame = useCurrentFrame();
  if (!data) {
    return null;
  }
  const style = settle(frame);
  if (data.title) {
    return (
      <div
        style={{
          position: "absolute",
          left: 120,
          right: 120,
          top: 116,
          textAlign: "center",
          fontFamily: FONT,
          color: "#ffffff",
          ...style,
        }}
      >
        <div style={{ fontSize: 88, fontWeight: 600, letterSpacing: "0.01em" }}>{data.title}</div>
        {data.sub ? (
          <div style={{ fontSize: 38, fontWeight: 500, color: MUTE, marginTop: 18 }}>{data.sub}</div>
        ) : null}
      </div>
    );
  }
  const chip = chips?.filter((c) => c.at <= frame).pop()?.label ?? data.chip;
  if (!chip && !data.sub) {
    return null;
  }
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: 88,
        display: "flex",
        justifyContent: "center",
        fontFamily: FONT,
        ...style,
      }}
    >
      {/* Solid navy, never a blur: the chip has to hold its contrast over the light UI as
          well as over the set, and glass would fail on one of the two. */}
      <div
        style={{
          background: COLOR.brand,
          border: `1px solid ${COLOR.rule}`,
          borderRadius: 12,
          padding: "24px 44px",
          maxWidth: 1680,
          textAlign: "center",
        }}
      >
        {chip ? <div style={{ fontSize: 44, fontWeight: 600, color: "#ffffff" }}>{chip}</div> : null}
        {data.sub ? (
          <div style={{ fontSize: 30, fontWeight: 500, color: MUTE, marginTop: chip ? 10 : 0 }}>
            {data.sub}
          </div>
        ) : null}
      </div>
    </div>
  );
};
