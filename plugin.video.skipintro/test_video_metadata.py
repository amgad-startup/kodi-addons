import unittest
import tempfile
import os
from unittest.mock import MagicMock, patch

# Mock Kodi modules
class MockXBMC:
    LOGDEBUG = 0
    LOGINFO = 1
    LOGERROR = 2
    
    @staticmethod
    def log(msg, level):
        pass
    
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
            
        def getPlayingFile(self):
            return '/path/to/Test.Show.S01E02.mkv'
            
    class Monitor:
        def __init__(self):
            pass

class MockXBMCGUI:
    class Dialog:
        def yesno(self, heading, message):
            return True

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
        """Set up test database"""
        from resources.lib.database import ShowDatabase
        self.db = ShowDatabase(':memory:')
        
    def test_show_operations(self):
        """Test show database operations"""
        # Add show
        show_id = self.db.get_show('Test Show')
        self.assertIsNotNone(show_id)
        
        # Add episode times
        success = self.db.save_episode_times(
            show_id, 1, 2, 30, 90, 2700, 2760, 'test'
        )
        self.assertTrue(success)
        
        # Get episode times
        times = self.db.get_episode_times(show_id, 1, 2)
        self.assertIsNotNone(times)
        self.assertEqual(times[0], 30)  # intro_start
        self.assertEqual(times[1], 90)  # intro_end
        self.assertEqual(times[2], 2700)  # outro_start
        self.assertEqual(times[3], 2760)  # outro_end

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
        """Test chapter detection"""
        # Test getting chapters
        chapters = self.metadata.get_chapters()
        if chapters:
            self.assertIsInstance(chapters, list)
            for chapter in chapters:
                self.assertIn('number', chapter)
                self.assertIn('name', chapter)
                self.assertIn('time', chapter)
        else:
            self.assertIsNone(chapters)

    def test_show_detection_filename(self):
        """Test show detection from filename"""
        # Mock Kodi info labels to return None
        with patch('xbmc.getInfoLabel', return_value=''):
            info = self.metadata.get_show_info()
            self.assertEqual(info['title'], 'Test Show')
            self.assertEqual(info['season'], 1)
            self.assertEqual(info['episode'], 2)

class TestSkipIntro(unittest.TestCase):
    def setUp(self):
        self.player = default.SkipIntroPlayer()
        
    def test_duration_parsing(self):
        """Test duration parsing in various formats"""
        # Test MM:SS format
        self.assertEqual(self.player.parse_duration("05:30"), 330)
        
        # Test HH:MM:SS format
        self.assertEqual(self.player.parse_duration("01:05:30"), 3930)
        
        # Test invalid format
        self.assertIsNone(self.player.parse_duration("invalid"))

    def test_validate_settings(self):
        """Test settings validation"""
        # Test normal values
        settings = default.validate_settings()
        self.assertEqual(settings['default_delay'], 30)
        self.assertEqual(settings['skip_duration'], 60)
        self.assertTrue(settings['use_chapters'])
        self.assertFalse(settings['use_api'])
        self.assertTrue(settings['save_times'])
        
        # Test below minimum
        with patch.object(default.addon, 'getSetting', side_effect=["-1", "5"]):
            settings = default.validate_settings()
            self.assertEqual(settings['default_delay'], 30)  # Should use default
            self.assertEqual(settings['skip_duration'], 60)  # Should use default
            
        # Test above maximum
        with patch.object(default.addon, 'getSetting', side_effect=["301", "301"]):
            settings = default.validate_settings()
            self.assertEqual(settings['default_delay'], 300)
            self.assertEqual(settings['skip_duration'], 300)

    def test_find_intro_chapter(self):
        """Test finding intro chapter"""
        chapters = [
            {"name": "Start", "time": 0},
            {"name": "Intro", "time": 120},
            {"name": "Intro End", "time": 180},
            {"name": "Main Content", "time": 200}
        ]
        
        intro_time = self.player.find_intro_chapter(chapters)
        self.assertEqual(intro_time, 180)

    def test_find_intro_chapter_no_intro(self):
        """Test finding intro chapter when none exists"""
        chapters = [
            {"name": "Start", "time": 0},
            {"name": "Main Content", "time": 120}
        ]
        
        intro_time = self.player.find_intro_chapter(chapters)
        self.assertIsNone(intro_time)

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

    def test_check_for_default_skip(self):
        """Test default skip check"""
        self.player.getTime = MagicMock(return_value=35)  # Mock current time
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
        
        self.assertEqual(self.player.intro_bookmark, 95)  # 35 + 60
        self.assertTrue(self.player.default_skip_checked)

if __name__ == '__main__':
    unittest.main()
