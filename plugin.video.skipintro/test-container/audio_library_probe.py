#!/usr/bin/env python3
"""Probe audio fingerprint detection against episodes from a local Kodi library.

The script queries Kodi JSON-RPC for TV shows and episodes, maps Kodi library
paths to local filesystem paths when needed, then runs the real
AudioIntroDetector fingerprint backend on a bounded Arabic/English sample.
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import types
from collections import Counter


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARABIC_START = '\u0600'
ARABIC_END = '\u06ff'
LATIN_UPPER_START = 'A'
LATIN_UPPER_END = 'Z'
LATIN_LOWER_START = 'a'
LATIN_LOWER_END = 'z'


def install_kodi_mocks():
    class VfsFile:
        def __init__(self, path):
            self._handle = open(path, 'r', encoding='utf-8', errors='replace')

        def read(self):
            return self._handle.read()

        def close(self):
            self._handle.close()

    xbmc = types.SimpleNamespace(
        LOGDEBUG=0,
        LOGINFO=1,
        LOGERROR=2,
        LOGWARNING=3,
        log=lambda msg, level=1: None,
    )
    xbmcvfs = types.SimpleNamespace(
        translatePath=lambda path: path,
        listdir=lambda path: ([], []),
        File=VfsFile,
    )
    sys.modules.setdefault('xbmc', xbmc)
    sys.modules.setdefault('xbmcvfs', xbmcvfs)


def kodi_rpc(url, method, params=None):
    payload = {
        'jsonrpc': '2.0',
        'method': method,
        'id': 1,
    }
    if params is not None:
        payload['params'] = params

    result = subprocess.run(
        [
            'curl',
            '-sS',
            '-H', 'Content-Type: application/json',
            '--data', json.dumps(payload),
            url,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    data = json.loads(result.stdout)
    if 'error' in data:
        raise RuntimeError(f'Kodi JSON-RPC error calling {method}: {data["error"]}')
    return data.get('result', {})


def has_arabic(text):
    return any(ARABIC_START <= char <= ARABIC_END for char in text or '')


def has_latin(text):
    return any(
        (LATIN_UPPER_START <= char <= LATIN_UPPER_END) or
        (LATIN_LOWER_START <= char <= LATIN_LOWER_END)
        for char in text or ''
    )


def show_language_bucket(show, episodes=None):
    title = show.get('title', '')
    file_path = show.get('file', '')
    episode_text = ' '.join(
        f"{episode.get('title', '')} {episode.get('file', '')}"
        for episode in episodes or []
    )
    combined = f'{title} {file_path} {episode_text}'
    if has_arabic(combined):
        return 'arabic'
    if title.strip().lower() == 'unnamed':
        return None
    if has_latin(title) or has_latin(file_path):
        return 'english'
    return None


def map_kodi_path(path, mappings):
    for source, target in mappings:
        if path.startswith(source):
            return target + path[len(source):]
    return path


def parse_path_mappings(values):
    mappings = []
    for value in values:
        if '=' not in value:
            raise ValueError(f'Invalid path mapping {value!r}; expected source=target')
        source, target = value.split('=', 1)
        mappings.append((source, target))
    return mappings


def get_tvshows(args):
    result = kodi_rpc(
        args.kodi_url,
        'VideoLibrary.GetTVShows',
        {
            'properties': ['title', 'file', 'year'],
            'limits': {'start': 0, 'end': args.max_shows},
            'sort': {'method': 'title', 'order': 'ascending'},
        },
    )
    return result.get('tvshows', [])


def get_episodes(args, tvshowid):
    result = kodi_rpc(
        args.kodi_url,
        'VideoLibrary.GetEpisodes',
        {
            'tvshowid': tvshowid,
            'properties': ['title', 'file', 'season', 'episode', 'runtime'],
            'limits': {'start': 0, 'end': args.max_episodes_per_show},
            'sort': {'method': 'episode', 'order': 'ascending'},
        },
    )
    return result.get('episodes', [])


def is_existing_video(path):
    return path and os.path.exists(path) and os.path.isfile(path)


def load_sample_titles(args):
    titles = []
    if args.show_title:
        titles.extend(args.show_title)
    if args.sample_file:
        with open(args.sample_file, 'r', encoding='utf-8') as handle:
            for line in handle:
                title = line.strip()
                if title and not title.startswith('#'):
                    titles.append(title)
    return [title.strip().casefold() for title in titles if title.strip()]


def title_matches_sample(show, requested_titles):
    if not requested_titles:
        return True
    title = show.get('title', '').strip().casefold()
    return title in requested_titles


def select_sample(args, mappings):
    shows = get_tvshows(args)
    requested_titles = load_sample_titles(args)
    if args.sample_strategy == 'random':
        random.Random(args.seed).shuffle(shows)
    buckets = {language: [] for language in args.language}
    skipped = Counter()

    for show in shows:
        if not title_matches_sample(show, requested_titles):
            continue
        preliminary_bucket = show_language_bucket(show)
        if preliminary_bucket not in buckets:
            skipped['unclassified_language'] += 1
            continue
        if len(buckets[preliminary_bucket]) >= args.shows_per_language:
            continue

        episodes = get_episodes(args, show['tvshowid'])
        bucket = show_language_bucket(show, episodes)
        if bucket not in buckets:
            skipped['unclassified_language'] += 1
            continue
        if len(buckets[bucket]) >= args.shows_per_language:
            continue

        mapped_episodes = []
        for episode in episodes:
            mapped_path = map_kodi_path(episode.get('file', ''), mappings)
            if is_existing_video(mapped_path):
                item = dict(episode)
                item['mapped_file'] = mapped_path
                mapped_episodes.append(item)

        if len(mapped_episodes) < args.episodes_per_show:
            skipped[f'{bucket}:too_few_local_episodes'] += 1
            continue

        buckets[bucket].append({
            'bucket': bucket,
            'tvshowid': show['tvshowid'],
            'title': show.get('title', ''),
            'year': show.get('year'),
            'file': show.get('file', ''),
            'episodes': mapped_episodes[:args.episodes_per_show],
        })

        if all(len(items) >= args.shows_per_language for items in buckets.values()):
            break

    return buckets, skipped, len(shows)


def classify_failure(error):
    text = str(error)
    if 'ffprobe' in text:
        return 'ffprobe_failed'
    if 'ffmpeg' in text:
        return 'ffmpeg_failed'
    return 'detector_error'


def sanitize_probe_path(path):
    from resources.lib.metadata import sanitize_path

    return sanitize_path(path) if path else path


def sanitize_detection_result(detected):
    if not detected:
        return detected

    sanitized = dict(detected)
    for key in ('file', 'left_file', 'right_file'):
        if key in sanitized:
            sanitized[key] = sanitize_probe_path(sanitized[key])
    if 'episode_detections' in sanitized:
        sanitized['episode_detections'] = [
            dict(item, file=sanitize_probe_path(item.get('file')))
            for item in sanitized['episode_detections']
        ]
    if 'outro_detections' in sanitized:
        sanitized['outro_detections'] = [
            dict(item, file=sanitize_probe_path(item.get('file')))
            for item in sanitized['outro_detections']
        ]
    return sanitized


def sanitize_diagnostics(diagnostics):
    if not diagnostics:
        return diagnostics

    def sanitize_value(value):
        if isinstance(value, dict):
            sanitized = {}
            for key, item in value.items():
                if key in ('file', 'left_file', 'right_file', 'mapped_file'):
                    sanitized[key] = sanitize_probe_path(item)
                else:
                    sanitized[key] = sanitize_value(item)
            return sanitized
        if isinstance(value, list):
            return [sanitize_value(item) for item in value]
        return value

    return sanitize_value(diagnostics)


def load_ground_truth(args):
    if not args.ground_truth:
        return {}
    with open(args.ground_truth, 'r', encoding='utf-8') as handle:
        data = json.load(handle)
    return {str(title).casefold(): value for title, value in data.items()}


def ground_truth_for_show(show, ground_truth):
    return ground_truth.get(show['title'].strip().casefold())


def detection_accuracy(detected, ground_truth, tolerance):
    if not detected or not ground_truth:
        return None
    start = ground_truth.get('intro_start_time')
    end = ground_truth.get('intro_end_time')
    if start is None or end is None:
        return None
    start_delta = float(detected.get('intro_start_time', 0)) - float(start)
    end_delta = float(detected.get('intro_end_time', 0)) - float(end)
    return {
        'start_delta': round(start_delta, 3),
        'end_delta': round(end_delta, 3),
        'within_tolerance': abs(start_delta) <= tolerance and abs(end_delta) <= tolerance,
        'tolerance_seconds': tolerance,
    }


def run_detection(args, sample):
    from resources.lib.audio_intro import AudioIntroDetector

    detector = AudioIntroDetector(
        backend='fingerprint',
        max_scan_seconds=args.max_scan_seconds,
        max_episodes=args.max_detector_episodes or len(sample['episodes']),
        fingerprint_hop_seconds=args.hop_seconds,
        fingerprint_min_common_seconds=args.min_common_seconds,
        fingerprint_hamming_distance=args.hamming_distance,
        ffmpeg_path=args.ffmpeg,
        ffmpeg_timeout_seconds=args.ffmpeg_timeout_seconds,
    )
    if args.skip_outro:
        detector._detect_outro_by_fingerprint = lambda analyzed, ffmpeg: None
    files = [episode['mapped_file'] for episode in sample['episodes']]
    diagnostics = {} if args.include_diagnostics else None
    start = time.time()
    try:
        detected = detector.detect_show_intro(files, diagnostics=diagnostics)
    except Exception as error:
        result = {
            'status': 'error',
            'failure_reason': classify_failure(error),
            'error': str(error),
            'elapsed_seconds': round(time.time() - start, 3),
        }
        if diagnostics is not None:
            result['diagnostics'] = sanitize_diagnostics(diagnostics)
        return result

    if not detected:
        result = {
            'status': 'miss',
            'failure_reason': (
                diagnostics.get('failure_reason')
                if diagnostics and diagnostics.get('failure_reason')
                else 'no_common_fingerprint_match'
            ),
            'elapsed_seconds': round(time.time() - start, 3),
        }
        if diagnostics is not None:
            result['diagnostics'] = sanitize_diagnostics(diagnostics)
        return result

    result = {
        'status': 'hit',
        'detected': sanitize_detection_result(detected),
        'elapsed_seconds': round(time.time() - start, 3),
    }
    if diagnostics is not None:
        result['diagnostics'] = sanitize_diagnostics(diagnostics)
    return result


def summarize(results, languages):
    total = len(results)
    hits = sum(1 for item in results if item['status'] == 'hit')
    by_bucket = {}
    for bucket in languages:
        bucket_items = [item for item in results if item['bucket'] == bucket]
        bucket_hits = sum(1 for item in bucket_items if item['status'] == 'hit')
        by_bucket[bucket] = {
            'total': len(bucket_items),
            'hits': bucket_hits,
            'success_rate': bucket_hits / float(len(bucket_items)) if bucket_items else None,
            'failures': dict(Counter(
                item.get('failure_reason', item['status'])
                for item in bucket_items
                if item['status'] != 'hit'
            )),
        }
    return {
        'total': total,
        'hits': hits,
        'success_rate': hits / float(total) if total else None,
        'by_language': by_bucket,
        'failures': dict(Counter(
            item.get('failure_reason', item['status'])
            for item in results
            if item['status'] != 'hit'
        )),
    }


def main(argv):
    parser = argparse.ArgumentParser(description='Probe SkipIntro audio detection against a Kodi TV library')
    parser.add_argument('--kodi-url', default='http://127.0.0.1:8080/jsonrpc')
    parser.add_argument(
        '--path-map',
        action='append',
        default=[],
        help='source=target path mapping, e.g. smb://nas/share/=/mnt/share/',
    )
    parser.add_argument('--language', action='append', choices=('arabic', 'english'))
    parser.add_argument('--sample-strategy', choices=('alphabetical', 'random', 'from-file'), default='alphabetical')
    parser.add_argument('--seed', type=int, default=1)
    parser.add_argument('--sample-file', help='UTF-8 file containing one show title per line')
    parser.add_argument('--show-title', action='append', help='Exact show title to include; can be repeated')
    parser.add_argument('--shows-per-language', type=int, default=3)
    parser.add_argument('--episodes-per-show', type=int, default=3)
    parser.add_argument('--max-detector-episodes', type=int, default=None)
    parser.add_argument('--max-shows', type=int, default=4000)
    parser.add_argument('--max-episodes-per-show', type=int, default=12)
    parser.add_argument('--max-scan-seconds', type=int, default=120)
    parser.add_argument('--min-common-seconds', type=int, default=30)
    parser.add_argument('--hamming-distance', type=int, default=16)
    parser.add_argument('--hop-seconds', type=float, default=1.0)
    parser.add_argument('--ffmpeg', default=shutil.which('ffmpeg') or 'ffmpeg')
    parser.add_argument('--ffmpeg-timeout-seconds', type=int, default=180)
    parser.add_argument('--skip-outro', action='store_true', help='Probe intro success without tail/outro scanning')
    parser.add_argument('--include-diagnostics', action='store_true', help='Include detector candidate diagnostics')
    parser.add_argument('--ground-truth', help='JSON file mapping show titles to intro_start_time/intro_end_time')
    parser.add_argument('--ground-truth-tolerance', type=float, default=5.0)
    parser.add_argument('--output', help='Write JSON results to this path instead of stdout')
    args = parser.parse_args(argv)
    if not args.language:
        args.language = ['arabic', 'english']
    args.language = list(dict.fromkeys(args.language))
    if args.sample_strategy == 'from-file' and not args.sample_file:
        parser.error('--sample-strategy from-file requires --sample-file')

    install_kodi_mocks()
    sys.path.insert(0, REPO_ROOT)

    mappings = parse_path_mappings(args.path_map)
    ground_truth = load_ground_truth(args)
    sample, skipped, scanned_shows = select_sample(args, mappings)
    selected = []
    for language in args.language:
        selected.extend(sample.get(language, []))

    results = []
    for show in selected:
        outcome = run_detection(args, show)
        truth = ground_truth_for_show(show, ground_truth)
        result = {
            'bucket': show['bucket'],
            'tvshowid': show['tvshowid'],
            'title': show['title'],
            'year': show['year'],
            'episode_count': len(show['episodes']),
            'episodes': [
                {
                    'season': episode.get('season'),
                    'episode': episode.get('episode'),
                    'title': episode.get('title'),
                    'file': sanitize_probe_path(episode.get('file')),
                    'mapped_file': sanitize_probe_path(episode.get('mapped_file')),
                }
                for episode in show['episodes']
            ],
        }
        result.update(outcome)
        if truth:
            result['ground_truth'] = truth
            result['accuracy'] = detection_accuracy(
                result.get('detected'),
                truth,
                args.ground_truth_tolerance
            )
        results.append(result)

    payload = {
        'parameters': {
            'shows_per_language': args.shows_per_language,
            'episodes_per_show': args.episodes_per_show,
            'max_detector_episodes': args.max_detector_episodes,
            'max_scan_seconds': args.max_scan_seconds,
            'min_common_seconds': args.min_common_seconds,
            'hamming_distance': args.hamming_distance,
            'hop_seconds': args.hop_seconds,
            'ffmpeg_timeout_seconds': args.ffmpeg_timeout_seconds,
            'skip_outro': args.skip_outro,
            'languages': args.language,
            'sample_strategy': args.sample_strategy,
            'seed': args.seed,
            'sample_file': args.sample_file,
            'show_titles': args.show_title or [],
            'include_diagnostics': args.include_diagnostics,
            'ground_truth': args.ground_truth,
            'ground_truth_tolerance': args.ground_truth_tolerance,
            'path_mappings': mappings,
        },
        'scanned_show_count': scanned_shows,
        'selection_skips': dict(skipped),
        'summary': summarize(results, args.language),
        'results': results,
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as handle:
            handle.write(output)
            handle.write('\n')
    else:
        print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
