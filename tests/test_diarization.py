import numpy as np
import pytest

from src.processors.diarization import SpeakerRouting, SpeakerTracker, features

SAMPLE_RATE = 48000


def tone(pitch, seconds=0.25, level=0.2):
    times = np.arange(int(SAMPLE_RATE * seconds)) / SAMPLE_RATE
    return (level * np.sign(np.sin(2 * np.pi * pitch * times))).astype(np.float32)


def test_features_find_pitch_and_voicing():
    pitch, centroid, rms, voiced = features(tone(200.0), SAMPLE_RATE)
    assert voiced and pitch == pytest.approx(200.0, rel=0.1)
    assert centroid > 0 and rms > 0


def test_noise_has_no_speaker_because_it_has_no_pitch():
    rng = np.random.default_rng(4)
    _, _, _, voiced = features((rng.normal(0, .1, 12000)).astype(np.float32), SAMPLE_RATE)
    assert voiced is False


def test_silence_reports_nothing():
    assert features(np.zeros(12000, dtype=np.float32), SAMPLE_RATE)[3] is False


def test_two_speakers_stay_separate():
    rng = np.random.default_rng(9)
    tracker = SpeakerTracker(speakers=2)
    labels = {0: [], 1: []}
    for step in range(40):
        speaker = step % 2
        pitch = (120.0 if speaker == 0 else 230.0) * rng.uniform(0.96, 1.04)
        centroid = (900.0 if speaker == 0 else 2600.0) * rng.uniform(0.97, 1.03)
        labels[speaker].append(tracker.observe(pitch, centroid, voiced=True).label)
    for speaker, found in labels.items():
        common = max(found.count(label) for label in set(found))
        assert common / len(found) >= 0.9
    assert set(labels[0][-10:]) != set(labels[1][-10:])


def test_a_second_speaker_who_starts_later_is_still_found():
    """The first speaker must not spend the discovery budget by speaking first."""
    tracker = SpeakerTracker(speakers=2)
    for _ in range(20):
        tracker.observe(130.0, 1100.0, voiced=True)
    assert len(tracker._centroids) == 1
    labels = [tracker.observe(250.0, 2700.0, voiced=True).label for _ in range(8)]
    assert len(tracker._centroids) == 2
    assert labels.count(1) >= 6 and labels[-1] == 1


def test_a_single_outlier_does_not_take_a_speaker_slot():
    tracker = SpeakerTracker(speakers=2)
    for _ in range(10):
        tracker.observe(150.0, 1200.0, voiced=True)
    tracker.observe(320.0, 3200.0, voiced=True)  # one cough, never repeated
    assert len(tracker._centroids) == 1
    assert tracker.observe(150.0, 1200.0, voiced=True).label == 0


def test_one_speaker_uses_one_centroid():
    tracker = SpeakerTracker(speakers=2)
    for _ in range(20):
        tracker.observe(150.0, 1500.0, voiced=True)
    assert tracker.observe(150.0, 1500.0, voiced=True).speakers == 1


def test_unvoiced_blocks_keep_the_previous_label():
    tracker = SpeakerTracker(speakers=2)
    tracker.observe(140.0, 1200.0, voiced=True)
    state = tracker.observe(0.0, 0.0, voiced=False)
    assert state.label == tracker.label and state.reason == 'unvoiced'


def test_the_speaker_limit_is_respected():
    tracker = SpeakerTracker(speakers=2)
    for pitch in (120.0, 230.0, 340.0):
        for _ in range(3):
            tracker.observe(pitch, 1000.0 + pitch, voiced=True)
    assert len(tracker._centroids) == 2


def test_a_new_speaker_must_be_far_from_the_existing_ones():
    tracker = SpeakerTracker(speakers=2)
    tracker.observe(200.0, 2000.0, voiced=True)
    # A small difference is jitter, not a second person.
    assert tracker.observe(205.0, 2050.0, voiced=True).speakers == 1


def test_invalid_configuration_is_rejected():
    for speakers in (1, 5, True, 'two'):
        with pytest.raises(ValueError):
            SpeakerTracker(speakers=speakers)
    with pytest.raises(ValueError):
        SpeakerTracker(minimum_frames=0)


def test_routing_maps_speakers_to_voices():
    routing = SpeakerRouting({0: 'user_a', 1: 'user_b'})
    assert routing.voice_for(0) == 'user_a'
    assert routing.voice_for(1) == 'user_b'
    # No decision keeps the current voice.
    assert routing.voice_for(2) is None and routing.voice_for(None) is None
    routing.set(1, None)
    assert routing.voice_for(1) is None
    with pytest.raises(ValueError):
        routing.set(9, 'user_a')
    with pytest.raises(ValueError):
        routing.set(0, '')
