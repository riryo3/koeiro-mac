import { spring } from "remotion";
import { CANVAS, FPS, WINDOW } from "../constants";
import { BEATS, beatStart, type Beat } from "../meta/beats";
import { fillScale, lerpAim, makeAim, tiltScale, translateOf, coverClamp, type Aim } from "./projection";

/** The window floats in navy at this size. */
export const OBJECT_S = 0.84;

/**
 * The frame clips the plane, so going full-bleed is won by scaling the window past the
 * canvas height, not by magnifying inside it. The small margin keeps the rounded corners
 * off the edge of the canvas.
 */
export const FILL_S = (CANVAS.height / WINDOW.height) * 1.01;

/** Beyond this the recorded pixels are a smear, so a small target is framed by widening
 *  its box in beats.ts rather than by magnifying further. */
export const K_CAP = 4.5;

export const targetAim = (beat: Beat): Aim => {
  const s = beat.s ?? (beat.mode === "fill" ? FILL_S : OBJECT_S);
  const k = beat.k ?? Math.min(fillScale(beat.box!, s), K_CAP);
  return makeAim(beat.box!, s, k);
};

export type Rig = { s: number; rx: number; ry: number; k: number; tx: number; ty: number };

/**
 * A beat glides in from wherever the previous beat parked the camera, so the film reads as
 * one operator moving one camera rather than eleven separate shots.
 */
export const rigAt = (index: number, local: number): Rig => {
  const beat = BEATS[index];
  const to = targetAim(beat);
  const from = beat.entry ?? (index > 0 ? targetAim(BEATS[index - 1]) : to);
  const p = spring({ frame: local, fps: FPS, config: { damping: 14, stiffness: 120, mass: 1 } });
  const aim = coverClamp(lerpAim(from, to, p));
  const tilt = tiltScale(aim.k);
  const { tx, ty } = translateOf(aim);
  return {
    s: aim.s,
    k: aim.k,
    tx,
    ty,
    rx: (beat.tilt?.rx ?? 0) * tilt,
    // Tied to the global frame so the drift carries across cuts instead of restarting, and
    // scaled by tilt so it fades out as a push-in flattens rather than snapping off.
    ry:
      (beat.tilt?.ry ?? 0) * tilt +
      Math.sin(((beatStart(index) + local) / FPS) * ((2 * Math.PI) / 7)) * 1.4 * tilt,
  };
};
