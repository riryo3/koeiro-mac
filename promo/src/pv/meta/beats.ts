import type { Aim } from "../camera/projection";
import { DRAWER, HOTSPOTS, type Box, type HotspotName } from "./hotspots";

const box = (name: HotspotName): Box => HOTSPOTS[name].box;

/** A box grown around a small target so a push-in stops before the pixels run out. */
const widened = (name: HotspotName, wide: number, tall: number): Box => {
  const { nx, ny, nw, nh } = box(name);
  const cx = nx + nw / 2;
  const cy = ny + nh / 2;
  const w = Math.min(nw * wide, 0.5);
  const h = Math.min(nh * tall, 0.5);
  return {
    nx: Math.min(Math.max(cx - w / 2, 0), 1 - w),
    ny: Math.min(Math.max(cy - h / 2, 0), 1 - h),
    nw: w,
    nh: h,
  };
};

const WHOLE: Box = { nx: 0, ny: 0, nw: 1, nh: 1 };

/** The drawer is tall and narrow, so a beat frames a band of it rather than the whole face:
 *  containing the full height would leave it the width of a column. */
const drawerBand = (ny: number, nh: number): Box => ({ nx: DRAWER.nx, ny, nw: DRAWER.nw, nh });

export type Caption = {
  /** Opening title, set above the window rather than over it. */
  title?: string;
  /** A solid navy chip. It has to be solid: it sits on top of the light UI. */
  chip?: string;
  sub?: string;
};

export type Beat = {
  id: string;
  kind: "plate" | "window" | "endcard";
  duration: number;
  /** Seconds into the recorded take. Window beats only. */
  srcStart?: number;
  box?: Box;
  /** object: the window floats in navy. fill: the plane covers the canvas. */
  mode?: "object" | "fill";
  s?: number;
  k?: number;
  pan?: { x: number; y: number };
  tilt?: { rx: number; ry: number };
  entry?: Aim;
  clicks?: { aim: HotspotName; cueMs: number }[];
  /** Labels that swap on a cue inside the beat instead of on the cut. */
  chips?: { at: number; label: string }[];
  caption?: Caption;
};

/**
 * The cut. Source ranges always start on the state the caption claims: the tuning drawer is
 * marked open at cue 44328, so the beat that frames it starts at 45.250 and catches it
 * arriving, and the close beat jumps to 54.200 where the drawer has been scrolled back to
 * the same position the earlier beat left it in.
 */
export const BEATS: Beat[] = [
  { id: "plate", kind: "plate", duration: 75 },
  {
    id: "arrival",
    kind: "window",
    duration: 130,
    srcStart: 1.17,
    box: WHOLE,
    mode: "object",
    k: 1,
    s: 0.62,
    pan: { x: 0, y: 150 },
    tilt: { rx: 5, ry: -26 },
    entry: { s: 0.38, k: 1, dx: 0, dy: 0 },
    caption: { title: "Koeiro（声彩）", sub: "自分の声を、登録した声にリアルタイムで変換する" },
  },
  {
    id: "start",
    kind: "window",
    duration: 124,
    srcStart: 3.67,
    box: widened("start", 3.4, 4.2),
    mode: "object",
    k: 2.15,
    tilt: { rx: 5, ry: -14 },
    clicks: [{ aim: "start", cueMs: 2812 }],
    caption: { chip: "Start", sub: "押すとバーの状態が 変換中 に変わる" },
  },
  {
    id: "ready",
    kind: "window",
    duration: 108,
    /* Cue 41265 is when the app reports AI ready; starting earlier showed 未起動 under a
       caption that said 準備完了. */
    srcStart: 42.45,
    box: box("relay"),
    mode: "fill",
    tilt: { rx: 0, ry: 0 },
    caption: { chip: "準備完了", sub: "選んだ声に変換できます。" },
  },
  {
    id: "tune",
    kind: "window",
    duration: 93,
    srcStart: 43.7,
    box: widened("tune", 2.6, 2.6),
    mode: "object",
    k: 2.2,
    tilt: { rx: 5, ry: -14 },
    clicks: [{ aim: "tune", cueMs: 43687 }],
    caption: { chip: "調整" },
  },
  {
    id: "wiring",
    kind: "window",
    duration: 189,
    srcStart: 45.25,
    box: drawerBand(0.33, 0.45),
    mode: "fill",
    tilt: { rx: 0, ry: 0 },
    caption: { chip: "① 配線", sub: "マイク、出力先、モニター、音の規格。" },
  },
  {
    id: "close",
    kind: "window",
    duration: 102,
    srcStart: 54.2,
    box: drawerBand(0, 0.1),
    mode: "fill",
    tilt: { rx: 0, ry: 0 },
    caption: { chip: "閉じる" },
  },
  {
    id: "lab",
    kind: "window",
    duration: 102,
    srcStart: 57.6,
    box: widened("lab", 2.6, 2.6),
    mode: "object",
    k: 2.2,
    tilt: { rx: 5, ry: -14 },
    clicks: [{ aim: "lab", cueMs: 56953 }],
    caption: { chip: "実験" },
  },
  {
    id: "cards",
    kind: "window",
    duration: 113,
    srcStart: 59.3,
    box: drawerBand(0.28, 0.42),
    mode: "fill",
    tilt: { rx: 0, ry: 0 },
    caption: {
      chip: "① レイテンシ・ガバナ ・ ② 同時通訳ボイス ・ ③ 囁きモード",
      sub: "「実験機能有効」をONにすると、各機能のON/OFFが効くようになります。",
    },
  },
  {
    id: "voice",
    kind: "window",
    duration: 440,
    srcStart: 66.6,
    box: WHOLE,
    mode: "object",
    k: 1,
    tilt: { rx: 6, ry: -16 },
    chips: [
      { at: 0, label: "変換前" },
      { at: 230, label: "変換後（AI Voice）" },
    ],
    caption: {},
  },
  { id: "end", kind: "endcard", duration: 144 },
];

export const DURATION = BEATS.reduce((total, beat) => total + beat.duration, 0);

export const beatStart = (index: number) =>
  BEATS.slice(0, index).reduce((total, beat) => total + beat.duration, 0);
