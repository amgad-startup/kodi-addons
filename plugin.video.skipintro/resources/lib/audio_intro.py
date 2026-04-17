import os
import shutil
import subprocess
import tempfile
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import xbmc
import xbmcvfs

from resources.lib.metadata import sanitize_path


VIDEO_EXTENSIONS = ('.mkv', '.mp4', '.avi', '.mov', '.m4v', '.webm', '.ts', '.strm')
SPEECH_LABELS = {'speech', 'male', 'female'}
MUSIC_LABELS = {'music'}
SILENCE_LABELS = {'noise', 'noenergy', 'silence'}

DEFAULT_SCAN_SECONDS = 10 * 60
DEFAULT_MAX_EPISODES = 3
DEFAULT_MIN_MUSIC_SECONDS = 2 * 60
DEFAULT_MIN_SPEECH_SECONDS = 12
DEFAULT_EPISODE_TOLERANCE_SECONDS = 25


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
        max_episodes: int = DEFAULT_MAX_EPISODES,
        min_music_seconds: int = DEFAULT_MIN_MUSIC_SECONDS,
        min_speech_seconds: int = DEFAULT_MIN_SPEECH_SECONDS,
        episode_tolerance_seconds: int = DEFAULT_EPISODE_TOLERANCE_SECONDS,
        ffmpeg_path: Optional[str] = None,
        segmenter_factory: Optional[Callable[[], Callable[[str], Iterable[Tuple[str, float, float]]]]] = None,
    ):
        self.max_scan_seconds = max_scan_seconds
        self.max_episodes = max_episodes
        self.min_music_seconds = min_music_seconds
        self.min_speech_seconds = min_speech_seconds
        self.episode_tolerance_seconds = episode_tolerance_seconds
        self.ffmpeg_path = ffmpeg_path
        self._segmenter_factory = segmenter_factory
        self._segmenter = None

    def detect_show_intro(self, episode_files: Sequence[str]) -> Optional[Dict[str, float]]:
        """Analyze a few episodes and return a show-level intro estimate."""
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
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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

        return output_path

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
