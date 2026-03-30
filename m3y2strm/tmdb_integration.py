import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

class TMDBIntegration:
    def __init__(self):
        self.iptveditor_path = Path(os.path.expanduser("~/Projects/kodi/iptveditor"))
        self.shows_cache = self._load_shows_cache()
        self.db_connection = self._connect_cache_db()
        if self.db_connection:
            self._init_db()

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
            print(f"Error loading shows cache: {str(e)}")
            return {}

    def _connect_cache_db(self):
        """Connect to the cache database"""
        try:
            db_path = self.iptveditor_path / "cache.db"
            if not db_path.exists():
                print(f"Warning: Cache database not found at {db_path}")
                return None
            return sqlite3.connect(db_path)
        except Exception as e:
            print(f"Error connecting to cache DB: {str(e)}")
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
            print(f"Error initializing database: {str(e)}")

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
            print(f"Error querying {table_name}: {str(e)}")
        return None

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
