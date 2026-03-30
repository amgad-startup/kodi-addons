import xbmc
import json
import subprocess
from typing import List, Dict, Union

class ChapterManager:
    """Manages chapter detection for video files using FFmpeg."""
    
    def __init__(self):
        self._cached_chapters = {}
        # On macOS, ffmpeg is typically installed in /usr/local/bin
        self._ffmpeg_path = "/usr/local/bin/ffmpeg"
    
    def get_chapters(self) -> List[Dict[str, Union[str, int, float]]]:
        """Get chapter information using ffmpeg."""
        try:
            # Get current file using Kodi's JSON-RPC API
            result = xbmc.executeJSONRPC(json.dumps({
                "jsonrpc": "2.0",
                "method": "Player.GetItem",
                "params": {
                    "playerid": 1,
                    "properties": ["title", "file"]
                },
                "id": 1
            }))
            
            result = json.loads(result)
            if 'result' not in result or 'item' not in result['result']:
                return []
                
            current_file = result['result']['item'].get('file')
            if not current_file:
                return []
            
            # Return cached chapters if available
            if current_file in self._cached_chapters:
                return self._cached_chapters[current_file]
            
            # Get chapter metadata using ffmpeg
            cmd = [self._ffmpeg_path, "-i", current_file, "-f", "ffmetadata", "-"]
            
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                metadata = result.stdout
                
                if result.returncode != 0:
                    xbmc.log(f"SkipIntro: FFmpeg error: {result.stderr}", xbmc.LOGERROR)
                    return []
                
                chapters = []
                current_chapter = {}
                chapter_number = 1
                
                # Parse metadata
                for line in metadata.splitlines():
                    if line.startswith("[CHAPTER]"):
                        if current_chapter and 'start' in current_chapter and 'end' in current_chapter:
                            chapters.append({
                                'name': current_chapter.get('title', f'Chapter {chapter_number}'),
                                'time': current_chapter['start'],
                                'end_time': current_chapter['end'],
                                'number': chapter_number
                            })
                            chapter_number += 1
                        current_chapter = {}
                    elif line.startswith("START="):
                        current_chapter["start"] = int(line.split("=")[1]) / 1e9  # Convert nanoseconds to seconds
                    elif line.startswith("END="):
                        current_chapter["end"] = int(line.split("=")[1]) / 1e9  # Convert nanoseconds to seconds
                    elif line.startswith("title="):
                        current_chapter["title"] = line.split("=")[1]
                
                # Add the last chapter
                if current_chapter and 'start' in current_chapter and 'end' in current_chapter:
                    chapters.append({
                        'name': current_chapter.get('title', f'Chapter {chapter_number}'),
                        'time': current_chapter['start'],
                        'end_time': current_chapter['end'],
                        'number': chapter_number
                    })
                
                if chapters:
                    xbmc.log(f"SkipIntro: Found {len(chapters)} chapters", xbmc.LOGINFO)
                        
                self._cached_chapters[current_file] = chapters
                return chapters
                
            except subprocess.TimeoutExpired:
                xbmc.log("SkipIntro: FFmpeg command timed out", xbmc.LOGERROR)
                return []
            except Exception as e:
                xbmc.log(f"SkipIntro: Error running ffmpeg: {str(e)}", xbmc.LOGERROR)
                return []

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
