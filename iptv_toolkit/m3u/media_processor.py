import os
from iptv_toolkit.core.utils import should_skip_title, sanitize_filename, extract_show_info, reorder_mixed_language
from iptv_toolkit.m3u.file_ops import safe_create_dir, safe_write_file
from iptv_toolkit.media.nfo import generate_movie_nfo, generate_tvshow_nfo, generate_episode_nfo
from iptv_toolkit.media.tmdb import TMDBIntegration

class MediaProcessor:
    def __init__(self, output_dir_grouped, output_dir_flat):
        self.output_dir_grouped = output_dir_grouped
        self.output_dir_flat = output_dir_flat
        self.processed_count = 0
        self.skipped_count = 0
        self.error_count = 0
        self.total_processed = 0
        self.tmdb = TMDBIntegration()

    def process_show(self, tvg_name, group_title, stream_url):
        """Process a TV show entry"""
        show_name, season, episode = extract_show_info(tvg_name)
        if not (show_name and season and episode):
            print(f"\nSkipping '{tvg_name}' as it doesn't match TV show format.")
            return (False, True)  # (success, skipped)

        # Get metadata in both languages (but don't fail if not found)
        metadata_ar = self.tmdb.get_show_metadata(show_name, language='ar')
        metadata_en = self.tmdb.get_show_metadata(show_name, language='en')
        
        # Use Arabic metadata if available, fallback to English, or create basic metadata
        metadata = metadata_ar if metadata_ar else metadata_en
        if not metadata:
            metadata = {
                'title': show_name,
                'original_title': show_name,
                'transliterated_title': show_name,
                'plot': '',
                'genre': '',
                'director': '',
                'cast': [],
                'premiered': '',
                'episode_run_time': '',
                'status': '',
                'poster': '',
                'fanart': '',
                'language': 'en'
            }

        # Use transliterated or original name for directory structure
        dir_name = metadata.get('transliterated_title') or sanitize_filename(show_name)

        # Create grouped structure (with group-title)
        group_dir = os.path.join(self.output_dir_grouped, sanitize_filename(group_title))
        show_dir_grouped = os.path.join(group_dir, dir_name)
        season_dir_grouped = os.path.join(show_dir_grouped, f"Season {season.zfill(2)}")
        
        # Create flat structure (without group-title)
        show_dir_flat = os.path.join(self.output_dir_flat, dir_name)
        season_dir_flat = os.path.join(show_dir_flat, f"Season {season.zfill(2)}")
        
        # Create all necessary directories
        dirs_to_create = [
            group_dir,
            show_dir_grouped,
            season_dir_grouped,
            show_dir_flat,
            season_dir_flat
        ]
        
        for dir_path in dirs_to_create:
            if not safe_create_dir(dir_path):
                return (False, False)

        # Generate and write NFO files
        tvshow_nfo_path, tvshow_nfo_content = generate_tvshow_nfo(
            show_dir_grouped, show_name, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        episode_nfo_path, episode_nfo_content = generate_episode_nfo(
            season_dir_grouped, show_name, season, episode, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        
        if not safe_write_file(tvshow_nfo_path, tvshow_nfo_content):
            return (False, False)
        if not safe_write_file(episode_nfo_path, episode_nfo_content):
            return (False, False)

        # Generate and write NFO files for flat structure
        tvshow_nfo_path_flat, _ = generate_tvshow_nfo(
            show_dir_flat, show_name, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        episode_nfo_path_flat, _ = generate_episode_nfo(
            season_dir_flat, show_name, season, episode, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        
        if not safe_write_file(tvshow_nfo_path_flat, tvshow_nfo_content):
            return (False, False)
        if not safe_write_file(episode_nfo_path_flat, episode_nfo_content):
            return (False, False)

        # Create the strm filename with season and episode
        strm_filename = f"S{season.zfill(2)}E{episode.zfill(2)}.strm"
        strm_file_path_grouped = os.path.join(season_dir_grouped, strm_filename)
        strm_file_path_flat = os.path.join(season_dir_flat, strm_filename)

        # Write both .strm files
        success = (safe_write_file(strm_file_path_grouped, stream_url) and 
                  safe_write_file(strm_file_path_flat, stream_url))
        return (success, False)

    def process_movie(self, tvg_name, group_title, stream_url):
        """Process a movie entry"""
        # Reorder mixed language parts in movie name
        movie_name = reorder_mixed_language(tvg_name)
        
        # Get metadata in both languages (but don't fail if not found)
        metadata_ar = self.tmdb.get_movie_metadata(movie_name, language='ar')
        metadata_en = self.tmdb.get_movie_metadata(movie_name, language='en')
        
        # Use Arabic metadata if available, fallback to English, or create basic metadata
        metadata = metadata_ar if metadata_ar else metadata_en
        if not metadata:
            metadata = {
                'title': movie_name,
                'original_title': movie_name,
                'transliterated_title': movie_name,
                'plot': '',
                'genre': '',
                'director': '',
                'cast': [],
                'release_date': '',
                'runtime': '',
                'mpaa': '',
                'poster': '',
                'fanart': '',
                'language': 'en'
            }

        # Use transliterated or original name for directory structure
        dir_name = metadata.get('transliterated_title') or sanitize_filename(movie_name)
        
        # Create grouped structure (with group-title)
        group_dir = os.path.join(self.output_dir_grouped, sanitize_filename(group_title))
        movie_dir_grouped = os.path.join(group_dir, dir_name)
        
        # Create flat structure (without group-title)
        movie_dir_flat = os.path.join(self.output_dir_flat, dir_name)
        
        # Create all necessary directories
        dirs_to_create = [
            group_dir,
            movie_dir_grouped,
            movie_dir_flat
        ]
        
        for dir_path in dirs_to_create:
            if not safe_create_dir(dir_path):
                return (False, False)

        # Generate and write NFO files
        movie_nfo_path, movie_nfo_content = generate_movie_nfo(
            movie_dir_grouped, movie_name, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        movie_nfo_path_flat, _ = generate_movie_nfo(
            movie_dir_flat, movie_name, metadata,
            alt_metadata=metadata_en if metadata_ar else None
        )
        
        if not safe_write_file(movie_nfo_path, movie_nfo_content):
            return (False, False)
        if not safe_write_file(movie_nfo_path_flat, movie_nfo_content):
            return (False, False)

        # Create .strm files in both locations
        strm_filename = "movie.strm"
        strm_file_path_grouped = os.path.join(movie_dir_grouped, strm_filename)
        strm_file_path_flat = os.path.join(movie_dir_flat, strm_filename)

        # Write both .strm files
        success = (safe_write_file(strm_file_path_grouped, stream_url) and 
                  safe_write_file(strm_file_path_flat, stream_url))
        return (success, False)

    def process_entry(self, tvg_name, group_title, stream_url, is_tvshow):
        """Process a single media entry"""
        # Skip if the name should be skipped (non-Arabic and non-mixed-Arabic)
        if should_skip_title(tvg_name):
            self.skipped_count += 1
            return False

        success = False
        skipped = False
        if is_tvshow:
            success, skipped = self.process_show(tvg_name, group_title, stream_url)
        else:
            success, skipped = self.process_movie(tvg_name, group_title, stream_url)
        
        if success:
            self.processed_count += 1
        elif skipped:
            self.skipped_count += 1
        else:
            self.error_count += 1
            
        self.total_processed += 1
        return success

    def get_progress_message(self, num_to_process, current_name=""):
        """Get the current progress message"""
        if current_name:
            current_name = f" | Current: {current_name}"
        return (f"Progress: {self.processed_count}/{num_to_process} "
                f"({(self.processed_count/num_to_process*100):.1f}%) "
                f"| Skipped: {self.skipped_count}"
                f"{current_name}")

    def get_completion_summary(self, m3u_file):
        """Get the completion summary"""
        return [
            f"\nCompleted processing '{m3u_file}':",
            f"- Successfully created: {self.processed_count} files",
            f"- Skipped (non-Arabic): {self.skipped_count}",
            f"- Errors encountered: {self.error_count}",
            f"- Total processed: {self.total_processed}",
            f"Grouped structure in: '{self.output_dir_grouped}'",
            f"Flat structure in: '{self.output_dir_flat}'"
        ]
