import React from "react";
import { Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { FONT } from "../constants";

const ICON = 112;
/** The wordmark is 1708x481 once its transparent padding is trimmed (DESIGN.md 9). */
const WORDMARK = { width: Math.round((ICON * 1708) / 481), height: ICON };

export const EndCard: React.FC = () => {
  const frame = useCurrentFrame();
  const appear = {
    opacity: interpolate(frame, [0, 18], [0, 1], { extrapolateRight: "clamp" }),
    transform: `translateY(${interpolate(frame, [0, 18], [22, 0], { extrapolateRight: "clamp" })}px)`,
  };
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: FONT,
        color: "#ffffff",
        ...appear,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
        <Img src={staticFile("brand/icon.png")} width={ICON} height={ICON} />
        <Img src={staticFile("brand/logo_trimmed.png")} width={WORDMARK.width} height={WORDMARK.height} />
      </div>
      <div style={{ fontSize: 40, fontWeight: 600, marginTop: 34 }}>声彩 / こえいろ</div>
      <div
        style={{
          width: 420,
          height: 1,
          background: "rgba(255, 255, 255, 0.28)",
          marginTop: 40,
        }}
      />
      <div style={{ fontSize: 30, fontWeight: 500, color: "rgba(255, 255, 255, 0.86)", marginTop: 30 }}>
        v0.12.0 ・ Windows 10/11 ・ Linux
      </div>
      <div style={{ fontSize: 30, fontWeight: 500, color: "#ffffff", marginTop: 14 }}>
        github.com/heynegix/koeiro
      </div>
    </div>
  );
};
