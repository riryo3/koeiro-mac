import { CANVAS, WINDOW } from "../constants";
import type { Box } from "../meta/hotspots";

/**
 * The camera layer is a plane the size of the window, scaled about its own centre and slid
 * so the framed box lands on that centre. Because the pivot receives the box, any rotation
 * applied outside this layer leaves the subject dead centre; tilt changes its shape and
 * size, never its position.
 */
export type Aim = { s: number; k: number; dx: number; dy: number };

export const centreOffset = (box: Box) => ({
  dx: (box.nx + box.nw / 2) * WINDOW.width - WINDOW.width / 2,
  dy: (box.ny + box.nh / 2) * WINDOW.height - WINDOW.height / 2,
});

/**
 * Magnification that makes the box fill the canvas without cropping any of it. This is about
 * the box, not the plane: the frame clips the plane, so how much of the canvas is covered is
 * decided by `s` alone.
 */
export const fillScale = (box: Box, s: number): number =>
  Math.min(
    CANVAS.width / (s * box.nw * WINDOW.width),
    CANVAS.height / (s * box.nh * WINDOW.height),
  );

export const makeAim = (box: Box, s: number, k: number): Aim => {
  const { dx, dy } = centreOffset(box);
  return coverClamp({ s, k, dx, dy });
};

/**
 * A control that sits against the edge of the window cannot be both centred and covering: at
 * that magnification the plane simply runs out. This pulls the pivot in as far as it can go
 * while the plane still reaches everything that is actually visible, so the subject lands
 * near the frame rather than in the middle of it, and no strip of bare surface is exposed.
 * A fill beat scales the window past the canvas, so what is visible is narrower than the
 * frame; an object beat shows the whole frame, so the frame itself is the limit.
 */
export const coverClamp = (aim: Aim): Aim => {
  const reachX = Math.min(CANVAS.width / 2 / aim.s, WINDOW.width / 2) / aim.k;
  const reachY = Math.min(CANVAS.height / 2 / aim.s, WINDOW.height / 2) / aim.k;
  const cx = clamp(aim.dx + WINDOW.width / 2, reachX, WINDOW.width - reachX);
  const cy = clamp(aim.dy + WINDOW.height / 2, reachY, WINDOW.height - reachY);
  return { ...aim, dx: cx - WINDOW.width / 2, dy: cy - WINDOW.height / 2 };
};

const clamp = (value: number, low: number, high: number) =>
  Math.min(Math.max(value, low), Math.max(high, low));

export const translateOf = (aim: Aim) => ({
  tx: -aim.k * aim.dx,
  ty: -aim.k * aim.dy,
});

export const lerp = (from: number, to: number, p: number) => from + (to - from) * p;

/** Interpolate the aim, not the translation: lerping tx while k moves on its own curve is
 *  what makes a push-in drift off the button it was meant to land on. */
export const lerpAim = (from: Aim, to: Aim, p: number): Aim => ({
  s: lerp(from.s, to.s, p),
  k: lerp(from.k, to.k, p),
  dx: lerp(from.dx, to.dx, p),
  dy: lerp(from.dy, to.dy, p),
});

/** How much of a beat's declared tilt survives at a given magnification. A push-in reads as
 *  a skewed trapezoid unless it flattens, so this is driven by k and animates for free. */
export const tiltScale = (k: number): number => {
  const FULL = 1.35;
  const NONE = 2.3;
  if (k <= FULL) return 1;
  if (k >= NONE) return 0;
  const p = (k - FULL) / (NONE - FULL);
  return 0.5 + 0.5 * Math.cos(Math.PI * p);
};
