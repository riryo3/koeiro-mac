import React, { type ReactNode } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { CANVAS, COLOR, WINDOW, WINDOW_TOP } from "../constants";
import { rigAt } from "../camera/rig";
import type { Beat } from "../meta/beats";
import { SourceFilm } from "./SourceFilm";

/**
 * Three layers, one job each, so the camera maths stay separable:
 * Stage owns the perspective, Tilt owns the float and the shadow, Camera owns the framing.
 * Because the camera hands its subject to the tilt pivot, the framed control stays centred
 * at any rotation; the tilt only changes how the subject is shaped.
 */
export const Window3D: React.FC<{ index: number; beat: Beat; children?: ReactNode }> = ({
  index,
  beat,
  children,
}) => {
  const rig = rigAt(index, useCurrentFrame());
  const pan = beat.pan ?? { x: 0, y: beat.mode === "fill" ? 0 : -24 };
  return (
    <AbsoluteFill style={{ perspective: 2400, perspectiveOrigin: "50% 50%" }}>
      <div
        style={{
          position: "absolute",
          left: CANVAS.width / 2 - WINDOW.width / 2 + pan.x,
          top: WINDOW_TOP + pan.y,
          width: WINDOW.width,
          height: WINDOW.height,
          transform: `rotateX(${rig.rx}deg) rotateY(${rig.ry}deg) scale(${rig.s})`,
          transformOrigin: "50% 50%",
          borderRadius: 12,
          border: `1px solid ${COLOR.rule}`,
          background: COLOR.surface,
          overflow: "hidden",
          // The film's only shadow. A tilted plane with no contact shade under it reads as a
          // cropped screenshot rather than an object in a room.
          boxShadow: "0 70px 130px -50px rgba(10, 24, 46, 0.75)",
        }}
      >
        <div
          style={{
            width: "100%",
            height: "100%",
            transform: `translate(${rig.tx}px, ${rig.ty}px) scale(${rig.k})`,
            transformOrigin: "50% 50%",
          }}
        >
          <SourceFilm start={beat.srcStart ?? 0} duration={beat.duration} />
          {children}
        </div>
      </div>
    </AbsoluteFill>
  );
};
