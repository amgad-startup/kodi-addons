import unittest
import tempfile
import os
import json
import warnings
from unittest.mock import MagicMock, patch

# Suppress sqlite3 ResourceWarnings from mock teardown GC — the actual code
# properly closes connections via context managers and ShowDatabase.close().
warnings.filterwarnings('ignore', category=ResourceWarning, message='unclosed database')

# Mock Kodi modules
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGWARNING = 3
    LOGERROR = 2

    @staticmethod
    def log(msg, level):
        pass

    @staticmethod
    def sleep(ms):
        pass

    @staticmethod
    def executeJSONRPC(json_str):
        import json
        return json.dumps({"result": {}})

    @staticmethod
    def executebuiltin(cmd):
        pass

    @staticmethod
    def getInfoLabel(label):
        if label == 'VideoPlayer.TVShowTitle':
            return 'Test Show'
        elif label == 'VideoPlayer.Season':
            return '1'
        elif label == 'VideoPlayer.Episode':
            return '2'
        elif label == 'Player.ChapterCount':
            return '0'
        elif label == 'Player.Chapter':
            return '1'
        return ''

    class Player:
        def __init__(self):
            self.playing = True

        def isPlaying(self):
            return self.playing

        def isPlayingVideo(self):
            return self.playing

        def getPlayingFile(self):
            return '/path/to/Test.Show.S01E02.mkv'

    class Monitor:
        def __init__(self):
            pass

class MockXBMCGUI:
    ACTION_PREVIOUS_MENU = 10
    ACTION_NAV_BACK = 92
    NOTIFICATION_INFO = 'info'
    NOTIFICATION_ERROR = 'error'
    NOTIFICATION_WARNING = 'warning'

    class Dialog:
        def yesno(self, heading, message, *args, **kwargs):
            return True
        def notification(self, heading, message, icon=None, time=5000):
            pass

    class WindowXMLDialog:
        def __init__(self, *args, **kwargs):
            pass
        def show(self):
            pass
        def close(self):
            pass
        def getControl(self, controlId):
            return MagicMock()
        def setFocus(self, control):
            pass
        def setFocusId(self, controlId):
            pass

class MockXBMCAddon:
    class Addon:
        def __init__(self, addon_id=None):
            self._settings = {
                "enable_autoskip": "true",
                "pre_skip_seconds": "3",
                "delay_autoskip": "0",
                "auto_dismiss_button": "0",
                "database_path": ":memory:",
                "backup_restore_path": ""
            }

        def getSetting(self, key):
            return self._settings.get(key, "")

        def getSettingBool(self, key):
            return self._settings.get(key, "false").lower() == "true"

        def setSetting(self, key, value):
            self._settings[key] = value

        def getAddonInfo(self, key):
            if key == 'path':
                return os.path.dirname(os.path.abspath(__file__))
            return ''

class MockXBMCVFS:
    @staticmethod
    def translatePath(path):
        return path

    @staticmethod
    def exists(path):
        return os.path.exists(path)

    @staticmethod
    def mkdirs(path):
        os.makedirs(path, exist_ok=True)

    @staticmethod
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

    class File:
        def __init__(self, path, mode='r'):
            pass
        def read(self):
            return ''
        def write(self, data):
            pass
        def close(self):
            pass
        def size(self):
            return 0

# Mock the Kodi modules
import sys
sys.modules['xbmc'] = MockXBMC
sys.modules['xbmcgui'] = MockXBMCGUI
sys.modules['xbmcaddon'] = MockXBMCAddon
sys.modules['xbmcvfs'] = MockXBMCVFS

# Now import our addon code
import default

class TestDatabase(unittest.TestCase):
    def setUp(self):
        """Set up test database using a temp file (ShowDatabase needs a real path)"""
        from resources.lib.database import ShowDatabase
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.db = ShowDatabase(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_show_create_and_lookup(self):
        """Test show creation and retrieval"""
        show_id = self.db.get_show('Test Show')
        self.assertIsNotNone(show_id)
        # Second call returns same ID
        self.assertEqual(self.db.get_show('Test Show'), show_id)

    def test_show_config_save_and_load(self):
        """Test saving and loading show config"""
        show_id = self.db.get_show('Test Show')
        success = self.db.set_manual_show_times(show_id, 30, 90, 2700)
        self.assertTrue(success)

        config = self.db.get_show_config(show_id)
        self.assertIsNotNone(config)
        self.assertEqual(config['intro_start_time'], 30)
        self.assertEqual(config['intro_end_time'], 90)
        self.assertEqual(config['outro_start_time'], 2700)
        self.assertFalse(config['use_chapters'])

    def test_show_chapter_config(self):
        """Test saving and loading chapter-based config"""
        show_id = self.db.get_show('Test Show')
        success = self.db.set_manual_show_chapters(show_id, True, 1, 3, 8)
        self.assertTrue(success)

        config = self.db.get_show_config(show_id)
        self.assertIsNotNone(config)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 1)
        self.assertEqual(config['intro_end_chapter'], 3)

    def test_show_title_strip(self):
        """Test that show titles are stripped of whitespace"""
        show_id1 = self.db.get_show('Test Show')
        show_id2 = self.db.get_show('  Test Show  ')
        self.assertEqual(show_id1, show_id2)

    def test_episode_times_save_and_load(self):
        """Episode-specific times can be saved and loaded"""
        show_id = self.db.get_show('Test Show')
        success = self.db.save_episode_times(show_id, 1, 2, {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'outro_start_time': None,
            'source': 'audio_detection'
        })
        self.assertTrue(success)

        config = self.db.get_episode_times(show_id, 1, 2)
        self.assertIsNotNone(config)
        self.assertFalse(config['use_chapters'])
        self.assertEqual(config['intro_start_time'], 0)
        self.assertEqual(config['intro_end_time'], 263)
        self.assertEqual(config['source'], 'audio_detection')

