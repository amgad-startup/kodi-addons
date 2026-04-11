import logging
import requests
import os
from typing import Dict, Any, List, Optional
from iptv_toolkit.core.utils import detect_language, arabic_to_english
from iptv_toolkit.db.cache import cache_manager
from iptv_toolkit.core.config import TMDB_BASE_URL

class TMDBApi:
    def __init__(self):
        self.api_key = os.getenv('TMDB_API_KEY', 'a2764023c82b647eac48485b4deac0bf')
        self.base_url = TMDB_BASE_URL
        self.logger = logging.getLogger(__name__)

    def search_show(self, title: str) -> Optional[Dict]:
        """Search for a TV show by title with improved language handling"""
        self.logger.debug(f"Searching for show: {title}")
        
        # Check cache first using title as key
        cached_result = cache_manager.get('tmdb_search', title)
        if cached_result:
            self.logger.debug("Using cached search result")
            return cached_result
        
        # Detect language
        lang = detect_language(title)
        self.logger.debug(f"Detected language for '{title}': {lang}")
        
        # Try with detected language first
        result = self._search_tmdb(title, lang)
        if result:
            # Add overview in both languages and additional metadata
            result = self._enrich_show_data(result, lang)
            self.logger.debug(f"Found match in {lang}")
            cache_manager.set('tmdb_search', title, result)
            return result
            
        # If no results and language was Arabic, try English transliteration
        if lang == 'ar':
            transliterated = arabic_to_english(title)
            self.logger.debug(f"Trying transliterated title: {transliterated}")
            result = self._search_tmdb(transliterated, 'en')
            if result:
                # Add overview in both languages and additional metadata
                result = self._enrich_show_data(result, 'ar')
                self.logger.debug("Found match using transliterated title")
                # Cache using original title for easier lookup
                cache_manager.set('tmdb_search', title, result)
                return result
        
        # If still no results and language wasn't English, try English as fallback
        elif lang != 'en':
            self.logger.debug("Trying English as fallback")
            result = self._search_tmdb(title, 'en')
            if result:
                # Add overview in both languages and additional metadata
                result = self._enrich_show_data(result, lang)
                self.logger.debug("Found match in English")
                cache_manager.set('tmdb_search', title, result)
                return result
        
        self.logger.debug(f"No matches found for '{title}'")
        return None

    def _search_tmdb(self, title: str, lang: str) -> Optional[Dict]:
        """Internal method to search TMDB API"""
        params = {
            'api_key': self.api_key,
            'query': title,
            'language': f"{lang}-{'us' if lang == 'en' else lang}",
            'include_adult': True
        }
        
        response = requests.get(f"{self.base_url}/search/tv", params=params)
        results = response.json().get('results', [])
        
        if not results:
            return None
            
        # Try to find exact title match first
        for result in results:
            if result['name'].lower() == title.lower():
                return result
        
        # Fallback to first result
        return results[0]

    def _enrich_show_data(self, show_data: Dict, original_lang: str) -> Dict:
        """Add additional language data and metadata to show info"""
        show_id = show_data['id']
        
        # Get English data with credits and images
        en_params = {
            'api_key': self.api_key,
            'language': 'en-US',
            'append_to_response': 'credits,images,external_ids,content_ratings,keywords,recommendations,similar,videos,watch/providers'
        }
        en_response = requests.get(f"{self.base_url}/tv/{show_id}", params=en_params)
        en_data = en_response.json()
        
        # Get Arabic data
        ar_params = {
            'api_key': self.api_key,
            'language': 'ar-SA'
        }
        ar_response = requests.get(f"{self.base_url}/tv/{show_id}", params=ar_params)
        ar_data = ar_response.json()
        
        # Add both overviews to the result
        show_data['overview_en'] = en_data.get('overview', '')
        show_data['overview_ar'] = ar_data.get('overview', '')
        
        # Add episode runtime
        episode_runtime = en_data.get('episode_run_time', [])
        show_data['episode_runtime'] = episode_runtime[0] if episode_runtime else 0
        
        # Add director information from credits
        credits = en_data.get('credits', {})
        crew = credits.get('crew', [])
        directors = [member for member in crew if member.get('job') == 'Director']
        show_data['director'] = directors[0]['name'] if directors else None
        
        # Add full crew information
        show_data['crew'] = [
            {
                'name': member['name'],
                'job': member['job'],
                'department': member['department'],
                'profile_path': member['profile_path']
            }
            for member in crew
        ]
        
        # Add cast information
        cast = credits.get('cast', [])
        show_data['cast'] = [
            {
                'name': actor['name'],
                'character': actor['character'],
                'profile_path': actor['profile_path'],
                'order': actor['order'],
                'known_for_department': actor.get('known_for_department', '')
            }
            for actor in cast[:10]  # Get top 10 cast members
        ]
        
        # Add images/fanart with full metadata
        images = en_data.get('images', {})
        show_data['backdrops'] = [
            {
                'file_path': img['file_path'],
                'width': img['width'],
                'height': img['height'],
                'aspect_ratio': img['aspect_ratio'],
                'vote_average': img['vote_average'],
                'vote_count': img['vote_count'],
                'language': img.get('iso_639_1')
            }
            for img in images.get('backdrops', [])
        ]
        show_data['posters'] = [
            {
                'file_path': img['file_path'],
                'width': img['width'],
                'height': img['height'],
                'aspect_ratio': img['aspect_ratio'],
                'vote_average': img['vote_average'],
                'vote_count': img['vote_count'],
                'language': img.get('iso_639_1')
            }
            for img in images.get('posters', [])
        ]
        
        # Add videos (trailers, teasers, etc.)
        videos = en_data.get('videos', {}).get('results', [])
        show_data['videos'] = [
            {
                'name': video['name'],
                'key': video['key'],
                'site': video['site'],
                'type': video['type'],
                'official': video['official'],
                'language': video.get('iso_639_1')
            }
            for video in videos
        ]
        
        # Add content ratings
        content_ratings = en_data.get('content_ratings', {}).get('results', [])
        show_data['content_ratings'] = {
            rating['iso_3166_1']: rating['rating']
            for rating in content_ratings
        }
        
        # Add keywords/tags
        keywords = en_data.get('keywords', {}).get('results', [])
        show_data['keywords'] = [keyword['name'] for keyword in keywords]
        
        # Add recommendations
        recommendations = en_data.get('recommendations', {}).get('results', [])
        show_data['recommendations'] = [
            {
                'id': show['id'],
                'name': show['name'],
                'overview': show['overview'],
                'poster_path': show['poster_path'],
                'backdrop_path': show['backdrop_path'],
                'vote_average': show['vote_average']
            }
            for show in recommendations[:5]  # Get top 5 recommendations
        ]
        
        # Add similar shows
        similar = en_data.get('similar', {}).get('results', [])
        show_data['similar'] = [
            {
                'id': show['id'],
                'name': show['name'],
                'overview': show['overview'],
                'poster_path': show['poster_path'],
                'backdrop_path': show['backdrop_path'],
                'vote_average': show['vote_average']
            }
            for show in similar[:5]  # Get top 5 similar shows
        ]
        
        # Add watch providers (streaming platforms)
        watch_providers = en_data.get('watch/providers', {}).get('results', {})
        show_data['watch_providers'] = watch_providers
        
        # Add additional metadata
        show_data.update({
            'number_of_episodes': en_data.get('number_of_episodes', 0),
            'number_of_seasons': en_data.get('number_of_seasons', 0),
            'status': en_data.get('status', ''),
            'genres': en_data.get('genres', []),
            'networks': en_data.get('networks', []),
            'production_companies': en_data.get('production_companies', []),
            'production_countries': en_data.get('production_countries', []),
            'spoken_languages': en_data.get('spoken_languages', []),
            'first_air_date': en_data.get('first_air_date', ''),
            'last_air_date': en_data.get('last_air_date', ''),
            'homepage': en_data.get('homepage', ''),
            'in_production': en_data.get('in_production', False),
            'languages': en_data.get('languages', []),
            'origin_country': en_data.get('origin_country', []),
            'original_language': en_data.get('original_language', ''),
            'popularity': en_data.get('popularity', 0),
            'vote_average': en_data.get('vote_average', 0),
            'vote_count': en_data.get('vote_count', 0),
            'type': en_data.get('type', ''),
            'tagline': en_data.get('tagline', ''),
            'season_details': [
                {
                    'air_date': season.get('air_date'),
                    'episode_count': season.get('episode_count'),
                    'name': season.get('name'),
                    'overview': season.get('overview'),
                    'poster_path': season.get('poster_path'),
                    'season_number': season.get('season_number')
                }
                for season in en_data.get('seasons', [])
            ]
        })
        
        # Add external IDs
        external_ids = en_data.get('external_ids', {})
        show_data['external_ids'] = {
            'imdb_id': external_ids.get('imdb_id'),
            'tvdb_id': external_ids.get('tvdb_id'),
            'facebook_id': external_ids.get('facebook_id'),
            'instagram_id': external_ids.get('instagram_id'),
            'twitter_id': external_ids.get('twitter_id')
        }
        
        return show_data

    def get_show_details(self, tmdb_id: int) -> Dict:
        """Get detailed information for a TV show"""
        self.logger.debug(f"Getting details for TMDB ID: {tmdb_id}")
        
        # Check cache first
        cache_key = f"tmdb_details_{tmdb_id}"
        cached_result = cache_manager.get('tmdb_details', cache_key)
        if cached_result:
            self.logger.debug("Using cached show details")
            return cached_result
        
        self.logger.debug(f"No cache found, fetching details from TMDB API for ID: {tmdb_id}")
        
        # Get show details from TMDB API with all additional data
        params = {
            'api_key': self.api_key,
            'language': 'en-us',
            'append_to_response': 'credits,images,videos,external_ids'
        }
        
        response = requests.get(f"{self.base_url}/tv/{tmdb_id}", params=params)
        result = response.json()
        
        self.logger.debug(f"Cached details for TMDB ID {tmdb_id}")
        cache_manager.set('tmdb_details', cache_key, result)
        return result
