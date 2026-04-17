
import xbmc
import xbmcgui
import xbmcaddon
import xbmcvfs
import json
import os
from resources.lib.database import ShowDatabase
from resources.lib.metadata import ShowMetadata
from resources.lib.chapters import ChapterManager
from resources.lib.audio_intro import AudioIntroDetectionError, AudioIntroDetector

def get_selected_item_info():
    """Get info about the selected item in Kodi"""
    try:
        xbmc.log('SkipIntro: Getting selected item info', xbmc.LOGINFO)

        # Get info from selected list item
        showtitle = xbmc.getInfoLabel('ListItem.TVShowTitle')
        season = xbmc.getInfoLabel('ListItem.Season')
        episode = xbmc.getInfoLabel('ListItem.Episode')
        filepath = xbmc.getInfoLabel('ListItem.FileNameAndPath')

        # If we have all info from library (DBType), use it
        if showtitle and season and episode and filepath:
            try:
                item = {
                    'showtitle': showtitle,
                    'season': int(season),
                    'episode': int(episode),
                    'file': filepath
                }
                xbmc.log(f'SkipIntro: Found item from library - Show: {showtitle}, S{season}E{episode}', xbmc.LOGINFO)
                return item
            except ValueError as e:
                xbmc.log(f'SkipIntro: Error parsing season/episode from library: {str(e)}', xbmc.LOGWARNING)

        # Fallback: Try to parse from filename if not in library
        if filepath:
            xbmc.log('SkipIntro: Item not in library, attempting to parse from filename', xbmc.LOGINFO)
            metadata = ShowMetadata()
            # Try to parse show info from filename
            show_info = metadata._parse_filename(filepath)

            if show_info:
                item = {
                    'showtitle': show_info['title'],
                    'season': show_info['season'],
                    'episode': show_info['episode'],
                    'file': filepath
                }
                xbmc.log(f'SkipIntro: Parsed from filename - Show: {show_info["title"]}, S{show_info["season"]}E{show_info["episode"]}', xbmc.LOGINFO)
                return item
            else:
                xbmc.log('SkipIntro: Could not parse show info from filename', xbmc.LOGWARNING)
                # Still allow configuration with just filename if parsing fails
                # Use filename as show title
                from resources.lib.metadata import safe_basename
                filename = safe_basename(filepath)
                item = {
                    'showtitle': os.path.splitext(filename)[0],  # Use filename without extension as title
                    'season': 1,  # Default to season 1
                    'episode': 1,  # Default to episode 1
                    'file': filepath
                }
                xbmc.log(f'SkipIntro: Using filename as show title: {item["showtitle"]}', xbmc.LOGINFO)
                return item

        xbmc.log('SkipIntro: Missing required item info (no file path)', xbmc.LOGWARNING)
        return None

    except Exception as e:
        xbmc.log(f'SkipIntro: Error getting item info: {str(e)}', xbmc.LOGERROR)
        import traceback
        xbmc.log(f'SkipIntro: Traceback: {traceback.format_exc()}', xbmc.LOGERROR)
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
                if 0 <= minutes <= 999 and 0 <= seconds < 60:
                    return time_str  # Return the original formatted string
        except (ValueError, IndexError):
            pass

        if dialog.yesno('Skip Intro', 'Invalid time format. Try again?'):
            continue
        return None

def get_manual_times(show_id, db, item=None):
    """Get times manually from user input or select chapters"""
    try:
        dialog = xbmcgui.Dialog()

        # Get existing show config
        config = get_show_settings(show_id, db)

        # Detect which method was previously used
        is_using_chapters = config and config.get('use_chapters', False)
        is_using_manual = config and (config.get('intro_start_time') or config.get('intro_end_time'))

        # Build options list with indicator for previously used method
        options = [
            'Manual time input' + (' [Currently Used]' if is_using_manual else ''),
            'Chapter selection' + (' [Currently Used]' if is_using_chapters else ''),
            'Auto-detect from episode audio'
        ]

        # Ask user to choose between manual time input or chapter selection
        choice = dialog.select('Choose skip method', options)

        if choice == 0:  # Manual time input
            return get_manual_time_input(dialog, config)
        elif choice == 1:  # Chapter selection
            return get_chapter_selection(dialog, config)
        elif choice == 2:  # Audio auto-detection
            return get_audio_intro_detection(dialog, item)
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
    intro_start = get_time_input(dialog, 'When does intro START? (MM:SS, or empty for video start)', default_intro_start, required=False)
    if intro_start is None:
        return None

    intro_end = get_time_input(dialog, 'When does intro END? (MM:SS, e.g. 01:30)', default_intro_end, required=True)
    if intro_end is None:
        return None

    outro_start = get_time_input(dialog, 'Outro start time? (MM:SS, optional - leave empty to skip)', default_outro_start, required=False)

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