class TestMetadata(unittest.TestCase):
    def setUp(self):
        """Set up metadata detector"""
        from resources.lib.metadata import ShowMetadata
        self.metadata = ShowMetadata()

    def test_show_detection_kodi(self):
        """Test show detection using Kodi info labels"""
        info = self.metadata.get_show_info()
        self.assertEqual(info['title'], 'Test Show')
        self.assertEqual(info['season'], 1)
        self.assertEqual(info['episode'], 2)

    def test_chapters(self):
        """Test chapter detection returns list (empty when no video playing)"""
        chapters = self.metadata.get_chapters()
        self.assertIsInstance(chapters, list)

    def test_show_detection_filename(self):
        """Test show detection from filename when info labels unavailable"""
        with patch('xbmc.getInfoLabel', return_value=''):
            info = self.metadata.get_show_info()
            # Filename parser produces 'Test Show' (with dots replaced by spaces)
            self.assertEqual(info['title'].strip(), 'Test Show')
            self.assertEqual(info['season'], 1)
            self.assertEqual(info['episode'], 2)

class TestSkipIntro(unittest.TestCase):
    def setUp(self):
        self.player = default.SkipIntroPlayer()

    def tearDown(self):
        if self.player.db:
            self.player.db.close()

    def test_cleanup(self):
        """Test cleanup resets all state"""
        self.player.intro_bookmark = 100
        self.player.outro_bookmark = 200
        self.player.bookmarks_checked = True
        self.player.show_info = {'title': 'Test'}
        self.player.timer_active = True
        self.player.show_from_start = True
        self.player.has_config = True
        self.player._skip_to_chapter = 3

        self.player.cleanup()

        self.assertIsNone(self.player.intro_bookmark)
        self.assertIsNone(self.player.outro_bookmark)
        self.assertIsNone(self.player.intro_start)
        self.assertIsNone(self.player.intro_duration)
        self.assertFalse(self.player.bookmarks_checked)
        self.assertFalse(self.player.prompt_shown)
        self.assertIsNone(self.player.show_info)
        self.assertFalse(self.player.timer_active)
        self.assertEqual(self.player.next_check_time, 0)
        self.assertFalse(self.player.show_from_start)
        self.assertFalse(self.player.has_config)
        self.assertIsNone(self.player._skip_to_chapter)

    def test_playback_stopped_calls_cleanup(self):
        """onPlayBackStopped should reset state"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackStopped()
        self.assertIsNone(self.player.intro_bookmark)

    def test_playback_ended_calls_cleanup(self):
        """onPlayBackEnded should reset state"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackEnded()
        self.assertIsNone(self.player.intro_bookmark)

    def test_playback_started_calls_cleanup(self):
        """onPlayBackStarted should reset state for new playback"""
        self.player.intro_bookmark = 100
        self.player.onPlayBackStarted()
        self.assertIsNone(self.player.intro_bookmark)

    # --- set_time_based_markers ---

    def test_set_time_based_markers(self):
        """Time-based markers set intro_start, intro_bookmark, and duration"""
        times = {'intro_start_time': 30, 'intro_end_time': 90, 'outro_start_time': 1200}
        result = self.player.set_time_based_markers(times, "test")

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 30)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.intro_duration, 60)
        self.assertEqual(self.player.outro_bookmark, 1200)
        self.assertFalse(self.player.show_from_start)

    def test_set_time_based_markers_from_start(self):
        """show_from_start is True when intro_start_time is 0"""
        times = {'intro_start_time': 0, 'intro_end_time': 90, 'outro_start_time': None}
        self.player.set_time_based_markers(times, "test")
        self.assertTrue(self.player.show_from_start)

    def test_set_time_based_markers_returns_false_when_none(self):
        """Returns False when intro times are None"""
        self.assertFalse(self.player.set_time_based_markers(
            {'intro_start_time': None, 'intro_end_time': None}, "test"))
        self.assertFalse(self.player.set_time_based_markers(
            {'intro_start_time': 30, 'intro_end_time': None}, "test"))

    def test_check_saved_times_prefers_episode_config(self):
        """Episode-specific config wins over show-level config"""
        self.player.show_info = {'title': 'Test Show', 'season': 1, 'episode': 2}
        show_id = self.player.db.get_show('Test Show')
        self.player.db.set_manual_show_times(show_id, 30, 90)
        self.player.db.save_episode_times(show_id, 1, 2, {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'source': 'audio_detection'
        })

        self.player.check_saved_times()

        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 263)
        self.assertTrue(self.player.has_config)

    # --- set_chapter_based_markers ---

    def test_set_chapter_based_markers(self):
        """Chapter-based markers resolve chapter numbers to times"""
        chapters = [
            {'time': 0, 'name': 'Start', 'number': 1},
            {'time': 112, 'name': 'Intro', 'number': 2},
            {'time': 157, 'name': 'Intro End', 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': None}
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 157)
        self.assertTrue(self.player.show_from_start)

    def test_set_chapter_based_markers_with_outro(self):
        """Chapter-based markers with outro chapter"""
        chapters = [
            {'time': 0, 'number': 1}, {'time': 112, 'number': 2},
            {'time': 157, 'number': 3}, {'time': 1200, 'number': 4},
            {'time': 1350, 'number': 5},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': 4}
        self.player.set_chapter_based_markers(config)

        self.assertEqual(self.player.outro_bookmark, 1200)

    def test_set_chapter_based_markers_invalid_chapter(self):
        """Returns False when chapter numbers are out of range"""
        chapters = [{'time': 0, 'number': 1}, {'time': 100, 'number': 2}]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 5}  # 5 > len(chapters)
        self.assertFalse(self.player.set_chapter_based_markers(config))

    def test_set_chapter_based_markers_no_chapters(self):
        """Returns False when no chapters found"""
        self.player.getChapters = MagicMock(return_value=[])
        config = {'intro_start_chapter': 1, 'intro_end_chapter': 2}
        self.assertFalse(self.player.set_chapter_based_markers(config))

    def test_set_chapter_based_markers_missing_config(self):
        """Returns False when chapter config is missing"""
        chapters = [{'time': 0, 'number': 1}, {'time': 100, 'number': 2}]
        self.player.getChapters = MagicMock(return_value=chapters)
        self.assertFalse(self.player.set_chapter_based_markers(
            {'intro_start_chapter': None, 'intro_end_chapter': None}))

    def test_set_chapter_based_markers_network_seek_mode(self):
        """Chapter-seek mode when chapters have no 'time' field"""
        chapters = [
            {'number': 1, 'name': 'Chapter 1'},
            {'number': 2, 'name': 'Chapter 2'},
            {'number': 3, 'name': 'Chapter 3'},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': None}
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player._skip_to_chapter, 3)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 99999)
        self.assertIsNone(self.player.intro_duration)
        self.assertTrue(self.player.show_from_start)

    def test_set_chapter_based_markers_start_plus_duration(self):
        """Start chapter + duration mode calculates end from start + duration"""
        chapters = [
            {'time': 0, 'number': 1},
            {'time': 112, 'number': 2},
            {'time': 157, 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {
            'intro_start_chapter': 1,
            'intro_end_chapter': None,
            'intro_duration': 90,
            'outro_start_chapter': None
        }
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_start, 0)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.intro_duration, 90)

    def test_set_chapter_based_markers_end_plus_duration(self):
        """End chapter + duration mode calculates start from end - duration"""
        chapters = [
            {'time': 0, 'number': 1},
            {'time': 112, 'number': 2},
            {'time': 157, 'number': 3},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {
            'intro_start_chapter': None,
            'intro_end_chapter': 3,
            'intro_duration': 45,
            'outro_start_chapter': None
        }
        result = self.player.set_chapter_based_markers(config)

        self.assertTrue(result)
        self.assertEqual(self.player.intro_bookmark, 157)
        self.assertEqual(self.player.intro_start, 112)  # 157 - 45
        self.assertEqual(self.player.intro_duration, 45)

class TestSkipDialog(unittest.TestCase):
    """Tests for skip button display logic and actual skip execution"""

    def setUp(self):
        self.player = default.SkipIntroPlayer()
        self.player.getTime = MagicMock(return_value=35)
        self.player.seekTime = MagicMock()
        self.player.ui = MagicMock()

    def tearDown(self):
        if self.player.db:
            self.player.db.close()

    # --- show_skip_button ---

    def test_skip_button_shown(self):
        """Button should show when intro_bookmark is set"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35  # within window
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertTrue(self.player.prompt_shown)

    def test_skip_button_not_shown_twice(self):
        """Button should only show once per playback"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()
        self.player.show_skip_button()  # second call

        # prompt_skip_intro should have been called only once
        self.assertEqual(self.player.ui.prompt_skip_intro.call_count, 1)

    def test_skip_button_show_from_start_chapter_mode(self):
        """In chapter-only mode, button shows from time 0 until intro_bookmark"""
        self.player.show_from_start = True
        self.player.intro_start = 0
        self.player.intro_bookmark = 157
        self.player.getTime.return_value = 5  # near start
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertTrue(self.player.prompt_shown)

    def test_skip_button_not_shown_when_no_bookmark(self):
        """No button when intro_bookmark is None"""
        self.player.intro_bookmark = None
        self.player.intro_start = 30

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_not_called()

    def test_skip_button_handles_ui_failure(self):
        """prompt_shown stays False if UI fails to show the dialog"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35
        self.player.ui.prompt_skip_intro.return_value = False  # UI failure

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertFalse(self.player.prompt_shown)

    # --- skip_to_intro_end ---

    def test_skip_seeks_to_bookmark(self):
        """skip_to_intro_end should seekTime to intro_bookmark"""
        self.player.intro_bookmark = 157.074

        self.player.skip_to_intro_end()

        self.player.seekTime.assert_called_once_with(157.074)

    def test_skip_does_nothing_without_bookmark(self):
        """skip_to_intro_end should be a no-op if intro_bookmark is None"""
        self.player.intro_bookmark = None

        self.player.skip_to_intro_end()

        self.player.seekTime.assert_not_called()

    def test_skip_handles_seek_error(self):
        """skip_to_intro_end should not raise if seekTime throws"""
        self.player.intro_bookmark = 157.074
        self.player.seekTime.side_effect = RuntimeError("Player not ready")

        # Should not raise
        self.player.skip_to_intro_end()

    def test_skip_uses_chapter_seek_when_set(self):
        """skip_to_intro_end should use _seek_to_chapter when _skip_to_chapter is set"""
        self.player.intro_bookmark = 99999
        self.player._skip_to_chapter = 3
        self.player._seek_to_chapter = MagicMock(return_value=True)

        self.player.skip_to_intro_end()

        self.player._seek_to_chapter.assert_called_once_with(3)
        self.player.seekTime.assert_not_called()

    # --- onPlayBackTime (timer-driven skip) ---

    def test_warning_timer_triggers_skip_button(self):
        """onPlayBackTime should trigger show_skip_button when warning timer fires"""
        self.player.warning_timer_active = True
        self.player.warning_check_time = 30
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.onPlayBackTime(35)

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertFalse(self.player.warning_timer_active)

    def test_timer_does_not_trigger_before_threshold(self):
        """onPlayBackTime should not trigger before next_check_time"""
        self.player.timer_active = True
        self.player.next_check_time = 30
        self.player.intro_start = 30
        self.player.intro_bookmark = 90

        self.player.onPlayBackTime(20)  # before threshold

        self.player.ui.prompt_skip_intro.assert_not_called()
        self.assertTrue(self.player.timer_active)  # still active

    def test_timer_inactive_does_nothing(self):
        """onPlayBackTime should be a no-op when timer_active is False"""
        self.player.timer_active = False
        self.player.next_check_time = 30

        self.player.onPlayBackTime(35)

        self.player.ui.prompt_skip_intro.assert_not_called()

    # --- callback wiring ---

    def test_skip_button_callback_calls_seek(self):
        """The callback passed to prompt_skip_intro should call skip_to_intro_end"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 157.074
        self.player.getTime.return_value = 35

        # Capture the callback that gets passed to prompt_skip_intro
        captured_callback = None
        def capture_callback(cb):
            nonlocal captured_callback
            captured_callback = cb
            return True
        self.player.ui.prompt_skip_intro.side_effect = capture_callback

        self.player.show_skip_button()

        # Now invoke the captured callback (simulates user pressing the button)
        self.assertIsNotNone(captured_callback)
        captured_callback()

        self.player.seekTime.assert_called_once_with(157.074)


class TestSettings(unittest.TestCase):
    """Tests for Settings validation and bounds enforcement"""

    def test_default_settings(self):
        """Normal settings are read correctly"""
        s = default.Settings()
        self.assertTrue(s.settings['enable_autoskip'])
        self.assertEqual(s.settings['pre_skip_seconds'], 3)
        self.assertEqual(s.settings['delay_autoskip'], 0)
        self.assertEqual(s.settings['auto_dismiss_button'], 0)

    def test_get_setting(self):
        """get_setting returns individual values"""
        s = default.Settings()
        self.assertEqual(s.get_setting('pre_skip_seconds'), 3)
        self.assertIsNone(s.get_setting('nonexistent'))

    def test_invalid_settings_fall_back_to_defaults(self):
        """ValueError in settings returns all defaults"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting', return_value='not_a_number'):
            s = default.Settings()
            self.assertTrue(s.settings['enable_autoskip'])
            self.assertEqual(s.settings['pre_skip_seconds'], 3)
            self.assertEqual(s.settings['delay_autoskip'], 0)


class TestChapterManager(unittest.TestCase):
    """Tests for ChapterManager chapter lookup methods"""

    def setUp(self):
        from resources.lib.chapters import ChapterManager
        self.mgr = ChapterManager()
        self.chapters = [
            {'name': 'Start', 'time': 0, 'end_time': 112, 'number': 1},
            {'name': 'Intro', 'time': 112, 'end_time': 157, 'number': 2},
            {'name': 'Intro End', 'time': 157, 'end_time': 1352, 'number': 3},
            {'name': 'Credits', 'time': 1352, 'end_time': 1363, 'number': 4},
        ]

    def test_get_chapter_by_number(self):
        """Finds chapter by its number"""
        ch = self.mgr.get_chapter_by_number(self.chapters, 2)
        self.assertEqual(ch['name'], 'Intro')
        self.assertEqual(ch['time'], 112)

    def test_get_chapter_by_number_not_found(self):
        """Returns None for non-existent chapter number"""
        self.assertIsNone(self.mgr.get_chapter_by_number(self.chapters, 99))

    def test_get_chapter_by_number_none_input(self):
        """Returns None for None chapter number or empty list"""
        self.assertIsNone(self.mgr.get_chapter_by_number(self.chapters, None))
        self.assertIsNone(self.mgr.get_chapter_by_number([], 1))
        self.assertIsNone(self.mgr.get_chapter_by_number(None, 1))

    def test_get_intro_chapters(self):
        """Returns start and end chapter objects"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, 3)
        self.assertEqual(start['name'], 'Start')
        self.assertEqual(end['name'], 'Intro End')

    def test_get_intro_chapters_defaults_start_to_1(self):
        """When start_chapter is None/0, defaults to chapter 1"""
        start, end = self.mgr.get_intro_chapters(self.chapters, None, 3)
        self.assertEqual(start['number'], 1)
        self.assertEqual(end['number'], 3)

    def test_get_intro_chapters_missing_end(self):
        """Returns None, None when end_chapter is None"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, None)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_intro_chapters_invalid_end(self):
        """Returns None, None when end chapter not found"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 1, 99)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_intro_chapters_invalid_start(self):
        """Returns None, None when specific start chapter not found"""
        start, end = self.mgr.get_intro_chapters(self.chapters, 99, 3)
        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_get_outro_chapter(self):
        """Returns outro chapter object"""
        ch = self.mgr.get_outro_chapter(self.chapters, 4)
        self.assertEqual(ch['name'], 'Credits')

    def test_get_outro_chapter_none(self):
        """Returns None when no outro chapter configured"""
        self.assertIsNone(self.mgr.get_outro_chapter(self.chapters, None))

    def test_get_outro_chapter_not_found(self):
        """Returns None when outro chapter number doesn't exist"""
        self.assertIsNone(self.mgr.get_outro_chapter(self.chapters, 99))

    def test_find_chapter_by_name(self):
        """find_chapter_by_name finds intro chapter"""
        from resources.lib.chapters import ChapterManager as CM
        ch = CM.find_chapter_by_name(self.chapters, 'Intro')
        self.assertIsNotNone(ch)
        self.assertEqual(ch['name'], 'Intro')

    def test_find_chapter_by_name_none(self):
        """find_chapter_by_name returns None for no match"""
        from resources.lib.chapters import ChapterManager as CM
        ch = CM.find_chapter_by_name(self.chapters, 'NonExistent')
        self.assertIsNone(ch)

    def test_autodetect_intro_by_name(self):
        """autodetect_intro finds intro by 'Intro'/'Intro End' chapter names"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 112, 'number': 2},
            {'name': 'Intro End', 'time': 157, 'number': 3},
            {'name': 'Credits Starting', 'time': 1352, 'number': 4},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 2)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertEqual(result['intro_start_time'], 112)
        self.assertEqual(result['intro_end_time'], 157)
        self.assertEqual(result['outro_start_chapter'], 4)

    def test_autodetect_intro_no_match(self):
        """autodetect_intro returns None when no intro-named chapter exists"""
        chapters = [
            {'name': 'Chapter 1', 'time': 0, 'number': 1},
            {'name': 'Chapter 2', 'time': 100, 'number': 2},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNone(result)

    def test_autodetect_intro_by_next_chapter(self):
        """autodetect_intro uses next chapter as end when only 'Intro' found"""
        chapters = [
            {'name': 'Start', 'time': 0, 'number': 1},
            {'name': 'Intro', 'time': 30, 'number': 2},
            {'name': 'Main Content', 'time': 90, 'number': 3},
        ]
        result = self.mgr.autodetect_intro(chapters)
        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_chapter'], 2)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertEqual(result['intro_end_time'], 90)


class TestAudioIntroDetector(unittest.TestCase):
    """Tests for music-to-dialogue audio intro detection"""

    def test_detect_intro_from_music_silence_speech(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(min_music_seconds=120, min_speech_seconds=10)
        segments = [
            ('music', 0, 260),
            ('noEnergy', 260, 263),
            ('speech', 263, 320),
        ]

        result = detector.detect_intro_from_segments(segments)

        self.assertIsNotNone(result)
        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 263)

    def test_detect_intro_requires_long_music(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(min_music_seconds=120, min_speech_seconds=10)
        segments = [
            ('music', 0, 45),
            ('speech', 45, 120),
        ]

        self.assertIsNone(detector.detect_intro_from_segments(segments))

    def test_detect_show_intro_uses_median_across_episodes(self):
        from resources.lib.audio_intro import AudioIntroDetector
        detector = AudioIntroDetector(max_episodes=3)
        detector.analyze_file = MagicMock(side_effect=[
            {'intro_start_time': 0, 'intro_end_time': 260, 'source': 'audio'},
            {'intro_start_time': 0, 'intro_end_time': 263, 'source': 'audio'},
            {'intro_start_time': 0, 'intro_end_time': 301, 'source': 'audio'},
        ])

        result = detector.detect_show_intro(['e1.mkv', 'e2.mkv', 'e3.mkv'])

        self.assertEqual(result['intro_end_time'], 263)
        self.assertEqual(result['episode_count'], 3)
        self.assertEqual(len(result['episode_detections']), 3)

    def test_detect_show_intro_skips_unreadable_episode(self):
        from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector
        detector = AudioIntroDetector(max_episodes=2)
        detector.analyze_file = MagicMock(side_effect=[
            AudioIntroDetectionError('bad media'),
            {'intro_start_time': 0, 'intro_end_time': 263, 'source': 'audio'},
        ])

        result = detector.detect_show_intro(['bad.mkv', 'good.mkv'])

        self.assertEqual(result['intro_end_time'], 263)
        self.assertEqual(result['episode_count'], 1)

    def test_find_episode_candidates_uses_neighboring_video_files(self):
        from resources.lib.audio_intro import AudioIntroDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Show.S01E01.mkv', 'Show.S01E02.mkv', 'Show.S01E03.mkv', 'notes.txt']:
                open(os.path.join(tmpdir, name), 'w').close()

            selected = os.path.join(tmpdir, 'Show.S01E02.mkv')
            detector = AudioIntroDetector(max_episodes=2)
            result = detector.find_episode_candidates(selected)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].endswith('Show.S01E02.mkv'))
        self.assertTrue(result[1].endswith('Show.S01E03.mkv'))

    def test_find_episode_candidates_accepts_show_folder(self):
        from resources.lib.audio_intro import AudioIntroDetector
        with tempfile.TemporaryDirectory() as tmpdir:
            for name in ['Show.S01E01.mkv', 'Show.S01E02.mkv']:
                open(os.path.join(tmpdir, name), 'w').close()

            detector = AudioIntroDetector(max_episodes=2)
            result = detector.find_episode_candidates(tmpdir + os.sep)

        self.assertEqual(len(result), 2)
        self.assertTrue(result[0].endswith('Show.S01E01.mkv'))
        self.assertTrue(result[1].endswith('Show.S01E02.mkv'))


class TestMetadataFilenameEdgeCases(unittest.TestCase):
    """Tests for ShowMetadata filename parsing edge cases"""

    def setUp(self):
        from resources.lib.metadata import ShowMetadata
        self.metadata = ShowMetadata()

    def test_parse_sxxexx_format(self):
        """Standard SxxExx format"""
        result = self.metadata._parse_filename('/path/to/Friends.S02E05.720p.mkv')
        self.assertEqual(result['title'].strip(), 'Friends')
        self.assertEqual(result['season'], 2)
        self.assertEqual(result['episode'], 5)

    def test_parse_xxXxx_format(self):
        """Alternative xxXxx format"""
        result = self.metadata._parse_filename('/path/to/Friends.02x05.720p.mkv')
        self.assertEqual(result['title'].strip(), 'Friends')
        self.assertEqual(result['season'], 2)
        self.assertEqual(result['episode'], 5)

    def test_parse_show_with_dots(self):
        """Show names with dots get spaces"""
        result = self.metadata._parse_filename('/path/to/The.Office.US.S06E01.mkv')
        self.assertEqual(result['title'].strip(), 'The Office US')

    def test_parse_no_match_returns_none(self):
        """Returns None when filename doesn't match any pattern"""
        result = self.metadata._parse_filename('/path/to/random_movie.mkv')
        self.assertIsNone(result)

    def test_parse_case_insensitive(self):
        """Matches case-insensitively"""
        result = self.metadata._parse_filename('/path/to/show.s01e01.mkv')
        self.assertIsNotNone(result)
        self.assertEqual(result['season'], 1)
        self.assertEqual(result['episode'], 1)

    def test_parse_windows_path(self):
        """Handles backslash paths"""
        result = self.metadata._parse_filename('C:\\Videos\\Show.S01E01.mkv')
        self.assertIsNotNone(result)
        self.assertEqual(result['season'], 1)


class TestPlayerUI(unittest.TestCase):
    """Tests for PlayerUI and SkipIntroDialog"""

    def setUp(self):
        from resources.lib.ui import PlayerUI
        self.ui = PlayerUI()

    def test_initial_state(self):
        """PlayerUI starts with no dialog and prompt_shown=False"""
        self.assertFalse(self.ui.prompt_shown)
        self.assertIsNone(self.ui._dialog)

    def test_prompt_skip_intro_creates_dialog(self):
        """prompt_skip_intro creates and shows dialog"""
        callback = MagicMock()
        result = self.ui.prompt_skip_intro(callback)
        self.assertTrue(result)
        self.assertTrue(self.ui.prompt_shown)
        self.assertIsNotNone(self.ui._dialog)

    def test_prompt_skip_intro_only_once(self):
        """Second call returns False"""
        self.ui.prompt_skip_intro(MagicMock())
        result = self.ui.prompt_skip_intro(MagicMock())
        self.assertFalse(result)

    def test_cleanup_closes_dialog(self):
        """cleanup closes dialog and resets state"""
        self.ui.prompt_skip_intro(MagicMock())
        self.ui.cleanup()
        self.assertIsNone(self.ui._dialog)
        self.assertFalse(self.ui.prompt_shown)

    def test_cleanup_no_dialog(self):
        """cleanup is safe when no dialog exists"""
        self.ui.cleanup()  # should not raise

    def test_skip_intro_dialog_onclick_calls_callback(self):
        """SkipIntroDialog.onClick calls callback on button 1"""
        from resources.lib.ui import SkipIntroDialog
        callback = MagicMock()
        dialog = SkipIntroDialog('skip_button.xml', '.', 'default', '720p', callback=callback)
        dialog.onClick(1)
        callback.assert_called_once()

    def test_skip_intro_dialog_onclick_ignores_other_controls(self):
        """SkipIntroDialog.onClick ignores non-button controls"""
        from resources.lib.ui import SkipIntroDialog
        callback = MagicMock()
        dialog = SkipIntroDialog('skip_button.xml', '.', 'default', '720p', callback=callback)
        dialog.onClick(999)
        callback.assert_not_called()

    def test_show_notification_uses_dialog(self):
        """show_notification uses xbmcgui.Dialog().notification() not executebuiltin"""
        self.ui.show_notification('test message')
        # Should not raise - uses safe Dialog API


class TestContextModule(unittest.TestCase):
    """Tests for context.py input validation"""

    def test_get_time_input_valid(self):
        """Valid MM:SS input is accepted"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.return_value = '02:30'
        result = get_time_input(dialog, 'prompt')
        self.assertEqual(result, '02:30')

    def test_get_time_input_invalid_seconds(self):
        """Seconds >= 60 are rejected, user cancels retry"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.side_effect = ['02:70', '']  # bad, then empty
        dialog.yesno.return_value = False  # don't retry
        result = get_time_input(dialog, 'prompt', required=False)
        self.assertIsNone(result)

    def test_get_time_input_empty_optional(self):
        """Empty input on optional field returns None"""
        from context import get_time_input
        dialog = MagicMock()
        dialog.numeric.return_value = ''
        result = get_time_input(dialog, 'prompt', required=False)
        self.assertIsNone(result)

    def test_get_chapter_selection_valid(self):
        """Valid chapter numbers are accepted (full chapter mode)"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode (both start & end)
        dialog.numeric.side_effect = ['1', '3', '']  # start, end, no outro
        result = get_chapter_selection(dialog, None)
        self.assertEqual(result['intro_start_chapter'], 1)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertIsNone(result['outro_start_chapter'])
        self.assertTrue(result['use_chapters'])

    def test_get_chapter_selection_end_before_start(self):
        """End chapter <= start chapter is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode
        dialog.numeric.side_effect = ['3', '2', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog, None)
        self.assertIsNone(result)

    def test_get_chapter_selection_zero_chapter(self):
        """Chapter number 0 is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.select.return_value = 2  # Full chapter mode
        dialog.numeric.side_effect = ['0', '', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog, None)
        self.assertIsNone(result)

    def test_get_manual_time_input(self):
        """Manual time input converts MM:SS to seconds"""
        from context import get_manual_time_input
        dialog = MagicMock()
        dialog.numeric.side_effect = ['01:30', '03:00', '']  # start, end, no outro
        dialog.yesno.return_value = False
        result = get_manual_time_input(dialog, None)
        self.assertEqual(result['intro_start_time'], 90)
        self.assertEqual(result['intro_end_time'], 180)
        self.assertIsNone(result['outro_start_time'])

    def test_get_audio_intro_detection_confirms_detected_times(self):
        import context

        dialog = MagicMock()
        dialog.yesno.return_value = True
        fake_detector = MagicMock()
        fake_detector.find_episode_candidates.return_value = ['e1.mkv', 'e2.mkv']
        fake_detector.detect_show_intro.return_value = {
            'intro_start_time': 0,
            'intro_end_time': 263,
            'episode_count': 2,
            'matching_episode_count': 2,
        }

        with patch.object(context, 'AudioIntroDetector', return_value=fake_detector):
            result = context.get_audio_intro_detection(dialog, {'file': '/videos/e1.mkv'})

        self.assertEqual(result['intro_start_time'], 0)
        self.assertEqual(result['intro_end_time'], 263)
        self.assertEqual(result['source'], 'audio_detection')
        dialog.yesno.assert_called_once()


class TestDatabaseMigration(unittest.TestCase):
    """Tests for database schema creation and migration"""

    def setUp(self):
        from resources.lib.database import ShowDatabase
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.db = ShowDatabase(self.tmp.name)

    def tearDown(self):
        self.db.close()
        os.unlink(self.tmp.name)

    def test_tables_created(self):
        """All required tables exist after init"""
        import sqlite3
        with sqlite3.connect(self.tmp.name) as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in c.fetchall()}
        self.assertIn('shows', tables)
        self.assertIn('shows_config', tables)
        self.assertIn('episodes', tables)

    def test_shows_config_columns(self):
        """shows_config has all required columns"""
        import sqlite3
        with sqlite3.connect(self.tmp.name) as conn:
            c = conn.cursor()
            c.execute("PRAGMA table_info(shows_config)")
            columns = {row[1] for row in c.fetchall()}
        expected = {'show_id', 'use_chapters', 'intro_start_chapter', 'intro_end_chapter',
                    'intro_duration', 'intro_start_time', 'intro_end_time', 'outro_start_time', 'created_at'}
        self.assertTrue(expected.issubset(columns))

    def test_reinit_is_safe(self):
        """Re-initializing database doesn't lose data"""
        from resources.lib.database import ShowDatabase
        show_id = self.db.get_show('Persistent Show')
        self.db.set_manual_show_times(show_id, 10, 20, 30)

        db2 = ShowDatabase(self.tmp.name)
        config = db2.get_show_config(show_id)
        self.assertEqual(config['intro_start_time'], 10)

    def test_get_show_times_time_based(self):
        """get_show_times returns time-based config"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_times(show_id, 30, 90, 1200)
        times = self.db.get_show_times(show_id)
        self.assertFalse(times['use_chapters'])
        self.assertEqual(times['intro_start_time'], 30)

    def test_get_show_times_chapter_based(self):
        """get_show_times returns chapter-based config"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_chapters(show_id, True, 1, 3, 5)
        times = self.db.get_show_times(show_id)
        self.assertTrue(times['use_chapters'])
        self.assertEqual(times['intro_start_chapter'], 1)

    def test_get_show_times_no_config(self):
        """get_show_times returns None for unconfigured show"""
        show_id = self.db.get_show('New Show')
        # Default config has None times
        times = self.db.get_show_times(show_id)
        self.assertIsNotNone(times)

    def test_config_overwrite(self):
        """Saving config twice overwrites the first"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_times(show_id, 10, 20)
        self.db.set_manual_show_times(show_id, 50, 100, 200)
        config = self.db.get_show_config(show_id)
        self.assertEqual(config['intro_start_time'], 50)
        self.assertEqual(config['intro_end_time'], 100)

    def test_chapter_config_with_duration(self):
        """Chapter config with intro_duration is saved correctly"""
        show_id = self.db.get_show('Test')
        self.db.set_manual_show_chapters(show_id, True, 1, None, None, intro_duration=90)
        config = self.db.get_show_config(show_id)
        self.assertTrue(config['use_chapters'])
        self.assertEqual(config['intro_start_chapter'], 1)
        self.assertIsNone(config['intro_end_chapter'])
        self.assertEqual(config['intro_duration'], 90)


class TestShowManager(unittest.TestCase):
    """Tests for ShowManager facade"""

    def test_detect_show(self):
        """detect_show returns show info from metadata"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        result = mgr.detect_show()
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Test Show')
        self.assertEqual(mgr.current_show, result)

    def test_detect_show_no_video(self):
        """detect_show returns None when no info available"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        with patch('xbmc.getInfoLabel', return_value=''), \
             patch.object(MockXBMC.Player, 'isPlaying', return_value=False):
            result = mgr.detect_show()
            self.assertIsNone(result)

    def test_save_intro_time_no_db(self):
        """save_intro_time returns False without database"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()  # no db
        mgr.current_show = {'title': 'Test', 'season': 1, 'episode': 1}
        self.assertFalse(mgr.save_intro_time(30, 60))

    def test_get_saved_times_no_db(self):
        """get_saved_times returns None without database"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        self.assertIsNone(mgr.get_saved_times())

    def test_get_saved_times_no_show(self):
        """get_saved_times returns None without current_show"""
        from resources.lib.show import ShowManager
        mgr = ShowManager()
        mgr.current_show = None
        self.assertIsNone(mgr.get_saved_times())


if __name__ == '__main__':
    unittest.main()
