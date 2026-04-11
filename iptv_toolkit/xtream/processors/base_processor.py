"""Base class for stream processors.

This module provides the foundation for all stream processors (VOD, Series, Live) with common
functionality for handling streams from an Xtream API. It implements core features like:

- Progress tracking
- Stream filtering
- Batch processing
- Directory management
- Arabic content detection

The BaseProcessor is designed to be extended by specific processors that handle different
types of content (movies, TV shows, live TV). It provides a consistent interface and shared
functionality while allowing specialized behavior in subclasses.

Key Features:
    - Tracks processing progress and can resume interrupted operations
    - Handles Arabic content detection and filtering
    - Manages directory creation and cleanup
    - Provides batch processing capabilities
    - Implements random selection for limited processing

Example:
    class MyProcessor(BaseProcessor):
        def __init__(self, api_client, max_titles=None, fresh_run=False):
            super().__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
            
        def _process_stream(self, stream, batch_content):
            # Implement specific processing logic
            pass
"""

from iptv_toolkit.xtream.progress_manager import ProgressManager
from iptv_toolkit.core.utils import should_skip_title
from iptv_toolkit.xtream.catalog_manager import CatalogManager
import os
import shutil
from tqdm import tqdm
import random
from time import sleep

class BaseProcessor:
    def __init__(self, api_client=None, max_titles=None, fresh_run=False):
        """Initialize BaseProcessor.
        
        Args:
            api_client: Instance of XtreamCodesAPI for making API requests
            max_titles: Maximum number of titles to process (None for unlimited)
            fresh_run: Whether to start fresh (clean existing data)
        """
        print(f"Initializing BaseProcessor with max_titles={max_titles}, fresh_run={fresh_run}")
        self.api = api_client
        self.progress_manager = ProgressManager()
        self.catalog_manager = CatalogManager()
        self.max_titles = max_titles
        self.fresh_run = fresh_run
        self.skipped_count = 0
        self.processed_count = 0
        self.error_count = 0

    def _clean_directories(self, stream_type):
        """Clean output directories for fresh run.
        
        Args:
            stream_type: Type of stream ('live_streams', 'vod', 'series')
        """
        dirs_to_clean = {
            'live_streams': ['live-flat'],
            'vod': ['vod-flat'],
            'series': ['series-flat']
        }
        
        dir_path = dirs_to_clean.get(stream_type, [])[0]
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)

    def _write_batch(self, file, batch_content):
        """Write content to file in batch.
        
        Args:
            file: File object to write to
            batch_content: List of strings to write
        """
        if batch_content:
            file.write("\n".join(batch_content) + "\n")
            file.flush()

    def _get_random_delay(self):
        """Get a random delay between requests to avoid rate limiting.
        
        Returns:
            float: Random delay in seconds between 0.5 and 2.0
        """
        return random.uniform(0.5, 2.0)

    def _get_stream_id(self, stream):
        """Get stream ID based on stream type.
        
        Args:
            stream: Stream data dictionary
            
        Returns:
            str: Stream ID or None if not found
        """
        if 'stream_id' in stream:
            return str(stream['stream_id'])
        elif 'series_id' in stream:
            return f"s{stream['series_id']}"
        return None

    def _should_process_stream(self, stream):
        """Check if stream should be processed based on language and category.
        
        Args:
            stream: Stream data dictionary
            
        Returns:
            bool: True if stream should be processed, False otherwise
        """
        # Check category exclusions first
        category_name = stream.get('category_name', '')
        if not self.catalog_manager._should_include_category(category_name):
            return False
            
        # Then check language
        return not should_skip_title(stream.get('name', ''))

    def process_streams_in_batches(self, streams, stream_type, output_file):
        """Process streams with optional limit on number of titles.
        
        This is the main processing method that:
        1. Loads progress from previous runs
        2. Filters streams based on language and previous processing
        3. Randomly selects streams if max_titles is set
        4. Processes streams in batches with progress tracking
        5. Saves progress after each stream
        
        Args:
            streams: List of stream dictionaries from API
            stream_type: Type of stream ('live_streams', 'vod', 'series')
            output_file: Path to output M3U file
        """
        if not streams:
            return
            
        # Load progress
        progress = self.progress_manager.load_progress(stream_type)
        processed_ids = set() if self.fresh_run else set(progress.get("processed_ids", []))
        
        # Clean directories for fresh run
        if self.fresh_run:
            self._clean_directories(stream_type)
            self.progress_manager.save_progress(stream_type, {
                "processed": 0,
                "processed_ids": list(processed_ids)
            })
        
        # Filter out already processed streams, excluded categories, and non-Arabic content
        eligible_streams = []
        for stream in streams:
            stream_id = self._get_stream_id(stream)
            if stream_id and stream_id not in processed_ids and self._should_process_stream(stream):
                eligible_streams.append(stream)
        
        if not eligible_streams:
            print(f"No new eligible {stream_type} to process")
            return
            
        # Randomly select streams if max_titles is set
        if self.max_titles and len(eligible_streams) > self.max_titles:
            selected_streams = random.sample(eligible_streams, self.max_titles)
            print(f"\nRandomly selected {len(selected_streams)} out of {len(eligible_streams)} available Arabic {stream_type}")
        else:
            selected_streams = eligible_streams
            print(f"\nProcessing {len(selected_streams)} Arabic {stream_type}")
        
        # Reset counters
        self.skipped_count = 0
        self.processed_count = 0
        self.error_count = 0
        
        # Initialize or append to file
        mode = 'w' if self.fresh_run else 'a'
        with open(output_file, mode, encoding='utf-8') as f:
            # Write M3U header only for new files
            if self.fresh_run:
                f.write("#EXTM3U\n")
            
            # Process streams with progress bar
            with tqdm(total=len(selected_streams), desc=f"Processing {stream_type}", initial=0) as pbar:
                for stream in selected_streams:
                    try:
                        stream_id = self._get_stream_id(stream)
                        if not stream_id:
                            continue
                            
                        batch_content = []
                        self._process_stream(stream, batch_content)
                            
                        # Write content to file
                        self._write_batch(f, batch_content)
                        
                        # Update progress
                        processed_ids.add(stream_id)
                        self.progress_manager.save_progress(stream_type, {
                            "processed": len(processed_ids),
                            "processed_ids": list(processed_ids)
                        })
                        
                        # Update progress bar
                        pbar.set_postfix({
                            'processed': self.processed_count,
                            'skipped': self.skipped_count
                        })
                        pbar.update(1)
                        
                        # Add random delay between requests
                        sleep(self._get_random_delay())
                        
                    except Exception as e:
                        print(f"\nError processing stream: {str(e)}")
                        self.error_count += 1
                        continue

    def _process_stream(self, stream, batch_content):
        """Abstract method to be implemented by subclasses.
        
        Args:
            stream: Stream data dictionary
            batch_content: List to append M3U content to
            
        Raises:
            NotImplementedError: Must be implemented by subclasses
        """
        raise NotImplementedError("Subclasses must implement _process_stream method")
