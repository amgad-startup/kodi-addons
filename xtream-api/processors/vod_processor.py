"""Processor for video-on-demand streams."""

import os
from processors.base_processor import BaseProcessor
from processors.vod.metadata_extractor import VODMetadataExtractor
from processors.vod.file_generator import VODFileGenerator
from utils import should_skip_title, reorder_mixed_language, sanitize_filename, sanitize_category_name, VODTitleCleaner
from kodi_db_manager import KodiDBManager
from strm_processor import STRMProcessor

class VODProcessor(BaseProcessor):
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, mode='local'):
        """Initialize VODProcessor."""
        print(f"VODProcessor init with max_titles={max_titles}, fresh_run={fresh_run}, mode={mode}")
        super().__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
        self.mode = mode
        self.title_cleaner = VODTitleCleaner()
        self.metadata_extractor = VODMetadataExtractor()
        self.strm_processor = STRMProcessor()
        self.file_generator = VODFileGenerator(self.strm_processor)
        
        if mode == 'kodi':
            self.db_manager = KodiDBManager()

    def _process_stream(self, stream, batch_content, output_folder):
        """Process a VOD stream and add to batch content."""
        stream_id = stream.get("stream_id")
        name = stream.get("name", "")
        category = sanitize_category_name(stream.get("category_name", ""))
        
        # Skip non-Arabic content
        if should_skip_title(name):
            self.skipped_count += 1
            return name, category
        
        # Clean and reorder name
        name = self.title_cleaner.clean_title(name)
        name = reorder_mixed_language(name)
        name = sanitize_filename(name)
        
        if stream_id:
            # Get detailed movie info
            movie_info = self.api.get_movie_info(stream_id)
            
            # Create movie directory in flat structure
            movie_dir = os.path.join(output_folder, name)
            
            # Extract metadata
            info = self.metadata_extractor.extract_movie_metadata(stream, movie_info)
            
            # Add category as tag
            info['tags'] = [category] if category else []
            
            # Add path info
            info['path'] = os.path.abspath(movie_dir)
            info['filename'] = "movie.strm"
            
            if self.mode == 'kodi':
                # Insert into Kodi database
                success = self.db_manager.insert_movie(info)
                if not success:
                    print(f"Failed to insert movie {name} into database")
            else:
                # Create STRM and NFO files
                stream_data = {
                    'stream_id': stream_id,
                    'name': name,
                    'category_name': category,
                    'api_client': self.api
                }
                self.file_generator.generate_files(movie_dir, name, stream_data, info, category)
            
            # Add to M3U playlist
            m3u_content = self.file_generator.generate_m3u_content(
                stream_id,
                name,
                info,
                category,
                self.api.base_url,
                {'username': self.api.username, 'password': self.api.password}
            )
            batch_content.extend(m3u_content)
            
            self.processed_count += 1
            
            return info['name'], category
