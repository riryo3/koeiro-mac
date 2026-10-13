import React from "react";
import { Composition } from "remotion";
import { CANVAS, FPS } from "./pv/constants";
import { DURATION } from "./pv/meta/beats";
import { PV } from "./pv/PV";
import { HotspotCheck } from "./pv/HotspotCheck";

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="KoeiroPV"
      component={PV}
      durationInFrames={DURATION}
      fps={FPS}
      width={CANVAS.width}
      height={CANVAS.height}
    />
    <Composition
      id="HotspotCheck"
      component={HotspotCheck}
      durationInFrames={30}
      fps={FPS}
      width={CANVAS.width}
      height={CANVAS.height}
      defaultProps={{ beatId: "wiring" }}
    />
  </>
);
