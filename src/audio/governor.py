"""Latency governor: decide which quality profile this machine can actually afford.

The callback already records how long each block took and how often it overran its
deadline (see :class:`src.audio.performance.TimingStats`). The governor reads those
counters -- on the GUI thread, from a snapshot, never in the callback -- and answers
one question: can this machine keep the heavier profile, or should it drop to the
cheap one?

It is deliberately *advisory*: the app keeps working exactly as before and the
governor only reports. Applying a profile changes a live route, so that decision
stays with the user (or with an explicit opt-in), and a wrong recommendation costs
nothing.

Two rules keep it from flapping:

* decisions use the delta between snapshots, so an early spike on a long run does not
  pin the profile forever;
* a heavier profile requires several consecutive clean windows, while dropping back is
  immediate -- an overrun is evidence, silence is not.
"""
from dataclasses import dataclass
import logging

log = logging.getLogger(__name__)

PROFILES = ('low_latency', 'balanced')
# Fraction of blocks that may miss the deadline before the heavy profile is refused.
DEFAULT_MISS_RATIO = 0.02
# A heavier profile needs this many consecutive clean windows before it is suggested.
DEFAULT_STREAK = 3
# The cheap profile is suggested when the 99th percentile passes the budget.
DEFAULT_TARGET_MS = 45.0


@dataclass(frozen=True)
class GovernorDecision:
    """What the governor concluded, and the numbers it concluded it from."""

    profile: str
    changed: bool
    reason: str
    deadline_ratio: float
    p99_ms: float
    headroom_ms: float

    @property
    def label(self):
        return '低遅延' if self.profile == 'low_latency' else '高品質'


class LatencyGovernor:
    """Turns two cumulative timing snapshots into a bounded profile recommendation."""

    def __init__(self, target_ms=DEFAULT_TARGET_MS, miss_ratio=DEFAULT_MISS_RATIO,
                 streak=DEFAULT_STREAK, profile='low_latency'):
        if profile not in PROFILES:
            raise ValueError('Unknown profile')
        if not 1 <= target_ms <= 1000 or not 0 <= miss_ratio <= 1 or not 1 <= streak <= 400:
            raise ValueError('Invalid governor limits')
        self.target_ms = float(target_ms)
        self.miss_ratio = float(miss_ratio)
        self.streak = int(streak)
        self.profile = profile
        self.reset()

    def reset(self):
        self._count = None
        self._missed = None
        self._clean_runs = 0
        self._last = None

    def observe(self, snapshot):
        """Fold one :class:`TimingSnapshot` in and return the current decision.

        A snapshot whose counters moved backwards means the stats were reset (a new
        stream, a restarted worker): the window starts over rather than computing a
        negative delta.
        """
        count = int(getattr(snapshot, 'count', 0) or 0)
        missed = int(getattr(snapshot, 'deadline_exceeded', 0) or 0)
        p99 = float(getattr(snapshot, 'p99_ms', 0.0) or 0.0)
        if self._count is None or count < self._count or missed < self._missed:
            delta_count, delta_missed = count, missed
        else:
            delta_count, delta_missed = count - self._count, missed - self._missed
        self._count, self._missed = count, missed
        ratio = delta_missed / delta_count if delta_count else 0.0
        headroom = self.target_ms - p99
        changed = False
        if delta_count and (ratio > self.miss_ratio or p99 > self.target_ms):
            reason = (f'締切超過 {ratio*100:.1f}% / p99 {p99:.1f}ms' if ratio > self.miss_ratio
                      else f'p99 {p99:.1f}ms が予算 {self.target_ms:.0f}ms を超過')
            self._clean_runs = 0
            if self.profile != 'low_latency':
                changed = True
                log.info('Governor: dropping to low_latency (%s)', reason)
            self.profile = 'low_latency'
        elif delta_count and ratio == 0.0 and p99 < self.target_ms * 0.6:
            self._clean_runs += 1
            if self._clean_runs >= self.streak and self.profile != 'balanced':
                changed = True
                reason = f'{self._clean_runs}回連続で余裕 {headroom:.1f}ms'
                log.info('Governor: raising to balanced (%s)', reason)
                self.profile = 'balanced'
            else:
                reason = f'余裕あり {self._clean_runs}/{self.streak}'
        else:
            self._clean_runs = 0
            reason = f'様子見 (p99 {p99:.1f}ms)'
        self._last = GovernorDecision(self.profile, changed, reason, ratio, p99, headroom)
        return self._last

    @property
    def last(self):
        return self._last