def get_chapter_selection(dialog, config):
    """Get chapter numbers for intro and outro"""
    # Get existing chapter values from config if available
    existing_intro_start = str(config.get('intro_start_chapter', '')) if config and config.get('intro_start_chapter') else ''
    existing_intro_end = str(config.get('intro_end_chapter', '')) if config and config.get('intro_end_chapter') else ''
    existing_intro_duration = str(config.get('intro_duration', '60')) if config and config.get('intro_duration') else '60'
    existing_outro_start = str(config.get('outro_start_chapter', '')) if config and config.get('outro_start_chapter') else ''

    # Detect which mode was previously used
    previous_mode = None
    if config and config.get('use_chapters'):
        if config.get('intro_start_chapter') and not config.get('intro_end_chapter') and config.get('intro_duration'):
            previous_mode = 0  # Start chapter + duration
        elif not config.get('intro_start_chapter') and config.get('intro_end_chapter') and config.get('intro_duration'):
            previous_mode = 1  # End chapter + duration
        elif config.get('intro_start_chapter') and config.get('intro_end_chapter'):
            previous_mode = 2  # Both start and end chapters

    # Build options list with indicator for previously used mode
    options = [
        'I know: Start chapter & how long intro lasts' + (' [Currently Used]' if previous_mode == 0 else ''),
        'I know: End chapter & how long intro lasts' + (' [Currently Used]' if previous_mode == 1 else ''),
        'I know: Both start & end chapters' + (' [Currently Used]' if previous_mode == 2 else '')
    ]

    # Ask user to choose configuration method with clear descriptions
    method = dialog.select('How would you like to configure skip times?', options)

    if method == -1:  # User cancelled
        return None

    if method == 0:
        # Start chapter + duration: Calculate end time from start + duration
        intro_start = dialog.numeric(0, 'Which chapter does the intro START at?', existing_intro_start)
        if not intro_start:
            return None
        intro_start = int(intro_start)
        if intro_start < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        intro_duration = dialog.numeric(0, 'How many seconds does the intro last? (e.g. 60)', existing_intro_duration)
        if not intro_duration:
            return None
        intro_duration = int(intro_duration)

        outro_start = dialog.numeric(0, 'Outro chapter (optional - leave empty to skip)', existing_outro_start)
        outro_start = int(outro_start) if outro_start else None
        if outro_start is not None and outro_start < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        return {
            'use_chapters': True,
            'intro_start_chapter': intro_start,
            'intro_end_chapter': None,  # Will be calculated from start + duration
            'intro_duration': intro_duration,
            'outro_start_chapter': outro_start,
            'intro_start_time': None,
            'intro_end_time': None,
            'outro_start_time': None
        }

    elif method == 1:
        # End chapter + duration: Calculate start time from end - duration
        intro_end = dialog.numeric(0, 'Which chapter does the intro END at?', existing_intro_end)
        if not intro_end:
            return None
        intro_end = int(intro_end)
        if intro_end < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        intro_duration = dialog.numeric(0, 'How many seconds does the intro last? (e.g. 90)', existing_intro_duration)
        if not intro_duration:
            return None
        intro_duration = int(intro_duration)

        outro_start = dialog.numeric(0, 'Outro chapter (optional - leave empty to skip)', existing_outro_start)
        outro_start = int(outro_start) if outro_start else None
        if outro_start is not None and outro_start < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        return {
            'use_chapters': True,
            'intro_start_chapter': None,  # Will be calculated from end - duration
            'intro_end_chapter': intro_end,
            'intro_duration': intro_duration,
            'outro_start_chapter': outro_start,
            'intro_start_time': None,
            'intro_end_time': None,
            'outro_start_time': None
        }

    else:  # method == 2
        # Full chapter-based: Specify both start and end
        intro_start = dialog.numeric(0, 'Which chapter does the intro START at?', existing_intro_start)
        if not intro_start:
            return None
        intro_start = int(intro_start)
        if intro_start < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        intro_end = dialog.numeric(0, 'Which chapter does the intro END at?', existing_intro_end)
        if not intro_end:
            return None
        intro_end = int(intro_end)
        if intro_end < 1 or intro_end <= intro_start:
            dialog.notification('Skip Intro', 'End chapter must be after start chapter', xbmcgui.NOTIFICATION_ERROR)
            return None

        outro_start = dialog.numeric(0, 'Outro chapter (optional - leave empty to skip)', existing_outro_start)
        outro_start = int(outro_start) if outro_start else None
        if outro_start is not None and outro_start < 1:
            dialog.notification('Skip Intro', 'Chapter number must be positive', xbmcgui.NOTIFICATION_ERROR)
            return None

        return {
            'use_chapters': True,
            'intro_start_chapter': intro_start,
            'intro_end_chapter': intro_end,
            'intro_duration': None,
            'outro_start_chapter': outro_start,
            'intro_start_time': None,
            'intro_end_time': None,
            'outro_start_time': None
        }

