import xbmc
import xbmcaddon

class Settings:
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.settings = self.validate_settings()

    def validate_settings(self):
        """Validate and sanitize addon settings"""
        try:
            default_delay = int(self.addon.getSetting('default_delay'))
            skip_duration = int(self.addon.getSetting('skip_duration'))
            use_chapters = self.addon.getSettingBool('use_chapters')
            use_api = self.addon.getSettingBool('use_api')
            save_times = self.addon.getSettingBool('save_times')
            
            # Get chapter settings
            intro_start_chapter = self.addon.getSetting('intro_start_chapter')
            intro_end_chapter = self.addon.getSetting('intro_end_chapter')
            outro_start_chapter = self.addon.getSetting('outro_start_chapter')
            
            # Get time settings
            intro_start_time = self.addon.getSetting('intro_start_time')
            intro_end_time = self.addon.getSetting('intro_end_time')
            outro_start_time = self.addon.getSetting('outro_start_time')
            
            # Convert chapter settings (handle empty values)
            intro_start_chapter = int(intro_start_chapter) if intro_start_chapter else 0
            intro_end_chapter = int(intro_end_chapter) if intro_end_chapter else 1
            outro_start_chapter = int(outro_start_chapter) if outro_start_chapter else None
            
            # Convert time settings (handle empty values)
            intro_start_time = int(intro_start_time) if intro_start_time else 0
            intro_end_time = int(intro_end_time) if intro_end_time else 90
            outro_start_time = int(outro_start_time) if outro_start_time else None
            
            # Ensure values are within reasonable bounds
            if default_delay < 0:
                default_delay = 30
                self.addon.setSetting('default_delay', '30')
            elif default_delay > 300:  # Max 5 minutes
                default_delay = 300
                self.addon.setSetting('default_delay', '300')
                
            if skip_duration < 10:  # Min 10 seconds
                skip_duration = 60
                self.addon.setSetting('skip_duration', '60')
            elif skip_duration > 300:  # Max 5 minutes
                skip_duration = 300
                self.addon.setSetting('skip_duration', '300')
                
            return {
                'default_delay': default_delay,
                'skip_duration': skip_duration,
                'use_chapters': use_chapters,
                'use_api': use_api,
                'save_times': save_times,
                'intro_start_chapter': intro_start_chapter,
                'intro_end_chapter': intro_end_chapter,
                'outro_start_chapter': outro_start_chapter,
                'intro_start_time': intro_start_time,
                'intro_end_time': intro_end_time,
                'outro_start_time': outro_start_time
            }
        except ValueError as e:
            xbmc.log('SkipIntro: Error reading settings: {} - using defaults'.format(str(e)), xbmc.LOGERROR)
            return {
                'default_delay': 30,
                'skip_duration': 60,
                'use_chapters': True,
                'use_api': False,
                'save_times': True,
                'intro_start_chapter': 0,
                'intro_end_chapter': 1,
                'outro_start_chapter': None,
                'intro_start_time': 0,
                'intro_end_time': 90,
                'outro_start_time': None
            }

    def get_setting(self, key):
        return self.settings.get(key)
