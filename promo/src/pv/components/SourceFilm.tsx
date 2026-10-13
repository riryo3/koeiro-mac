import React from "react";
import { OffthreadVideo, staticFile } from "remotion";
import { FPS, WINDOW } from "../constants";

export const TAKE = "raw/koeiro_20261012-143724.mp4";

/**
 * The take is 1920x1008 and the plane is 1920x1008, so the recorded pixels land 1:1 and a
 * push-in magnifies real detail rather than a resampled copy.
 */
export const SourceFilm: React.FC<{ start: number; duration: number }> = ({ start, duration }) => (
  <OffthreadVideo
    src={staticFile(TAKE)}
    muted
    trimBefore={Math.round(start * FPS)}
    durationInFrames={duration}
    style={{ width: WINDOW.width, height: WINDOW.height, display: "block" }}
  />
);
