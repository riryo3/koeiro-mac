import numpy as np
import time

from src.audio.performance import TimingStats
from src.vc.models import is_meanvc2

from .base import AudioProcessor
from .denoise import NoiseSuppressionProcessor
from .dsp_parameters import DSPParameters
from .female_dsp import FemaleDSPProcessor
from .gain import GainProcessor
from .leveler import AutoLevelProcessor
from .low_cut import InputLowCutProcessor, OutputHighCutProcessor
from .noise_gate import NoiseGateProcessor
from .passthrough import PassthroughProcessor


class SafetyClampProcessor(AudioProcessor):
    def prepare(self, sample_rate, max_frames):
        self._finite = np.empty((max_frames, 1), dtype=bool)

    def process(self, audio, sample_rate):
        # Reuse a boolean mask rather than nan_to_num's temporary masks.
        mask = self._finite[:len(audio)]
        np.isfinite(audio, out=mask)
        np.logical_not(mask, out=mask)
        np.copyto(audio, 0.0, where=mask)
        np.clip(audio, -1.0, 1.0, out=audio)
        return audio


class OutputGate(NoiseGateProcessor):
    """A noise gate on the converted output, armed only on the AI route.

    The MeanVC2 model keeps producing a faint breath (about -37 dBFS) from silence, so
    the input gate alone cannot keep the output quiet while nobody speaks.
    """

    def __init__(self, threshold_db=-34.0):
        super().__init__(threshold_db)
        self.enabled = False

    def process(self, audio, sample_rate):
        if not self.enabled:
            return audio
        return super().process(audio, sample_rate)


