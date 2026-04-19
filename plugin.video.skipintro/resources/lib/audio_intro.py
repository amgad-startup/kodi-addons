import array
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import xbmc
import xbmcvfs

from resources.lib.metadata import sanitize_path


VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm', '.ts', '.strm')
SPEECH_LABELS = {'speech', 'male', 'female'}
MUSIC_LABELS = {'music'}
SILENCE_LABELS = {'noise', 'noenergy', 'silence'}

DEFAULT_SCAN_SECONDS = 10 * 60
DEFAULT_MAX_EPISODES = 3
DEFAULT_FINGERPRINT_MAX_EPISODES = 5
DEFAULT_MIN_MUSIC_SECONDS = 2 * 60
DEFAULT_MIN_SPEECH_SECONDS = 12
DEFAULT_EPISODE_TOLERANCE_SECONDS = 25
DEFAULT_FINGERPRINT_SAMPLE_RATE = 8000
DEFAULT_FINGERPRINT_WINDOW_SECONDS = 2
DEFAULT_FINGERPRINT_HOP_SECONDS = 1.0
DEFAULT_FINGERPRINT_MIN_COMMON_SECONDS = 30
DEFAULT_FINGERPRINT_MIN_OUTRO_SECONDS = 30
DEFAULT_FINGERPRINT_HAMMING_DISTANCE = 16
DEFAULT_INTRO_LIMIT_RATIO = 1.0 / 3.0
DEFAULT_OUTRO_SEARCH_RATIO = 2.0 / 3.0
DEFAULT_FFMPEG_TIMEOUT_SECONDS = 180
FINGERPRINT_BITS = 64
FINGERPRINT_BUCKETS = FINGERPRINT_BITS // 2
PCM_SAMPLE_WIDTH_BYTES = 2


class AudioIntroDetectionError(Exception):
    """Raised when audio intro detection cannot run."""


class AudioIntroDependencyError(AudioIntroDetectionError):
    """Raised when a required external audio detection dependency is missing."""


