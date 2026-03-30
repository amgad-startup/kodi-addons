"""Processor for live TV streams."""

from processors.base_processor import BaseProcessor
from utils import should_skip_title, sanitize_filename, sanitize_category_name
from kodi_db_manager import KodiDBManager
from strm_processor import STRMProcessor

class LiveProcessor(BaseProcessor):
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, mode='local'):
        """Initialize LiveProcessor."""
        print(f"LiveProcessor init with max_titles={max_titles}, fresh_run={fresh_run}, mode={mode}")
        super(LiveProcessor, self).__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
        self.mode = mode
        if mode == 'kodi':
            self.db_manager = KodiDBManager()
        self.strm_processor = STRMProcessor()

    def _process_stream(self, stream, batch_content):
        """Process a live stream and add to batch content."""
        stream_id = stream.get("stream_id")
        name = stream.get("name", "")
        category = sanitize_category_name(stream.get("category_name", ""))
        
        # Skip non-Arabic content
        if should_skip_title(name):
            self.skipped_count += 1
            return
        
        if stream_id:
            # Clean name for file system
            clean_name = sanitize_filename(name)
            
            # Create stream URL
            stream_url = f"{self.api.base_url}/live/{self.api.username}/{self.api.password}/{stream_id}.ts"
            
            # Process based on mode
            if self.mode == 'kodi':
                # For live TV, we might want to add PVR integration in the future
                pass
            else:
                # Create STRM file using STRMProcessor
                stream_data = {
                    'stream_id': stream_id,
                    'name': clean_name,
                    'category_name': category
                }
                self.strm_processor.process_stream(stream_data, 'live_streams', self.api)
            
            # Add to M3U playlist
            metadata_parts = [
                f'CUID="{stream_id}"',
                f'tvg-name="{name}"'
            ]
            
            if stream.get('stream_icon'):
                metadata_parts.append(f'tvg-logo="{stream["stream_icon"]}"')
                
            metadata_parts.append(f'group-title="{category}"')
            
            extinf = f'#EXTINF:0 {" ".join(metadata_parts)},{name}'
            batch_content.extend([extinf, stream_url])
            
            self.processed_count += 1
            
        return name, category
