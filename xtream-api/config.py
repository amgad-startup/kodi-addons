"""Configuration settings for the Xtream Codes API client and content processing."""

import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_config():
    """Load configuration from config.json file."""
    config_path = Path(__file__).parent / 'config.json'
    with open(config_path) as f:
        return json.load(f)

# Load configuration
CONFIG = load_config()

# Update API credentials from environment variables
CONFIG['api']['url'] = os.getenv('XTREAM_API_URL')
CONFIG['api']['username'] = os.getenv('XTREAM_USERNAME')
CONFIG['api']['password'] = os.getenv('XTREAM_PASSWORD')

# Expand base path
CONFIG['directories']['base_path'] = os.path.expanduser(CONFIG['directories']['base_path'])

# Create output directories structure
content_path = os.path.join(CONFIG['directories']['base_path'], CONFIG['directories']['folder_name'])
OUTPUT_DIRS = {
    name: os.path.join(content_path, subdir)
    for name, subdir in CONFIG['directories']['subdirs'].items()
}

# Create output files structure
OUTPUT_FILES = {
    'live_streams': os.path.join(OUTPUT_DIRS['live_streams'], 'live.m3u'),
    'vod': os.path.join(OUTPUT_DIRS['vod'], 'movies.m3u'),
    'series': os.path.join(OUTPUT_DIRS['series'], 'series.m3u'),
    'radio': os.path.join(OUTPUT_DIRS['radio'], 'radio.m3u')
}

def ensure_directories():
    """Create all required directories if they don't exist."""
    # First ensure base path exists
    base_path = Path(CONFIG['directories']['base_path'])
    if not base_path.exists():
        print(f"Creating base directory: {base_path}")
        base_path.mkdir(parents=True, exist_ok=True)
    
    # Create content folder under base path
    content_path = base_path / CONFIG['directories']['folder_name']
    if not content_path.exists():
        print(f"Creating content directory: {content_path}")
        content_path.mkdir(parents=True, exist_ok=True)
    
    # Create all subdirectories under content folder
    for name, subdir in CONFIG['directories']['subdirs'].items():
        full_path = content_path / subdir
        if not full_path.exists():
            print(f"Creating {name} directory: {full_path}")
            full_path.mkdir(parents=True, exist_ok=True)

# Initialize directories when config is imported
# ensure_directories()

# Export commonly used configurations
API_CONFIG = CONFIG['api']
PROCESSING = CONFIG['processing']
CACHE = CONFIG['cache']
FILTERING = CONFIG['filtering']
STREAM_TYPES = {
    'default': ['live_streams', 'vod', 'series'],
    'available': ['live_streams', 'vod', 'series', 'radio']
}

# Export delay constants for backwards compatibility
SERIES_PROCESSING_DELAY = PROCESSING['delays']['series_processing']
SERIES_BATCH_DELAY = PROCESSING['delays']['series_batch']
API_CALL_DELAY = PROCESSING['delays']['api_calls']
