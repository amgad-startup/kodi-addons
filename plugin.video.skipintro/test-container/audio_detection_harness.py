#!/usr/bin/env python3
"""Synthetic harness for the context-menu audio auto-detection flow.

This does not require Kodi. It creates deterministic MKV fixtures with a shared
intro audio block, runs the same candidate discovery and fingerprint detector
used by context.py, and exits non-zero if the detected boundary is off.
"""

import argparse
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import wave


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_RATE = 16000
WINDOW_SECONDS = 2
AMPLITUDE = 12000


def install_kodi_mocks():
    xbmc = types.SimpleNamespace(
        LOGDEBUG=0,
        LOGINFO=1,
        LOGERROR=2,
        LOGWARNING=3,
        log=lambda msg, level=1: None,
    )

    def listdir(path):
        dirs = []
        files = []
        for entry in os.listdir(path):
            full_path = os.path.join(path, entry)
            if os.path.isdir(full_path):
                dirs.append(entry)
            else:
                files.append(entry)
        return dirs, files

    xbmcvfs = types.SimpleNamespace(
        translatePath=lambda path: path,
        listdir=listdir,
    )
    sys.modules.setdefault('xbmc', xbmc)
    sys.modules.setdefault('xbmcvfs', xbmcvfs)


def random_window(seed, sample_count):
    rng = random.Random(seed)
    return [rng.randint(-AMPLITUDE, AMPLITUDE) for _ in range(sample_count)]


def tone_window(frequency, sample_count):
    samples = []
    for index in range(sample_count):
        t = index / float(SAMPLE_RATE)
        samples.append(int(math.sin(2 * math.pi * frequency * t) * AMPLITUDE))
    return samples