class SilenceMute(AudioProcessor):
    """Passes the converted output only where the input had speech, one model delay earlier.

    With nothing coming in, the model still hallucinates short hiss bursts (3-6 kHz, up to
    -14 dBFS, measured on a recording with the microphone off), and no filter separates
    those from speech. The input gate knows when speech went in, and the voice comes out
    about 2.4 s later (measured by replaying a recording through the real chain; a 1.5 s
    hold muted whole words before they were played). So the output at time t is let through
    when the input was open somewhere in [t - delay - tail, t - delay + lead], and muted
    otherwise. The delay is measured while running: each input onset is paired with the next
    output onset, and the median of the last few pairs is used. Until the first pair exists
    the output is muted after a plain 4 s hold. Ramps are 10 ms (close) and 5 ms (open);
    switched off it is a pass-through.
    """

    DEFAULT_DELAY = 2.4
    MIN_DELAY, MAX_DELAY = 0.8, 3.8
    LEAD, TAIL = 0.5, 0.9           # seconds around the delayed input that stay open
    START_HOLD = 4.0                # the rule used before a delay has been measured
    ONSET_DB = -45.0
    PAIRS = 5

    def __init__(self, hold_seconds=START_HOLD):
        self.hold_seconds = float(hold_seconds)
        self.enabled = True
        self.armed = False          # set per block by the chain: AI route only
        self.input_open = True      # set per block by the chain: the input gate's state
        self.delay_seconds = None   # measured model delay; None until the first pair
        self.reset()

    def prepare(self, sample_rate, max_frames):
        self._rate = sample_rate
        self.reset()

    def reset(self):
        self._frame = 0
        self._silent_frames = 0
        self._level = 1.0
        self._was_open = False
        self._intervals = []        # [start, end] input-open spans, in frames
        self._pending_onsets = []   # input onsets (frames) not yet paired with an output onset
        self._quiet_out_frames = 10 ** 9
        self._pairs = []

    # -- delay measurement -------------------------------------------------------------
    def _note_input(self, start, frames, rate):
        if self.input_open:
            if self._intervals and start - self._intervals[-1][1] <= frames:
                self._intervals[-1][1] = start + frames
            else:
                self._intervals.append([start, start + frames])
            if not self._was_open:
                self._pending_onsets.append(start)
        self._was_open = self.input_open
        horizon = start - int(8 * rate)
        while self._intervals and self._intervals[0][1] < horizon:
            self._intervals.pop(0)
        self._pending_onsets = [onset for onset in self._pending_onsets if onset > horizon]

    def _note_output(self, audio, start, frames, rate):
        level = float(np.sqrt(np.mean(audio * audio))) if frames else 0.0
        loud = level > 10.0 ** (self.ONSET_DB / 20.0)
        if loud and self._quiet_out_frames >= int(0.4 * rate):
            for onset in self._pending_onsets:
                seconds = (start - onset) / rate
                if self.MIN_DELAY <= seconds <= self.MAX_DELAY:
                    self._pairs.append(seconds)
                    del self._pairs[:-self.PAIRS]
                    self.delay_seconds = float(np.median(self._pairs))
                    self._pending_onsets = [o for o in self._pending_onsets if o > onset]
                    break
        self._quiet_out_frames = 0 if loud else self._quiet_out_frames + frames

    def _allowed(self, start, frames, rate):
        if self.delay_seconds is None:
            return self._silent_frames <= self.hold_seconds * rate
        low = start - int((self.delay_seconds + self.TAIL) * rate)
        high = start + frames - int((self.delay_seconds - self.LEAD) * rate)
        return any(span[1] >= low and span[0] <= high for span in self._intervals)

    def process(self, audio, sample_rate):
        frames = len(audio)
        start = self._frame
        self._frame += frames
        if not (self.enabled and self.armed):
            self._silent_frames = 0
            self._was_open = self.input_open
            return audio
        self._silent_frames = 0 if self.input_open else self._silent_frames + frames
        self._note_input(start, frames, sample_rate)
        self._note_output(audio, start, frames, sample_rate)
        target = 1.0 if self._allowed(start, frames, sample_rate) else 0.0
        if self._level == target:
            if target == 0.0:
                audio.fill(0.0)
            return audio
        seconds = 0.010 if target < self._level else 0.005
        step = frames / (seconds * sample_rate)
        delta = target - self._level
        end = self._level + (min(abs(delta), step) if delta > 0 else -min(abs(delta), step))
        ramp = np.linspace(self._level, end, frames, dtype=np.float32).reshape(-1, 1)
        np.multiply(audio, ramp, out=audio)
        self._level = float(end)
        return audio


