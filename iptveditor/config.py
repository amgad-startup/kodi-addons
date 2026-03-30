import os
from typing import Dict
from dotenv import load_dotenv
from utils import load_env_var

# Load environment variables from .env file
load_dotenv()

# API Keys and Tokens (loaded from environment)
TMDB_API_KEY = load_env_var('TMDB_API_KEY')
IPTVEDITOR_TOKEN = load_env_var('IPTVEDITOR_TOKEN')
IPTVEDITOR_PLAYLIST_ID = load_env_var('IPTVEDITOR_PLAYLIST_ID')

# File paths
STATE_FILE = "editor_state.json"
CATEGORIES_FILE = "tvshows-categories.json"
SHOWS_FILE = "tvshows-shows.json"

# API URLs
IPTVEDITOR_BASE_URL = "https://editor.iptveditor.com/api"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# HTTP Headers
HTTP_HEADERS: Dict[str, str] = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'content-type': 'application/json',
    'origin': 'https://cloud.iptveditor.com',
    'priority': 'u=1, i',
    'referer': 'https://cloud.iptveditor.com/',
    'sec-ch-ua': '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
}

# Default settings
DEFAULT_BATCH_SIZE = 10

# Language settings
FALLBACK_TO_FIRST_RESULT = True  # Whether to use first result when language doesn't match
