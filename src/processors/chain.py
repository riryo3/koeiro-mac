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


class ProcessorChain(AudioProcessor):
    def __init__(self, main_processor=None, gain_db=0.0, threshold_db=-45.0, denoise_strength=0.0,
                 whisper=None, finish=None):
        # Denoise first, then the gate, then gain: the gate sees a cleaner signal
        # and the strength-0 default makes the stage a true pass-through.
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
        self.pre_processors = ((self.whisper, self.leveler, self.denoise, self.gate, self.gain)
                               if whisper is not None
                               else (self.leveler, self.denoise, self.gate, self.gain))
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
        self.out_gate = OutputGate()
        self.out_gate_on = True
        self.post_processors = (self.out_gate, self.ai_formant, self.finish, SafetyClampProcessor())
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
            started = time.perf_counter_ns() if processor is self.main_processor else 0
            audio = processor.process(audio, sample_rate)
            if started:
                self.performance.record(time.perf_counter_ns() - started, len(audio), sample_rate)
            if not isinstance(audio, np.ndarray) or audio.shape != shape or audio.dtype != np.float32:
                raise ValueError("Processor must return float32 mono with unchanged frame count")
        return audio
