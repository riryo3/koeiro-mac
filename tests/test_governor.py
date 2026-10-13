import pytest

from src.audio.governor import LatencyGovernor
from src.audio.performance import TimingSnapshot


def snapshot(count, missed=0, p99=10.0):
    return TimingSnapshot(count=count, average_ms=6.0, maximum_ms=max(p99, 6.0), last_ms=6.0,
                          deadline_exceeded=missed, p95_ms=p99 * .9, p50_ms=5.0, p99_ms=p99)


def test_starts_on_the_cheap_profile():
    assert LatencyGovernor().profile == 'low_latency'


def test_one_clean_window_is_not_enough_to_raise():
    governor = LatencyGovernor(streak=3)
    decisions = [governor.observe(snapshot(100 * step)) for step in range(1, 4)]
    # Only the third clean window raises the profile; the first two are silence.
    assert [decision.profile for decision in decisions] == ['low_latency'] * 2 + ['balanced']
    assert decisions[0].changed is False
    assert decisions[-1].changed is True
    assert governor.profile == 'balanced'


def test_deadline_ratio_drops_back_immediately():
    governor = LatencyGovernor(streak=2)
    for step in (1, 2):
        governor.observe(snapshot(100 * step))
    assert governor.profile == 'balanced'
    decision = governor.observe(snapshot(500, missed=12))  # 12 misses in 300 blocks
    assert decision.profile == 'low_latency' and decision.changed is True
    assert decision.deadline_ratio == pytest.approx(0.04)
    assert '締切超過' in decision.reason


def test_p99_over_budget_drops_back_even_without_a_miss():
    governor = LatencyGovernor(streak=2, target_ms=45.0)
    for step in (1, 2):
        governor.observe(snapshot(100 * step))
    decision = governor.observe(snapshot(300, missed=0, p99=60.0))
    assert decision.profile == 'low_latency'
    assert decision.headroom_ms == pytest.approx(-15.0)


def test_balanced_needs_a_clean_run_not_a_single_quiet_window():
    governor = LatencyGovernor(streak=3)
    governor.observe(snapshot(100))
    governor.observe(snapshot(200))
    governor.observe(snapshot(300, missed=1))  # breaks the run
    governor.observe(snapshot(400))
    assert governor.profile == 'low_latency'


def test_reset_counters_start_a_new_window():
    governor = LatencyGovernor(streak=2)
    for step in (1, 2):
        governor.observe(snapshot(1000 * step))
    assert governor.profile == 'balanced'
    # A restarted stream reports small counters again: that is a fresh window, not a
    # negative delta, and it must not be read as a miss.
    decision = governor.observe(snapshot(4, missed=0, p99=9.0))
    assert decision.profile == 'balanced' and decision.deadline_ratio == 0.0


def test_no_blocks_observed_reports_no_ratio():
    decision = LatencyGovernor().observe(snapshot(0, missed=0, p99=0.0))
    assert decision.deadline_ratio == 0.0 and decision.profile == 'low_latency'


def test_invalid_limits_are_rejected():
    for limits in ({'target_ms': 0}, {'target_ms': 2000}, {'miss_ratio': -0.1},
                   {'miss_ratio': 2}, {'streak': 0}, {'profile': 'turbo'}):
        with pytest.raises(ValueError):
            LatencyGovernor(**limits)