class AudioIntroDetector:
    """Detect show intro times from music-to-dialogue audio segmentation.

    The primary backend is inaSpeechSegmenter, loaded lazily so the addon can
    still run on Kodi installs that do not have the optional ML dependency.
    """

    def __init__(
        self,
        max_scan_seconds: int = DEFAULT_SCAN_SECONDS,
        max_episodes: Optional[int] = None,
        min_music_seconds: int = DEFAULT_MIN_MUSIC_SECONDS,
        min_speech_seconds: int = DEFAULT_MIN_SPEECH_SECONDS,
        episode_tolerance_seconds: int = DEFAULT_EPISODE_TOLERANCE_SECONDS,
        ffmpeg_path: Optional[str] = None,
        backend: str = 'segments',
        fingerprint_sample_rate: int = DEFAULT_FINGERPRINT_SAMPLE_RATE,
        fingerprint_window_seconds: int = DEFAULT_FINGERPRINT_WINDOW_SECONDS,
        fingerprint_hop_seconds: float = DEFAULT_FINGERPRINT_HOP_SECONDS,
        fingerprint_min_common_seconds: int = DEFAULT_FINGERPRINT_MIN_COMMON_SECONDS,
        fingerprint_min_outro_seconds: int = DEFAULT_FINGERPRINT_MIN_OUTRO_SECONDS,
        fingerprint_hamming_distance: int = DEFAULT_FINGERPRINT_HAMMING_DISTANCE,
        intro_limit_ratio: float = DEFAULT_INTRO_LIMIT_RATIO,
        outro_search_ratio: float = DEFAULT_OUTRO_SEARCH_RATIO,
        ffmpeg_timeout_seconds: int = DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        segmenter_factory: Optional[Callable[[], Callable[[str], Iterable[Tuple[str, float, float]]]]] = None,
    ):
        self.max_scan_seconds = max_scan_seconds
        if max_episodes is None:
            max_episodes = DEFAULT_FINGERPRINT_MAX_EPISODES if backend == 'fingerprint' else DEFAULT_MAX_EPISODES
        self.max_episodes = max_episodes
        self.min_music_seconds = min_music_seconds
        self.min_speech_seconds = min_speech_seconds
        self.episode_tolerance_seconds = episode_tolerance_seconds
        self.ffmpeg_path = ffmpeg_path
        self.backend = backend
        self.fingerprint_sample_rate = fingerprint_sample_rate
        self.fingerprint_window_seconds = fingerprint_window_seconds
        self.fingerprint_hop_seconds = fingerprint_hop_seconds
        self.fingerprint_min_common_seconds = fingerprint_min_common_seconds
        self.fingerprint_min_outro_seconds = fingerprint_min_outro_seconds
        self.fingerprint_hamming_distance = fingerprint_hamming_distance
        self.intro_limit_ratio = intro_limit_ratio
        self.outro_search_ratio = outro_search_ratio
        self.ffmpeg_timeout_seconds = ffmpeg_timeout_seconds
        self._segmenter_factory = segmenter_factory
        self._segmenter = None

    def detect_show_intro(
        self,
        episode_files: Sequence[str],
        diagnostics: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, float]]:
        """Analyze a few episodes and return a show-level intro estimate."""
        if self.backend == 'fingerprint':
            return self.detect_show_intro_by_fingerprint(episode_files, diagnostics=diagnostics)

        detections = []
        for episode_file in episode_files[:self.max_episodes]:
            try:
                detected = self.analyze_file(episode_file)
            except AudioIntroDependencyError:
                raise
            except AudioIntroDetectionError as e:
                xbmc.log(f'SkipIntro: Audio intro detection skipped {sanitize_path(episode_file)}: {str(e)}', xbmc.LOGWARNING)
                continue
            except Exception as e:
                xbmc.log(f'SkipIntro: Audio intro detection failed for {sanitize_path(episode_file)}: {str(e)}', xbmc.LOGWARNING)
                continue

            if detected:
                detected = dict(detected)
                detected['file'] = episode_file
                detections.append(detected)

        if not detections:
            return None

        intro_ends = sorted(d['intro_end_time'] for d in detections)
        median_end = intro_ends[len(intro_ends) // 2]
        matching = [
            d for d in detections
            if abs(d['intro_end_time'] - median_end) <= self.episode_tolerance_seconds
        ]
        if not matching:
            matching = detections

        start_times = sorted(d.get('intro_start_time', 0) for d in matching)
        end_times = sorted(d['intro_end_time'] for d in matching)

        return {
            'intro_start_time': start_times[len(start_times) // 2],
            'intro_end_time': end_times[len(end_times) // 2],
            'episode_count': len(detections),
            'matching_episode_count': len(matching),
            'episode_detections': detections,
            'source': 'audio'
        }

    def detect_show_intro_by_fingerprint(
        self,
        episode_files: Sequence[str],
        diagnostics: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, float]]:
        """Find common intro audio across episodes using lightweight fingerprints."""
        ffmpeg = self._find_ffmpeg()
        analyzed = []
        if diagnostics is not None:
            diagnostics.clear()
            diagnostics.update({
                'parameters': {
                    'max_scan_seconds': self.max_scan_seconds,
                    'max_episodes': self.max_episodes,
                    'fingerprint_window_seconds': self.fingerprint_window_seconds,
                    'fingerprint_hop_seconds': self.fingerprint_hop_seconds,
                    'fingerprint_min_common_seconds': self.fingerprint_min_common_seconds,
                    'fingerprint_hamming_distance': self.fingerprint_hamming_distance,
                    'intro_limit_ratio': self.intro_limit_ratio,
                },
                'episodes': [],
                'pairs': [],
                'rejection_counts': {},
                'status': 'running',
            })

        for episode_file in episode_files[:self.max_episodes]:
            try:
                duration = self._probe_duration(episode_file)
                fingerprints = self._fingerprint_file(episode_file, ffmpeg)
            except AudioIntroDependencyError:
                raise
            except AudioIntroDetectionError as e:
                xbmc.log(f'SkipIntro: Audio fingerprint detection skipped {sanitize_path(episode_file)}: {str(e)}', xbmc.LOGWARNING)
                continue
            except Exception as e:
                xbmc.log(f'SkipIntro: Audio fingerprint detection failed for {sanitize_path(episode_file)}: {str(e)}', xbmc.LOGWARNING)
                continue

            if fingerprints:
                analyzed.append({
                    'file': episode_file,
                    'duration': duration,
                    'fingerprints': fingerprints
                })
                if diagnostics is not None:
                    diagnostics['episodes'].append({
                        'file': sanitize_path(episode_file),
                        'duration': duration,
                        'fingerprints': self._fingerprint_series_summary(fingerprints),
                    })

        if len(analyzed) < 2:
            if diagnostics is not None:
                diagnostics['status'] = 'miss'
                diagnostics['failure_reason'] = 'insufficient_analyzed_episodes'
                diagnostics['analyzed_episode_count'] = len(analyzed)
            return None

        best = None
        best_rejected = None
        for left_index in range(len(analyzed)):
            for right_index in range(left_index + 1, len(analyzed)):
                pair_diagnostics = None
                if diagnostics is not None:
                    pair_diagnostics = {
                        'left_index': left_index,
                        'right_index': right_index,
                        'left_file': sanitize_path(str(analyzed[left_index]['file'])),
                        'right_file': sanitize_path(str(analyzed[right_index]['file'])),
                        'rejection_counts': {},
                        'top_candidates': [],
                    }
                pair_match = self._find_common_fingerprint_run(
                    analyzed[left_index]['fingerprints'],
                    analyzed[right_index]['fingerprints'],
                    left_max_end=self._intro_end_limit(analyzed[left_index].get('duration')),
                    right_max_end=self._intro_end_limit(analyzed[right_index].get('duration')),
                    diagnostics=pair_diagnostics
                )
                if diagnostics is not None:
                    if pair_match:
                        pair_diagnostics['best_in_bounds'] = self._fingerprint_candidate_summary(pair_match)
                    elif pair_diagnostics.get('matching_window_count', 0) == 0:
                        pair_diagnostics['failure_reason'] = 'no_matching_fingerprints'
                    elif pair_diagnostics.get('candidate_count', 0) == 0:
                        pair_diagnostics['failure_reason'] = 'no_positive_duration_candidates'
                    elif pair_diagnostics['rejection_counts']:
                        pair_diagnostics['failure_reason'] = 'all_candidates_rejected'
                    else:
                        pair_diagnostics['failure_reason'] = 'no_candidate'
                if not pair_match:
                    if diagnostics is not None:
                        diagnostics['pairs'].append(pair_diagnostics)
                    continue

                duration = self._fingerprint_threshold_duration(pair_match)
                if duration < self.fingerprint_min_common_seconds:
                    if diagnostics is not None:
                        pair_diagnostics['failure_reason'] = 'below_min_common_seconds'
                        pair_diagnostics['selected_rejection'] = 'below_min_common_seconds'
                        pair_diagnostics['selected_threshold_duration'] = duration
                    if self._is_better_fingerprint_match(pair_match, best_rejected):
                        best_rejected = dict(pair_match)
                    if diagnostics is not None:
                        diagnostics['pairs'].append(pair_diagnostics)
                    continue

                if self._is_better_fingerprint_match(pair_match, best):
                    best = dict(pair_match)
                    best['left_file'] = analyzed[left_index]['file']
                    best['right_file'] = analyzed[right_index]['file']
                    if diagnostics is not None:
                        pair_diagnostics['selected'] = True
                if diagnostics is not None:
                    diagnostics['pairs'].append(pair_diagnostics)

        if not best:
            if best_rejected:
                xbmc.log(
                    'SkipIntro: Audio fingerprint found common audio '
                    f'({best_rejected["duration"]:.1f}s) shorter than minimum '
                    f'{self.fingerprint_min_common_seconds:.1f}s',
                    xbmc.LOGINFO
                )
            if diagnostics is not None:
                diagnostics['status'] = 'miss'
                diagnostics['failure_reason'] = self._fingerprint_failure_reason(diagnostics, best_rejected)
                diagnostics['best_rejected'] = (
                    self._fingerprint_candidate_summary(best_rejected)
                    if best_rejected else None
                )
                diagnostics['rejection_counts'] = self._aggregate_pair_rejections(diagnostics.get('pairs', []))
            return None

        detections = [
            {
                'file': best['left_file'],
                'intro_start_time': best['left_start_time'],
                'intro_end_time': best['left_end_time'],
                'match_duration': best['duration'],
                'source': 'audio_fingerprint'
            },
            {
                'file': best['right_file'],
                'intro_start_time': best['right_start_time'],
                'intro_end_time': best['right_end_time'],
                'match_duration': best['duration'],
                'source': 'audio_fingerprint'
            }
        ]
        start_times = sorted(d['intro_start_time'] for d in detections)
        end_times = sorted(d['intro_end_time'] for d in detections)
        outro = self._detect_outro_by_fingerprint(analyzed, ffmpeg)

        result = {
            'intro_start_time': start_times[len(start_times) // 2],
            'intro_end_time': end_times[len(end_times) // 2],
            'outro_start_time': None,
            'episode_count': len(analyzed),
            'matching_episode_count': len(detections),
            'episode_detections': detections,
            'match_duration': best['duration'],
            'source': 'audio_fingerprint'
        }
        if outro:
            result['outro_start_time'] = outro['outro_start_time']
            result['outro_match_duration'] = outro['duration']
            result['outro_detections'] = outro['detections']
        if diagnostics is not None:
            diagnostics['status'] = 'hit'
            diagnostics['failure_reason'] = None
            diagnostics['best_match'] = self._fingerprint_candidate_summary(best)
            diagnostics['rejection_counts'] = self._aggregate_pair_rejections(diagnostics.get('pairs', []))
        return result

    def _detect_outro_by_fingerprint(self, analyzed: List[Dict[str, object]], ffmpeg: str) -> Optional[Dict[str, object]]:
        tail_analyzed = []
        for item in analyzed:
            duration = item.get('duration')
            if not duration:
                continue

            tail_duration = min(self.max_scan_seconds, float(duration))
            tail_start = max(0.0, float(duration) - tail_duration)
            try:
                fingerprints = self._fingerprint_file(
                    str(item['file']),
                    ffmpeg,
                    start_seconds=tail_start,
                    scan_seconds=tail_duration,
                    base_time=tail_start
                )
            except AudioIntroDetectionError as e:
                xbmc.log(f'SkipIntro: Audio outro fingerprint detection skipped {sanitize_path(str(item["file"]))}: {str(e)}', xbmc.LOGWARNING)
                continue
            except Exception as e:
                xbmc.log(f'SkipIntro: Audio outro fingerprint detection failed for {sanitize_path(str(item["file"]))}: {str(e)}', xbmc.LOGWARNING)
                continue

            if fingerprints:
                tail_analyzed.append({
                    'file': item['file'],
                    'duration': duration,
                    'fingerprints': fingerprints
                })

        if len(tail_analyzed) < 2:
            return None

        best = None
        for left_index in range(len(tail_analyzed)):
            for right_index in range(left_index + 1, len(tail_analyzed)):
                left_duration = float(tail_analyzed[left_index]['duration'])
                right_duration = float(tail_analyzed[right_index]['duration'])
                pair_match = self._find_common_fingerprint_run(
                    tail_analyzed[left_index]['fingerprints'],
                    tail_analyzed[right_index]['fingerprints'],
                    left_min_start=left_duration * self.outro_search_ratio,
                    right_min_start=right_duration * self.outro_search_ratio
                )
                if not pair_match:
                    continue
                if self._fingerprint_threshold_duration(pair_match) < self.fingerprint_min_outro_seconds:
                    continue
                if self._is_better_outro_match(pair_match, best):
                    best = dict(pair_match)
                    best['left_file'] = tail_analyzed[left_index]['file']
                    best['right_file'] = tail_analyzed[right_index]['file']

        if not best:
            return None

        detections = [
            {
                'file': best['left_file'],
                'outro_start_time': best['left_start_time'],
                'outro_end_time': best['left_end_time'],
                'match_duration': best['duration'],
                'source': 'audio_fingerprint'
            },
            {
                'file': best['right_file'],
                'outro_start_time': best['right_start_time'],
                'outro_end_time': best['right_end_time'],
                'match_duration': best['duration'],
                'source': 'audio_fingerprint'
            }
        ]
        start_times = sorted(d['outro_start_time'] for d in detections)
        return {
            'outro_start_time': start_times[len(start_times) // 2],
            'duration': best['duration'],
            'detections': detections
        }

    def analyze_file(self, video_path: str) -> Optional[Dict[str, float]]:
        """Extract a short audio clip and detect the intro boundary."""
        ffmpeg = self._find_ffmpeg()
        wav_path = self._extract_audio_clip(video_path, ffmpeg)
        try:
            segments = self._segment_audio(wav_path)
            return self.detect_intro_from_segments(segments)
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def detect_intro_from_segments(self, segments: Iterable[Tuple[str, float, float]]) -> Optional[Dict[str, float]]:
        """Find a long music run followed by dialogue/speech."""
        normalized = self._normalize_segments(segments)
        if not normalized:
            return None

        intro_start = None
        music_seconds = 0.0

        for label, start, end in normalized:
            duration = max(0.0, end - start)
            if self._is_music(label):
                if intro_start is None:
                    intro_start = start
                music_seconds += duration
                continue

            if intro_start is None:
                continue

            if self._is_silence(label):
                continue

            if self._is_speech(label) and music_seconds >= self.min_music_seconds:
                speech_seconds = self._speech_seconds_from(normalized, start)
                if speech_seconds >= self.min_speech_seconds:
                    return {
                        'intro_start_time': intro_start,
                        'intro_end_time': start,
                        'music_seconds': music_seconds,
                        'speech_seconds_after': speech_seconds,
                        'source': 'audio'
                    }

            # A substantial non-music segment before enough music means this
            # was probably not the intro block. Start looking again.
            if duration >= self.min_speech_seconds:
                intro_start = None
                music_seconds = 0.0

        return None

    def find_episode_candidates(self, selected_path: str) -> List[str]:
        """Return selected episode plus nearby video files from the same folder."""
        if selected_path.endswith(('/', '\\')):
            directory = selected_path
            selected_name = ''
        else:
            directory, selected_name = self._split_path(selected_path)
        if not directory:
            return [selected_path]

        try:
            _dirs, files = xbmcvfs.listdir(directory)
        except Exception as e:
            xbmc.log(f'SkipIntro: Could not list episode folder {sanitize_path(directory)}: {str(e)}', xbmc.LOGWARNING)
            return [selected_path]

        candidates = []
        for filename in sorted(files, key=lambda value: value.lower()):
            if filename.lower().endswith(VIDEO_EXTENSIONS):
                candidates.append(self._join_path(directory, filename))

        if not candidates:
            return [selected_path]

        selected_basename = selected_name.lower()
        selected_index = 0
        for index, candidate in enumerate(candidates):
            if self._basename(candidate).lower() == selected_basename:
                selected_index = index
                break

        window = candidates[selected_index:selected_index + self.max_episodes]
        if len(window) < self.max_episodes:
            needed = self.max_episodes - len(window)
            prefix = candidates[max(0, selected_index - needed):selected_index]
            window = prefix + window

        if selected_name and selected_path not in window:
            window.insert(0, selected_path)

        return window[:self.max_episodes]

    def _segment_audio(self, wav_path: str):
        segmenter = self._get_segmenter()
        return segmenter(wav_path)

    def _get_segmenter(self):
        if self._segmenter is not None:
            return self._segmenter

        if self._segmenter_factory:
            self._segmenter = self._segmenter_factory()
            return self._segmenter

        self._patch_numpy_for_inaspeechsegmenter()
        try:
            from inaSpeechSegmenter import Segmenter
        except Exception as e:
            raise AudioIntroDependencyError(
                'inaSpeechSegmenter is required for audio intro detection. '
                'Install it with pip in the Kodi Python environment.'
            ) from e

        self._segmenter = Segmenter(vad_engine='smn', detect_gender=False)
        return self._segmenter

    @staticmethod
    def _patch_numpy_for_inaspeechsegmenter():
        """Keep older inaSpeechSegmenter/pyannote code running on modern NumPy."""
        # Compatibility shim for offline venv testing; inaSpeechSegmenter is
        # too heavy for Kodi's embedded Python in normal addon usage.
        try:
            import numpy as np
        except Exception:
            return

        if not hasattr(np.lib, 'pad') and hasattr(np, 'pad'):
            np.lib.pad = np.pad

        if getattr(np, '_skipintro_stack_sequence_patch', False):
            return

        original_stack = np.stack
        original_vstack = np.vstack
        original_hstack = np.hstack

        def coerce_sequence(values):
            if isinstance(values, (list, tuple)):
                return values
            return list(values)

        def stack(values, *args, **kwargs):
            return original_stack(coerce_sequence(values), *args, **kwargs)

        def vstack(values, *args, **kwargs):
            return original_vstack(coerce_sequence(values), *args, **kwargs)

        def hstack(values, *args, **kwargs):
            return original_hstack(coerce_sequence(values), *args, **kwargs)

        np.stack = stack
        np.vstack = vstack
        np.hstack = hstack
        np._skipintro_stack_sequence_patch = True

    def _extract_audio_clip(self, video_path: str, ffmpeg: str) -> str:
        fd, output_path = tempfile.mkstemp(prefix='skipintro-audio-', suffix='.wav')
        os.close(fd)

        input_path = self._resolve_input_path(video_path)
        command = [
            ffmpeg,
            '-y',
            '-hide_banner',
            '-loglevel', 'error',
            '-i', input_path,
            '-t', str(self.max_scan_seconds),
            '-vn',
            '-ac', '1',
            '-ar', '16000',
            '-f', 'wav',
            output_path,
        ]

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.ffmpeg_timeout_seconds
            )
        except subprocess.CalledProcessError as e:
            try:
                os.unlink(output_path)
            except OSError:
                pass
            error = e.stderr.decode('utf-8', errors='replace').strip()
            if input_path:
                error = error.replace(input_path, '[input]')
            raise AudioIntroDetectionError(
                f'ffmpeg could not extract audio from {sanitize_path(video_path)}: {error}'
            ) from e
        except subprocess.TimeoutExpired as e:
            try:
                os.unlink(output_path)
            except OSError:
                pass
            raise AudioIntroDetectionError(
                f'ffmpeg timed out extracting audio from {sanitize_path(video_path)} '
                f'after {self.ffmpeg_timeout_seconds} seconds'
            ) from e

        return output_path

    def _fingerprint_file(
        self,
        video_path: str,
        ffmpeg: str,
        start_seconds: Optional[float] = None,
        scan_seconds: Optional[float] = None,
        base_time: float = 0.0
    ) -> List[Dict[str, float]]:
        pcm = self._extract_pcm_clip(video_path, ffmpeg, start_seconds=start_seconds, scan_seconds=scan_seconds)
        return self._fingerprint_pcm(pcm, base_time=base_time)

    def _extract_pcm_clip(
        self,
        video_path: str,
        ffmpeg: str,
        start_seconds: Optional[float] = None,
        scan_seconds: Optional[float] = None
    ) -> bytes:
        input_path = self._resolve_input_path(video_path)
        command = [
            ffmpeg,
            '-nostdin',
            '-hide_banner',
            '-loglevel', 'error',
        ]
        if start_seconds is not None and start_seconds > 0:
            command.extend(['-ss', str(round(float(start_seconds), 3))])
        command.extend([
            '-i', input_path,
            '-t', str(round(float(scan_seconds if scan_seconds is not None else self.max_scan_seconds), 3)),
            '-vn',
            '-ac', '1',
            '-ar', str(self.fingerprint_sample_rate),
            '-f', 's16le',
            '-',
        ])

        try:
            result = subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.ffmpeg_timeout_seconds
            )
        except subprocess.CalledProcessError as e:
            error = e.stderr.decode('utf-8', errors='replace').strip()
            if input_path:
                error = error.replace(input_path, '[input]')
            raise AudioIntroDetectionError(
                f'ffmpeg could not extract fingerprint audio from {sanitize_path(video_path)}: {error}'
            ) from e
        except subprocess.TimeoutExpired as e:
            raise AudioIntroDetectionError(
                f'ffmpeg timed out extracting fingerprint audio from {sanitize_path(video_path)} '
                f'after {self.ffmpeg_timeout_seconds} seconds'
            ) from e

        return result.stdout

    def _fingerprint_pcm(self, pcm: bytes, base_time: float = 0.0) -> List[Dict[str, float]]:
        if not pcm:
            return []

        sample_data = pcm[:len(pcm) - (len(pcm) % PCM_SAMPLE_WIDTH_BYTES)]
        samples = array.array('h')
        samples.frombytes(sample_data)
        if sys.byteorder != 'little':
            samples.byteswap()

        window_size = int(self.fingerprint_sample_rate * self.fingerprint_window_seconds)
        hop_size = int(self.fingerprint_sample_rate * self.fingerprint_hop_seconds)
        if window_size <= 0 or hop_size <= 0 or len(samples) < window_size:
            return []

        fingerprints = []
        for start in range(0, len(samples) - window_size + 1, hop_size):
            window = samples[start:start + window_size]
            fingerprint_hash, rms = self._fingerprint_window(window)
            fingerprints.append({
                'time': float(base_time) + start / float(self.fingerprint_sample_rate),
                'hash': fingerprint_hash,
                'rms': rms
            })
        return fingerprints

    @staticmethod
    def _fingerprint_window(window: Sequence[int]) -> Tuple[Optional[int], float]:
        if not window:
            return None, 0.0

        rms = (sum(int(sample) * int(sample) for sample in window) / float(len(window))) ** 0.5
        if rms <= 1:
            return None, rms

        bucket_size = max(1, len(window) // FINGERPRINT_BUCKETS)
        energies = []
        crossings = []
        for bucket_index in range(FINGERPRINT_BUCKETS):
            start = bucket_index * bucket_size
            end = len(window) if bucket_index == FINGERPRINT_BUCKETS - 1 else min(len(window), start + bucket_size)
            if start >= end:
                break

            previous = int(window[start])
            crossing_count = 0
            absolute_sum = 0
            for sample in window[start:end]:
                sample = int(sample)
                absolute_sum += abs(sample)
                if (previous < 0 <= sample) or (previous >= 0 > sample):
                    crossing_count += 1
                previous = sample

            size = float(end - start)
            energies.append(absolute_sum / size)
            crossings.append(crossing_count / size)

        if not energies:
            return None, rms

        average_energy = sum(energies) / len(energies)
        average_crossings = sum(crossings) / len(crossings)
        if average_energy <= 1:
            return None, rms

        fingerprint_hash = 0
        for index, energy in enumerate(energies):
            if energy >= average_energy:
                fingerprint_hash |= 1 << index

        offset = len(energies)
        for index, crossing_rate in enumerate(crossings):
            if crossing_rate >= average_crossings:
                fingerprint_hash |= 1 << (offset + index)

        return fingerprint_hash, rms

    def _find_common_fingerprint_run(
        self,
        left: List[Dict[str, float]],
        right: List[Dict[str, float]],
        left_min_start: Optional[float] = None,
        right_min_start: Optional[float] = None,
        left_max_end: Optional[float] = None,
        right_max_end: Optional[float] = None,
        diagnostics: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, float]]:
        best = None
        previous_runs = {}
        matching_window_count = 0
        candidate_count = 0
        rejection_counts = {}

        for left_index, left_item in enumerate(left):
            current_runs = {}
            left_hash = left_item.get('hash')
            if left_hash is None:
                previous_runs = {}
                continue

            for right_index, right_item in enumerate(right):
                right_hash = right_item.get('hash')
                if right_hash is None:
                    continue

                distance = self._hamming_distance(int(left_hash), int(right_hash))
                if distance > self.fingerprint_hamming_distance:
                    continue
                matching_window_count += 1

                previous = previous_runs.get(right_index - 1)
                if previous:
                    length = previous['length'] + 1
                    distance_total = previous['distance_total'] + distance
                else:
                    length = 1
                    distance_total = distance

                run = {
                    'length': length,
                    'distance_total': distance_total,
                    'left_end_index': left_index,
                    'right_end_index': right_index
                }
                current_runs[right_index] = run

                left_start_index = left_index - length + 1
                right_start_index = right_index - length + 1
                left_hop = self._fingerprint_run_hop(left, left_start_index, left_index)
                right_hop = self._fingerprint_run_hop(right, right_start_index, right_index)
                edge_trim = max(0.0, float(self.fingerprint_window_seconds) - min(left_hop, right_hop))
                left_start_time = left[left_start_index]['time'] + edge_trim
                left_end_time = left[left_index]['time'] + left_hop
                right_start_time = right[right_start_index]['time'] + edge_trim
                right_end_time = right[right_index]['time'] + right_hop
                duration = min(left_end_time - left_start_time, right_end_time - right_start_time)
                raw_left_end_time = left[left_index]['time'] + self.fingerprint_window_seconds
                raw_right_end_time = right[right_index]['time'] + self.fingerprint_window_seconds
                raw_left_start_time = left[left_start_index]['time']
                raw_right_start_time = right[right_start_index]['time']
                raw_duration = min(
                    raw_left_end_time - raw_left_start_time,
                    raw_right_end_time - raw_right_start_time
                )
                if duration <= 0:
                    continue
                candidate_count += 1
                candidate = {
                    'duration': duration,
                    'raw_duration': raw_duration,
                    'left_start_time': left_start_time,
                    'left_end_time': left_end_time,
                    'raw_left_start_time': raw_left_start_time,
                    'raw_left_end_time': raw_left_end_time,
                    'right_start_time': right_start_time,
                    'right_end_time': right_end_time,
                    'raw_right_start_time': raw_right_start_time,
                    'raw_right_end_time': raw_right_end_time,
                    'average_distance': distance_total / float(length),
                    'start_spread': abs(left_start_time - right_start_time)
                }
                rejection_reasons = self._fingerprint_match_bounds_reasons(
                    candidate,
                    left_min_start=left_min_start,
                    right_min_start=right_min_start,
                    left_max_end=left_max_end,
                    right_max_end=right_max_end
                )
                if rejection_reasons:
                    for reason in rejection_reasons:
                        rejection_counts[reason] = rejection_counts.get(reason, 0) + 1
                    self._record_fingerprint_candidate(diagnostics, candidate, rejection_reasons[0])
                    continue
                self._record_fingerprint_candidate(diagnostics, candidate, None)
                if self._is_better_fingerprint_match(candidate, best):
                    best = candidate

            previous_runs = current_runs

        if diagnostics is not None:
            diagnostics['matching_window_count'] = matching_window_count
            diagnostics['candidate_count'] = candidate_count
            diagnostics['rejection_counts'] = rejection_counts
        return best

    def _fingerprint_run_hop(self, fingerprints: List[Dict[str, float]], start_index: int, end_index: int) -> float:
        for index in range(start_index + 1, end_index + 1):
            delta = fingerprints[index]['time'] - fingerprints[index - 1]['time']
            if delta > 0:
                return float(delta)
        return float(self.fingerprint_hop_seconds or self.fingerprint_window_seconds)

    @staticmethod
    def _fingerprint_threshold_duration(match: Dict[str, float]) -> float:
        return float(max(match.get('duration', 0), match.get('raw_duration', 0)))

    @staticmethod
    def _fingerprint_match_bounds_reasons(
        match: Dict[str, float],
        left_min_start: Optional[float] = None,
        right_min_start: Optional[float] = None,
        left_max_end: Optional[float] = None,
        right_max_end: Optional[float] = None
    ) -> List[str]:
        reasons = []
        if left_min_start is not None and match['left_start_time'] < left_min_start:
            reasons.append('left_start_before_min')
        if left_min_start is not None and match.get('raw_left_start_time', match['left_start_time']) < left_min_start:
            reasons.append('raw_left_start_before_min')
        if right_min_start is not None and match['right_start_time'] < right_min_start:
            reasons.append('right_start_before_min')
        if right_min_start is not None and match.get('raw_right_start_time', match['right_start_time']) < right_min_start:
            reasons.append('raw_right_start_before_min')
        if left_max_end is not None and match['left_end_time'] > left_max_end:
            reasons.append('left_end_after_max')
        if left_max_end is not None and match.get('raw_left_end_time', match['left_end_time']) > left_max_end:
            reasons.append('raw_left_end_after_max')
        if right_max_end is not None and match['right_end_time'] > right_max_end:
            reasons.append('right_end_after_max')
        if right_max_end is not None and match.get('raw_right_end_time', match['right_end_time']) > right_max_end:
            reasons.append('raw_right_end_after_max')
        return reasons

    @staticmethod
    def _fingerprint_match_in_bounds(
        match: Dict[str, float],
        left_min_start: Optional[float] = None,
        right_min_start: Optional[float] = None,
        left_max_end: Optional[float] = None,
        right_max_end: Optional[float] = None
    ) -> bool:
        return not AudioIntroDetector._fingerprint_match_bounds_reasons(
            match,
            left_min_start=left_min_start,
            right_min_start=right_min_start,
            left_max_end=left_max_end,
            right_max_end=right_max_end
        )

    def _fingerprint_candidate_summary(
        self,
        match: Optional[Dict[str, float]],
        rejection_reason: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        if not match:
            return None
        summary = {
            'duration': round(float(match.get('duration', 0)), 3),
            'raw_duration': round(float(match.get('raw_duration', 0)), 3),
            'threshold_duration': round(self._fingerprint_threshold_duration(match), 3),
            'duration_bucket': self._fingerprint_duration_bucket(match),
            'left_start_time': round(float(match.get('left_start_time', 0)), 3),
            'left_end_time': round(float(match.get('left_end_time', 0)), 3),
            'right_start_time': round(float(match.get('right_start_time', 0)), 3),
            'right_end_time': round(float(match.get('right_end_time', 0)), 3),
            'start_spread': round(float(match.get('start_spread', 0)), 3),
            'average_distance': round(float(match.get('average_distance', 0)), 3),
        }
        if rejection_reason:
            summary['rejection_reason'] = rejection_reason
        return summary

    def _record_fingerprint_candidate(
        self,
        diagnostics: Optional[Dict[str, Any]],
        candidate: Dict[str, float],
        rejection_reason: Optional[str]
    ) -> None:
        if diagnostics is None:
            return
        top_candidates = diagnostics.setdefault('top_candidates', [])
        top_candidates.append(self._fingerprint_candidate_summary(candidate, rejection_reason))
        top_candidates.sort(
            key=lambda item: (
                item.get('threshold_duration', 0),
                -item.get('start_spread', 0),
                -item.get('average_distance', 0)
            ),
            reverse=True
        )
        del top_candidates[8:]

    @staticmethod
    def _fingerprint_duration_bucket(match: Dict[str, float]) -> str:
        duration = AudioIntroDetector._fingerprint_threshold_duration(match)
        if duration < 15:
            return 'too_short'
        if duration < 45:
            return 'short'
        if duration < 120:
            return 'normal'
        if duration <= 180:
            return 'long'
        return 'suspicious'

    @staticmethod
    def _fingerprint_series_summary(fingerprints: List[Dict[str, float]]) -> Dict[str, Any]:
        rms_values = [float(item.get('rms', 0) or 0) for item in fingerprints]
        valid_hash_count = sum(1 for item in fingerprints if item.get('hash') is not None)
        if not rms_values:
            return {
                'window_count': 0,
                'valid_hash_count': 0,
                'missing_hash_count': 0,
                'quiet_window_count': 0,
            }
        sorted_rms = sorted(rms_values)
        return {
            'window_count': len(fingerprints),
            'valid_hash_count': valid_hash_count,
            'missing_hash_count': len(fingerprints) - valid_hash_count,
            'quiet_window_count': sum(1 for value in rms_values if value <= 1),
            'rms_min': round(sorted_rms[0], 3),
            'rms_median': round(sorted_rms[len(sorted_rms) // 2], 3),
            'rms_max': round(sorted_rms[-1], 3),
            'rms_average': round(sum(rms_values) / float(len(rms_values)), 3),
        }

    @staticmethod
    def _aggregate_pair_rejections(pairs: List[Dict[str, Any]]) -> Dict[str, int]:
        aggregate = {}
        for pair in pairs:
            for reason, count in pair.get('rejection_counts', {}).items():
                aggregate[reason] = aggregate.get(reason, 0) + int(count)
            selected_rejection = pair.get('selected_rejection')
            if selected_rejection:
                aggregate[selected_rejection] = aggregate.get(selected_rejection, 0) + 1
        return aggregate

    @staticmethod
    def _fingerprint_failure_reason(
        diagnostics: Dict[str, Any],
        best_rejected: Optional[Dict[str, float]]
    ) -> str:
        pairs = diagnostics.get('pairs', [])
        if not pairs:
            return 'no_episode_pairs'
        if best_rejected:
            return 'below_min_common_seconds'
        if all(pair.get('matching_window_count', 0) == 0 for pair in pairs):
            return 'no_matching_fingerprints'
        if all(pair.get('candidate_count', 0) == 0 for pair in pairs):
            return 'no_positive_duration_candidates'
        if any(pair.get('rejection_counts') for pair in pairs):
            return 'all_candidates_rejected'
        return 'no_common_fingerprint_match'

    @staticmethod
    def _is_better_fingerprint_match(candidate: Dict[str, float], current: Optional[Dict[str, float]]) -> bool:
        if not current:
            return True
        if candidate['duration'] != current['duration']:
            return candidate['duration'] > current['duration']
        if candidate.get('start_spread', 0) != current.get('start_spread', 0):
            return candidate.get('start_spread', 0) < current.get('start_spread', 0)
        return candidate.get('average_distance', 0) < current.get('average_distance', 0)

    @staticmethod
    def _is_better_outro_match(candidate: Dict[str, float], current: Optional[Dict[str, float]]) -> bool:
        if not current:
            return True
        if candidate['duration'] != current['duration']:
            return candidate['duration'] > current['duration']
        if candidate.get('start_spread', 0) != current.get('start_spread', 0):
            return candidate.get('start_spread', 0) < current.get('start_spread', 0)
        candidate_start = min(candidate.get('left_start_time', 0), candidate.get('right_start_time', 0))
        current_start = min(current.get('left_start_time', 0), current.get('right_start_time', 0))
        if candidate_start != current_start:
            return candidate_start > current_start
        return candidate.get('average_distance', 0) < current.get('average_distance', 0)

    def _intro_end_limit(self, duration: Optional[float]) -> Optional[float]:
        if not duration:
            return None
        return float(duration) * self.intro_limit_ratio

    def _probe_duration(self, video_path: str) -> Optional[float]:
        ffprobe = self._find_ffprobe()
        if not ffprobe:
            xbmc.log('SkipIntro: ffprobe not found; intro/outro audio bounds will be limited to scanned audio only', xbmc.LOGWARNING)
            return None

        input_path = self._resolve_input_path(video_path)
        command = [
            ffprobe,
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            input_path,
        ]

        try:
            result = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            duration = float(result.stdout.decode('utf-8', errors='replace').strip())
        except subprocess.TimeoutExpired:
            xbmc.log(
                f'SkipIntro: Could not probe duration for {sanitize_path(video_path)}: '
                'ffprobe timed out after 30 seconds',
                xbmc.LOGWARNING
            )
            return None
        except subprocess.CalledProcessError as e:
            error = ''
            if e.stderr:
                error = e.stderr.decode('utf-8', errors='replace').strip()
                error = error.replace(input_path, '[input]')
            if not error:
                error = f'ffprobe exited with status {e.returncode}'
            xbmc.log(f'SkipIntro: Could not probe duration for {sanitize_path(video_path)}: {error}', xbmc.LOGWARNING)
            return None
        except (TypeError, ValueError):
            xbmc.log(
                f'SkipIntro: Could not probe duration for {sanitize_path(video_path)}: invalid duration output',
                xbmc.LOGWARNING
            )
            return None

        if duration <= 0:
            return None
        return duration

    @staticmethod
    def _hamming_distance(left: int, right: int) -> int:
        return bin(left ^ right).count('1')

    def _find_ffprobe(self) -> Optional[str]:
        if self.ffmpeg_path:
            ffmpeg_dir = os.path.dirname(self.ffmpeg_path)
            ffprobe_name = 'ffprobe.exe' if os.path.basename(self.ffmpeg_path).lower().endswith('.exe') else 'ffprobe'
            ffprobe_path = os.path.join(ffmpeg_dir, ffprobe_name)
            if os.path.exists(ffprobe_path):
                return ffprobe_path

        return shutil.which('ffprobe')

    def _find_ffmpeg(self) -> str:
        if self.ffmpeg_path:
            return self.ffmpeg_path

        ffmpeg = shutil.which('ffmpeg')
        if ffmpeg:
            return ffmpeg

        raise AudioIntroDependencyError('ffmpeg is required for audio intro detection but was not found in PATH.')

    @staticmethod
    def _normalize_segments(segments: Iterable[Tuple[str, float, float]]) -> List[Tuple[str, float, float]]:
        normalized = []
        for segment in segments:
            if len(segment) < 3:
                continue
            label, start, end = segment[0], segment[1], segment[2]
            try:
                start = float(start)
                end = float(end)
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue
            normalized.append((str(label).lower(), start, end))
        return sorted(normalized, key=lambda item: item[1])

    def _speech_seconds_from(self, segments: List[Tuple[str, float, float]], start_time: float) -> float:
        speech_seconds = 0.0
        for label, start, end in segments:
            if end <= start_time:
                continue
            if start > start_time + self.min_speech_seconds * 3:
                break
            if self._is_speech(label):
                speech_seconds += end - max(start, start_time)
                if speech_seconds >= self.min_speech_seconds:
                    return speech_seconds
            elif not self._is_silence(label):
                break
        return speech_seconds

    @staticmethod
    def _is_music(label: str) -> bool:
        return label.lower() in MUSIC_LABELS

    @staticmethod
    def _is_speech(label: str) -> bool:
        return label.lower() in SPEECH_LABELS

    @staticmethod
    def _is_silence(label: str) -> bool:
        return label.lower() in SILENCE_LABELS

    def _resolve_input_path(self, path: str) -> str:
        native_path = self._to_native_path(path)
        if self._is_strm_path(path) or self._is_strm_path(native_path):
            stream_path = self._read_strm_target(native_path)
            if not stream_path:
                raise AudioIntroDetectionError(f'No playable stream URL found in {sanitize_path(path)}')
            xbmc.log('SkipIntro: Resolved .strm episode for audio intro detection', xbmc.LOGDEBUG)
            return stream_path

        if native_path.startswith(('smb://', 'nfs://')):
            xbmc.log('SkipIntro: Network path may not be supported by ffmpeg audio detection', xbmc.LOGWARNING)

        return native_path

    @staticmethod
    def _to_native_path(path: str) -> str:
        if path.startswith('special://'):
            return xbmcvfs.translatePath(path)
        return path

    @staticmethod
    def _is_strm_path(path: str) -> bool:
        return path.lower().endswith('.strm')

    @staticmethod
    def _read_strm_target(path: str) -> Optional[str]:
        handle = None
        try:
            handle = xbmcvfs.File(path)
            content = handle.read()
        except Exception as e:
            raise AudioIntroDetectionError(f'Could not read .strm file {sanitize_path(path)}: {str(e)}') from e
        finally:
            if handle is not None:
                try:
                    handle.close()
                except Exception:
                    pass

        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='replace')
        else:
            content = str(content or '')

        for line in content.splitlines():
            line = line.lstrip('\ufeff').strip()
            if line and not line.startswith('#'):
                return line
        return None

    @staticmethod
    def _split_path(path: str) -> Tuple[str, str]:
        slash = max(path.rfind('/'), path.rfind('\\'))
        if slash < 0:
            return '', path
        return path[:slash + 1], path[slash + 1:]

    @staticmethod
    def _join_path(directory: str, filename: str) -> str:
        if directory.endswith(('/', '\\')):
            return directory + filename
        return directory + '/' + filename

    @staticmethod
    def _basename(path: str) -> str:
        return path.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
