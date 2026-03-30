import logging
import requests
from typing import Dict, List
from database import cache_manager
from config import HTTP_HEADERS, IPTVEDITOR_TOKEN, IPTVEDITOR_BASE_URL, IPTVEDITOR_PLAYLIST_ID

class IPTVEditorApi:
    def __init__(self):
        self.base_url = IPTVEDITOR_BASE_URL
        self.logger = logging.getLogger(__name__)
        self.headers = HTTP_HEADERS.copy()

    def get_categories(self) -> List[Dict]:
        """Get all categories"""
        url = f"{self.base_url}/category/series/get-data"
        payload = {
            "playlist": IPTVEDITOR_PLAYLIST_ID,
            "token": IPTVEDITOR_TOKEN
        }
        
        self.logger.debug(f"Making POST request to: {url}")
        self.logger.debug(f"Headers: {self.headers}")
        self.logger.debug(f"Payload: {payload}")
        
        response = requests.post(
            url,
            headers=self.headers,
            json=payload
        )
        
        self.logger.debug(f"Response status code: {response.status_code}")
        self.logger.debug(f"Response headers: {response.headers}")
        self.logger.debug(f"Response content: {response.text}")
        
        response.raise_for_status()
        return response.json()['items']

    def get_shows(self) -> List[Dict]:
        """Get all shows"""
        url = f"{self.base_url}/stream/series/get-data"
        payload = {
            "playlist": IPTVEDITOR_PLAYLIST_ID,
            "token": IPTVEDITOR_TOKEN
        }
        
        self.logger.debug(f"Making POST request to: {url}")
        
        response = requests.post(
            url,
            headers=self.headers,
            json=payload
        )
        
        response.raise_for_status()
        return response.json()['items']

    def get_episodes(self, show_id: int) -> List[Dict]:
        """Get episodes for a show"""
        self.logger.debug(f"Getting episodes for show ID: {show_id}")
        
        # Check cache first
        cache_key = f"episodes_{show_id}"
        cached_result = cache_manager.get('episodes', cache_key)
        if cached_result:
            self.logger.debug("Using cached episodes")
            return cached_result
        
        self.logger.debug(f"No cache found, fetching episodes from API for show ID: {show_id}")
        
        # Get episodes from API
        payload = {
            'seriesId': str(show_id),
            'url': None,
            'playlist': IPTVEDITOR_PLAYLIST_ID,
            'token': IPTVEDITOR_TOKEN
        }
        
        response = requests.post(
            f"{self.base_url}/episode/get-data",
            headers=self.headers,
            json=payload
        )
        result = response.json()['items']
        
        self.logger.debug(f"Cached episodes for show ID {show_id}")
        cache_manager.set('episodes', cache_key, result)
        return result

    def update_show(self, show_id: int, tmdb_id: int, category_id: int) -> bool:
        """Update a show with TMDB information"""
        self.logger.debug(f"Updating show ID {show_id} with TMDB ID {tmdb_id}")
        
        # Check cache first
        cache_key = f"update_{show_id}_{tmdb_id}"
        cached_result = cache_manager.get('update', cache_key)
        if cached_result:
            self.logger.debug("Using cached update result")
            return cached_result
        
        self.logger.debug(f"No cache found, updating show via API: {show_id}")
        
        # Update show via API with the correct payload structure
        payload = {
            'items': [{
                'id': show_id,
                'tmdb': tmdb_id,
                'youtube_trailer': '',
                'category': category_id
            }],
            'checkSaved': False,
            'playlist': IPTVEDITOR_PLAYLIST_ID,
            'token': IPTVEDITOR_TOKEN
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/stream/series/save",
                headers=self.headers,
                json=payload
            )
            
            # Log the full response for debugging
            self.logger.debug(f"API Response Status: {response.status_code}")
            self.logger.debug(f"Response headers: {response.headers}")
            self.logger.debug(f"Response content: {response.text}")
            
            response.raise_for_status()
            
            # Consider 200 status code and "200" response as success
            result = response.status_code == 200 and response.text.strip() == "200"
            
            self.logger.debug(f"Cached update result for show ID {show_id}")
            cache_manager.set('update', cache_key, result)
            return result
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"API request failed: {str(e)}")
            if hasattr(e.response, 'text'):
                self.logger.error(f"Error response content: {e.response.text}")
            return False
