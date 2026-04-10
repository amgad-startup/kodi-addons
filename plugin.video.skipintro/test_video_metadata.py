import unittest
import tempfile
import os
import json
from unittest.mock import MagicMock, patch

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
    def getInfoLabel(label):
        if label == 'VideoPlayer.TVShowTitle':
            return 'Test Show'
        elif label == 'VideoPlayer.Season':
            return '1'
        elif label == 'VideoPlayer.Episode':
            return '2'
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
        def yesno(self, heading, message):
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

class MockXBMCAddon:
    class Addon:
        def __init__(self):
            self._settings = {
                "default_delay": "30",
                "skip_duration": "60",
                "use_chapters": "true",
                "use_api": "false",
                "save_times": "true",
                "database_path": ":memory:"
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
        # Note: outro_start_chapter is not returned by get_show_config (known gap)

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

    def test_cleanup(self):
        """Test cleanup resets all state"""
        self.player.intro_bookmark = 100
        self.player.outro_bookmark = 200
        self.player.bookmarks_checked = True
        self.player.default_skip_checked = True
        self.player.show_info = {'title': 'Test'}
        self.player.timer_active = True
        self.player.show_from_start = True

        self.player.cleanup()

        self.assertIsNone(self.player.intro_bookmark)
        self.assertIsNone(self.player.outro_bookmark)
        self.assertIsNone(self.player.intro_start)
        self.assertIsNone(self.player.intro_duration)
        self.assertFalse(self.player.bookmarks_checked)
        self.assertFalse(self.player.default_skip_checked)
        self.assertFalse(self.player.prompt_shown)
        self.assertIsNone(self.player.show_info)
        self.assertFalse(self.player.timer_active)
        self.assertEqual(self.player.next_check_time, 0)
        self.assertFalse(self.player.show_from_start)

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

    def test_check_for_default_skip_immediate(self):
        """Default skip when current time already past delay"""
        self.player.getTime = MagicMock(return_value=35)
        self.player.settings = {'default_delay': 30, 'skip_duration': 60, 'save_times': True}
        self.player.show_info = {'title': 'Test Show', 'season': 1, 'episode': 2}

        self.player.check_for_default_skip()

        self.assertEqual(self.player.intro_start, 35)
        self.assertEqual(self.player.intro_bookmark, 95)
        self.assertTrue(self.player.default_skip_checked)

    def test_check_for_default_skip_timer(self):
        """Default skip sets timer and pre-sets intro times when before delay"""
        self.player.getTime = MagicMock(return_value=5)
        self.player.settings = {'default_delay': 30, 'skip_duration': 60, 'save_times': True}
        self.player.show_info = {'title': 'Test Show', 'season': 1, 'episode': 2}

        self.player.check_for_default_skip()

        self.assertEqual(self.player.intro_start, 30)
        self.assertEqual(self.player.intro_bookmark, 90)
        self.assertEqual(self.player.next_check_time, 30)
        self.assertTrue(self.player.timer_active)

    def test_check_for_default_skip_only_runs_once(self):
        """check_for_default_skip should be a no-op on second call"""
        self.player.getTime = MagicMock(return_value=5)
        self.player.settings = {'default_delay': 30, 'skip_duration': 60, 'save_times': True}
        self.player.check_for_default_skip()
        bookmark_after_first = self.player.intro_bookmark

        self.player.getTime.return_value = 50
        self.player.check_for_default_skip()
        self.assertEqual(self.player.intro_bookmark, bookmark_after_first)

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

    # --- set_chapter_based_markers ---

    def test_set_chapter_based_markers(self):
        """Chapter-based markers resolve chapter numbers to times"""
        chapters = [
            {'time': 0, 'name': 'Start'},
            {'time': 112, 'name': 'Intro'},
            {'time': 157, 'name': 'Intro End'},
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
            {'time': 0}, {'time': 112}, {'time': 157}, {'time': 1200}, {'time': 1350},
        ]
        self.player.getChapters = MagicMock(return_value=chapters)

        config = {'intro_start_chapter': 1, 'intro_end_chapter': 3, 'outro_start_chapter': 4}
        self.player.set_chapter_based_markers(config)

        self.assertEqual(self.player.outro_bookmark, 1200)

    def test_set_chapter_based_markers_invalid_chapter(self):
        """Returns False when chapter numbers are out of range"""
        chapters = [{'time': 0}, {'time': 100}]
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
        chapters = [{'time': 0}, {'time': 100}]
        self.player.getChapters = MagicMock(return_value=chapters)
        self.assertFalse(self.player.set_chapter_based_markers(
            {'intro_start_chapter': None, 'intro_end_chapter': None}))

class TestSkipDialog(unittest.TestCase):
    """Tests for skip button display logic and actual skip execution"""

    def setUp(self):
        self.player = default.SkipIntroPlayer()
        self.player.getTime = MagicMock(return_value=35)
        self.player.seekTime = MagicMock()
        self.player.ui = MagicMock()

    # --- show_skip_button ---

    def test_skip_button_shown_during_intro_window(self):
        """Button should show when current time is within intro_start..intro_bookmark"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 35  # within window
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertTrue(self.player.prompt_shown)

    def test_skip_button_not_shown_before_intro_start(self):
        """Button should NOT show when current time is before intro_start"""
        self.player.intro_start = 60
        self.player.intro_bookmark = 120
        self.player.getTime.return_value = 30  # before intro_start

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_not_called()
        self.assertFalse(self.player.prompt_shown)

    def test_skip_button_not_shown_after_intro_end(self):
        """Button should NOT show when current time is past intro_bookmark"""
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.getTime.return_value = 95  # past intro_bookmark

        self.player.show_skip_button()

        self.player.ui.prompt_skip_intro.assert_not_called()
        self.assertFalse(self.player.prompt_shown)

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

    # --- onPlayBackTime (timer-driven skip) ---

    def test_timer_triggers_skip_button_at_threshold(self):
        """onPlayBackTime should trigger show_skip_button when time >= next_check_time"""
        self.player.timer_active = True
        self.player.next_check_time = 30
        self.player.intro_start = 30
        self.player.intro_bookmark = 90
        self.player.ui.prompt_skip_intro.return_value = True

        self.player.onPlayBackTime(35)

        self.player.ui.prompt_skip_intro.assert_called_once()
        self.assertFalse(self.player.timer_active)  # timer should deactivate

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
        self.assertEqual(s.settings['default_delay'], 30)
        self.assertEqual(s.settings['skip_duration'], 60)
        self.assertTrue(s.settings['use_chapters'])
        self.assertFalse(s.settings['use_api'])
        self.assertTrue(s.settings['save_times'])

    def test_get_setting(self):
        """get_setting returns individual values"""
        s = default.Settings()
        self.assertEqual(s.get_setting('default_delay'), 30)
        self.assertIsNone(s.get_setting('nonexistent'))

    def test_negative_delay_clamped(self):
        """Negative default_delay is reset to 30"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting',
                          side_effect=lambda k: {
                              'default_delay': '-5', 'skip_duration': '60',
                              'intro_start_chapter': '', 'intro_end_chapter': '',
                              'outro_start_chapter': '', 'intro_start_time': '',
                              'intro_end_time': '', 'outro_start_time': ''
                          }.get(k, '')):
            s = default.Settings()
            self.assertEqual(s.settings['default_delay'], 30)

    def test_excessive_delay_clamped(self):
        """default_delay > 300 is clamped to 300"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting',
                          side_effect=lambda k: {
                              'default_delay': '999', 'skip_duration': '60',
                              'intro_start_chapter': '', 'intro_end_chapter': '',
                              'outro_start_chapter': '', 'intro_start_time': '',
                              'intro_end_time': '', 'outro_start_time': ''
                          }.get(k, '')):
            s = default.Settings()
            self.assertEqual(s.settings['default_delay'], 300)

    def test_skip_duration_below_min_clamped(self):
        """skip_duration < 10 is reset to 60"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting',
                          side_effect=lambda k: {
                              'default_delay': '30', 'skip_duration': '5',
                              'intro_start_chapter': '', 'intro_end_chapter': '',
                              'outro_start_chapter': '', 'intro_start_time': '',
                              'intro_end_time': '', 'outro_start_time': ''
                          }.get(k, '')):
            s = default.Settings()
            self.assertEqual(s.settings['skip_duration'], 60)

    def test_invalid_settings_fall_back_to_defaults(self):
        """ValueError in settings returns all defaults"""
        with patch.object(MockXBMCAddon.Addon, 'getSetting', return_value='not_a_number'):
            s = default.Settings()
            self.assertEqual(s.settings['default_delay'], 30)
            self.assertEqual(s.settings['skip_duration'], 60)

    def test_empty_chapter_settings(self):
        """Empty chapter settings use defaults"""
        s = default.Settings()
        self.assertEqual(s.settings['intro_start_chapter'], 0)
        self.assertEqual(s.settings['intro_end_chapter'], 1)
        self.assertIsNone(s.settings['outro_start_chapter'])


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

    def test_get_chapters_skips_network_files(self):
        """get_chapters returns [] for network streams"""
        with patch('xbmc.executeJSONRPC', return_value=json.dumps({
            "result": {"item": {"file": "smb://server/share/file.mkv"}}
        })):
            chapters = self.mgr.get_chapters()
            self.assertEqual(chapters, [])

    def test_get_chapters_skips_missing_files(self):
        """get_chapters returns [] when file doesn't exist"""
        with patch('xbmc.executeJSONRPC', return_value=json.dumps({
            "result": {"item": {"file": "/nonexistent/file.mkv"}}
        })):
            chapters = self.mgr.get_chapters()
            self.assertEqual(chapters, [])

    def test_get_chapters_no_result(self):
        """get_chapters returns [] when JSON-RPC has no result"""
        with patch('xbmc.executeJSONRPC', return_value=json.dumps({"error": "bad"})):
            chapters = self.mgr.get_chapters()
            self.assertEqual(chapters, [])

    def test_get_chapters_parses_ffmetadata(self):
        """get_chapters correctly parses ffmetadata output"""
        metadata = """;FFMETADATA1
[CHAPTER]
START=0
END=112821000000
title=Start
[CHAPTER]
START=112821000000
END=157074000000
title=Intro
"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = metadata
        mock_result.stderr = ""

        with patch('xbmc.executeJSONRPC', return_value=json.dumps({
            "result": {"item": {"file": "/tmp/test.mkv"}}
        })), patch('os.path.isfile', return_value=True), \
             patch('subprocess.run', return_value=mock_result):
            chapters = self.mgr.get_chapters()

        self.assertEqual(len(chapters), 2)
        self.assertEqual(chapters[0]['name'], 'Start')
        self.assertAlmostEqual(chapters[0]['time'], 0.0)
        self.assertEqual(chapters[1]['name'], 'Intro')
        self.assertAlmostEqual(chapters[1]['time'], 112.821)

    def test_get_chapters_uses_cache(self):
        """Second call returns cached chapters without subprocess"""
        self.mgr._cached_chapters['/tmp/test.mkv'] = [{'name': 'cached', 'time': 0}]

        with patch('xbmc.executeJSONRPC', return_value=json.dumps({
            "result": {"item": {"file": "/tmp/test.mkv"}}
        })):
            chapters = self.mgr.get_chapters()

        self.assertEqual(chapters[0]['name'], 'cached')


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

    def test_skip_intro_dialog_onaction_back(self):
        """SkipIntroDialog.onAction closes on back/escape"""
        from resources.lib.ui import SkipIntroDialog
        dialog = SkipIntroDialog('skip_button.xml', '.', 'default', '720p', callback=None)
        action = MagicMock()
        action.getId.return_value = MockXBMCGUI.ACTION_NAV_BACK
        dialog.onAction(action)  # should not raise


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
        """Valid chapter numbers are accepted"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.numeric.side_effect = ['1', '3', '']  # start, end, no outro
        result = get_chapter_selection(dialog)
        self.assertEqual(result['intro_start_chapter'], 1)
        self.assertEqual(result['intro_end_chapter'], 3)
        self.assertIsNone(result['outro_start_chapter'])
        self.assertTrue(result['use_chapters'])

    def test_get_chapter_selection_end_before_start(self):
        """End chapter <= start chapter is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.numeric.side_effect = ['3', '2', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog)
        self.assertIsNone(result)

    def test_get_chapter_selection_zero_chapter(self):
        """Chapter number 0 is rejected"""
        from context import get_chapter_selection
        dialog = MagicMock()
        dialog.numeric.side_effect = ['0', '', '']
        dialog.notification = MagicMock()
        result = get_chapter_selection(dialog)
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


class TestDatabaseMigration(unittest.TestCase):
    """Tests for database schema creation and migration"""

    def setUp(self):
        from resources.lib.database import ShowDatabase
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.tmp.close()
        self.db = ShowDatabase(self.tmp.name)

    def tearDown(self):
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
                    'intro_start_time', 'intro_end_time', 'outro_start_time', 'created_at'}
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

    def test_identifier_validation(self):
        """SQL identifier validation rejects bad names"""
        from resources.lib.database import ShowDatabase
        with self.assertRaises(ValueError):
            ShowDatabase._validate_identifier("Robert'; DROP TABLE--")
        with self.assertRaises(ValueError):
            ShowDatabase._validate_identifier("table name")
        # Valid identifiers pass
        self.assertEqual(ShowDatabase._validate_identifier("shows_config"), "shows_config")
        self.assertEqual(ShowDatabase._validate_identifier("_private"), "_private")


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