def append_noise_windows(samples, seconds, seed_prefix):
    window_samples = SAMPLE_RATE * WINDOW_SECONDS
    windows = int(seconds // WINDOW_SECONDS)
    for window in range(windows):
        samples.extend(random_window(f'{seed_prefix}-{window}', window_samples))


def append_tone_remainder(samples, seconds, frequency):
    remainder = seconds % WINDOW_SECONDS
    if remainder:
        samples.extend(tone_window(frequency, int(SAMPLE_RATE * remainder)))


def write_fixture_wav(path, episode_index, cold_open_seconds, intro_seconds, body_seconds):
    samples = []
    append_noise_windows(samples, cold_open_seconds, f'cold-{episode_index}')
    append_tone_remainder(samples, cold_open_seconds, 220 + episode_index * 30)

    # The intro block is byte-identical across episodes, which is what the
    # production fingerprint matcher is expected to recover.
    append_noise_windows(samples, intro_seconds, 'shared-intro')
    append_tone_remainder(samples, intro_seconds, 440)

    append_noise_windows(samples, body_seconds, f'body-{episode_index}')
    append_tone_remainder(samples, body_seconds, 660 + episode_index * 40)

    with wave.open(path, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(b''.join(struct.pack('<h', sample) for sample in samples))


def convert_wav_to_mkv(ffmpeg, wav_path, mkv_path):
    subprocess.run(
        [
            ffmpeg,
            '-y',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', wav_path,
            '-c:a', 'pcm_s16le',
            mkv_path,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def build_fixtures(directory, ffmpeg, episodes, cold_open_seconds, intro_seconds, body_seconds):
    paths = []
    if isinstance(cold_open_seconds, (list, tuple)):
        cold_open_values = list(cold_open_seconds)
    else:
        cold_open_values = [cold_open_seconds] * episodes

    for index in range(1, episodes + 1):
        cold_open = cold_open_values[index - 1] if index - 1 < len(cold_open_values) else cold_open_values[-1]
        wav_path = os.path.join(directory, f'Harness.Show.S01E{index:02d}.wav')
        mkv_path = os.path.join(directory, f'Harness.Show.S01E{index:02d}.mkv')
        write_fixture_wav(wav_path, index, cold_open, intro_seconds, body_seconds)
        convert_wav_to_mkv(ffmpeg, wav_path, mkv_path)
        paths.append(mkv_path)
    return paths


def parse_seconds_list(value):
    return [float(part.strip()) for part in str(value).split(',') if part.strip()]


def run_detection(args, workdir, cold_open_seconds, intro_seconds, body_seconds):
    from resources.lib.audio_intro import AudioIntroDetector

    ffmpeg = args.ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg was not found in PATH')

    episodes = len(cold_open_seconds) if isinstance(cold_open_seconds, list) else args.episodes
    paths = build_fixtures(
        workdir,
        ffmpeg,
        episodes,
        cold_open_seconds,
        intro_seconds,
        body_seconds,
    )

    detector = AudioIntroDetector(
        backend='fingerprint',
        max_scan_seconds=args.max_scan_seconds,
        fingerprint_window_seconds=WINDOW_SECONDS,
        fingerprint_hop_seconds=args.hop_seconds,
        fingerprint_min_common_seconds=args.min_common_seconds,
        fingerprint_hamming_distance=args.hamming_distance,
        ffmpeg_path=ffmpeg,
    )
    candidates = detector.find_episode_candidates(paths[0])
    result = detector.detect_show_intro(candidates)
    expected_start = sorted(cold_open_seconds if isinstance(cold_open_seconds, list) else [cold_open_seconds] * episodes)[episodes // 2]

    return {
        'paths': paths,
        'candidates': candidates,
        'expected': {
            'intro_start_time': float(expected_start),
            'intro_end_time': float(expected_start + intro_seconds),
        },
        'detected': result,
    }


def is_detection_close(result, expected, tolerance):
    if not result:
        return False
    start_delta = abs(result.get('intro_start_time', -9999) - expected['intro_start_time'])
    end_delta = abs(result.get('intro_end_time', -9999) - expected['intro_end_time'])
    return start_delta <= tolerance and end_delta <= tolerance


def run_single_harness(args):
    install_kodi_mocks()
    sys.path.insert(0, REPO_ROOT)

    ffmpeg = args.ffmpeg or shutil.which('ffmpeg')
    if not ffmpeg:
        raise RuntimeError('ffmpeg was not found in PATH')

    keep_fixtures = args.keep_dir is not None
    workdir = args.keep_dir or tempfile.mkdtemp(prefix='skipintro-audio-harness-')
    os.makedirs(workdir, exist_ok=True)
    try:
        cold_open_seconds = parse_seconds_list(args.cold_open_seconds)
        if len(cold_open_seconds) == 1:
            cold_open_seconds = cold_open_seconds[0]
        detection = run_detection(
            args,
            workdir,
            cold_open_seconds,
            args.intro_seconds,
            args.body_seconds,
        )

        payload = {
            'workdir': workdir,
            'fixtures_kept': keep_fixtures,
            'candidates': detection['candidates'],
            'expected': detection['expected'],
            'detected': detection['detected'],
        }
        print(json.dumps(payload, indent=2, sort_keys=True))

        return 0 if is_detection_close(detection['detected'], detection['expected'], args.tolerance) else 1
    finally:
        if not keep_fixtures:
            shutil.rmtree(workdir, ignore_errors=True)


def run_matrix(args):
    install_kodi_mocks()
    sys.path.insert(0, REPO_ROOT)

    cases = [
        {
            'name': 'baseline_exact_offsets',
            'cold_open_seconds': [12, 12, 12],
            'intro_seconds': 48,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'offset_by_one_second',
            'cold_open_seconds': [11, 12, 13],
            'intro_seconds': 48,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'offset_by_two_seconds',
            'cold_open_seconds': [10, 12, 14],
            'intro_seconds': 48,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'fractional_offsets_half_second',
            'cold_open_seconds': [10.0, 10.5, 11.0],
            'intro_seconds': 48,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'fractional_offsets_mixed',
            'cold_open_seconds': [10.25, 11.0, 11.75],
            'intro_seconds': 48,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'minimum_30_second_intro',
            'cold_open_seconds': [12, 12, 12],
            'intro_seconds': 30,
            'body_seconds': 150,
            'expect_detection': True,
        },
        {
            'name': 'below_threshold_24_second_intro',
            'cold_open_seconds': [12, 12, 12],
            'intro_seconds': 24,
            'body_seconds': 150,
            'expect_detection': False,
        },
        {
            'name': 'long_cold_open_still_first_third',
            'cold_open_seconds': [60, 62, 64],
            'intro_seconds': 48,
            'body_seconds': 240,
            'expect_detection': True,
        },
        {
            'name': 'short_episode_intro_past_first_third',
            'cold_open_seconds': [12, 12, 12],
            'intro_seconds': 48,
            'body_seconds': 60,
            'expect_detection': False,
        },
    ]

    results = []
    positive_cases = 0
    positive_hits = 0
    expectation_matches = 0

    for case in cases:
        workdir = tempfile.mkdtemp(prefix=f"skipintro-audio-{case['name']}-")
        try:
            detection = run_detection(
                args,
                workdir,
                case['cold_open_seconds'],
                case['intro_seconds'],
                case['body_seconds'],
            )
            detected = detection['detected']
            close = is_detection_close(detected, detection['expected'], args.tolerance)
            hit = bool(detected) and close
            if case['expect_detection']:
                positive_cases += 1
                if hit:
                    positive_hits += 1
            expectation_matched = hit if case['expect_detection'] else detected is None
            if expectation_matched:
                expectation_matches += 1

            results.append({
                'name': case['name'],
                'cold_open_seconds': case['cold_open_seconds'],
                'intro_seconds': case['intro_seconds'],
                'body_seconds': case['body_seconds'],
                'expect_detection': case['expect_detection'],
                'expected': detection['expected'],
                'detected': detected,
                'hit': hit,
                'expectation_matched': expectation_matched,
            })
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    payload = {
        'hop_seconds': args.hop_seconds,
        'window_seconds': WINDOW_SECONDS,
        'min_common_seconds': args.min_common_seconds,
        'hamming_distance': args.hamming_distance,
        'positive_success_rate': positive_hits / float(positive_cases) if positive_cases else None,
        'expectation_success_rate': expectation_matches / float(len(cases)),
        'positive_hits': positive_hits,
        'positive_cases': positive_cases,
        'expectation_matches': expectation_matches,
        'total_cases': len(cases),
        'results': results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if args.strict:
        return 0 if expectation_matches == len(cases) else 1
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description='Run synthetic SkipIntro audio detection harness')
    parser.add_argument('--matrix', action='store_true', help='Run a synthetic success-rate matrix')
    parser.add_argument('--strict', action='store_true', help='Return non-zero when a matrix expectation fails')
    parser.add_argument('--episodes', type=int, default=3)
    parser.add_argument('--cold-open-seconds', default='12')
    parser.add_argument('--intro-seconds', type=int, default=48)
    parser.add_argument('--body-seconds', type=int, default=150)
    parser.add_argument('--max-scan-seconds', type=int, default=120)
    parser.add_argument('--min-common-seconds', type=int, default=30)
    parser.add_argument('--hamming-distance', type=int, default=16)
    parser.add_argument('--hop-seconds', type=float, default=1.0)
    parser.add_argument('--tolerance', type=float, default=2.0)
    parser.add_argument('--ffmpeg')
    parser.add_argument('--keep-dir')
    return parser.parse_args(argv)


if __name__ == '__main__':
    parsed_args = parse_args(sys.argv[1:])
    if parsed_args.matrix:
        raise SystemExit(run_matrix(parsed_args))
    raise SystemExit(run_single_harness(parsed_args))
