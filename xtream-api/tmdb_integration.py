"""Module for integrating with TMDB API."""

import os
import json
import sqlite3
import requests
from pathlib import Path
from datetime import datetime
from logger import get_logger

# Setup logger
logger = get_logger(__name__)

class TMDBIntegration:
    def __init__(self):
        """Initialize TMDBIntegration."""
        self.iptveditor_path = Path(os.path.expanduser("~/Projects/kodi/iptveditor"))
        self.shows_cache = self._load_shows_cache()
        self.db_connection = self._connect_cache_db()
        if self.db_connection:
            self._init_db()
            
        # TMDB API configuration
        self.base_url = "https://api.themoviedb.org/3"  # Use v3 API
        self.language = "ar"  # Default to Arabic
        self.headers = {
            "accept": "application/json"
            # "Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJhdWQiOiIxYzdiOTZjOWRlOGQ4Mzg1Mjc1NzVlNzgzNGMxZTRjYyIsInN1YiI6IjY1NjY4ZjE3ODlkOTdmMDBlMTI0ZjVhZiIsInNjb3BlcyI6WyJhcGlfcmVhZCJdLCJ2ZXJzaW9uIjoxfQ.Hs_Yj_GrK_OHrNu8QqHGXqHGUzrO-uYuEX-cV1F5Ztg"
        }

    def _load_shows_cache(self):
        """Load the shows cache from tvshows-shows.json"""
        try:
            shows_file = self.iptveditor_path / "tvshows-shows.json"
            if shows_file.exists():
                with open(shows_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    cache = {}
                    for item in data.get('items', []):
                        cache[item['name']] = item
                        if 'transliterated_name' in item:
                            cache[item['transliterated_name']] = item
                    return cache
            return {}
        except Exception as e:
            logger.error(f"Error loading shows cache: {str(e)}")
            return {}

    def _connect_cache_db(self):
        """Connect to the cache database"""
        try:
            db_path = self.iptveditor_path / "cache.db"
            if not db_path.exists():
                logger.warning(f"Cache database not found at {db_path}")
                return None
            return sqlite3.connect(db_path)
        except Exception as e:
            logger.error(f"Error connecting to cache DB: {str(e)}")
            return None

    def _init_db(self):
        """Initialize database tables if they don't exist"""
        try:
            if not self.db_connection:
                return
                
            cursor = self.db_connection.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tmdb_search_cache (
                    title TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tmdb_details_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS episodes_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS update_cache (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Error initializing database: {str(e)}")

    def _get_from_cache(self, table_name, key, use_title=False):
        """Get data from cache table"""
        if not self.db_connection:
            return None
        try:
            cursor = self.db_connection.cursor()
            field = "title" if use_title else "key"
            cursor.execute(f"SELECT value FROM {table_name} WHERE {field} = ?", (key,))
            row = cursor.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Error querying {table_name}: {str(e)}")
        return None

    def _save_to_cache(self, table_name, key, value, use_title=False):
        """Save data to cache table"""
        if not self.db_connection:
            return
        try:
            cursor = self.db_connection.cursor()
            field = "title" if use_title else "key"
            cursor.execute(f"INSERT OR REPLACE INTO {table_name} ({field}, value) VALUES (?, ?)",
                         (key, json.dumps(value)))
            self.db_connection.commit()
        except Exception as e:
            logger.error(f"Error saving to {table_name}: {str(e)}")

    def _get_tmdb_data(self, endpoint, params=None):
            """Make a request to TMDB API"""
            if params is None:
                params = {}
            params['language'] = self.language
            params['api_key'] = os.getenv('TMDB_API_KEY')
            
            url = f"{self.base_url}/{endpoint}"
            try:
                response = requests.get(url, params=params, headers=self.headers)
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.error(f"Error fetching from TMDB: {str(e)}")
                return None


    def _get_series_details(self, series_id):
        """Get detailed series information from TMDB"""
        # Get basic series info
        series_data = self._get_tmdb_data(f"tv/{series_id}", {
            'append_to_response': 'credits,videos,external_ids'
        })
        
        if not series_data:
            return None
            
        # Extract director from crew
        director = None
        if series_data.get('credits', {}).get('crew'):
            for crew_member in series_data['credits']['crew']:
                if crew_member.get('job') == 'Director':
                    director = crew_member.get('name')
                    break
                    
        # Add director to data
        if director:
            series_data['director'] = director
            
        # Add cast from credits
        if series_data.get('credits', {}).get('cast'):
            series_data['cast'] = series_data['credits']['cast']
            
        # Get English overview
        en_data = self._get_tmdb_data(f"tv/{series_id}", {'language': 'en-US'})
        if en_data and en_data.get('overview'):
            series_data['overview_en'] = en_data['overview']
            
        return series_data

    def search_by_tmdb_id(self, tmdb_id, media_type='movie'):
        """Search for content by TMDB ID"""
        if not tmdb_id:
            return None
            
        logger.debug(f"Searching TMDB by ID: {tmdb_id} (type: {media_type})")
            
        # Check cache first
        cache_key = f"{media_type}_{tmdb_id}"
        cached_data = self._get_from_cache('tmdb_details_cache', cache_key)
        if cached_data:
            logger.debug(f"Found cached TMDB data for ID {tmdb_id}")
            return cached_data
            
        # If not in cache, fetch from API
        if media_type == 'series':
            data = self._get_series_details(tmdb_id)
        else:
            data = self._get_tmdb_data(f"movie/{tmdb_id}", {
                'append_to_response': 'credits,videos,external_ids'
            })
            
        if data:
            # Save to cache
            self._save_to_cache('tmdb_details_cache', cache_key, data)
            return data
            
        return None

    def search_by_name(self, name, media_type='movie', language='en'):
        """Search for content by name"""
        if not name:
            return None
            
        logger.debug(f"Searching TMDB by name: {name} (type: {media_type}, language: {language})")
            
        # Check cache first
        cached_data = self._get_from_cache('tmdb_search_cache', name, use_title=True)
        if cached_data:
            logger.debug(f"Found cached TMDB data for name '{name}'")
            return cached_data
            
        # If not in cache, search TMDB
        search_type = "tv" if media_type == 'series' else "movie"
        
        # Try searching with Arabic language first
        search_data = self._get_tmdb_data(f"search/{search_type}", {
            'query': name,
            'include_adult': 'false',
            'language': 'ar'
        })
        
        # If no results, try with English language
        if not search_data or not search_data.get('results'):
            search_data = self._get_tmdb_data(f"search/{search_type}", {
                'query': name,
                'include_adult': 'false',
                'language': 'en-US'
            })
        
        if search_data and search_data.get('results'):
            # Get first result that matches Arabic content (either by original_language or production_countries)
            for result in search_data['results']:
                # Get full details to check production countries
                if media_type == 'series':
                    data = self._get_series_details(result['id'])
                else:
                    data = self._get_tmdb_data(f"movie/{result['id']}", {
                        'append_to_response': 'credits,videos,external_ids'
                    })
                
                if data:
                    # Check if it's Arabic content by language or production country
                    is_arabic = (
                        data.get('original_language') == 'ar' or
                        any(country.get('iso_3166_1') in ['EG', 'SA', 'AE', 'KW', 'BH', 'QA', 'OM', 'LB', 'SY', 'JO', 'IQ', 'YE', 'PS', 'SD', 'TN', 'DZ', 'MA', 'LY']
                            for country in data.get('production_countries', []))
                    )
                    
                    if is_arabic:
                        # Save to cache
                        self._save_to_cache('tmdb_search_cache', name, data, use_title=True)
                        return data
                        
        return None

    def get_metadata(self, xtream_data, media_type='movie', language='en'):
        """Get metadata, using TMDB as fallback for missing Xtream data"""
        if not xtream_data:
            return None
            
        logger.debug(f"Getting metadata for {xtream_data.get('name', 'Unknown')} (type: {media_type})")
            
        # Initialize with Xtream data
        metadata = {
            'title': xtream_data.get('name', ''),
            'original_title': xtream_data.get('o_name', ''),
            'plot': xtream_data.get('plot', ''),
            'cast': xtream_data.get('cast', ''),
            'director': xtream_data.get('director', ''),
            'genre': xtream_data.get('genre', ''),
            'rating': xtream_data.get('rating', ''),
            'cover': xtream_data.get('cover', ''),
            'backdrop': xtream_data.get('backdrop', ''),
        }
        
        # Add media type specific fields
        if media_type == 'movie':
            metadata.update({
                'duration_secs': xtream_data.get('duration_secs', 0),
                'year': xtream_data.get('year', ''),
            })
        else:  # series
            metadata.update({
                'episode_run_time': xtream_data.get('episode_run_time', ''),
                'status': xtream_data.get('status', ''),
                'last_modified': xtream_data.get('last_modified', ''),
            })
        
        # Try to get TMDB data if plot is missing or empty
        if not metadata.get('plot'):
            tmdb_data = None
            
            # First try by TMDB ID if available
            tmdb_id = xtream_data.get('tmdb_id')
            if tmdb_id:
                logger.debug(f"Trying TMDB lookup by ID: {tmdb_id}")
                tmdb_data = self.search_by_tmdb_id(tmdb_id, media_type)
            
            # If no TMDB ID or not found, try by name
            if not tmdb_data:
                name = metadata.get('title')
                if name:
                    logger.debug(f"Trying TMDB lookup by name: {name}")
                    tmdb_data = self.search_by_name(name, media_type, language)
            
            # If TMDB data found, enhance metadata
            if tmdb_data:
                logger.debug("Found TMDB data, enhancing metadata")
                # Update plot if missing
                if not metadata['plot']:
                    metadata['plot'] = tmdb_data.get(f'overview_{language}', tmdb_data.get('overview', ''))
                
                # Update other missing fields
                if not metadata['cast'] and tmdb_data.get('cast'):
                    metadata['cast'] = tmdb_data['cast']
                if not metadata['director'] and tmdb_data.get('director'):
                    metadata['director'] = tmdb_data['director']
                if not metadata['genre'] and tmdb_data.get('genres'):
                    metadata['genre'] = ', '.join(g.get('name', '') for g in tmdb_data['genres'])
                if not metadata['rating'] and tmdb_data.get('vote_average'):
                    metadata['rating'] = tmdb_data['vote_average']
                
                # Update images if missing
                if not metadata['cover'] and tmdb_data.get('poster_path'):
                    metadata['cover'] = f"https://image.tmdb.org/t/p/original{tmdb_data['poster_path']}"
                if not metadata['backdrop'] and tmdb_data.get('backdrop_path'):
                    metadata['backdrop'] = f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}"
                
                # Add TMDB specific fields
                metadata['tmdb_id'] = tmdb_data.get('id', '')
                metadata['production_companies'] = tmdb_data.get('production_companies', [])
                metadata['external_ids'] = tmdb_data.get('external_ids', {})
                metadata['videos'] = tmdb_data.get('videos', [])
            else:
                logger.debug("No TMDB data found")
        
        return metadata

    def get_movie_metadata(self, movie_name, language='en'):
        """Get movie metadata from cache with language support"""
        # Check cache.db first
        search_data = self._get_from_cache('tmdb_search_cache', movie_name, use_title=True)
        if search_data and isinstance(search_data, dict):
            # Format cast with character names
            cast_list = []
            for actor in search_data.get('cast', [])[:10]:
                name = actor.get('name', '')
                character = actor.get('character', '')
                if character:
                    cast_list.append(f"{name} as {character}")
                else:
                    cast_list.append(name)

            # Get genre from genres array
            genres = search_data.get('genres', [])
            genre = ', '.join(g.get('name', '') for g in genres) if genres else None

            # Get production companies
            production_companies = [p.get('name', '') for p in search_data.get('production_companies', [])]

            # Get plot in correct language
            plot = search_data.get(f'overview_{language}', search_data.get('overview', ''))

            # Get backdrop path
            backdrop_path = search_data.get('backdrop_path', '')
            fanart = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else ''

            # Get poster path
            poster_path = search_data.get('poster_path', '')
            poster = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else ''

            return {
                'title': search_data.get('title', movie_name),
                'original_title': search_data.get('original_title', movie_name),
                'transliterated_title': '',
                'rating': search_data.get('vote_average', 0),
                'plot': plot,
                'genre': genre,
                'director': search_data.get('director', ''),
                'cast': cast_list,
                'release_date': search_data.get('release_date', ''),
                'runtime': str(search_data.get('runtime', 0)),
                'mpaa': search_data.get('mpaa', ''),
                'tmdb_id': search_data.get('id', ''),
                'poster': poster,
                'fanart': fanart,
                'language': language,
                # Additional fields
                'production_companies': production_companies,
                'external_ids': search_data.get('external_ids', {}),
                'videos': search_data.get('videos', []),
                'country': search_data.get('production_countries', [{}])[0].get('name', ''),
                'year': search_data.get('release_date', '')[:4] if search_data.get('release_date') else ''
            }

        return None

    def get_show_metadata(self, show_name, language='en'):
        """Get show metadata from cache with language support"""
        # Check cache.db first
        search_data = self._get_from_cache('tmdb_search_cache', show_name, use_title=True)
        if search_data and isinstance(search_data, dict):
            # Format cast with character names
            cast_list = []
            for actor in search_data.get('cast', [])[:10]:
                name = actor.get('name', '')
                character = actor.get('character', '')
                if character:
                    cast_list.append(f"{name} as {character}")
                else:
                    cast_list.append(name)

            # Get genre from genres array
            genres = search_data.get('genres', [])
            genre = ', '.join(g.get('name', '') for g in genres) if genres else None

            # Get networks
            networks = [n.get('name', '') for n in search_data.get('networks', [])]

            # Get production companies
            production_companies = [p.get('name', '') for p in search_data.get('production_companies', [])]

            # Get plot in correct language
            plot = search_data.get(f'overview_{language}', search_data.get('overview', ''))

            # Get backdrop path
            backdrop_path = search_data.get('backdrop_path', '')
            fanart = f"https://image.tmdb.org/t/p/original{backdrop_path}" if backdrop_path else ''

            # Get poster path
            poster_path = search_data.get('poster_path', '')
            poster = f"https://image.tmdb.org/t/p/original{poster_path}" if poster_path else ''

            return {
                'title': search_data.get('name', show_name),
                'original_title': search_data.get('original_name', show_name),
                'transliterated_title': '',
                'rating': search_data.get('vote_average', 0),
                'plot': plot,
                'genre': genre,
                'director': search_data.get('director', ''),
                'cast': cast_list,
                'premiered': search_data.get('first_air_date', ''),
                'episode_run_time': str(search_data.get('episode_runtime', 0)),
                'status': search_data.get('status', ''),
                'tmdb_id': search_data.get('id', ''),
                'poster': poster,
                'fanart': fanart,
                'language': language,
                # Additional fields
                'number_of_episodes': search_data.get('number_of_episodes', ''),
                'number_of_seasons': search_data.get('number_of_seasons', ''),
                'networks': networks,
                'production_companies': production_companies,
                'season_details': search_data.get('season_details', []),
                'external_ids': search_data.get('external_ids', {}),
                'videos': search_data.get('videos', []),
                'type': search_data.get('type', ''),
                'in_production': search_data.get('in_production', True),
                'last_air_date': search_data.get('last_air_date', '')
            }

        # Then check tvshows-shows.json cache as fallback
        show_data = self.shows_cache.get(show_name)
        if show_data:
            title = show_data.get('arabic_name', show_data['name']) if language == 'ar' else show_data['name']
            return {
                'title': title,
                'original_title': show_data.get('old_name', show_data['name']),
                'transliterated_title': show_data.get('transliterated_name', ''),
                'rating': show_data.get('rating', ''),
                'plot': show_data.get(f'overview_{language}', ''),
                'genre': show_data.get('genre', ''),
                'director': show_data.get('director', ''),
                'cast': show_data.get('cast', '').split(', ') if show_data.get('cast') else [],
                'premiered': show_data.get('releaseDate', ''),
                'episode_run_time': show_data.get('episode_run_time', ''),
                'status': 'Continuing' if not show_data.get('finished', False) else 'Ended',
                'tmdb_id': show_data.get('tmdb'),
                'poster': show_data.get('image', ''),
                'fanart': show_data.get('backdrop', ''),
                'language': language
            }

        return None

    def __del__(self):
        """Clean up database connection"""
        if self.db_connection:
            self.db_connection.close()
