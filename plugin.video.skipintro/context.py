
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import os
from resources.lib.database import ShowDatabase
from resources.lib.metadata import ShowMetadata
from resources.lib.chapters import ChapterManager

def get_selected_item_info():
    """Get info about the selected item in Kodi"""
    try:
        xbmc.log('SkipIntro: Getting selected item info', xbmc.LOGINFO)
        
        # Get info from selected list item
        showtitle = xbmc.getInfoLabel('ListItem.TVShowTitle')
        season = xbmc.getInfoLabel('ListItem.Season')
        episode = xbmc.getInfoLabel('ListItem.Episode')
        filepath = xbmc.getInfoLabel('ListItem.FileNameAndPath')
        
        if not all([showtitle, season, episode, filepath]):
            xbmc.log('SkipIntro: Missing required item info', xbmc.LOGWARNING)
            return None
            
        item = {
            'showtitle': showtitle,
            'season': int(season),
            'episode': int(episode),
            'file': filepath
        }
        
        xbmc.log(f'SkipIntro: Found item - Show: {showtitle}, S{season}E{episode}', xbmc.LOGINFO)
        return item
    except Exception as e:
        xbmc.log(f'SkipIntro: Error getting item info: {str(e)}', xbmc.LOGERROR)
    return None

def get_show_settings(show_id, db):
    """Get show settings"""
    return db.get_show_config(show_id)

def get_time_input(dialog, prompt, default='', required=True):
    """Helper function to get properly formatted time input"""
    while True:
        # Use time input type (2) for MM:SS format, with default value if available
        time_str = dialog.numeric(2, prompt, default)
        if not time_str:
            if not required:
                return None
            if dialog.yesno('Skip Intro', 'This field is required. Try again?'):
                continue
            return None
        
        try:
            # Parse time input
            parts = time_str.split(':')
            if len(parts) == 2:
                minutes = int(parts[0])
                seconds = int(parts[1])
                if seconds < 60:
                    return time_str  # Return the original formatted string
        except:
            pass
        
        if dialog.yesno('Skip Intro', 'Invalid time format. Try again?'):
            continue
        return None

def get_manual_times(show_id, db):
    """Get times manually from user input or select chapters"""
    try:
        dialog = xbmcgui.Dialog()
        
        # Get existing show config
        config = get_show_settings(show_id, db)
        
        # Ask user to choose between manual time input or chapter selection
        choice = dialog.select('Choose skip method', ['Manual time input', 'Chapter selection'])
        
        if choice == 0:  # Manual time input
            return get_manual_time_input(dialog, config)
        elif choice == 1:  # Chapter selection
            return get_chapter_selection(dialog)
        else:
            return None
        
    except Exception as e:
        xbmc.log(f'SkipIntro: Error getting manual times: {str(e)}', xbmc.LOGERROR)
        return None

def get_manual_time_input(dialog, config):
    """Get times manually from user input"""
    # Convert seconds to MM:SS format
    def seconds_to_time(seconds):
        if seconds is None:
            return ''
        minutes = int(seconds) // 60
        secs = int(seconds) % 60
        return f"{minutes:02d}:{secs:02d}"

    # Get default values from existing config
    default_intro_start = seconds_to_time(config.get('intro_start_time')) if config else ''
    default_intro_end = seconds_to_time(config.get('intro_end_time')) if config else ''
    default_outro_start = seconds_to_time(config.get('outro_start_time')) if config else ''
    
    # Get times using the helper function with defaults
    intro_start = get_time_input(dialog, 'Enter Intro Start Time (0 or empty for video start)', default_intro_start, required=False)
    if intro_start is None:
        return None
        
    intro_end = get_time_input(dialog, 'Enter Intro End Time (required)', default_intro_end, required=True)
    if intro_end is None:
        return None
        
    outro_start = get_time_input(dialog, 'Enter Outro Start Time (optional)', default_outro_start, required=False)
    
    # Convert MM:SS to seconds
    def time_to_seconds(time_str):
        if not time_str:
            return None
        try:
            parts = time_str.split(':')
            return int(parts[0]) * 60 + int(parts[1]) if len(parts) == 2 else None
        except (ValueError, IndexError):
            return None
        
    return {
        'intro_start_time': time_to_seconds(intro_start),
        'intro_end_time': time_to_seconds(intro_end),
        'outro_start_time': time_to_seconds(outro_start) if outro_start else None
    }

