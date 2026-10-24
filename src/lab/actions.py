"""The lab features' real work, kept out of the GUI thread.

Each function here is a complete job: it runs off the GUI thread (through
:class:`src.utils.background_files.BackgroundFiles`), touches no widget, and returns a
one-line status the GUI can print. Keeping them here means they can be tested without
a window, which is the only way to know they work before a user clicks them.

They are deliberately honest about outcomes. ``translate_test`` writes a WAV and
reports what it measured instead of playing audio -- a listening check is the user's
to make, on their own machine. ``speaker_test`` runs the tracker over two real
reference recordings and reports how well they separated, including when they did not.
"""
import json
import logging
from pathlib import Path
import time
import wave

import numpy as np

from src.processors.diarization import SpeakerTracker, features
from src.vc import remote

log = logging.getLogger(__name__)
BLOCK_SECONDS = 0.25


def load_wav(path, target_rate=None):
    """Mono float32 from a PCM WAV file. Raises ValueError when it is not readable.

    The wave module answers a float-encoded export (the common DAW default), a
    truncated download and a renamed non-WAV with its own wave.Error/EOFError, which
    the callers here do not catch: the promise of this function is one error type.
    """
    try:
        with wave.open(str(path), 'rb') as handle:
            if handle.getsampwidth() != 2:
                raise ValueError(f'16-bit PCM WAV only: {Path(path).name}')
            rate = handle.getframerate()
            channels = handle.getnchannels()
            raw = handle.readframes(handle.getnframes())
            samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    except (wave.Error, EOFError) as error:
        raise ValueError(f'16-bit PCM WAV として読めません: {Path(path).name}') from error
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    if not samples.size:
        # A header-only WAV is readable but useless: cloning and diarization both
        # need samples, and an empty array travels far before it complains.
        raise ValueError(f'音声が入っていない WAV です: {Path(path).name}')
    if target_rate and rate != target_rate:
        index = np.linspace(0, samples.size - 1, max(1, round(samples.size * target_rate / rate)))
        samples = np.interp(index, np.arange(samples.size), samples).astype(np.float32)
    return rate, samples


