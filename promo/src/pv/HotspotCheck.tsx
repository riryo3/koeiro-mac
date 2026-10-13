import React from "react";
import { AbsoluteFill } from "remotion";
import { WINDOW } from "./constants";
import { BEATS, beatStart } from "./meta/beats";
import { DRAWER, HOTSPOTS, type HotspotName } from "./meta/hotspots";
import { targetAim } from "./camera/rig";
import { translateOf } from "./camera/projection";
import { Window3D } from "./components/Window3D";

const NAMES: HotspotName[] = ["start", "stop", "tune", "lab", "relay", "nameplate", "voicePanel"];

const Label: React.FC<{ x: number; y: number; text: string }> = ({ x, y, text }) => (
  <div
    style={{
      position: "absolute",
      left: x,
      top: y,
      fontSize: 22,
      fontFamily: "monospace",
      color: "#ff00ff",
      textShadow: "0 0 4px #ffffff",
    }}
  >
    {text}
  </div>
);

/**
 * Proves the camera maths before the edit depends on them: every measured box, the aim a
 * click ring would use, and the beat's own framing rect, drawn in the camera layer so they
 * inherit the same magnification the film will apply. Still-frame it at a beat's last frame
 * and the subject should be dead centre.
 */
export const HotspotCheck: React.FC<{ beatId: string }> = ({ beatId }) => {
  const index = BEATS.findIndex((beat) => beat.id === beatId);
  const beat = BEATS[index];
  const aim = targetAim(beat);
  const { tx, ty } = translateOf(aim);
  return (
    <AbsoluteFill style={{ background: "#101826" }}>
      <>
        <Window3D index={index} beat={beat}>
          {NAMES.map((name) => {
            const { box, center } = HOTSPOTS[name];
            return (
              <React.Fragment key={name}>
                <div
                  style={{
                    position: "absolute",
                    left: box.nx * WINDOW.width,
                    top: box.ny * WINDOW.height,
                    width: box.nw * WINDOW.width,
                    height: box.nh * WINDOW.height,
                    border: "2px solid #ff00ff",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    left: center[0] - 6,
                    top: center[1] - 6,
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: "#ff00ff",
                  }}
                />
                <Label x={box.nx * WINDOW.width} y={box.ny * WINDOW.height - 26} text={name} />
              </React.Fragment>
            );
          })}
          <div
            style={{
              position: "absolute",
              left: DRAWER.nx * WINDOW.width,
              top: DRAWER.ny * WINDOW.height,
              width: DRAWER.nw * WINDOW.width,
              height: DRAWER.nh * WINDOW.height,
              border: "2px dashed #00e0ff",
            }}
          />
          <Label x={DRAWER.nx * WINDOW.width + 8} y={DRAWER.ny * WINDOW.height + 8} text="drawer" />
          <div
            style={{
              position: "absolute",
              left: (beat.box?.nx ?? 0) * WINDOW.width,
              top: (beat.box?.ny ?? 0) * WINDOW.height,
              width: (beat.box?.nw ?? 1) * WINDOW.width,
              height: (beat.box?.nh ?? 1) * WINDOW.height,
              border: "3px solid #284b7d",
            }}
          />
        </Window3D>
      </>
      <div
        style={{
          position: "absolute",
          left: 24,
          bottom: 24,
          fontFamily: "monospace",
          fontSize: 24,
          color: "#ffffff",
        }}
      >
        {`${beatId}  beatStart=${beatStart(index)}  s=${aim.s.toFixed(3)}  k=${aim.k.toFixed(3)}  tx=${tx.toFixed(0)}  ty=${ty.toFixed(0)}`}
      </div>
    </AbsoluteFill>
  );
};