def get_chapter_selection(dialog):
    """Get chapter numbers for intro and outro"""
    intro_start = dialog.numeric(0, 'Enter Intro Start Chapter Number', '')
    if not intro_start:
        return None
    intro_start = int(intro_start)

    intro_end = dialog.numeric(0, 'Enter Intro End Chapter Number', '')
    if not intro_end:
        return None
    intro_end = int(intro_end)

    outro_start = dialog.numeric(0, 'Enter Outro Start Chapter Number (Optional)', '')
    outro_start = int(outro_start) if outro_start else None

    return {
        'use_chapters': True,
        'intro_start_chapter': intro_start,
        'intro_end_chapter': intro_end,
        'outro_start_chapter': outro_start,
        'intro_start_time': None,
        'intro_end_time': None,
        'outro_start_time': None
    }

def save_user_times():
    """Save user-provided times for show"""
    xbmc.log('SkipIntro: Starting manual time input', xbmc.LOGINFO)
    
    item = get_selected_item_info()
    if not item:
        xbmc.log('SkipIntro: No item selected', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Skip Intro', 'No item selected', xbmcgui.NOTIFICATION_ERROR)
        return
    
    xbmc.log(f'SkipIntro: Selected item info: {item}', xbmc.LOGINFO)
        
    # Initialize database
    xbmc.log('SkipIntro: Initializing database', xbmc.LOGINFO)
    addon = xbmcaddon.Addon()
    db_path = addon.getSetting('database_path')
    if not db_path:
        db_path = 'special://userdata/addon_data/plugin.video.skipintro/shows.db'
    
    translated_path = xbmcvfs.translatePath(db_path)
    xbmc.log(f'SkipIntro: Database path translated: {translated_path}', xbmc.LOGINFO)
    
    # Ensure database directory exists
    db_dir = os.path.dirname(translated_path)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
        xbmc.log(f'SkipIntro: Created database directory: {db_dir}', xbmc.LOGINFO)
    
    try:
        db = ShowDatabase(translated_path)
        if not db:
            raise Exception("Failed to initialize database")
        xbmc.log('SkipIntro: Database initialized successfully', xbmc.LOGINFO)
    except Exception as e:
        xbmc.log(f'SkipIntro: Database initialization error: {str(e)}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Skip Intro', 'Database error', xbmcgui.NOTIFICATION_ERROR)
        return
    
    show_id = db.get_show(item['showtitle'])
    if not show_id:
        xbmc.log('SkipIntro: Failed to get show ID', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Skip Intro', 'Database error', xbmcgui.NOTIFICATION_ERROR)
        return
    
    xbmc.log(f'SkipIntro: Got show ID: {show_id}', xbmc.LOGINFO)
    
    # Get times from user
    times = get_manual_times(show_id, db)
    if times is None:
        xbmc.log('SkipIntro: User cancelled time input', xbmc.LOGINFO)
        return
    
    xbmc.log(f'SkipIntro: User input times: {times}', xbmc.LOGINFO)
    
    # Save times or chapters for the show
    try:
        if 'use_chapters' in times and times['use_chapters']:
            xbmc.log('SkipIntro: Saving chapter-based configuration', xbmc.LOGINFO)
            success = db.set_manual_show_chapters(
                show_id,
                times['use_chapters'],
                times.get('intro_start_chapter'),
                times.get('intro_end_chapter'),
                times.get('outro_start_chapter')
            )
        else:
            xbmc.log('SkipIntro: Saving time-based configuration', xbmc.LOGINFO)
            success = db.set_manual_show_times(
                show_id,
                times.get('intro_start_time'),
                times.get('intro_end_time'),
                times.get('outro_start_time')
            )
        
        if success:
            xbmc.log('SkipIntro: Show times saved successfully', xbmc.LOGINFO)
            xbmcgui.Dialog().notification('Skip Intro', 'Times saved successfully', xbmcgui.NOTIFICATION_INFO)
        else:
            raise Exception("Failed to save show times")
    except Exception as e:
        xbmc.log(f'SkipIntro: Error saving show times: {str(e)}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Skip Intro', 'Failed to save times', xbmcgui.NOTIFICATION_ERROR)
    
    # Verify saved times
    saved_config = db.get_show_config(show_id)
    xbmc.log(f'SkipIntro: Verified saved configuration: {saved_config}', xbmc.LOGINFO)

if __name__ == '__main__':
    save_user_times()
