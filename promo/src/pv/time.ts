import { FPS } from "./constants";

/** take.json: file time = cue time + this. Verified against the take itself: the tuning
 *  drawer is marked open at cue 44328 (file 45.498) and first appears at 45.550. */
export const CUE_OFFSET_S = 1.17;

export const cueToSeconds = (cueMs: number) => cueMs / 1000 + CUE_OFFSET_S;

/** Frames into the beat at which a recorded click lands, so a ring can be pinned to it. */
export const cueToBeatFrame = (cueMs: number, beatStartS: number) =>
  Math.round((cueToSeconds(cueMs) - beatStartS) * FPS);