class ProcessorChain(AudioProcessor):
    def __init__(self, main_processor=None, gain_db=0.0, threshold_db=-45.0, denoise_strength=0.0,
                 whisper=None, finish=None):
        # Denoise first, then the gate, then gain: the gate sees a cleaner signal
        # and the strength-0 default makes the stage a true pass-through.
        # The input low-cut leads the chain so nothing downstream sees desk thumps or plosives.
        self.low_cut = InputLowCutProcessor()
        self.leveler = AutoLevelProcessor()
        self.denoise = NoiseSuppressionProcessor(denoise_strength)
        self.gate = NoiseGateProcessor(threshold_db)
        self.gain = GainProcessor(gain_db)
        # Whisper mode sits before everything: restoring a pitch before the gate and
        # the model see the signal is the point. It is off by default (amount 0), and
        # a chain without it is exactly what this build shipped before.
        self.whisper = whisper
        # Levelling rides behind whisper (so its excitation is levelled too) and
        # ahead of denoise: the gate threshold and the model both behave when the
        # input sits at one level. Disabled is a true pass-through.
        self.pre_processors = ((self.low_cut, self.whisper, self.leveler, self.denoise, self.gate, self.gain)
                               if whisper is not None
                               else (self.low_cut, self.leveler, self.denoise, self.gate, self.gain))
        self.main_processor = main_processor if main_processor is not None else PassthroughProcessor()
        # The AI formant finish lifts converted output toward a brighter vocal
        # tract without moving its pitch. Off by default; the native stage is
        # prepared in any case so toggling needs no restart, and it only ever
        # engages on the AI route (Original, Female DSP and translate pass by).
        self.ai_formant = FemaleDSPProcessor(DSPParameters(
            mode='original', pitch=0.0, formant=0.0, brightness=50.0,
            low_cut=False, limiter=False, wet=1.0, quality='low_latency'))
        self.ai_formant_enabled = False
        self.ai_formant_semitones = 0.0
        # The natural finish conditions converted output only: Original never
        # passes through it, and a chain without it is the previous behaviour.
        from .natural_finish import NaturalFinishProcessor
        self.finish = finish if finish is not None else NaturalFinishProcessor()
        # Converted output only: the model can answer desk thumps and plosives with a loud
        # low thud, so the same high-pass also runs after it.
        self.out_low_cut = InputLowCutProcessor()
        self.out_low_cut_on = False
        # The matching low-pass trims hiss and sibilant bursts; the cutoff is a slider.
        self.out_high_cut = OutputHighCutProcessor()
        self.out_high_cut_on = False
        self.silence_mute = SilenceMute()
        self.out_gate = OutputGate()
        self.out_gate_on = True
        self.post_processors = (self.silence_mute, self.out_low_cut, self.out_high_cut, self.out_gate, self.ai_formant, self.finish, SafetyClampProcessor())
        self._stages = (*self.pre_processors, self.main_processor, *self.post_processors)
        self.performance = TimingStats()

    def prepare(self, sample_rate, max_frames):
        self.performance.reset()
        for processor in self._stages:
            processor.prepare(sample_rate, max_frames)

    def reset(self):
        for processor in self._stages:
            processor.reset()

    def stop(self):
        for processor in self._stages:
            processor.stop()

    def process(self, audio, sample_rate):
        shape = audio.shape
        router = self.main_processor
        ai = getattr(router, 'ai', None)
        self.gate.protect_quiet = (getattr(router, 'mode', None) == 'ai_voice'
                                   and ai is not None and is_meanvc2(ai.bridge.parameters.model))
        self.out_gate.enabled = self.out_gate_on and getattr(router, 'mode', None) == 'ai_voice'
        self.silence_mute.armed = getattr(router, 'mode', None) == 'ai_voice'
        self.out_low_cut.set_enabled(self.out_low_cut_on and getattr(router, 'mode', None) == 'ai_voice')
        self.out_high_cut.set_enabled(self.out_high_cut_on and getattr(router, 'mode', None) == 'ai_voice')
        # The finish only ever conditions converted output. The flag rides along
        # per block so a mid-stream route change takes effect on the next block.
        self.finish.route_active = getattr(router, 'mode', 'ai_voice') != 'original'
        # Same arming for the AI formant finish: converted AI output only. The
        # parameter swap is a store, so toggling mid-stream never reallocates.
        if getattr(router, 'mode', None) == 'ai_voice' and self.ai_formant_enabled:
            self.ai_formant.set_parameters(DSPParameters(
                mode='female_dsp', pitch=0.0, formant=self.ai_formant_semitones,
                brightness=50.0, low_cut=False, limiter=False, wet=1.0, quality='low_latency'))
        else:
            self.ai_formant.set_parameters(DSPParameters(
                mode='original', pitch=0.0, formant=0.0,
                brightness=50.0, low_cut=False, limiter=False, wet=1.0, quality='low_latency'))
        for processor in self._stages:
            if processor is self.silence_mute:
                # The gate has seen this block by now: it is open while the input has speech.
                processor.input_open = self.gate._opened
            started = time.perf_counter_ns() if processor is self.main_processor else 0
            audio = processor.process(audio, sample_rate)
            if started:
                self.performance.record(time.perf_counter_ns() - started, len(audio), sample_rate)
            if not isinstance(audio, np.ndarray) or audio.shape != shape or audio.dtype != np.float32:
                raise ValueError("Processor must return float32 mono with unchanged frame count")
        return audio