def write_wav(path, audio, sample_rate):
    """Write 16-bit PCM. Returns the path."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(np.asarray(audio, dtype=np.float32).reshape(-1), -1.0, 1.0)
    with wave.open(str(path), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes((clipped * 32767.0).astype('<i2').tobytes())
    return path


MAX_BATCH_TEXTS = 32
MAX_BATCH_SECONDS = 180.0


def translate_batch(root, provider, voice, reference_path, texts, output_path,
                    sample_rate=48000, translator=None, gap_ms=300.0,
                    source='ja', target='en'):
    """Synthesize several translated lines into one WAV and report the timing.

    ``texts`` is a list of input lines; a single string is accepted as one line.
    Audio parts are joined with ``gap_ms`` of silence. No playback: the file is
    the deliverable and the timing is the measurement. Bounded: at most
    ``MAX_BATCH_TEXTS`` lines and ``MAX_BATCH_SECONDS`` of output.
    """
    from src.translate.providers import build_pipeline
    if isinstance(texts, str):
        lines = [texts]
    else:
        lines = list(texts or [])
    if len(lines) > MAX_BATCH_TEXTS:
        raise ValueError(f'Too many lines (at most {MAX_BATCH_TEXTS})')
    if not 0 <= gap_ms <= 2000:
        raise ValueError('Gap must be 0..2000 ms')
    reference = None
    if reference_path is not None:
        _, reference = load_wav(reference_path, sample_rate)
    pipeline, status = build_pipeline(root, provider, voice, reference, sample_rate,
                                      translator, source, target)
    started = time.perf_counter()
    translated_lines, parts = [], []
    for text in lines:
        translated, audio = pipeline.process(text, source, target, voice)
        translated_lines.append(translated)
        if np.asarray(audio, dtype=np.float32).size:
            parts.append(np.asarray(audio, dtype=np.float32).reshape(-1))
    elapsed = time.perf_counter() - started
    if not parts:
        return f'{status} · 音声が生成されませんでした（{len(lines)}件）'
    gap = np.zeros(max(0, round(gap_ms / 1000.0 * sample_rate)), dtype=np.float32)
    joined = parts[0]
    for part in parts[1:]:
        joined = np.concatenate((joined, gap, part)) if gap.size else np.concatenate((joined, part))
    seconds = joined.size / sample_rate
    if seconds > MAX_BATCH_SECONDS:
        raise ValueError(f'Translated audio too long ({seconds:.1f} s)')
    write_wav(output_path, joined, sample_rate)
    realtime = elapsed / seconds if seconds else 0.0
    preview = ' / '.join(repr(line) for line in translated_lines[:3])
    if len(translated_lines) > 3:
        preview += f' …他{len(translated_lines) - 3}件'
    return (f'{status} · {len(lines)}件 {preview} · {seconds:.2f}秒の音声を {elapsed:.2f}秒で生成'
            f'（RTF {realtime:.2f}）→ {Path(output_path).name}。再生と聴感は未確認です。')


def translate_test(root, provider, voice, reference_path, text, output_path,
                   sample_rate=48000, translator=None):
    """Synthesize one translated line and write it to ``output_path``.

    No playback: the file is the deliverable and the timing is the measurement.
    """
    return translate_batch(root, provider, voice, reference_path, [text], output_path,
                            sample_rate, translator)


def probe_worker(host, port, timeout=3.0):
    """One connection test against a LAN worker, reported as a sentence."""
    if not host:
        return 'ホストが未設定です。GPU機のIPかホスト名を入れてください。'
    client = remote.RemoteClient(host, port, timeout)
    try:
        with client:
            status = client.describe()
    except remote.RemoteError as error:
        return f'接続できません: {error}'
    if not status.available:
        return f'ワーカーが応答しません: {status.detail}'
    return f'{status.worker} に接続しました（protocol {status.version}）· {status.detail}'


def speaker_test(folder_a, folder_b, speakers=2, sample_rate=48000):
    """Run the speaker tracker over two reference recordings and report the split.

    Honest by construction: the numbers say how far apart the two voices actually
    were in the feature space, and a poor split is reported as a poor split.
    """
    reference = {}
    for label, folder in (('A', Path(folder_a)), ('B', Path(folder_b))):
        profile = json.loads((Path(folder) / 'profile.json').read_text(encoding='utf-8'))
        source = Path(folder) / profile['source_filename']
        rate, samples = load_wav(source, sample_rate)
        reference[label] = samples
    tracker = SpeakerTracker(speakers=speakers)
    labels = {}
    for label, samples in reference.items():
        frame = int(rate * BLOCK_SECONDS)
        found = []
        for start in range(0, max(1, samples.size - frame + 1), frame):
            pitch, centroid, _rms, voiced = features(samples[start:start + frame], rate)
            state = tracker.observe(pitch, centroid, voiced)
            if state.label is not None:
                found.append(state.label)
        labels[label] = found
        if not found:
            return f'{label} の参照音声からは声を検出できませんでした（囁き・無音・短すぎ）'
    dominant = {}
    purity = {}
    for label, found in labels.items():
        winner = max(set(found), key=found.count)
        dominant[label] = winner
        purity[label] = found.count(winner) / len(found)
    if dominant['A'] != dominant['B']:
        return (f'2つの声を別の話者として分離しました'
                f'（A→話者{dominant["A"]} {purity["A"]*100:.0f}%, '
                f'B→話者{dominant["B"]} {purity["B"]*100:.0f}%, '
                f'重心 {len(tracker._centroids)} 個）')
    return (f'分離できませんでした: どちらも話者{dominant["A"]}と判定されました'
            f'（A {purity["A"]*100:.0f}%, B {purity["B"]*100:.0f}%）。'
            '声の高さと明るさが近いと、この方式では区別できません。')
