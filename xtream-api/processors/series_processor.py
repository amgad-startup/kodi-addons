"""Processor for TV series streams."""

import os
import config
from time import sleep
from processors.base_processor import BaseProcessor
from processors.series.metadata_extractor import SeriesMetadataExtractor
from processors.series.cast_cleaner import CastCleaner
from processors.series.file_generator import SeriesFileGenerator
from utils import should_skip_title, reorder_mixed_language, sanitize_filename, sanitize_category_name
from kodi_db_manager import KodiDBManager
from strm_processor import STRMProcessor
from logger import get_logger

# Setup logger
logger = get_logger(__name__)

class SeriesProcessor(BaseProcessor):
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, max_episodes=None, mode='local'):
        """Initialize SeriesProcessor."""
        logger.info(f"SeriesProcessor init with max_titles={max_titles}, fresh_run={fresh_run}, max_episodes={max_episodes}, mode={mode}")
        super().__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
        self.max_episodes = max_episodes
        self.mode = mode
        self.episodes_processed = 0
        
        # Initialize helper modules
        self.metadata_extractor = SeriesMetadataExtractor()
        self.cast_cleaner = CastCleaner()
        self.strm_processor = STRMProcessor(max_episodes=max_episodes)
        self.file_generator = SeriesFileGenerator(self.strm_processor)
        
        if mode == 'kodi':
            self.db_manager = KodiDBManager()

    def _process_stream(self, stream, batch_content, output_folder=None):
        """Process a series and add to batch content."""
        # Reset episodes counter for each stream
        self.episodes_processed = 0
        
        series_id = stream.get("series_id")
        series_name = stream.get("name", "Unknown Series")
        category = sanitize_category_name(stream.get("category_name", ""))
        
        # Skip non-Arabic content
        if should_skip_title(series_name):
            self.skipped_count += 1
            return
        
        # Clean and reorder series name
        series_name = sanitize_filename(reorder_mixed_language(series_name))
        
        series_info = self.api.get_series_info(series_id)
        if not series_info:
            return
            
        # Add category name to series info for year extraction
        if 'info' not in series_info:
            series_info['info'] = {}
        series_info['info']['category_name'] = category
            
        # Use provided output_folder or default to OUTPUT_DIRS path
        base_dir = output_folder if output_folder else config.OUTPUT_DIRS['series']
        series_dir = os.path.join(base_dir, series_name)
        
        # Extract and process TV show metadata
        show_data = self.metadata_extractor.extract_series_metadata(series_info)
        show_data['cast'] = self.cast_cleaner.clean_cast(series_info.get('info', {}).get('cast', ''))
        show_data.update({
            'path': os.path.abspath(series_dir),
            'tags': [category] if category else []
        })
        
        show_id = None
        if self.mode == 'kodi':
            # Insert show into database
            show_id = self.db_manager.insert_tvshow(show_data)
            if not show_id:
                return
        else:
            # Generate show files
            self.file_generator.generate_show_files(series_dir, series_name, show_data, category)
        
        # Get seasons info for metadata
        seasons_info = {}
        if series_info.get("seasons"):
            for season in series_info["seasons"]:
                if isinstance(season, dict) and "season_number" in season:
                    season_num = str(season["season_number"])
                    seasons_info[season_num] = season
        
        if series_info.get("episodes"):
            for season_num, episodes in series_info["episodes"].items():
                # Check if we've reached max episodes
                if self.max_episodes and self.episodes_processed >= self.max_episodes:
                    return
                    
                # Create season directory
                season_dir = self.file_generator.create_season_directory(series_dir, season_num)
                
                # Get season metadata
                season_info = seasons_info.get(str(season_num), {})
                
                if isinstance(episodes, list):
                    season_episodes = episodes
                elif isinstance(episodes, dict):
                    season_episodes = list(episodes.values())
                else:
                    continue
                    
                for episode in season_episodes:
                    # Check if we've reached max episodes
                    if self.max_episodes and self.episodes_processed >= self.max_episodes:
                        return
                        
                    if isinstance(episode, dict):
                        episode_num = episode.get("episode_num") or episode.get("episode_number", "1")
                        
                        # Extract episode metadata
                        episode_data = self.metadata_extractor.extract_episode_metadata(episode, season_info, series_name)
                        episode_data['cast'] = self.cast_cleaner.clean_cast(episode.get('cast', ''))
                        episode_data.update({
                            'show_id': show_id,
                            'season': int(season_num),
                            'episode': int(episode_num),
                            'path': os.path.abspath(season_dir),
                            'tags': [category] if category else []
                        })
                        
                        if self.mode == 'kodi':
                            # Insert episode into database
                            self.db_manager.insert_episode(episode_data)
                        else:
                            # Generate episode files
                            stream_data = {
                                'series_id': series_id,
                                'season': season_num,
                                'episode': episode_num,
                                'stream_id': episode.get('id'),
                                'container_extension': episode.get('container_extension', 'mp4'),
                                'name': series_name,
                                'api_client': self.api
                            }
                            self.file_generator.generate_episode_files(
                                season_dir,
                                series_name,
                                season_num,
                                episode_num,
                                episode_data,
                                season_info,
                                stream_data,
                                category
                            )
                            
                        self.episodes_processed += 1
        
        self.processed_count += 1
        # Add delay between series to avoid rate limiting
        sleep(config.SERIES_PROCESSING_DELAY)
        return series_name, category
