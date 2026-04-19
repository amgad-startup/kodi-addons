import os
import time
import threading

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.settings import Settings
from resources.lib.chapters import ChapterManager
from resources.lib.ui import PlayerUI
from resources.lib.database import ShowDatabase
from resources.lib.metadata import ShowMetadata, sanitize_path
from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector, VIDEO_EXTENSIONS

addon = xbmcaddon.Addon()

# Constants
CHAPTER_WAIT_MS = 3000  # Additional wait for chapters to be available (3 seconds)
MONITOR_INTERVAL_SEC = 0.5  # How often to check playback state (500ms)
AUTO_AUDIO_DETECTION_MIN_WATCH_SECONDS = 60
AUTO_AUDIO_DETECTION_TRIGGER_EPISODES = 2
AUDIO_DETECTION_INITIAL_SCAN_SECONDS = 90
AUDIO_DETECTION_FALLBACK_SCAN_SECONDS = 180

_audio_detection_lock = threading.Lock()
_audio_detection_running_shows = set()

def get_database():
    """Initialize and return database connection"""
    try:
        db_path = 'special://userdata/addon_data/plugin.video.skipintro/shows.db'

        # Ensure directory exists
        translated_path = xbmcvfs.translatePath(db_path)
        db_dir = os.path.dirname(translated_path)
        if not xbmcvfs.exists(db_dir):
            xbmcvfs.mkdirs(db_dir)

        return ShowDatabase(translated_path)
    except Exception as e:
        xbmc.log('SkipIntro: Error initializing database: {}'.format(str(e)), xbmc.LOGERROR)
        return None

