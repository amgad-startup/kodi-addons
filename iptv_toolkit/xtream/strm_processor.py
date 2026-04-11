"""Module for converting streams to STRM files with organized directory structures."""

import os
from iptv_toolkit.core.utils import (
    reorder_mixed_language, 
    sanitize_filename,
    sanitize_category_name,
    format_season_number,
    format_episode_number
)
from iptv_toolkit.media.nfo import (
    generate_movie_nfo,
    generate_tvshow_nfo,
    generate_episode_nfo
)

class STRMProcessor:
    def __init__(self, max_episodes=None):
        """Initialize STRMProcessor."""
        self.max_episodes = max_episodes
        self.episodes_processed = 0

    def process_stream(self, movie_dir, stream_data, stream_type, api_client):
        """Process a stream and create STRM file(s)."""
        # Reset episodes counter for each stream
        self.episodes_processed = 0
        
        # Get common stream info
        name = stream_data.get('name', '')
        category = sanitize_category_name(stream_data.get('category_name', ''))
        category_id = str(stream_data.get('category_id', ''))
        
        # Get category info including tags
        category_info = api_client.get_category_info(stream_type, category_id)
        if not category and category_info:
            category = sanitize_category_name(category_info.get('name', ''))
        
        # Get tags from category info
        tags = category_info.get('tags', []) if category_info else []
        
        # Handle mixed language titles for VOD and Series
        if stream_type in ['vod', 'series']:
            name = reorder_mixed_language(name)
        
        # Create base paths
        if stream_type == "series":
            base_path = "series-flat"
        elif stream_type == "vod":
            base_path = "vod-flat"
        else:  # live_streams
            base_path = "live"
        
        if stream_type == "series":
            self._process_series_stream(stream_data, api_client, base_path, category, tags)
        elif stream_type == "vod":
            self._process_movie_stream(movie_dir, stream_data, api_client, base_path, category, tags)
        else:  # live_streams
            self._process_live_stream(stream_data, api_client, base_path, category, tags)

    def _process_series_stream(self, series_data, api_client, base_path, category, tags):
        """Process a series stream."""
        series_id = series_data.get('series_id')
        series_name = series_data.get('name', '')
        series_name = sanitize_filename(series_name)
        
        # Get detailed series info
        series_info = series_data.get('series_info')  # Already fetched in StreamProcessor
        if not series_info or 'episodes' not in series_info:
            return
            
        # Create tvshow NFO file
        show_dir = os.path.join(base_path, series_name)
        generate_tvshow_nfo(show_dir, series_name, series_info, category, tags)
            
        # Process each season and its episodes
        for season_num, episodes in series_info['episodes'].items():
            # Check if we've reached max episodes
            if self.max_episodes and self.episodes_processed >= self.max_episodes:
                return
                
            # Format season number with leading zero for Kodi compatibility
            season_num = format_season_number(season_num, True)  # with leading zero
            
            # Create season directory (Kodi format: "Season 01", "Season 02", etc.)
            season_dir = os.path.join(base_path, series_name, f"Season {season_num}")
            
            # Process episodes
            for episode in episodes:
                # Check if we've reached max episodes
                if self.max_episodes and self.episodes_processed >= self.max_episodes:
                    return
                    
                if isinstance(episode, dict):
                    episode_id = episode.get('id')
                    episode_num = format_episode_number(episode.get('episode_num', '1'))
                    container_extension = episode.get('container_extension', 'mp4')
                    
                    if episode_id:
                        # Format filename according to Kodi standards: ShowName S01E02
                        base_filename = f"{series_name} S{season_num}E{episode_num}"
                        strm_filename = f"{base_filename}.strm"
                        
                        # Generate NFO file for episode
                        generate_episode_nfo(
                            season_dir,
                            series_name,
                            int(season_num),
                            int(episode_num),
                            episode,
                            series_info,
                            f"{base_filename}.nfo",
                            category,
                            tags
                        )
                        
                        # Use direct episode_id for the stream URL
                        stream_url = f"{api_client.base_url}/series/{api_client.username}/{api_client.password}/{episode_id}.{container_extension}"
                        
                        # Create STRM file
                        self._create_strm_file(season_dir, strm_filename, stream_url)
                        self.episodes_processed += 1

    def _process_movie_stream(self, movie_dir, movie_data, api_client, base_path, category, tags):
        """Process a movie stream."""
        stream_id = movie_data.get('stream_id')
        name = movie_data.get('name', '')
        name = sanitize_filename(name)
        
        if stream_id:
            stream_url = f"{api_client.base_url}/movie/{api_client.username}/{api_client.password}/{stream_id}.mp4"
            
            # Create STRM file in flat structure
            movie_dir = movie_dir
            self._create_strm_file(movie_dir, "movie.strm", stream_url)
            
            # Generate NFO file with tags
            generate_movie_nfo(movie_dir, name, movie_data, category, tags)

    def _process_live_stream(self, stream_data, api_client, base_path, category, tags):
        """Process a live stream."""
        stream_id = stream_data.get('stream_id')
        name = stream_data.get('name', '')
        name = sanitize_filename(name)
        
        if stream_id:
            stream_url = f"{api_client.base_url}/live/{api_client.username}/{api_client.password}/{stream_id}"
            
            # Create STRM file
            live_dir = os.path.join(base_path, name)
            self._create_strm_file(live_dir, f"{name}.strm", stream_url)
            
            # Generate NFO file with tags
            generate_movie_nfo(live_dir, name, stream_data, category, tags)

    def _create_strm_file(self, directory, filename, stream_url):
        """Create a STRM file with the stream URL."""
        try:
            # Create directory if it doesn't exist
            os.makedirs(directory, exist_ok=True)
            
            file_path = os.path.join(directory, filename)
            
            # Write stream URL to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(stream_url)
                
            return True
        except Exception as e:
            print(f"Error creating STRM file: {str(e)}")
            return False
