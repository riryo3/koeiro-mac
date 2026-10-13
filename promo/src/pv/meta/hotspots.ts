export type Box = { nx: number; ny: number; nw: number; nh: number };

export type Hotspot = {
  box: Box;
  /** The click aim, in device px of the 1920x1008 frame. */
  center: [number, number];
  lower: [number, number];
};

/** Measured off the live take by tools/promo_run.py. The widget boxes were taken at
 *  1280x672 logical with devicePixelRatio 1.5, so the normalized halves land directly
 *  on the recorded frame. Only these seven were visible during the take. */
export const HOTSPOTS = {
  start: {
    box: { nx: 0.021875, ny: 0.4568452380952381, nw: 0.0671875, nh: 0.06547619047619048 },
    center: [106, 494],
    lower: [106, 718],
  },
  stop: {
    box: { nx: 0.0984375, ny: 0.4568452380952381, nw: 0.0359375, nh: 0.06547619047619048 },
    center: [224, 494],
    lower: [224, 718],
  },
  tune: {
    box: { nx: 0.70703125, ny: 0.008928571428571428, nw: 0.0328125, nh: 0.047619047619047616 },
    center: [1389, 33],
    lower: [1389, 258],
  },
  lab: {
    box: { nx: 0.74609375, ny: 0.008928571428571428, nw: 0.0328125, nh: 0.047619047619047616 },
    center: [1464, 33],
    lower: [1464, 258],
  },
  relay: {
    box: { nx: 0.021875, ny: 0.16071428571428573, nw: 0.6984375, nh: 0.14285714285714285 },
    center: [712, 234],
    lower: [712, 459],
  },
  nameplate: {
    box: { nx: 0.575, ny: 0.9136904761904762, nw: 0.1453125, nh: 0.05952380952380952 },
    center: [1244, 951],
    lower: [1244, 1176],
  },
  voicePanel: {
    box: { nx: 0.7421875, ny: 0.06547619047619048, nw: 0.2578125, nh: 0.9345238095238095 },
    center: [1672, 537],
    lower: [1672, 762],
  },
} satisfies Record<string, Hotspot>;

export type HotspotName = keyof typeof HOTSPOTS;

/** The drawer is not in the measured hotspots (tools/promo_run.py never saw it closed
 *  on camera), so this was measured off the take itself: the face settles at x 1167..1916
 *  across the full height. */
export const DRAWER: Box = { nx: 0.6078, ny: 0.0089, nw: 0.3901, nh: 0.9901 };
