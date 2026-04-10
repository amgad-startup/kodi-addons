import xbmc
from typing import List, Dict, Union, Optional

class ChapterManager:
    """Chapter utility methods for skip intro functionality.

    Chapter data is obtained via ShowMetadata.get_chapters() (InfoLabels).
    This class provides helper methods for looking up chapters by number
    and identifying intro/outro chapters.
    """

    def __init__(self):
        self._cached_chapters = {}

    def get_chapters(self) -> List[Dict[str, Union[str, int, float]]]:
        """Get chapter information using Kodi InfoLabels.

        Returns a list of chapter dicts with 'number' keys.
        Timestamps are not available via InfoLabels alone.
        """
        try:
            if not xbmc.Player().isPlayingVideo():
                return []

            count_str = xbmc.getInfoLabel('Player.ChapterCount')
            chapter_count = int(count_str) if count_str and count_str.isdigit() else 0

            if chapter_count == 0:
                return []

            xbmc.log(f'SkipIntro: Found {chapter_count} chapters via InfoLabels', xbmc.LOGINFO)
            return [{'number': i + 1, 'name': f'Chapter {i + 1}'} for i in range(chapter_count)]

        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting chapters: {str(e)}', xbmc.LOGERROR)
            return []

    def get_chapter_by_number(self, chapters, chapter_number):
        """Get chapter info by chapter number."""
        if not chapters or chapter_number is None:
            return None

        try:
            for chapter in chapters:
                if chapter['number'] == chapter_number:
                    return chapter
            return None
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting chapter by number: {str(e)}', xbmc.LOGERROR)
            return None

    def get_intro_chapters(self, chapters, start_chapter, end_chapter):
        """Get intro start and end chapters based on configured chapter numbers."""
        if not chapters or end_chapter is None:  # end chapter is required
            return None, None

        try:
            # Get start chapter (optional, defaults to first chapter)
            start = self.get_chapter_by_number(chapters, start_chapter if start_chapter else 1)
            if not start and start_chapter:  # Only fail if specific start chapter was requested
                xbmc.log(f'SkipIntro: Start chapter {start_chapter} not found', xbmc.LOGWARNING)
                return None, None

            # Get end chapter (required)
            end = self.get_chapter_by_number(chapters, end_chapter)
            if not end:
                xbmc.log(f'SkipIntro: End chapter {end_chapter} not found', xbmc.LOGWARNING)
                return None, None

            return start, end
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting intro chapters: {str(e)}', xbmc.LOGERROR)
            return None, None

    def get_outro_chapter(self, chapters, outro_chapter):
        """Get outro chapter based on configured chapter number."""
        if not chapters or outro_chapter is None:
            return None

        try:
            outro = self.get_chapter_by_number(chapters, outro_chapter)
            if not outro:
                xbmc.log(f'SkipIntro: Outro chapter {outro_chapter} not found', xbmc.LOGWARNING)
                return None

            return outro
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting outro chapter: {str(e)}', xbmc.LOGERROR)
            return None

    @staticmethod
    def find_chapter_by_name(chapters, name):
        """Find a chapter by name (case-insensitive partial match)."""
        if not chapters or not name:
            return None
        name_lower = name.lower()
        for chapter in chapters:
            if name_lower in chapter.get('name', '').lower():
                return chapter
        return None

    def find_intro_chapter(self, chapters):
        """Find the intro chapter by name heuristics.

        Returns the start time of the intro chapter, or None.
        """
        if not chapters:
            return None

        intro_names = ['intro', 'opening', 'op']
        for chapter in chapters:
            chapter_name = chapter.get('name', '').lower()
            for name in intro_names:
                if name in chapter_name:
                    return chapter.get('time')
        return None