class SkipIntroPlayer(xbmc.Player):
    def __init__(self):
        super(SkipIntroPlayer, self).__init__()
        self.intro_start = None
        self.intro_duration = None
        self.intro_bookmark = None
        self.outro_bookmark = None
        self.bookmarks_checked = False
        self.prompt_shown = False
        self.show_info = None
        self.db = get_database()
        self.metadata = ShowMetadata()
        self.ui = PlayerUI()
        self.show_from_start = False  # Flag for chapter-only mode
        self.has_config = False  # Track if show has saved configuration
        self._skip_to_chapter = None  # Chapter number for network-file seek
        self._playing_file = None
        self._max_playback_time = 0
        self._playback_chapters = []

        # Initialize settings
        self.settings_manager = Settings()
        self.settings = self.settings_manager.settings

        # Timing control variables
        self.timer_active = False
        self.next_check_time = 0
        self.warning_timer_active = False
        self.warning_check_time = 0
        self.dismiss_timer_active = False
        self.dismiss_check_time = 0

        # Thread safety lock for timer operations
        self._timer_lock = threading.Lock()

    def onPlayBackStopped(self):
        """Called when playback is stopped by user"""
        self._record_watched_episode_for_audio_detection(force=False)
        self.cleanup()

    def onPlayBackEnded(self):
        """Called when playback ends naturally"""
        self._record_watched_episode_for_audio_detection(force=True)
        self.cleanup()

    def onPlayBackStarted(self):
        """Called when Kodi starts playing a file"""
        xbmc.log('SkipIntro: Playback started', xbmc.LOGINFO)
        self.cleanup()  # Reset state for new playback

    def _wait_for_video_info(self, timeout_ms=5000, interval_ms=500):
        """Poll until Kodi video info labels are available or timeout."""
        elapsed = 0
        while elapsed < timeout_ms:
            if not self.isPlaying():
                return False
            title = xbmc.getInfoLabel('VideoPlayer.TVShowTitle')
            filename = None
            try:
                filename = self.getPlayingFile()
            except Exception:
                pass
            if title or filename:
                return True
            xbmc.sleep(interval_ms)
            elapsed += interval_ms
        return self.isPlaying()

    def onAVStarted(self):
        """Called when Kodi has prepared audio/video for the file"""
        xbmc.log('SkipIntro: AV started', xbmc.LOGINFO)
        # Reset flags for new video
        self.bookmarks_checked = False
        self.prompt_shown = False
        self.timer_active = False
        self.next_check_time = 0
        self.warning_timer_active = False
        self.warning_check_time = 0
        self.dismiss_timer_active = False
        self.dismiss_check_time = 0
        self.show_from_start = False
        self.has_config = False
        self._skip_to_chapter = None
        self._playing_file = None
        self._max_playback_time = 0
        self._playback_chapters = []

        # Wait for video info to become available (up to 5s, polls every 500ms)
        if not self._wait_for_video_info():
            return

        self.detect_show()
        try:
            self._playing_file = self.getPlayingFile()
        except Exception:
            self._playing_file = None

        if self.show_info:
            # Check saved times immediately (no wait needed for time-based config)
            self.check_saved_times()

            # Wait for chapters if we still need to resolve markers
            if not self.intro_bookmark:
                needs_chapters = True
                # Check if we need chapter data for the saved config
                if self.has_config:
                    show_id = self.db.get_show(self.show_info['title'])
                    if show_id:
                        config = self.db.get_show_config(show_id)
                        if config and config.get('use_chapters'):
                            needs_chapters = True
                        elif config and (config.get('intro_start_time') or config.get('intro_end_time')):
                            needs_chapters = False  # Time-based config already tried

                if needs_chapters:
                    xbmc.log('SkipIntro: Waiting for chapters to load...', xbmc.LOGINFO)
                    xbmc.sleep(CHAPTER_WAIT_MS)
                    if not self.isPlaying():
                        return

                    # Retry chapter-based config if applicable
                    if self.has_config and not self.intro_bookmark:
                        show_id = self.db.get_show(self.show_info['title'])
                        if show_id:
                            config = self.db.get_show_config(show_id)
                            if config and config.get('use_chapters'):
                                xbmc.log('SkipIntro: Loading chapter-based markers', xbmc.LOGINFO)
                                self.set_chapter_based_markers(config)

                    # Try autodetect if still no markers
                    if not self.intro_bookmark:
                        self._try_autodetect()

            # No intro bookmark found - skip detection will not be active
            if not self.intro_bookmark:
                xbmc.log('SkipIntro: No intro times found for this show', xbmc.LOGINFO)
            self.bookmarks_checked = True

            # If we have intro times, set up the timer
            if self.intro_bookmark is not None:
                # Reload settings to get latest values from UI
                self.settings = self.settings_manager.validate_settings()

                current_time = self.getTime()
                pre_skip_seconds = self.settings.get('pre_skip_seconds', 3)
                delay_autoskip = self.settings.get('delay_autoskip', 0)

                if self.show_from_start:
                    # Intro starts at 0 - show button from start, skip immediately (or after delay)
                    self.warning_check_time = 0
                    self.warning_timer_active = True
                    # Skip at intro_start (0) + delay, not at intro_end!
                    self.next_check_time = self.intro_start + delay_autoskip
                    self.timer_active = True
                    xbmc.log(f'SkipIntro: Timer set to show warning from start and skip at {self.next_check_time} (intro_start: {self.intro_start}, delay: {delay_autoskip}s)', xbmc.LOGINFO)
                elif self.intro_start is not None and current_time < self.intro_start:
                    # Calculate actual skip time with delay
                    actual_skip_time = self.intro_start + delay_autoskip

                    # Calculate warning time (show notification X seconds before skip)
                    self.warning_check_time = max(0, actual_skip_time - pre_skip_seconds)
                    self.next_check_time = actual_skip_time

                    # Activate warning timer if we haven't passed warning time
                    if current_time < self.warning_check_time:
                        self.warning_timer_active = True
                        xbmc.log(f'SkipIntro: Warning timer set for {self.warning_check_time}, skip timer set for {self.next_check_time} (intro starts at {self.intro_start}, delay: {delay_autoskip}s)', xbmc.LOGINFO)
                    else:
                        # Already past warning time, just set skip timer
                        self.timer_active = True
                        xbmc.log(f'SkipIntro: Skip timer set for {self.next_check_time} (intro starts at {self.intro_start}, delay: {delay_autoskip}s)', xbmc.LOGINFO)

                elif current_time < self.intro_bookmark:
                    # Already in intro period, show warning or skip immediately
                    warning_time = max(0, self.intro_bookmark - pre_skip_seconds)
                    if current_time < warning_time:
                        # Show warning
                        seconds_until_skip = int(self.intro_bookmark - current_time)
                        self.ui.show_skip_warning(seconds_until_skip)
                        self.warning_timer_active = False
                        # Set timer for actual skip
                        self.next_check_time = self.intro_bookmark
                        self.timer_active = True
                    else:
                        # Skip immediately
                        self.show_skip_button()

    def onPlayBackTime(self, time):
        """Called during playback with current time"""
        if time is not None and time > self._max_playback_time:
            self._max_playback_time = time

        # Use lock to prevent race conditions
        with self._timer_lock:
            # Check warning timer first - show the button dialog
            if self.warning_timer_active and time >= self.warning_check_time:
                xbmc.log(f'SkipIntro: Warning timer triggered at {time} - showing skip button', xbmc.LOGINFO)

                # Show the button dialog
                if not self.prompt_shown:
                    self.show_skip_button()

                self.warning_timer_active = False
                # Keep skip timer active for auto-skip
                self.timer_active = True

            # Check skip timer for auto-skip
            if self.timer_active and time >= self.next_check_time:
                xbmc.log(f'SkipIntro: Auto-skip timer triggered at {time}', xbmc.LOGINFO)

                # Auto-skip now (if enabled)
                if self.settings.get('enable_autoskip', True):
                    self.skip_to_intro_end()
                else:
                    xbmc.log('SkipIntro: Auto-skip disabled in settings, skipping', xbmc.LOGINFO)
                self.timer_active = False  # Disable timer after skip

            # Check dismiss timer for auto-dismissing button
            if self.dismiss_timer_active and time >= self.dismiss_check_time:
                xbmc.log(f'SkipIntro: Auto-dismiss timer triggered at {time}', xbmc.LOGINFO)
                self.ui.close_dialog()
                self.dismiss_timer_active = False

    def show_skip_button(self):
        """Show skip intro button"""
        if not self.prompt_shown and self.intro_bookmark is not None:
            current_time = self.getTime()
            xbmc.log(f'SkipIntro: Showing skip button at {current_time}', xbmc.LOGINFO)

            if self.ui.prompt_skip_intro(lambda: self.skip_to_intro_end()):
                self.prompt_shown = True
                xbmc.log('SkipIntro: Skip button shown successfully', xbmc.LOGINFO)

                # Set auto-dismiss timer if configured
                auto_dismiss = self.settings.get('auto_dismiss_button', 0)
                if auto_dismiss > 0:
                    self.dismiss_check_time = current_time + auto_dismiss
                    self.dismiss_timer_active = True
                    xbmc.log(f'SkipIntro: Auto-dismiss timer set for {auto_dismiss} seconds (at {self.dismiss_check_time})', xbmc.LOGINFO)
            else:
                xbmc.log('SkipIntro: Failed to show skip button', xbmc.LOGWARNING)

    def detect_show(self):
        """Detect current TV show and episode"""
        if not self.isPlaying():
            xbmc.log('SkipIntro: Not playing, skipping show detection', xbmc.LOGINFO)
            return

        playing_file = self.getPlayingFile()
        from resources.lib.metadata import safe_basename
        xbmc.log(f'SkipIntro: Detecting show for file: {safe_basename(playing_file)}', xbmc.LOGINFO)

        self.show_info = self.metadata.get_show_info()
        if self.show_info:
            xbmc.log('SkipIntro: Detected show info:', xbmc.LOGINFO)
            xbmc.log(f'  Title: {self.show_info.get("title")}', xbmc.LOGINFO)
            xbmc.log(f'  Season: {self.show_info.get("season")}', xbmc.LOGINFO)
            xbmc.log(f'  Episode: {self.show_info.get("episode")}', xbmc.LOGINFO)
        else:
            xbmc.log('SkipIntro: Could not detect show info', xbmc.LOGINFO)

    def find_chapter_by_name(self, chapters, name):
        return ChapterManager.find_chapter_by_name(chapters, name)

    def check_saved_times(self):
        """Check database for saved intro/outro times or chapters"""
        if not self.db or not self.show_info:
            xbmc.log('SkipIntro: Database or show_info not available', xbmc.LOGINFO)
            return

        try:
            show_id = self.db.get_show(self.show_info['title'])
            if not show_id:
                xbmc.log(f'SkipIntro: No show_id found for {self.show_info["title"]}', xbmc.LOGINFO)
                return

            episode_config = self.db.get_episode_times(
                show_id,
                self.show_info.get('season'),
                self.show_info.get('episode')
            )
            if episode_config and (
                episode_config.get('intro_end_time') is not None or
                episode_config.get('intro_end_chapter') is not None
            ):
                self.has_config = True
                if episode_config.get('use_chapters'):
                    self.set_chapter_based_markers(episode_config)
                else:
                    self.set_time_based_markers(episode_config, "episode config")
                xbmc.log(f'SkipIntro: Using episode-specific config: {episode_config}', xbmc.LOGINFO)
                return

            # Get show config
            config = self.db.get_show_config(show_id)
            xbmc.log(f'SkipIntro: Show config: {config}', xbmc.LOGINFO)

            if config:
                self.has_config = True
                if config.get('use_chapters'):
                    self.set_chapter_based_markers(config)
                else:
                    self.set_time_based_markers(config, "show config")
            else:
                xbmc.log(f'SkipIntro: No config found for {self.show_info["title"]}, will use default skip behavior', xbmc.LOGINFO)

        except Exception as e:
            xbmc.log('SkipIntro: Error checking saved times: {}'.format(str(e)), xbmc.LOGERROR)

        xbmc.log(f'SkipIntro: Final times - intro_start: {self.intro_start}, duration: {self.intro_duration}, '
                 f'outro_start: {self.outro_bookmark}, bookmark: {self.intro_bookmark}, show_from_start: {self.show_from_start}',
                 xbmc.LOGINFO)

    def set_time_based_markers(self, times, source_desc):
        """Set time-based markers"""
        self.intro_start = times.get('intro_start_time')
        self.intro_bookmark = times.get('intro_end_time')
        if self.intro_bookmark is not None:
            if self.intro_start is None:
                self.intro_start = 0
            self.intro_duration = self.intro_bookmark - self.intro_start
            xbmc.log(f'SkipIntro: Using {source_desc} time-based markers - start: {self.intro_start}, end: {self.intro_bookmark}', xbmc.LOGINFO)
            self.outro_bookmark = times.get('outro_start_time')
            self.show_from_start = self.intro_start == 0
            return True
        return False

    def set_chapter_based_markers(self, config):
        """Set chapter-based markers"""
        chapters = self.getChapters()
        if not chapters:
            if config.get('intro_end_time') is not None:
                xbmc.log('SkipIntro: No chapters found; using saved chapter config timestamps', xbmc.LOGINFO)
                return self.set_time_based_markers(config, "saved chapter config timestamps")
            xbmc.log('SkipIntro: No chapters found for chapter-based markers', xbmc.LOGWARNING)
            return False

        intro_start_chapter = config.get('intro_start_chapter')
        intro_end_chapter = config.get('intro_end_chapter')
        intro_duration = config.get('intro_duration')
        outro_start_chapter = config.get('outro_start_chapter')

        # Debug logging
        xbmc.log(f'SkipIntro: Chapter config debug - start_ch={intro_start_chapter} (type={type(intro_start_chapter).__name__}), end_ch={intro_end_chapter} (type={type(intro_end_chapter).__name__}), duration={intro_duration} (type={type(intro_duration).__name__ if intro_duration is not None else "None"}), chapters_count={len(chapters)}', xbmc.LOGINFO)

        # Start chapter + duration: Calculate end from start + duration
        if intro_start_chapter is not None and intro_end_chapter is None and intro_duration is not None:
            if 1 <= intro_start_chapter <= len(chapters):
                ch = chapters[intro_start_chapter - 1]
                if 'time' in ch and ch['time'] is not None:
                    self.intro_start = ch['time']
                    self.intro_bookmark = self.intro_start + intro_duration
                    self.intro_duration = intro_duration
                else:
                    # Network files: no timestamps, use chapter-seek mode
                    self._skip_to_chapter = intro_start_chapter  # Best effort
                    self.intro_start = 0
                    self.intro_bookmark = 99999
                    self.intro_duration = None
                    xbmc.log(f'SkipIntro: Using chapter-seek mode with start+duration', xbmc.LOGINFO)
                self.show_from_start = intro_start_chapter == 1

                if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                    outro_ch = chapters[outro_start_chapter - 1]
                    if 'time' in outro_ch and outro_ch['time'] is not None:
                        self.outro_bookmark = outro_ch['time']

                xbmc.log(f'SkipIntro: Using start chapter + duration markers - start: {self.intro_start}, end: {self.intro_bookmark}', xbmc.LOGINFO)
                return True
            else:
                xbmc.log('SkipIntro: Invalid intro start chapter number', xbmc.LOGWARNING)
        # End chapter + duration: Calculate start from end - duration
        elif intro_start_chapter is None and intro_end_chapter is not None and intro_duration is not None:
            if 1 <= intro_end_chapter <= len(chapters):
                chapter = chapters[intro_end_chapter - 1]

                if 'time' not in chapter or chapter['time'] is None:
                    # Network files: no timestamps, use chapter-seek mode
                    self._skip_to_chapter = intro_end_chapter
                    self.intro_start = 0
                    self.intro_bookmark = 99999
                    self.intro_duration = None
                    self.show_from_start = False
                    xbmc.log(f'SkipIntro: Using chapter-seek mode, will seek to chapter {intro_end_chapter}', xbmc.LOGINFO)

                    if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                        outro_ch = chapters[outro_start_chapter - 1]
                        if 'time' in outro_ch and outro_ch['time'] is not None:
                            self.outro_bookmark = outro_ch['time']

                    return True

                self.intro_bookmark = chapter['time']
                self.intro_start = max(0, self.intro_bookmark - intro_duration)
                self.intro_duration = intro_duration
                self.show_from_start = False

                if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                    outro_chapter = chapters[outro_start_chapter - 1]
                    if 'time' in outro_chapter and outro_chapter['time'] is not None:
                        self.outro_bookmark = outro_chapter['time']

                xbmc.log(f'SkipIntro: Using duration-based chapter markers - start: {self.intro_start} (calculated), end: {self.intro_bookmark}, duration: {intro_duration}s', xbmc.LOGINFO)
                return True
            else:
                xbmc.log('SkipIntro: Invalid intro end chapter number', xbmc.LOGWARNING)
        # Full chapter-based: Use both start and end chapters
        elif intro_start_chapter is not None and intro_end_chapter is not None:
            if 1 <= intro_start_chapter <= len(chapters) and 1 <= intro_end_chapter <= len(chapters):
                start_ch = chapters[intro_start_chapter - 1]
                end_ch = chapters[intro_end_chapter - 1]

                if 'time' in start_ch and start_ch['time'] is not None:
                    self.intro_start = start_ch['time']
                    self.intro_bookmark = end_ch['time']
                    self.intro_duration = self.intro_bookmark - self.intro_start
                else:
                    # Network files: no timestamps, use chapter-seek mode
                    self._skip_to_chapter = intro_end_chapter
                    self.intro_start = 0
                    self.intro_bookmark = 99999  # Large sentinel - button stays visible until clicked
                    self.intro_duration = None
                    xbmc.log(f'SkipIntro: Using chapter-seek mode, will seek to chapter {intro_end_chapter}', xbmc.LOGINFO)

                self.show_from_start = intro_start_chapter == 1

                if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                    outro_ch = chapters[outro_start_chapter - 1]
                    if 'time' in outro_ch and outro_ch['time'] is not None:
                        self.outro_bookmark = outro_ch['time']

                xbmc.log(f'SkipIntro: Using chapter-based markers - start: {self.intro_start}, end: {self.intro_bookmark}', xbmc.LOGINFO)
                return True
            else:
                xbmc.log('SkipIntro: Invalid chapter numbers for intro/outro', xbmc.LOGWARNING)
        # End chapter only (no start, no duration) — most common DB pattern.
        # Default start to chapter 1.
        elif intro_end_chapter is not None:
            intro_start_chapter = 1
            if 1 <= intro_start_chapter <= len(chapters) and 1 <= intro_end_chapter <= len(chapters):
                start_ch = chapters[intro_start_chapter - 1]
                end_ch = chapters[intro_end_chapter - 1]

                if 'time' in start_ch and start_ch['time'] is not None and 'time' in end_ch and end_ch['time'] is not None:
                    self.intro_start = start_ch['time']
                    self.intro_bookmark = end_ch['time']
                    self.intro_duration = self.intro_bookmark - self.intro_start
                else:
                    self._skip_to_chapter = intro_end_chapter
                    self.intro_start = 0
                    self.intro_bookmark = 99999
                    self.intro_duration = None
                    xbmc.log(f'SkipIntro: Using chapter-seek mode, will seek to chapter {intro_end_chapter}', xbmc.LOGINFO)

                self.show_from_start = True

                if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                    outro_ch = chapters[outro_start_chapter - 1]
                    if 'time' in outro_ch and outro_ch['time'] is not None:
                        self.outro_bookmark = outro_ch['time']

                xbmc.log(f'SkipIntro: Using chapter-based markers (end-only, start defaulted to 1) - start: {self.intro_start}, end: {self.intro_bookmark}', xbmc.LOGINFO)
                return True
            else:
                xbmc.log('SkipIntro: Invalid chapter numbers', xbmc.LOGWARNING)
        else:
            xbmc.log('SkipIntro: Missing required chapter configuration', xbmc.LOGWARNING)

        return False

    def check_for_intro_chapter(self):
        try:
            playing_file = self.getPlayingFile()
            if not playing_file:
                xbmc.log('SkipIntro: No file playing, skipping chapter check', xbmc.LOGINFO)
                return

            # Retrieve chapters
            xbmc.log('SkipIntro: Getting chapters for file', xbmc.LOGINFO)
            chapters = self.getChapters()
            if chapters:
                xbmc.log(f'SkipIntro: Found {len(chapters)} chapters:', xbmc.LOGINFO)
                for i, chapter in enumerate(chapters):
                    xbmc.log(f'  Chapter {i+1}: time={chapter.get("time")}, name={chapter.get("name", "Unnamed")}', xbmc.LOGINFO)

                intro_start = self.find_intro_chapter(chapters)
                if intro_start is not None:
                    xbmc.log(f'SkipIntro: Found potential intro start at {intro_start}', xbmc.LOGINFO)
                    intro_chapter_index = None
                    for i, chapter in enumerate(chapters):
                        if chapter.get('time') is not None and abs(chapter['time'] - intro_start) < 0.1:
                            intro_chapter_index = i
                            xbmc.log(f'SkipIntro: Matched intro to chapter {i+1}', xbmc.LOGINFO)
                            break

                    if intro_chapter_index is not None and intro_chapter_index + 1 < len(chapters):
                        self.intro_start = chapters[intro_chapter_index]['time']
                        self.intro_bookmark = chapters[intro_chapter_index + 1]['time']
                        self.intro_duration = self.intro_bookmark - self.intro_start
                        self.show_from_start = False
                        xbmc.log('SkipIntro: Set chapter-based intro times:', xbmc.LOGINFO)
                        xbmc.log(f'  Start: {self.intro_start}', xbmc.LOGINFO)
                        xbmc.log(f'  End: {self.intro_bookmark}', xbmc.LOGINFO)
                        xbmc.log(f'  Duration: {self.intro_duration}', xbmc.LOGINFO)
                else:
                    self.bookmarks_checked = True
            else:
                xbmc.log('SkipIntro: No chapters found for auto-detection', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('SkipIntro: Error in check_for_intro_chapter: {}'.format(str(e)), xbmc.LOGERROR)
            self.bookmarks_checked = True

    def getChapters(self):
        """Get chapters, trying ChapterManager first, falling back to metadata InfoLabels."""
        chapter_manager = ChapterManager()
        chapters = chapter_manager.get_chapters()
        if not chapters:
            # Fallback to metadata InfoLabels (works for network streams)
            chapters = self.metadata.get_chapters()
        if chapters:
            self._playback_chapters = chapters
        return chapters

    def _try_autodetect(self):
        """Try to autodetect intro from chapter names using enzyme.

        If intro chapters are found, sets markers and saves config to DB
        so future plays of this show skip immediately.
        """
        try:
            chapters = self.getChapters()
            if not chapters:
                xbmc.log('SkipIntro: No chapters for autodetect', xbmc.LOGINFO)
                return

            chapter_manager = ChapterManager()
            detected = chapter_manager.autodetect_intro(chapters)
            if not detected:
                xbmc.log('SkipIntro: Autodetect found no intro pattern in chapter names', xbmc.LOGINFO)
                return

            # Set the markers
            intro_start_time = detected.get('intro_start_time')
            intro_end_time = detected.get('intro_end_time')

            if intro_start_time is not None and intro_end_time is not None:
                self.intro_start = intro_start_time
                self.intro_bookmark = intro_end_time
                self.intro_duration = intro_end_time - intro_start_time
                self.outro_bookmark = detected.get('outro_start_time')
                self.show_from_start = intro_start_time == 0

                xbmc.log(f'SkipIntro: Autodetect set markers — intro: {self.intro_start:.1f}→{self.intro_bookmark:.1f}s', xbmc.LOGINFO)

                self._save_autodetected_chapter_config(detected)
            else:
                # No timestamps — use chapter-seek mode
                self._skip_to_chapter = detected.get('intro_end_chapter')
                self.intro_start = 0
                self.intro_bookmark = 99999
                self.intro_duration = None
                self.show_from_start = True
                xbmc.log(f'SkipIntro: Autodetect using chapter-seek to chapter {self._skip_to_chapter}', xbmc.LOGINFO)
                self._save_autodetected_chapter_config(detected)

        except Exception as e:
            xbmc.log(f'SkipIntro: Autodetect error: {str(e)}', xbmc.LOGERROR)

    def _save_autodetected_chapter_config(self, detected):
        """Persist chapter autodetect results so later plays do not rescan."""
        if not self.db or not self.show_info:
            return

        show_id = self.db.get_show(self.show_info['title'])
        if not show_id:
            return

        config = {
            'use_chapters': True,
            'intro_start_chapter': detected.get('intro_start_chapter'),
            'intro_end_chapter': detected.get('intro_end_chapter'),
            'outro_start_chapter': detected.get('outro_start_chapter'),
            'intro_start_time': detected.get('intro_start_time'),
            'intro_end_time': detected.get('intro_end_time'),
            'outro_start_time': detected.get('outro_start_time'),
        }
        self.db.save_show_config(show_id, config)
        xbmc.log(f'SkipIntro: Autodetect saved config for {self.show_info["title"]}', xbmc.LOGINFO)

    def _record_watched_episode_for_audio_detection(self, force=False):
        """Record watched episodes and start silent audio detection when ready."""
        if not self.settings.get('enable_audio_autodetect', True):
            return
        if not self.db or not self.show_info:
            return
        if not force and self._max_playback_time < AUTO_AUDIO_DETECTION_MIN_WATCH_SECONDS:
            xbmc.log(
                f'SkipIntro: Audio autodetect watch record skipped; only watched '
                f'{self._max_playback_time:.1f}s',
                xbmc.LOGINFO
            )
            return

        playing_file = self._playing_file
        if not playing_file:
            try:
                playing_file = self.getPlayingFile()
            except Exception:
                playing_file = None
        if not playing_file:
            return

        season = self.show_info.get('season')
        episode = self.show_info.get('episode')
        if season is None or episode is None:
            return

        show_id = self.db.get_show(self.show_info['title'])
        if not show_id:
            return

        if self._show_has_skip_config(show_id, self.db):
            xbmc.log('SkipIntro: Audio autodetect skipped; show already has config', xbmc.LOGINFO)
            return

        if not self.db.record_audio_detection_episode(show_id, season, episode, playing_file):
            return

        watched_count = self.db.get_audio_detection_episode_count(show_id)
        if watched_count < AUTO_AUDIO_DETECTION_TRIGGER_EPISODES:
            xbmc.log(
                f'SkipIntro: Audio autodetect waiting for more watched episodes '
                f'({watched_count}/{AUTO_AUDIO_DETECTION_TRIGGER_EPISODES})',
                xbmc.LOGINFO
            )
            return

        attempt = self.db.get_audio_detection_attempt(show_id)
        if attempt and (attempt.get('watched_episode_count') or 0) >= watched_count:
            xbmc.log('SkipIntro: Audio autodetect already attempted for current watched count', xbmc.LOGINFO)
            return

        chapters = list(self._playback_chapters)
        self._start_audio_detection_thread(show_id, self.show_info['title'], playing_file, watched_count, chapters)

    @staticmethod
    def _show_has_skip_config(show_id, db):
        config = db.get_show_config(show_id)
        return bool(config and (
            config.get('intro_end_time') is not None or
            config.get('intro_end_chapter') is not None
        ))

    def _start_audio_detection_thread(self, show_id, show_title, selected_file, watched_count, chapters=None):
        """Start a single background audio detection job per show."""
        with _audio_detection_lock:
            if show_id in _audio_detection_running_shows:
                xbmc.log(f'SkipIntro: Audio autodetect already running for {show_title}', xbmc.LOGINFO)
                return
            _audio_detection_running_shows.add(show_id)

        def worker():
            try:
                db = get_database()
                if not db:
                    xbmc.log('SkipIntro: Audio autodetect could not open database', xbmc.LOGERROR)
                    return
                try:
                    self._run_audio_detection_for_show(db, show_id, show_title, selected_file, watched_count, chapters)
                finally:
                    db.close()
            finally:
                with _audio_detection_lock:
                    _audio_detection_running_shows.discard(show_id)

        thread = threading.Thread(
            target=worker,
            name=f'SkipIntroAudioDetect-{show_id}',
            daemon=True
        )
        thread.start()
        xbmc.log(f'SkipIntro: Started audio autodetect worker for {show_title}', xbmc.LOGINFO)

    def _run_audio_detection_for_show(self, db, show_id, show_title, selected_file, watched_count, chapters=None):
        """Run progressive fingerprint detection and persist show config on hit."""
        if self._show_has_skip_config(show_id, db):
            xbmc.log(f'SkipIntro: Audio autodetect skipped for {show_title}; config already exists', xbmc.LOGINFO)
            db.save_audio_detection_attempt(show_id, watched_count, 'skipped_existing_config')
            return None

        try:
            detector = AudioIntroDetector(
                backend='fingerprint',
                max_scan_seconds=AUDIO_DETECTION_INITIAL_SCAN_SECONDS,
                detect_outro=False
            )
            candidates = detector.find_episode_candidates(
                selected_file,
                skip_first_episode=True
            )
            if len(candidates) < 2:
                xbmc.log(
                    f'SkipIntro: Audio autodetect skipped for {show_title}; '
                    f'only {len(candidates)} candidate episode(s)',
                    xbmc.LOGWARNING
                )
                db.save_audio_detection_attempt(show_id, watched_count, 'insufficient_candidates')
                return None

            xbmc.log(
                f'SkipIntro: Audio autodetect analyzing {len(candidates)} episode(s) for {show_title}',
                xbmc.LOGINFO
            )
            detected = detector.detect_show_intro(candidates)
            detection_scan_seconds = AUDIO_DETECTION_INITIAL_SCAN_SECONDS
            if not detected:
                xbmc.log(f'SkipIntro: Audio autodetect extending scan for {show_title}', xbmc.LOGINFO)
                fallback_detector = AudioIntroDetector(
                    backend='fingerprint',
                    max_scan_seconds=AUDIO_DETECTION_FALLBACK_SCAN_SECONDS,
                    detect_outro=False
                )
                detected = fallback_detector.detect_show_intro(candidates)
                detection_scan_seconds = AUDIO_DETECTION_FALLBACK_SCAN_SECONDS

            if not self._is_valid_audio_detection(detected):
                xbmc.log(f'SkipIntro: Audio autodetect found no stable intro for {show_title}', xbmc.LOGINFO)
                db.save_audio_detection_attempt(show_id, watched_count, 'miss')
                return None

            config = self._build_audio_detection_config(detected, chapters=chapters)
            if db.save_show_config(show_id, config):
                virtual_chapter_count = 0
                if not chapters:
                    episode_files = self._find_show_episode_files(selected_file, skip_first_episode=True)
                    virtual_chapter_count = self._save_audio_detection_episode_markers(
                        db,
                        show_id,
                        episode_files,
                        config
                    )
                db.save_audio_detection_attempt(show_id, watched_count, 'hit')
                xbmc.log(
                    f'SkipIntro: Audio autodetect saved config for {show_title}: '
                    f'intro {config.get("intro_start_time")}->{config.get("intro_end_time")}, '
                    f'outro pending, '
                    f'virtual_episode_markers={virtual_chapter_count}',
                    xbmc.LOGINFO
                )
                self._run_background_outro_detection(
                    db,
                    show_id,
                    show_title,
                    candidates,
                    config,
                    chapters=chapters,
                    scan_seconds=detection_scan_seconds,
                    selected_file=selected_file
                )
                return config

            db.save_audio_detection_attempt(show_id, watched_count, 'save_failed')
            return None
        except AudioIntroDetectionError as e:
            xbmc.log(f'SkipIntro: Audio autodetect unavailable for {show_title}: {str(e)}', xbmc.LOGWARNING)
            db.save_audio_detection_attempt(show_id, watched_count, 'unavailable')
            return None
        except Exception as e:
            xbmc.log(f'SkipIntro: Audio autodetect error for {show_title}: {str(e)}', xbmc.LOGERROR)
            db.save_audio_detection_attempt(show_id, watched_count, 'error')
            return None

    def _run_background_outro_detection(
        self,
        db,
        show_id,
        show_title,
        candidates,
        base_config,
        chapters=None,
        scan_seconds=AUDIO_DETECTION_INITIAL_SCAN_SECONDS,
        selected_file=None
    ):
        """Detect outro after intro config is already saved."""
        try:
            xbmc.log(f'SkipIntro: Audio autodetect scanning outro in background for {show_title}', xbmc.LOGINFO)
            detector = AudioIntroDetector(
                backend='fingerprint',
                max_scan_seconds=scan_seconds,
                detect_outro=True
            )
            detected = detector.detect_show_intro(candidates)
            outro_start = detected.get('outro_start_time') if detected else None
            if outro_start is None:
                xbmc.log(f'SkipIntro: Audio autodetect found no stable outro for {show_title}', xbmc.LOGINFO)
                return None

            existing_config = db.get_show_config(show_id) or base_config
            updated_config = dict(existing_config)
            updated_config['outro_start_time'] = outro_start
            chapter_config = self._audio_detection_chapter_config(
                updated_config.get('intro_start_time') or 0,
                updated_config.get('intro_end_time'),
                outro_start,
                chapters=chapters
            )
            if chapter_config:
                updated_config.update(chapter_config)

            if db.save_show_config(show_id, updated_config):
                virtual_chapter_count = 0
                if not chapters and selected_file:
                    episode_files = self._find_show_episode_files(selected_file, skip_first_episode=True)
                    virtual_chapter_count = self._save_audio_detection_episode_markers(
                        db,
                        show_id,
                        episode_files,
                        updated_config,
                        update_existing_audio_detection=True
                    )
                xbmc.log(
                    f'SkipIntro: Audio autodetect saved background outro for {show_title}: '
                    f'outro {outro_start}, virtual_episode_markers={virtual_chapter_count}',
                    xbmc.LOGINFO
                )
                return updated_config
        except AudioIntroDetectionError as e:
            xbmc.log(f'SkipIntro: Audio outro autodetect unavailable for {show_title}: {str(e)}', xbmc.LOGWARNING)
        except Exception as e:
            xbmc.log(f'SkipIntro: Audio outro autodetect error for {show_title}: {str(e)}', xbmc.LOGERROR)
        return None

    @staticmethod
    def _find_show_episode_files(selected_file, skip_first_episode=False):
        """Return all video files in the selected episode folder."""
        slash = max(selected_file.rfind('/'), selected_file.rfind('\\'))
        if slash < 0:
            directory = ''
            selected_name = selected_file
        else:
            directory = selected_file[:slash + 1]
            selected_name = selected_file[slash + 1:]
        if not directory:
            return [selected_file]

        try:
            _dirs, files = xbmcvfs.listdir(directory)
        except Exception as e:
            xbmc.log(
                f'SkipIntro: Could not list episode folder for virtual chapters '
                f'{sanitize_path(selected_file)}: {str(e)}',
                xbmc.LOGWARNING
            )
            return [selected_file]

        episode_files = []
        for filename in sorted(files, key=lambda value: value.lower()):
            if filename.lower().endswith(VIDEO_EXTENSIONS):
                episode_files.append(directory + filename)

        if not episode_files:
            return [selected_file]
        if skip_first_episode and len(episode_files) > 1:
            episode_files = episode_files[1:]

        if selected_name and selected_file not in episode_files:
            episode_files.append(selected_file)
        return episode_files

    def _save_audio_detection_episode_markers(
        self,
        db,
        show_id,
        episode_files,
        config,
        update_existing_audio_detection=False
    ):
        """Save audio-detected times as per-episode virtual chapter markers."""
        episode_markers = {
            'intro_start_time': config.get('intro_start_time'),
            'intro_end_time': config.get('intro_end_time'),
            'outro_start_time': config.get('outro_start_time'),
            'intro_start_chapter': None,
            'intro_end_chapter': None,
            'outro_start_chapter': None,
            'source': 'audio_detection'
        }
        if episode_markers['intro_end_time'] is None:
            return 0

        saved_count = 0
        metadata = ShowMetadata()
        seen = set()
        for episode_file in episode_files:
            episode_info = metadata._parse_filename(episode_file)
            if not episode_info:
                continue
            season = episode_info.get('season')
            episode = episode_info.get('episode')
            if season is None or episode is None:
                continue
            key = (season, episode)
            if key in seen:
                continue
            seen.add(key)

            existing = db.get_episode_times(show_id, season, episode)
            if existing and (
                existing.get('intro_end_time') is not None or
                existing.get('intro_end_chapter') is not None
            ):
                if not update_existing_audio_detection or existing.get('source') != 'audio_detection':
                    continue

            if db.save_episode_times(show_id, season, episode, episode_markers):
                saved_count += 1

        if saved_count:
            xbmc.log(
                f'SkipIntro: Saved {saved_count} audio-detected virtual episode marker(s)',
                xbmc.LOGINFO
            )
        return saved_count

    @staticmethod
    def _is_valid_audio_detection(detected):
        if not detected:
            return False
        intro_start = detected.get('intro_start_time') or 0
        intro_end = detected.get('intro_end_time')
        return intro_end is not None and intro_end > intro_start

    def _build_audio_detection_config(self, detected, chapters=None):
        intro_start = detected.get('intro_start_time') or 0
        intro_end = detected.get('intro_end_time')
        outro_start = detected.get('outro_start_time')
        config = {
            'use_chapters': False,
            'intro_start_chapter': None,
            'intro_end_chapter': None,
            'outro_start_chapter': None,
            'intro_duration': None,
            'intro_start_time': intro_start,
            'intro_end_time': intro_end,
            'outro_start_time': outro_start
        }

        chapter_config = self._audio_detection_chapter_config(intro_start, intro_end, outro_start, chapters=chapters)
        if chapter_config:
            config.update(chapter_config)
        return config

    def _audio_detection_chapter_config(self, intro_start, intro_end, outro_start, chapters=None):
        """Map audio-detected times to chapter numbers when boundaries align."""
        if chapters is None:
            try:
                chapters = self.getChapters()
            except Exception:
                chapters = []
        if not chapters:
            return None

        intro_end_chapter = self._chapter_number_near_time(chapters, intro_end)
        if intro_end_chapter is None:
            return None

        intro_start_chapter = self._chapter_number_near_time(chapters, intro_start)
        if intro_start_chapter is None and intro_start == 0:
            intro_start_chapter = 1

        outro_start_chapter = None
        if outro_start is not None:
            outro_start_chapter = self._chapter_number_near_time(chapters, outro_start)

        return {
            'use_chapters': True,
            'intro_start_chapter': intro_start_chapter,
            'intro_end_chapter': intro_end_chapter,
            'outro_start_chapter': outro_start_chapter,
        }

    @staticmethod
    def _chapter_number_near_time(chapters, target_time, tolerance=2.0):
        if target_time is None:
            return None
        best = None
        best_delta = None
        for index, chapter in enumerate(chapters):
            chapter_time = chapter.get('time')
            if chapter_time is None:
                continue
            delta = abs(float(chapter_time) - float(target_time))
            if best_delta is None or delta < best_delta:
                best = chapter.get('number') or index + 1
                best_delta = delta
        if best_delta is not None and best_delta <= tolerance:
            return best
        return None

    def find_intro_chapter(self, chapters):
        chapter_manager = ChapterManager()
        return chapter_manager.find_intro_chapter(chapters)

    def _seek_to_chapter(self, target_chapter):
        """Seek to a specific chapter number using InfoLabels and chapter-forward actions."""
        try:
            current = xbmc.getInfoLabel('Player.Chapter')
            current_num = int(current) if current and current.isdigit() else 0
            if current_num <= 0:
                xbmc.log('SkipIntro: Cannot determine current chapter', xbmc.LOGWARNING)
                return False

            steps = target_chapter - current_num
            if steps <= 0:
                xbmc.log(f'SkipIntro: Already at or past chapter {target_chapter}', xbmc.LOGINFO)
                return True

            xbmc.log(f'SkipIntro: Seeking from chapter {current_num} to {target_chapter} ({steps} steps)', xbmc.LOGINFO)
            for i in range(steps):
                xbmc.executebuiltin('PlayerControl(Next)')
                xbmc.sleep(200)

            xbmc.log(f'SkipIntro: Chapter seek completed, now at chapter {xbmc.getInfoLabel("Player.Chapter")}', xbmc.LOGINFO)
            return True
        except Exception as e:
            xbmc.log(f'SkipIntro: Error in chapter seek: {str(e)}', xbmc.LOGERROR)
            return False

    def skip_to_intro_end(self):
        try:
            # Close the dialog if it's open (for auto-skip case)
            self.ui.close_dialog()

            if self.intro_bookmark is not None:
                if self._skip_to_chapter:
                    xbmc.log(f'SkipIntro: Seeking to chapter {self._skip_to_chapter}', xbmc.LOGINFO)
                    self._seek_to_chapter(self._skip_to_chapter)
                else:
                    current_time = self.getTime()
                    xbmc.log(f'SkipIntro: Skipping from {current_time} to {self.intro_bookmark} seconds', xbmc.LOGINFO)
                    self.seekTime(self.intro_bookmark)
                xbmc.log('SkipIntro: Skip completed', xbmc.LOGINFO)
            else:
                xbmc.log('SkipIntro: No intro bookmark or chapter set, cannot skip', xbmc.LOGWARNING)

        except Exception as e:
            xbmc.log('SkipIntro: Error skipping to intro end: {}'.format(str(e)), xbmc.LOGERROR)

    def cleanup(self):
        """Clean up resources. Acquires timer lock to prevent race with onPlayBackTime."""
        with self._timer_lock:
            self.ui.cleanup()
            self.intro_start = None
            self.intro_duration = None
            self.intro_bookmark = None
            self.outro_bookmark = None
            self.bookmarks_checked = False
            self.prompt_shown = False
            self.show_info = None
            self.timer_active = False
            self.next_check_time = 0
            self.warning_timer_active = False
            self.warning_check_time = 0
            self.dismiss_timer_active = False
            self.dismiss_check_time = 0
            self.show_from_start = False
            self.has_config = False
            self._skip_to_chapter = None
            self._playing_file = None
            self._max_playback_time = 0
            self._playback_chapters = []

    def set_manual_times(self):
        """Prompt user for manual intro/outro times and save them"""
        if not self.show_info:
            xbmc.log('SkipIntro: No show info available for manual time setting', xbmc.LOGWARNING)
            return

        show_id = self.db.get_show(self.show_info['title'])
        if not show_id:
            xbmc.log('SkipIntro: Failed to get show ID for manual time setting', xbmc.LOGWARNING)
            return

        intro_start = xbmcgui.Dialog().numeric(2, 'Enter intro start time (MM:SS)')
        intro_end = xbmcgui.Dialog().numeric(2, 'Enter intro end time (MM:SS)')
        outro_start = xbmcgui.Dialog().numeric(2, 'Enter outro start time (MM:SS) or leave empty')

        def time_to_seconds(time_str):
            if not time_str:
                return None
            try:
                parts = time_str.split(':')
                if len(parts) == 2:
                    minutes, seconds = int(parts[0]), int(parts[1])
                elif len(parts) == 3:
                    hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
                    minutes += hours * 60
                else:
                    return None
                if seconds < 0 or seconds >= 60 or minutes < 0:
                    return None
                return minutes * 60 + seconds
            except (ValueError, IndexError):
                return None

        intro_start_seconds = time_to_seconds(intro_start)
        intro_end_seconds = time_to_seconds(intro_end)
        outro_start_seconds = time_to_seconds(outro_start)

        if intro_start_seconds is not None and intro_end_seconds is not None:
            success = self.db.set_manual_show_times(
                show_id,
                intro_start_seconds,
                intro_end_seconds,
                outro_start_seconds
            )
            if success:
                xbmcgui.Dialog().notification('SkipIntro', 'Times saved successfully', xbmcgui.NOTIFICATION_INFO, 3000)
                # Refresh times for current playback
                self.check_saved_times()
            else:
                xbmcgui.Dialog().notification('SkipIntro', 'Failed to save times', xbmcgui.NOTIFICATION_ERROR, 3000)
        else:
            xbmcgui.Dialog().notification('SkipIntro', 'Invalid time format', xbmcgui.NOTIFICATION_ERROR, 3000)

def main():
    xbmc.log('SkipIntro: Service starting', xbmc.LOGINFO)



    player = SkipIntroPlayer()
    monitor = xbmc.Monitor()

    try:
        # Main service loop
        while not monitor.abortRequested():
            if monitor.waitForAbort(MONITOR_INTERVAL_SEC):
                break

            if player.isPlaying():
                try:
                    time = player.getTime()
                    player.onPlayBackTime(time)
                except Exception as e:
                    xbmc.log(f'SkipIntro: Error checking playback time: {str(e)}', xbmc.LOGERROR)

    except Exception as e:
        xbmc.log(f'SkipIntro: Error in main loop: {str(e)}', xbmc.LOGERROR)
    finally:
        try:
            player.cleanup()
            xbmc.log('SkipIntro: Service stopped', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error during cleanup: {str(e)}', xbmc.LOGERROR)

if __name__ == '__main__':
    main()
