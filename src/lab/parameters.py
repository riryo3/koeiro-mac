"""Settings for the lab features, all off unless a user asks.

Every feature here is an addition to the shipped route, never a replacement for it,
so the defaults are the conservative ones: the governor is advisory (it reports, it
does not steer), the whisper stage is off, and nothing else runs at all until it is
switched on. Values are validated on load the same way the prosody parameters are,
so a hand-edited settings file degrades to the default instead of breaking the app.
"""
from dataclasses import dataclass
import math

# Where the translated speech is synthesized. "off" keeps the pack seam's base
# behaviour (a pass-through translator and bounded silence).
TRANSLATION_PROVIDERS = ('off', 'kokoro')


def _text(value, default, limit):
    return value if isinstance(value, str) and len(value) <= limit else default


def _flag(value, default):
    return value if type(value) is bool else default


def _number(value, default, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        return default
    return value


@dataclass(frozen=True)
class LabParameters:
    # The master switch. Off means the optional features are not in use at all, which
    # is what a fresh install should be: the drawer lists what exists and nothing else.
    enabled: bool = False
    # 1. Latency governor: measure the callback against its deadline and report the
    #    profile a struggling machine should run. Auto-apply is a separate, later
    #    decision because it changes a live route.
    governor: bool = True
    governor_auto: bool = False
    # 2. Translation voice: which providers the pack seam is assembled from.
    translation_provider: str = 'off'
    translate_voice: str = ''
    translate_reference: str = ''
    translate_preserve: bool = True
    # 3. Whisper mode: voiced excitation for speech the model cannot hear a pitch in.
    whisper: bool = False
    whisper_amount: float = .5
    whisper_pitch: float = 200.
    # 4. Distributed inference: a GPU machine on the LAN answers the worker calls.
    remote: bool = False
    remote_host: str = ''
    remote_port: int = 8765
    # 6. Speaker routing: split one microphone between speakers and give each its
    #    own voice slot.
    diarization: bool = False
    diarization_speakers: int = 2

    def __post_init__(self):
        for name in ('enabled', 'governor', 'governor_auto', 'translate_preserve',
                     'whisper', 'remote', 'diarization'):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f'{name} must be boolean')
        if self.translation_provider not in TRANSLATION_PROVIDERS:
            raise ValueError('Unsupported translation provider')
        if _text(self.translate_voice, '', 128) != self.translate_voice:
            raise ValueError('Invalid translate voice label')
        if _text(self.translate_reference, '', 64) != self.translate_reference:
            raise ValueError('Invalid translate reference')
        for name, low, high in self.bounds():
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f'{name} must be {low}..{high}')
        if _text(self.remote_host, '', 253) != self.remote_host:
            raise ValueError('Invalid remote host')

    @staticmethod
    def bounds():
        # (name, low, high) for every numeric field, mirrored by the loader so the
        # two can never disagree about what a valid file looks like.
        return [('whisper_amount', 0, 1), ('whisper_pitch', 80, 400),
                ('remote_port', 1, 65535),
                ('diarization_speakers', 2, 4)]

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            return cls()
        default = cls()
        valid = {name: _flag(data.get(name), getattr(default, name))
                 for name in ('enabled', 'governor', 'governor_auto', 'translate_preserve',
                              'whisper', 'remote', 'diarization')}
        provider = data.get('translation_provider')
        valid['translation_provider'] = (provider if provider in TRANSLATION_PROVIDERS
                                         else default.translation_provider)
        valid['translate_voice'] = _text(data.get('translate_voice'), '', 128)
        valid['translate_reference'] = _text(data.get('translate_reference'), '', 64)
        valid['remote_host'] = _text(data.get('remote_host'), '', 253)
        for name, low, high in cls.bounds():
            value = data.get(name)
            valid[name] = value if (type(value) in (int, float) and math.isfinite(value)
                                    and low <= value <= high) else getattr(default, name)
        # A port typed as a float (JSON has one number type) is still an int field.
        valid['remote_port'] = int(valid['remote_port'])
        valid['diarization_speakers'] = int(valid['diarization_speakers'])
        return cls(**valid)
