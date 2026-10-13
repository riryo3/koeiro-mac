/**
 * Writes the PV's sound effects as deterministic PCM16 WAV files.
 *
 * Remotion only captures audio from <Audio>/<Video> elements, so nothing here may run
 * in the browser: every sound is rendered to disk first and referenced by staticFile().
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const RATE = 48000;
const OUT = resolve(dirname(fileURLToPath(import.meta.url)), "../public/audio");

/** Seeded so two runs produce the same bytes; Math.random would make renders unreproducible. */
function random(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function writeWav(name, channels) {
  const frames = channels[0].length;
  const count = channels.length;
  const body = frames * count * 2;
  const buffer = Buffer.alloc(44 + body);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + body, 4);
  buffer.write("WAVEfmt ", 8);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(count, 22);
  buffer.writeUInt32LE(RATE, 24);
  buffer.writeUInt32LE(RATE * count * 2, 28);
  buffer.writeUInt16LE(count * 2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(body, 40);
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < count; c++) {
      const v = Math.max(-1, Math.min(1, channels[c][i]));
      buffer.writeInt16LE(Math.round(v * 32767), 44 + (i * count + c) * 2);
    }
  }
  const path = resolve(OUT, name);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, buffer);
  return `${name} ${(frames / RATE).toFixed(3)}s`;
}

const seconds = (n) => Math.round((n / 1000) * RATE);

function envelope(length, { attackMs, decayTauMs, gain }) {
  const attack = seconds(attackMs);
  const tau = seconds(decayTauMs);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    const rise = i < attack ? i / attack : 1;
    out[i] = rise * Math.exp(-Math.max(0, i - attack) / tau) * gain;
  }
  return out;
}

/** One-pole lowpass whose cutoff moves per sample; rc is the time constant in samples. */
function sweep(input, cutoffHz, gain) {
  let state = 0;
  const out = new Float32Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const a = 1 / (1 + RATE / (2 * Math.PI * cutoffHz(i)));
    state += a * (input[i] - state);
    out[i] = state * gain(i);
  }
  return out;
}

const lerp = (from, to, p) => from + (to - from) * p;
const ease = (p) => 0.5 - 0.5 * Math.cos(Math.PI * Math.min(1, Math.max(0, p)));

function tone(length, hz, phase = 0) {
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) out[i] = Math.sin((2 * Math.PI * hz * i) / RATE + phase);
  return out;
}

function shape(carrier, envelopeValues) {
  const out = new Float32Array(carrier.length);
  for (let i = 0; i < carrier.length; i++) out[i] = carrier[i] * envelopeValues[i];
  return out;
}

function noise(length, seed) {
  const next = random(seed);
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) out[i] = next() * 2 - 1;
  return out;
}

const files = [];

// A UI click: short, bright, no tail that could collide with the next beat.
{
  const length = seconds(60);
  const env = envelope(length, { attackMs: 8, decayTauMs: 18, gain: 0.5 });
  files.push(writeWav("click_blip.wav", [shape(tone(length, 1200), env)]));
}

// A drawer arriving: noise opening upward, which reads as something sliding into place.
{
  const length = seconds(240);
  const p = (i) => i / length;
  files.push(
    writeWav("drawer_open.wav", [
      sweep(noise(length, 0x4b4f4549), (i) => lerp(400, 4000, ease(p(i))), (i) => 0.32 * ease(p(i)) * (1 - p(i) ** 3)),
    ]),
  );
}

// The same gesture inverted, so closing sounds like the reverse of opening.
{
  const length = seconds(180);
  const p = (i) => i / length;
  files.push(
    writeWav("drawer_close.wav", [
      sweep(noise(length, 0x50563032), (i) => lerp(3600, 500, ease(p(i))), (i) => 0.28 * (1 - ease(p(i)))),
    ]),
  );
}

// The window arriving from depth: a low swell under a rising filter.
{
  const length = seconds(400);
  const p = (i) => i / length;
  const body = sweep(noise(length, 0x4b4f4549), (i) => lerp(120, 1800, ease(p(i))), (i) => 0.3 * ease(p(i)) * (1 - p(i)));
  const low = shape(tone(length, 90), envelope(length, { attackMs: 60, decayTauMs: 220, gain: 0.18 }));
  files.push(writeWav("arrive.wav", [body.map((v, i) => v + low[i])]));
}

// Two notes a fifth apart, slightly detuned between the ears, to close on.
{
  const length = seconds(1200);
  const env = envelope(length, { attackMs: 12, decayTauMs: 380, gain: 0.34 });
  const left = shape(tone(length, 392), env);
  const right = shape(tone(length, 588, 0.3), env);
  files.push(
    writeWav("end_sting.wav", [
      left.map((v, i) => v * 0.7 + right[i] * 0.3),
      right.map((v, i) => v * 0.7 + left[i] * 0.3),
    ]),
  );
}

console.log(files.join("\n"));
