export const CANVAS = { width: 1920, height: 1080 };
export const FPS = 60;

/** The take is 1920x1008 because it captured a maximised window on a screen whose taskbar
 *  takes 72 px. The app draws its own frame, so the whole frame is the window. */
export const WINDOW = { width: 1920, height: 1008 };
export const WINDOW_TOP = (CANVAS.height - WINDOW.height) / 2;

export const COLOR = {
  surface: "#eef2f7",
  card: "#ffffff",
  rule: "#d4dbe5",
  body: "#18181b",
  muted: "#606060",
  brand: "#284b7d",
};

export const FONT =
  "din-2014, 'Noto Sans JP', YuGothic, 'Yu Gothic', 'Yu Gothic UI', 'Segoe UI', sans-serif";

/** Where text may go. 104 px at the sides, 88 px top and bottom. */
export const SAFE = { left: 104, right: 104, top: 88, bottom: 88 };
