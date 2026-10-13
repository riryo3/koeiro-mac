import React, { type ReactNode } from "react";
import { AbsoluteFill } from "remotion";
import { COLOR } from "../constants";

/**
 * The vertical light is the only decoration on the set: it gives the tilted window a floor
 * to sit above, which is what makes the rotation read as depth instead of a skewed
 * screenshot. It stays inside the brand navy, so no new hue enters the film.
 */
export const Stage: React.FC<{ children?: ReactNode }> = ({ children }) => (
  <AbsoluteFill
    style={{
      background: `linear-gradient(180deg, #2f578c 0%, ${COLOR.brand} 52%, #1e3b64 100%)`,
    }}
  >
    {children}
  </AbsoluteFill>
);
