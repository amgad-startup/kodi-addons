# Add these lines at the very beginning of default.py, before any other imports
try:
    import ptvsd
    ptvsd.enable_attach(address=('localhost', 5678))
    # If you want the script to wait for the debugger to attach, uncomment next line
    # ptvsd.wait_for_attach()
except:
    pass

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs
import os
import time

from resources.lib.settings import Settings
from resources.lib.chapters import ChapterManager
from resources.lib.ui import PlayerUI
from resources.lib.show import ShowManager
from resources.lib.database import ShowDatabase
from resources.lib.metadata import ShowMetadata

addon = xbmcaddon.Addon()

def get_database():
    """Initialize and return database connection"""
    try:
        db_path = addon.getSetting('database_path')
        if not db_path:
            db_path = 'special://userdata/addon_data/plugin.video.skipintro/shows.db'
        
        # Ensure directory exists
        translated_path = xbmcvfs.translatePath(db_path)
        db_dir = os.path.dirname(translated_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
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
        self.default_skip_checked = False
        self.prompt_shown = False
        self.show_info = None
        self.db = get_database()
        self.metadata = ShowMetadata()
        self.ui = PlayerUI()
        self.show_from_start = False  # New flag for chapter-only mode
        
        # Initialize settings
        self.settings_manager = Settings()
        self.settings = self.settings_manager.settings
        
        # New timing control variables
        self.timer_active = False
        self.next_check_time = 0
        
    def onPlayBackStopped(self):
        """Called when playback is stopped by user"""
        self.cleanup()
        
    def onPlayBackEnded(self):
        """Called when playback ends naturally"""
        self.cleanup()
        
    def onPlayBackStarted(self):
        """Called when Kodi starts playing a file"""
        xbmc.log('SkipIntro: Playback started', xbmc.LOGINFO)
        self.cleanup()  # Reset state for new playback
        
    def onAVStarted(self):
        """Called when Kodi has prepared audio/video for the file"""
        xbmc.log('SkipIntro: AV started', xbmc.LOGINFO)
        # Reset flags for new video
        self.bookmarks_checked = False
        self.prompt_shown = False
        self.default_skip_checked = False
        self.timer_active = False
        self.next_check_time = 0
        self.show_from_start = False
        
        # Wait longer for video info and chapters to be available
        xbmc.sleep(5000)  # Initial 5 second wait
        if not self.isPlaying():
            return
            
        self.detect_show()
        
        # Additional wait for chapters with player state validation
        xbmc.sleep(3000)  # 3 more seconds
        if not self.isPlaying():
            return
            
        if self.show_info:
            # First check saved times
            self.check_saved_times()
            
            # If no saved times and chapters enabled AND show is configured to use chapters, check chapters
            if not self.intro_bookmark and self.settings['use_chapters'] and self.show_info:
                show_id = self.db.get_show(self.show_info['title'])
                if show_id:
                    config = self.db.get_show_config(show_id)
                    if config and config['use_chapters']:
                        chapters = self.getChapters()
                        if chapters:
                            xbmc.log(f'SkipIntro: Found {len(chapters)} chapters', xbmc.LOGINFO)
                            self.check_for_intro_chapter()
            
            # If still no intro bookmark, use default skip
            if not self.intro_bookmark:
                self.check_for_default_skip()
            self.bookmarks_checked = True
            
            # If we have intro times, set up the timer
            if self.intro_bookmark is not None:
                current_time = self.getTime()
                if self.show_from_start:
                    # For chapter-only mode, show button from start
                    self.next_check_time = 0
                    self.timer_active = True
                    xbmc.log('SkipIntro: Timer set to show button from start', xbmc.LOGINFO)
                elif self.intro_start is not None and current_time < self.intro_start:
                    # Set timer to wake up at intro start
                    self.next_check_time = self.intro_start
                    self.timer_active = True
                    xbmc.log(f'SkipIntro: Timer set to check at {self.next_check_time}', xbmc.LOGINFO)
                elif current_time < self.intro_bookmark:
                    # Already in intro period, show button immediately
                    self.show_skip_button()

    def onPlayBackTime(self, time):
        """Called during playback with current time"""
        if not self.prompt_shown and self.timer_active:
            if time >= self.next_check_time:
                xbmc.log(f'SkipIntro: Timer triggered at {time}', xbmc.LOGINFO)
                self.show_skip_button()
                self.timer_active = False  # Disable timer after showing button

    def show_skip_button(self):
        """Show skip intro button and handle timing"""
        if not self.prompt_shown and self.intro_bookmark is not None:
            current_time = self.getTime()
            show_button = False
            
            if self.show_from_start:
                # For chapter-only mode, show button until end chapter
                show_button = current_time < self.intro_bookmark
            elif self.intro_start is not None:
                # For normal mode, show button during intro period
                show_button = current_time >= self.intro_start and current_time < self.intro_bookmark
            
            if show_button:
                xbmc.log(f'SkipIntro: Showing skip button at {current_time}', xbmc.LOGINFO)
                if self.ui.prompt_skip_intro(lambda: self.skip_to_intro_end()):
                    self.prompt_shown = True
                    xbmc.log('SkipIntro: Skip button shown successfully', xbmc.LOGINFO)
                else:
                    xbmc.log('SkipIntro: Failed to show skip button', xbmc.LOGWARNING)
            else:
                xbmc.log(f'SkipIntro: Not showing skip button. Current time: {current_time}, Intro start: {self.intro_start}, Intro end: {self.intro_bookmark}', xbmc.LOGINFO)

    def detect_show(self):
        """Detect current TV show and episode"""
        if not self.isPlaying():
            xbmc.log('SkipIntro: Not playing, skipping show detection', xbmc.LOGINFO)
            return
            
        playing_file = self.getPlayingFile()
        xbmc.log(f'SkipIntro: Detecting show for file: {playing_file}', xbmc.LOGINFO)
            
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

            # Get show config
            config = self.db.get_show_config(show_id)
            xbmc.log(f'SkipIntro: Show config: {config}', xbmc.LOGINFO)
            
            if config:
                if config.get('use_chapters'):
                    self.set_chapter_based_markers(config)
                else:
                    self.set_time_based_markers(config, "show config")
            else:
                # If no config, use default times
                default_times = {
                    'intro_start_time': 0,
                    'intro_end_time': 120,  # Default 2-minute intro
                    'outro_start_time': None
                }
                self.set_time_based_markers(default_times, "default")

        except Exception as e:
            xbmc.log('SkipIntro: Error checking saved times: {}'.format(str(e)), xbmc.LOGERROR)
        
        xbmc.log('SkipIntro: Final times - intro_start: {}, duration: {}, outro_start: {}, bookmark: {}, show_from_start: {}'.format(
            self.intro_start, self.intro_duration, self.outro_bookmark, self.intro_bookmark, self.show_from_start), xbmc.LOGINFO)

    def set_time_based_markers(self, times, source_desc):
        """Set time-based markers"""
        self.intro_start = times.get('intro_start_time')
        self.intro_bookmark = times.get('intro_end_time')
        if self.intro_start is not None and self.intro_bookmark is not None:
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
            xbmc.log('SkipIntro: No chapters found for chapter-based markers', xbmc.LOGWARNING)
            return False

        intro_start_chapter = config.get('intro_start_chapter')
        intro_end_chapter = config.get('intro_end_chapter')
        outro_start_chapter = config.get('outro_start_chapter')

        if intro_start_chapter is not None and intro_end_chapter is not None:
            if 1 <= intro_start_chapter <= len(chapters) and 1 <= intro_end_chapter <= len(chapters):
                self.intro_start = chapters[intro_start_chapter - 1]['time']
                self.intro_bookmark = chapters[intro_end_chapter - 1]['time']
                self.intro_duration = self.intro_bookmark - self.intro_start
                self.show_from_start = intro_start_chapter == 1
                
                if outro_start_chapter is not None and 1 <= outro_start_chapter <= len(chapters):
                    self.outro_bookmark = chapters[outro_start_chapter - 1]['time']
                
                xbmc.log(f'SkipIntro: Using chapter-based markers - start: {self.intro_start}, end: {self.intro_bookmark}', xbmc.LOGINFO)
                return True
            else:
                xbmc.log('SkipIntro: Invalid chapter numbers for intro/outro', xbmc.LOGWARNING)
        else:
            xbmc.log('SkipIntro: Missing intro start or end chapter', xbmc.LOGWARNING)
        
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
                        if abs(chapter['time'] - intro_start) < 0.1:  # Compare with small tolerance
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
                        
                        if self.settings['save_times'] and self.show_info and self.db:
                            show_id = self.db.get_show(self.show_info['title'])
                            times = {
                                'intro_start_time': self.intro_start,
                                'intro_end_time': self.intro_bookmark,
                                'intro_start_chapter': intro_chapter_index + 1,  # Convert to 1-based index
                                'intro_end_chapter': intro_chapter_index + 2,
                                'outro_start_time': None,
                                'source': 'chapters'
                            }
                            self.db.save_episode_times(
                                show_id,
                                self.show_info['season'],
                                self.show_info['episode'],
                                times
                            )
                else:
                    self.bookmarks_checked = True
            else:
                self.check_for_default_skip()
        except Exception as e:
            xbmc.log('SkipIntro: Error in check_for_intro_chapter: {}'.format(str(e)), xbmc.LOGERROR)
            self.bookmarks_checked = True

    def getChapters(self):
        chapter_manager = ChapterManager()
        return chapter_manager.get_chapters()

    def find_intro_chapter(self, chapters):
        chapter_manager = ChapterManager()
        return chapter_manager.find_intro_chapter(chapters)

    def check_for_default_skip(self):
        if self.default_skip_checked:
            xbmc.log('SkipIntro: Default skip already checked', xbmc.LOGINFO)
            return

        try:
            current_time = self.getTime()
            default_delay = self.settings['default_delay']
            skip_duration = self.settings['skip_duration']
            
            xbmc.log(f'SkipIntro: Checking default skip - current time: {current_time}, delay: {default_delay}', xbmc.LOGINFO)
            
            if current_time >= default_delay:
                self.intro_bookmark = current_time + skip_duration
                xbmc.log(f'SkipIntro: Using default skip - will skip to: {self.intro_bookmark}', xbmc.LOGINFO)
                self.show_skip_button()
            else:
                # Set up timer for default skip
                self.next_check_time = default_delay
                self.timer_active = True
                xbmc.log(f'SkipIntro: Set timer for default skip at {default_delay}', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('SkipIntro: Error in default skip check: {}'.format(str(e)), xbmc.LOGERROR)

        self.default_skip_checked = True

    def skip_to_intro_end(self):
        if self.intro_bookmark:
            try:
                current_time = self.getTime()
                xbmc.log(f'SkipIntro: Skipping from {current_time} to {self.intro_bookmark} seconds', xbmc.LOGINFO)
                self.seekTime(self.intro_bookmark)
                xbmc.log('SkipIntro: Skip completed', xbmc.LOGINFO)
            except Exception as e:
                xbmc.log('SkipIntro: Error skipping to intro end: {}'.format(str(e)), xbmc.LOGERROR)

    def cleanup(self):
        """Clean up resources"""
        self.ui.cleanup()
        self.intro_start = None
        self.intro_duration = None
        self.intro_bookmark = None
        self.outro_bookmark = None
        self.bookmarks_checked = False
        self.default_skip_checked = False
        self.prompt_shown = False
        self.show_info = None
        self.timer_active = False
        self.next_check_time = 0
        self.show_from_start = False

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
            minutes, seconds = map(int, time_str.split(':'))
            return minutes * 60 + seconds

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
            if monitor.waitForAbort(0.5):  # Check every 500ms
                break
                
            if player.isPlaying() and player.timer_active:
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
        except:
            pass  # Ensure we don't hang during cleanup

if __name__ == '__main__':
    main()
