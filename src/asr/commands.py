"""Wake word and voice commands, matched against the ASR transcript.

A command is only honoured when the wake word is present, so ordinary speech that
happens to contain "止めて" never trips the router. Matching is pure and dependency
free: normalise loudly enough to survive kana/width variation, require the wake
word, then look for the first known command phrase after it. A short cooldown
absorbs the repeat windows a rolling partial decoder produces for one utterance.

This module decides *what* a transcript means. Acting on it -- stopping the stream,
switching the voice -- belongs to the caller, so the decision is testable without
audio, a worker or a GUI.
"""
from dataclasses import dataclass
import re
import time
import unicodedata

# The wake word, in the forms a Japanese ASR is likely to emit. Normalised to
# NFKC and case-folded before comparison, so width and full/half-width romanisation
# both collapse onto these.
WAKE_WORDS = ("こえいろ", "コエイロ", "声彩", "koeiro")

# Ordered: earlier entries win, so a specific phrase must not be shadowed by a
# later, shorter one. Only phrases after the wake word are considered.
COMMANDS = (
    ("stop", ("止めて", "止まって", "停止", "ストップ", "やめて", "とめて", "とまって")),
    ("start", ("始めて", "はじめて", "開始", "スタート", "再開", "さいかい")),
    ("next_voice", ("次の声", "つぎの声", "次のこえ", "ネクスト", "次へ")),
    ("prev_voice", ("前の声", "まえの声", "前のこえ")),
    ("original", ("地声", "元の声", "オリジナル", "無変換")),
    ("ai_voice", ("AIボイス", "エーアイボイス", "変換して", "かえて")),
)

# Two rolling partials of the same utterance can both carry the phrase.
DEFAULT_COOLDOWN = 1.5
_FILLER = re.compile(r"[\s。、,.!?！？・…「」（）()【】]+")
CONTROL_LIMIT = 256


def _normalise(text):
    if not isinstance(text, str):
        return ""
    text = unicodedata.normalize("NFKC", text)[:CONTROL_LIMIT]
    text = _FILLER.sub("", text)
    return text.casefold()


@dataclass(frozen=True)
class VoiceCommand:
    """A recognised command: a kind, and the phrase that produced it."""

    kind: str
    phrase: str


LABELS = {
    "stop": "変換を停止",
    "start": "変換を開始",
    "next_voice": "次の声に切替",
    "prev_voice": "前の声に切替",
    "original": "Originalに切替",
    "ai_voice": "AI Voiceに切替",
}


def label(command):
    """A short Japanese label for status text and logs."""
    return LABELS.get(command.kind, command.kind)


class CommandMatcher:
    """Turns a transcript into at most one :class:`VoiceCommand`."""

    def __init__(self, cooldown=DEFAULT_COOLDOWN, clock=time.monotonic):
        self.cooldown = float(cooldown)
        self._clock = clock
        self.reset()

    def reset(self):
        self._last_kind = None
        self._last_at = None

    def wake_present(self, text):
        normalised = _normalise(text)
        return any(wake.casefold() in normalised for wake in WAKE_WORDS)

    def match(self, text, now=None):
        """The command this transcript carries, or None."""
        normalised = _normalise(text)
        if not normalised:
            return None
        wake_at = -1
        wake_len = 0
        for wake in WAKE_WORDS:
            found = normalised.find(wake.casefold())
            if found >= 0 and (wake_at < 0 or found < wake_at):
                wake_at, wake_len = found, len(wake)
        if wake_at < 0:
            return None
        rest = normalised[wake_at + wake_len:]
        for kind, phrases in COMMANDS:
            for phrase in phrases:
                if phrase.casefold() in rest:
                    if not self._accept(kind, now):
                        return None
                    return VoiceCommand(kind, phrase)
        return None

    def _accept(self, kind, now):
        now = self._clock() if now is None else now
        if (kind == self._last_kind and self._last_at is not None
                and now - self._last_at < self.cooldown):
            return False
        self._last_kind, self._last_at = kind, now
        return True
