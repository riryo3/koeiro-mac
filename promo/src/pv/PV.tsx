import React from "react";
import { Audio, OffthreadVideo, Sequence, staticFile } from "remotion";
import { CANVAS } from "./constants";
import { BEATS, beatStart, type Beat } from "./meta/beats";
import { cueToBeatFrame } from "./time";
import { Stage } from "./components/Stage";
import { Window3D } from "./components/Window3D";
import { ClickRing } from "./components/ClickRing";
import { Caption } from "./components/Caption";
import { EndCard } from "./components/EndCard";

/** SendInput fires on the cue; the button's repaint lands a frame or two later. */
const CLICK_LAG = 2;

const beatIndex = (id: string) => BEATS.findIndex((beat) => beat.id === id);
const startsAt = (id: string) => beatStart(beatIndex(id));

/** Where a recorded cue lands on the film's own timeline. */
const inBeat = (id: string, cueMs: number) =>
  cueToBeatFrame(cueMs, BEATS[beatIndex(id)].srcStart ?? 0);
const onTimeline = (id: string, cueMs: number) => startsAt(id) + inBeat(id, cueMs);

const WindowBeat: React.FC<{ index: number; beat: Beat }> = ({ index, beat }) => (
  <Sequence from={beatStart(index)} durationInFrames={beat.duration} name={beat.id}>
    <Window3D index={index} beat={beat}>
      {beat.clicks?.map((click) => (
        <Sequence
          key={click.aim}
          from={inBeat(beat.id, click.cueMs) + CLICK_LAG}
          durationInFrames={36}
          layout="none"
        >
          <ClickRing aim={click.aim} />
        </Sequence>
      ))}
    </Window3D>
    <Caption data={beat.caption} chips={beat.chips} />
  </Sequence>
);

const Sfx: React.FC<{ file: string; from: number; frames: number; volume?: number }> = ({
  file,
  from,
  frames,
  volume = 0.5,
}) => (
  <Sequence from={from} durationInFrames={frames} layout="none" name={file}>
    <Audio src={staticFile(`audio/${file}`)} volume={volume} />
  </Sequence>
);

/**
 * Every sound is pinned to a mark from take.json rather than to a beat boundary, so the
 * click you hear is the click you see. The voice A/B is the one thing that is not in the
 * take: the recording carries no audio, so it plays over the stage hold at the end.
 */
const Soundtrack: React.FC = () => {
  const voice = startsAt("voice");
  return (
    <>
      <Sfx file="arrive.wav" from={startsAt("arrival")} frames={24} volume={1} />
      <Sfx file="click_blip.wav" from={onTimeline("start", 2812) + CLICK_LAG} frames={6} />
      <Sfx file="click_blip.wav" from={onTimeline("tune", 43687) + CLICK_LAG} frames={6} />
      <Sfx file="drawer_open.wav" from={onTimeline("tune", 44328)} frames={15} />
      <Sfx file="click_blip.wav" from={onTimeline("close", 53578)} frames={6} />
      <Sfx file="drawer_close.wav" from={onTimeline("close", 54250)} frames={11} />
      <Sfx file="click_blip.wav" from={onTimeline("lab", 56953) + CLICK_LAG} frames={6} />
      <Sfx file="drawer_open.wav" from={onTimeline("lab", 57515)} frames={15} />
      <Sfx file="voice_demo_original.wav" from={voice} frames={210} volume={1} />
      <Sfx file="voice_demo_converted.wav" from={voice + 230} frames={200} volume={1} />
      <Sfx file="end_sting.wav" from={startsAt("end")} frames={72} volume={0.9} />
    </>
  );
};

export const PV: React.FC = () => (
  <Stage>
    {BEATS.map((beat, index) => {
      if (beat.kind === "window") {
        return <WindowBeat key={beat.id} index={index} beat={beat} />;
      }
      if (beat.kind === "endcard") {
        return (
          <Sequence key={beat.id} from={beatStart(index)} durationInFrames={beat.duration} name={beat.id}>
            <EndCard />
          </Sequence>
        );
      }
      /* The splash is the app's own 900 ms in / 900 ms hold / 1200 ms out. trimBefore skips the
         reveal and durationInFrames stops before the fade, so the plate is cut on a logo that
         is fully lit rather than on the blank navy it fades to. */
      return (
        <Sequence key={beat.id} from={beatStart(index)} durationInFrames={beat.duration} name={beat.id}>
          <OffthreadVideo
            src={staticFile("brand/splash.mp4")}
            muted
            trimBefore={51}
            durationInFrames={beat.duration}
            style={{ width: CANVAS.width, height: CANVAS.height }}
          />
        </Sequence>
      );
    })}
    <Soundtrack />
  </Stage>
);
