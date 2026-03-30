"""Module for processing streams from Xtream Codes API."""

import os
import shutil
from tqdm import tqdm
import random
from pathlib import Path
from config import OUTPUT_DIRS, STREAM_TYPES, CONFIG
from processors.vod_processor import VODProcessor
from processors.series_processor import SeriesProcessor
from processors.live_processor import LiveProcessor
from catalog_manager import CatalogManager
from failed_streams import FailedStreamsTracker
from logger import get_logger

# Setup logger
logger = get_logger(__name__)

class StreamProcessor:
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, max_episodes=None, mode='local', types=[], name_filter=None):
        """Initialize stream processor."""
        logger.info(f"StreamProcessor init with max_titles={max_titles}, fresh_run={fresh_run}, max_episodes={max_episodes}, mode={mode}, name_filter={name_filter}")
        self.api = api_client
        self.max_titles = max_titles
        self.fresh_run = fresh_run
        self.max_episodes = max_episodes
        self.mode = mode
        self.types = types
        self.name_filter = name_filter.lower() if name_filter else None
        
        # Reset counters for each type
        self.processed_counts = {stream_type: 0 for stream_type in types}
        
        # Initialize processors with keyword arguments
        self.vod_processor = VODProcessor(
            api_client=self.api,
            max_titles=self.max_titles,
            fresh_run=self.fresh_run,
            mode=self.mode
        )
        self.series_processor = SeriesProcessor(
            api_client=self.api,
            max_titles=self.max_titles,
            fresh_run=self.fresh_run,
            max_episodes=self.max_episodes,
            mode=self.mode
        )
        self.live_processor = LiveProcessor(
            api_client=self.api,
            max_titles=self.max_titles,
            fresh_run=self.fresh_run,
            mode=self.mode
        )
        
        # Initialize managers
        self.catalog_manager = CatalogManager()
        self.failed_tracker = FailedStreamsTracker()
        
        # Clean directories if fresh run
        if fresh_run and mode == 'local':
            self._clean_directories()

    def _clean_directories(self):
        """Clean output directories for fresh run."""
        # Get base content path
        base_path = Path(CONFIG['directories']['base_path'])
        content_path = base_path / CONFIG['directories']['folder_name']
        
        # First, ensure base path exists
        if not base_path.exists():
            logger.info(f"Creating base directory: {base_path}")
            base_path.mkdir(parents=True, exist_ok=True)
        
        # Clean and recreate content directory if it exists
        if content_path.exists():
            logger.info(f"Cleaning content directory: {content_path}")
            shutil.rmtree(content_path)
        
        logger.info(f"Creating content directory: {content_path}")
        content_path.mkdir(parents=True, exist_ok=True)
        
        # Create directories for selected stream types
        for stream_type in self.types:
            if stream_type in OUTPUT_DIRS:
                dir_path = Path(OUTPUT_DIRS[stream_type])
                logger.info(f"Creating directory for {stream_type}: {dir_path}")
                dir_path.mkdir(parents=True, exist_ok=True)

    def _should_include_stream(self, stream):
        """Check if a stream should be included based on category and name filters."""
        # Check category exclusions first
        category_name = stream.get('category_name', '')
        if not self.catalog_manager._should_include_category(category_name):
            return False
            
        # Then check name filter if specified
        name = stream.get('name', '')
        if self.name_filter:
            return self.name_filter in name.lower()
            
        # Otherwise check for Arabic content
        return any(c >= '\u0600' and c <= '\u06FF' for c in name)  # Arabic Unicode range

    def _filter_streams(self, streams, stream_type):
        """Filter streams based on name and category criteria."""
        # Get current catalog
        catalog = self.catalog_manager.get_catalog(stream_type)
        
        # Print catalog comparison
        if catalog:
            logger.info(f"\nCatalog comparison for {stream_type}:")
            logger.info(f"Previous catalog from: {catalog['timestamp']}")
            logger.info(f"Streams: {len(streams)} (Previously: {len(catalog['streams'])})")
            logger.info(f"Categories: {len(catalog['categories'])} (Previously: {len(catalog['categories'])})")
        
        # Filter streams
        filtered_streams = [
            stream for stream in streams 
            if self._should_include_stream(stream)
        ]
        
        # Print filtering results
        if filtered_streams:
            filter_type = "name filter" if self.name_filter else "Arabic filter"
            logger.info(f"\nFound {len(filtered_streams)} streams matching {filter_type} for {stream_type}")
            
        return filtered_streams

    def _select_streams(self, streams, stream_type):
        """Select streams based on filtering and max_titles limit."""
        # First apply filtering
        filtered_streams = self._filter_streams(streams, stream_type)
        
        # Then apply max_titles limit if needed
        remaining_titles = self.max_titles - self.processed_counts[stream_type] if self.max_titles else None
        if remaining_titles and remaining_titles > 0 and len(filtered_streams) > remaining_titles:
            if self.name_filter:
                # Take first max_titles matches when using name filter
                selected_streams = filtered_streams[:remaining_titles]
                logger.info(f"Selected first {remaining_titles} out of {len(filtered_streams)} matching streams")
            else:
                # Random selection for Arabic content
                selected_streams = random.sample(filtered_streams, remaining_titles)
                logger.info(f"Randomly selected {remaining_titles} out of {len(filtered_streams)} available streams")
        else:
            selected_streams = filtered_streams
            logger.info(f"Processing all {len(filtered_streams)} matching streams")
        
        return selected_streams

    def process_streams_in_batches(self, streams, stream_type, output_folder, output_file):
        """Process streams in batches and write to M3U file."""
        logger.info(f"\nStarting batch processing:")
        logger.info(f"Stream type: {stream_type}")
        logger.info(f"Output folder: {output_folder}")
        logger.info(f"Number of streams: {len(streams)}")
        
        # Always apply filtering and selection
        selected_streams = self._select_streams(streams, stream_type)
        
        if not selected_streams:
            logger.warning(f"No matching streams found for {stream_type}")
            return
        
        # Initialize progress bar
        progress = tqdm(total=len(selected_streams), desc=f"Processing {stream_type}", 
                       bar_format='{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]')
        
        # Process streams
        batch_content = []
        for stream in selected_streams:
            # Check if we've reached max_titles for this type
            if self.max_titles and self.processed_counts[stream_type] >= self.max_titles:
                logger.info(f"Reached max titles limit ({self.max_titles}) for {stream_type}")
                break
                
            try:
                name = stream.get('name', 'Unknown')
                category = stream.get('category_name', 'Unknown')
                
                # Map stream types to processor attribute names
                processor_map = {
                    'vod': 'vod_processor',
                    'series': 'series_processor',
                    'live_streams': 'live_processor'
                }
                
                processor_name = processor_map.get(stream_type)
                if not processor_name:
                    raise ValueError(f"Unknown stream type: {stream_type}")
                
                processor = getattr(self, processor_name)
                
                # Pass output_folder to all processors
                result = processor._process_stream(stream, batch_content, output_folder)
                if result:
                    name, category = result
                    self.processed_counts[stream_type] += 1
                logger.debug(f"Processed stream: {name} ({category})")
                # Update progress
                progress.set_postfix_str(
                    f"processed={self.processed_counts[stream_type]} "
                    f"skipped={processor.skipped_count}"
                )
            except Exception as e:
                logger.error(f"\nError processing stream {stream.get('name', 'Unknown')}: {str(e)}")
                self.failed_tracker.add_failed_stream(stream, stream_type, str(e))
            
            progress.update(1)
        
        progress.close()
        
        # Save catalog
        self.catalog_manager.save_catalog(stream_type, streams, [])
