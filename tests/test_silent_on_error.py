import numpy as np
from dataclasses import replace


def _processor(flag, status):
    from src.processors.ai_voice import AIVoiceProcessor
    from src.vc.config import AIParameters
    from src.vc.voice_library import DEFAULT_VOICE_ID
    ai = AIVoiceProcessor()
    ai.prepare(48000, 256)
    ai.supported = True
    ai.bridge.parameters = replace(AIParameters(model=DEFAULT_VOICE_ID), silent_on_error=flag)
    ai.bridge.status = status
    return ai


def _peak(ai):
    out = ai.process(np.full((256, 1), 0.3, dtype=np.float32), 48000)
    return float(np.abs(out).max())


def test_worker_error_is_silent_by_default():
    assert _peak(_processor(True, 'Error')) == 0.0


def test_worker_error_can_still_fall_back_to_the_original():
    assert abs(_peak(_processor(False, 'Error')) - 0.3) < 1e-6


def test_loading_is_silent_either_way():
    assert _peak(_processor(False, 'Loading')) == 0.0
    assert _peak(_processor(True, 'Loading')) == 0.0
