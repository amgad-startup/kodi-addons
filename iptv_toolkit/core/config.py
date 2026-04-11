"""Unified configuration: env vars for credentials, config.json for Xtream runtime options.

Supports three CLIs:
- editor:   TMDB_API_KEY, IPTVEDITOR_TOKEN, IPTVEDITOR_PLAYLIST_ID
- xtream:   XTREAM_API_URL, XTREAM_USERNAME, XTREAM_PASSWORD + config.json
- m3u2strm: no config (CLI args + cwd)
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


# ---------- Editor CLI ----------

TMDB_API_KEY = _env('TMDB_API_KEY')
IPTVEDITOR_TOKEN = _env('IPTVEDITOR_TOKEN')
IPTVEDITOR_PLAYLIST_ID = _env('IPTVEDITOR_PLAYLIST_ID')

STATE_FILE = "editor_state.json"
CATEGORIES_FILE = "tvshows-categories.json"
SHOWS_FILE = "tvshows-shows.json"

IPTVEDITOR_BASE_URL = "https://editor.iptveditor.com/api"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

HTTP_HEADERS: Dict[str, str] = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://cloud.iptveditor.com',
    'referer': 'https://cloud.iptveditor.com/',
    'user-agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
    ),
}

DEFAULT_BATCH_SIZE = 10
FALLBACK_TO_FIRST_RESULT = True


# ---------- Xtream CLI ----------

_XTREAM_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / 'config.json'


def _load_xtream_config() -> Dict[str, Any]:
    """Load xtream runtime config; return a safe default if config.json is missing."""
    if _XTREAM_CONFIG_PATH.exists():
        with open(_XTREAM_CONFIG_PATH) as f:
            return json.load(f)
    return {
        'api': {'url': None, 'username': None, 'password': None, 'timeout': 30},
        'directories': {
            'base_path': '~/Media',
            'folder_name': 'xtream',
            'subdirs': {
                'live_streams': 'live',
                'vod': 'movies',
                'series': 'series',
                'radio': 'radio',
            },
        },
        'processing': {
            'delays': {
                'series_processing': 0.1,
                'series_batch': 1.0,
                'api_calls': 0.2,
            },
        },
        'cache': {},
        'filtering': {},
        'logging': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'date_format': '%Y-%m-%d %H:%M:%S',
        },
    }


CONFIG = _load_xtream_config()

CONFIG['api']['url'] = _env('XTREAM_API_URL', CONFIG['api'].get('url'))
CONFIG['api']['username'] = _env('XTREAM_USERNAME', CONFIG['api'].get('username'))
CONFIG['api']['password'] = _env('XTREAM_PASSWORD', CONFIG['api'].get('password'))

CONFIG['directories']['base_path'] = os.path.expanduser(CONFIG['directories']['base_path'])

_content_path = os.path.join(
    CONFIG['directories']['base_path'],
    CONFIG['directories']['folder_name'],
)
OUTPUT_DIRS = {
    name: os.path.join(_content_path, subdir)
    for name, subdir in CONFIG['directories']['subdirs'].items()
}
OUTPUT_FILES = {
    'live_streams': os.path.join(OUTPUT_DIRS['live_streams'], 'live.m3u'),
    'vod': os.path.join(OUTPUT_DIRS['vod'], 'movies.m3u'),
    'series': os.path.join(OUTPUT_DIRS['series'], 'series.m3u'),
    'radio': os.path.join(OUTPUT_DIRS['radio'], 'radio.m3u'),
}


def ensure_directories() -> None:
    """Create all required xtream output directories."""
    base = Path(CONFIG['directories']['base_path'])
    base.mkdir(parents=True, exist_ok=True)
    content = base / CONFIG['directories']['folder_name']
    content.mkdir(parents=True, exist_ok=True)
    for subdir in CONFIG['directories']['subdirs'].values():
        (content / subdir).mkdir(parents=True, exist_ok=True)


API_CONFIG = CONFIG['api']
PROCESSING = CONFIG['processing']
CACHE = CONFIG.get('cache', {})
FILTERING = CONFIG.get('filtering', {})
STREAM_TYPES = {
    'default': ['live_streams', 'vod', 'series'],
    'available': ['live_streams', 'vod', 'series', 'radio'],
}

SERIES_PROCESSING_DELAY = PROCESSING['delays']['series_processing']
SERIES_BATCH_DELAY = PROCESSING['delays']['series_batch']
API_CALL_DELAY = PROCESSING['delays']['api_calls']
