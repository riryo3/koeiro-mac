"""Live translation voice: Japanese speech in, English speech to Discord out.

While the translate route runs, this driver (control side only, never the audio
callback) reads the microphone tap in small blocks, feeds the local ASR worker,
and watches for finalized transcripts. Each finished sentence is translated and
synthesized, then queued whole into the router's translate playback, which the
callback renders to the output device. The ASR worker endpoints on pauses by
itself, so no separate voice-activity detector is needed here.

Honest costs, stated in the GUI next to the switch: the ASR worker loads a
~180 MB model into its own process, the translator is offline software when
installed (otherwise the input is read as-is), and the TTS subprocess takes
seconds per sentence on a weak CPU -- talk in sentences, then pause. Nothing
here trains, and nothing touches the conversion route.
"""
import logging
import threading
import time

import numpy as np

log = logging.getLogger(__name__)

# Microphone block size the driver pulls per step.
READ_FRAMES = 960
# Below this RMS a tap block counts as silence (same floor as the ASR worker).
SILENCE_RMS = 0.004
# A partial transcript unchanged for this long is spoken even without a pause:
# long monologues otherwise never finalize. Repeats are suppressed by speaking
# only the words not spoken yet (see _speak_delta).
STABLE_SPEAK_SECONDS = 3.0


class TranslationDriver:
    """Owns the ASR worker, the translate/synthesize jobs and the playback feed."""

    def __init__(self, engine, playback, sample_rate=48000):
        self.engine = engine
        self.playback = playback
        self.sample_rate = int(sample_rate)
        self.asr = None
        self.pipeline = None
        self.voice = ""
        self._thread = None
        self._stop = threading.Event()
        self.stable_speak_seconds = STABLE_SPEAK_SECONDS
        self._status = {"running": False, "asr": "stopped", "heard": "",
                        "said": "", "queued_seconds": 0.0, "spoken": 0,
                        "mic_silent": False, "error": ""}

    @property
    def status(self):
        return dict(self._status)

    @property
    def alive(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, asr_parameters, build_pipeline, voice="", client_factory=None):
        """Launch the ASR worker and the driver thread. Idempotent while alive.

        ``build_pipeline`` is a zero-argument callable returning the assembled
        translation pipeline; it runs inside the driver thread because model
        construction blocks for seconds and must never stall the GUI thread.
        """
        if self.alive:
            return
        if self.playback is None:
            self._status.update(running=False, asr="stopped",
                                error="この構成では同時通訳ルートを使えません（外部チェーン）。")
            return
        from src.asr.bridge import ASRBridge
        self._build_pipeline = build_pipeline
        self.pipeline = None
        self.voice = voice or ""
        self._status.update(running=True, asr="loading", heard="", said="",
                            queued_seconds=0.0, spoken=0, error="")
        try:
            self.asr = (ASRBridge(asr_parameters, client_factory)
                        if client_factory is not None else ASRBridge(asr_parameters))
            self.asr.load()
            self.asr.set_active(True)
        except Exception as error:
            self.asr = None
            self._status.update(asr="error", error=str(error))
            log.warning("Translation ASR unavailable: %s", error)
            return
        self.engine.translate_tap.reset()
        self.engine.translate_tap.active = True
        self._stop.clear()
        self._last_spoken = ""
        self._partial_text = ""
        self._partial_since = 0.0
        self._silent_blocks = 0
        self._thread = threading.Thread(target=self._run, name="translate-driver", daemon=True)
        self._thread.start()

    def begin_stop(self):
        """Signal shutdown without waiting: the joins happen in join()."""
        self._stop.set()
        self.engine.translate_tap.active = False

    def join(self, timeout=5):
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        self._status.update(running=False, asr="stopped")

    def stop(self):
        self.begin_stop()
        asr, self.asr = self.asr, None
        if asr is not None:
            try:
                asr.stop()
            except Exception:
                log.exception("Translation ASR stop failed")
        self.join()

    def _report(self, **fields):
        status = dict(self._status)
        status.update(fields)
        status["queued_seconds"] = round(self.playback.queued_seconds, 1)
        self._status = status

    def _run(self):
        try:
            self._report(asr="preparing")
            self.pipeline = self._build_pipeline()
        except Exception as error:
            log.warning("Translation pipeline unavailable: %s", error)
            self._report(asr="error", error=str(error))
            return
        scratch = np.empty(READ_FRAMES, dtype=np.float32)
        try:
            while not self._stop.is_set():
                asr = self.asr
                if asr is None:
                    return
                got = self.engine.translate_tap.read_into(scratch)
                if got <= 0:
                    self._stop.wait(0.02)
                    continue
                block = scratch[:got].copy()
                level = float(np.sqrt(np.mean(block.astype(np.float64) ** 2)))
                if level < SILENCE_RMS:
                    self._silent_blocks += 1
                else:
                    self._silent_blocks = 0
                if self._silent_blocks * got > self.sample_rate // 2:
                    self._report(mic_silent=True)
                else:
                    self._report(mic_silent=False)
                try:
                    asr.submit(block)
                except Exception as error:
                    self._report(asr="error", error=str(error))
                    return
                self._poll_transcript()
                self._report(asr=asr.status)
        except Exception as error:
            log.exception("Translation driver failed")
            self._report(asr="error", error=str(error))

    def _poll_transcript(self):
        try:
            context = self.asr.current() or {}
        except Exception:
            return
        now = time.monotonic()
        final = (context.get("final_text") or "").strip()
        if final:
            self._partial_text = ""
            self._speak_delta(final)
            return
        partial = (context.get("partial_text") or "").strip()
        if not partial:
            self._partial_text = ""
            if self._last_spoken:
                # A pause between sentences re-arms repeats of the same words.
                self._last_spoken = ""
            return
        if partial != self._partial_text:
            self._partial_text = partial
            self._partial_since = now
            return
        if now - self._partial_since >= self.stable_speak_seconds:
            self._speak_delta(partial)

    def _speak_delta(self, text):
        """Speak what has not been spoken yet, nothing twice.

        Finals and stable partials overlap: a sentence first appears as a
        partial, then as a final. Speaking only the unseen suffix keeps long
        monologues flowing without repeating words on Discord.
        """
        if not text or text == self._last_spoken:
            return
        if self._last_spoken and text.startswith(self._last_spoken):
            speak_text = text[len(self._last_spoken):].strip()
            if not speak_text:
                self._last_spoken = text
                return
        else:
            speak_text = text
        self._report(heard=text)
        try:
            translated, audio = self.pipeline.process(speak_text, "ja", "en", self.voice)
        except Exception as error:
            self._report(error=str(error))
            return
        if np.asarray(audio, dtype=np.float32).size == 0:
            self._report(said=translated or "", error="音声が生成されませんでした")
            return
        if self.playback.offer(audio):
            self._last_spoken = text
            self._report(said=translated or "", spoken=self._status.get("spoken", 0) + 1)
        else:
            self._report(said=translated or "", error="音声が生成されませんでした")
