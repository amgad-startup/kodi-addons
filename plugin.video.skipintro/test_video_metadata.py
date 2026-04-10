import unittest
import tempfile
import os
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
        
    @unittest.skip("parse_duration was removed from SkipIntroPlayer")
    def test_duration_parsing(self):
        """Test duration parsing in various formats"""
        pass

    @unittest.skip("validate_settings was moved to Settings class")
    def test_validate_settings(self):
        """Test settings validation"""
        pass

    @unittest.skip("find_intro_chapter was removed from ChapterManager")
    def test_find_intro_chapter(self):
        """Test finding intro chapter"""
        pass

    @unittest.skip("find_intro_chapter was removed from ChapterManager")
    def test_find_intro_chapter_no_intro(self):
        """Test finding intro chapter when none exists"""
        pass

    def test_cleanup(self):
        """Test cleanup method"""
        self.player.intro_bookmark = 100
        self.player.outro_bookmark = 200
        self.player.bookmarks_checked = True
        self.player.default_skip_checked = True
        self.player.show_info = {'title': 'Test'}
        
        self.player.cleanup()
        
        self.assertIsNone(self.player.intro_bookmark)
        self.assertIsNone(self.player.outro_bookmark)
        self.assertFalse(self.player.bookmarks_checked)
        self.assertFalse(self.player.default_skip_checked)
        self.assertIsNone(self.player.show_info)

    def test_check_for_default_skip_immediate(self):
        """Test default skip when current time already past delay"""
        self.player.getTime = MagicMock(return_value=35)  # past default_delay
        self.player.settings = {
            'default_delay': 30,
            'skip_duration': 60,
            'save_times': True
        }
        self.player.show_info = {
            'title': 'Test Show',
            'season': 1,
            'episode': 2
        }

        self.player.check_for_default_skip()

        self.assertEqual(self.player.intro_start, 35)  # current_time
        self.assertEqual(self.player.intro_bookmark, 95)  # 35 + 60
        self.assertTrue(self.player.default_skip_checked)

    def test_check_for_default_skip_timer(self):
        """Test default skip sets timer and pre-sets intro times when before delay"""
        self.player.getTime = MagicMock(return_value=5)  # before default_delay
        self.player.settings = {
            'default_delay': 30,
            'skip_duration': 60,
            'save_times': True
        }
        self.player.show_info = {
            'title': 'Test Show',
            'season': 1,
            'episode': 2
        }

        self.player.check_for_default_skip()

        self.assertEqual(self.player.intro_start, 30)  # default_delay
        self.assertEqual(self.player.intro_bookmark, 90)  # 30 + 60
        self.assertEqual(self.player.next_check_time, 30)
        self.assertTrue(self.player.timer_active)
        self.assertTrue(self.player.default_skip_checked)

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


if __name__ == '__main__':
    unittest.main()