def format_seconds(seconds):
    """Format seconds as MM:SS for user-facing prompts."""
    seconds = int(round(seconds or 0))
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes:02d}:{secs:02d}"

def get_audio_intro_detection(dialog, item):
    """Auto-detect show intro timing from common cross-episode audio."""
    if not item or not item.get('file'):
        dialog.notification('Skip Intro', 'No episode file selected', xbmcgui.NOTIFICATION_ERROR)
        return None

    try:
        detector = AudioIntroDetector(backend='fingerprint')
        candidates = detector.find_episode_candidates(item['file'])
        dialog.notification(
            'Skip Intro',
            f'Analyzing audio from {len(candidates)} episode(s)',
            xbmcgui.NOTIFICATION_INFO
        )

        detected = detector.detect_show_intro(candidates)
        if not detected:
            dialog.notification('Skip Intro', 'No common intro audio found', xbmcgui.NOTIFICATION_WARNING)
            return None

        intro_start = detected.get('intro_start_time') or 0
        intro_end = detected.get('intro_end_time')
        if intro_end is None or intro_end <= intro_start:
            dialog.notification('Skip Intro', 'Audio detection returned invalid times', xbmcgui.NOTIFICATION_WARNING)
            return None

        episode_count = detected.get('episode_count', 1)
        matching_count = detected.get('matching_episode_count', episode_count)
        message = (
            f'Detected intro from {format_seconds(intro_start)} to {format_seconds(intro_end)} '
            f'using {matching_count}/{episode_count} analyzed episode(s). Save this for the show?'
        )
        if not dialog.yesno('Skip Intro', message):
            return None

        return {
            'intro_start_time': intro_start,
            'intro_end_time': intro_end,
            'outro_start_time': None,
            'source': 'audio_detection'
        }

    except AudioIntroDetectionError as e:
        xbmc.log(f'SkipIntro: Audio intro detection unavailable: {str(e)}', xbmc.LOGWARNING)
        dialog.notification('Skip Intro', str(e), xbmcgui.NOTIFICATION_ERROR)
        return None
    except Exception as e:
        xbmc.log(f'SkipIntro: Audio intro detection error: {str(e)}', xbmc.LOGERROR)
        dialog.notification('Skip Intro', 'Audio detection failed', xbmcgui.NOTIFICATION_ERROR)
        return None

def save_user_times():
    """Save user-provided times for show"""
    xbmc.log('SkipIntro: Starting manual time input', xbmc.LOGINFO)

    item = get_selected_item_info()
    if not item:
        xbmc.log('SkipIntro: No item selected', xbmc.LOGERROR)
        xbmcgui.Dialog().notification('Skip Intro', 'No item selected', xbmcgui.NOTIFICATION_ERROR)
        return

    from resources.lib.metadata import sanitize_path
    xbmc.log(f'SkipIntro: Selected item: {item["showtitle"]} S{item["season"]}E{item["episode"]}', xbmc.LOGINFO)

    # Initialize database
    xbmc.log('SkipIntro: Initializing database', xbmc.LOGINFO)
    addon = xbmcaddon.Addon()
    db_path = 'special://userdata/addon_data/plugin.video.skipintro/shows.db'

    translated_path = xbmcvfs.translatePath(db_path)
    from resources.lib.metadata import sanitize_path
    xbmc.log(f'SkipIntro: Database path translated: {sanitize_path(translated_path)}', xbmc.LOGINFO)

    # Ensure database directory exists
    db_dir = os.path.dirname(translated_path)
    if not xbmcvfs.exists(db_dir):
        xbmcvfs.mkdirs(db_dir)
        xbmc.log(f'SkipIntro: Created database directory', xbmc.LOGINFO)

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
    times = get_manual_times(show_id, db, item)
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
                times.get('outro_start_chapter'),
                times.get('intro_duration')
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
            if times.get('source') == 'audio_detection':
                db.save_episode_times(
                    show_id,
                    item.get('season'),
                    item.get('episode'),
                    {
                        'intro_start_time': times.get('intro_start_time'),
                        'intro_end_time': times.get('intro_end_time'),
                        'outro_start_time': times.get('outro_start_time'),
                        'source': 'audio_detection'
                    }
                )
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
