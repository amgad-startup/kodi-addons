import logging
import json
import sqlite3
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

class CacheManager:
    def __init__(self):
        self.db_file = 'cache.db'
        self.hits = {}
        self.misses = {}
        self.logger = logging.getLogger(__name__)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database and create tables if they don't exist"""
        with sqlite3.connect(self.db_file) as conn:
            cursor = conn.cursor()
            
            # Create tables for different cache types
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tmdb_search_cache (
                    title TEXT PRIMARY KEY,  -- Using title as key for easy lookup
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
            
            # Create index on title for faster lookups
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_tmdb_search_title 
                ON tmdb_search_cache(title)
            ''')
            
            conn.commit()

    def _get_table_name(self, cache_type: str) -> str:
        """Get the corresponding table name for cache type"""
        return f"{cache_type}_cache"

    def get(self, cache_type: str, key: str) -> Optional[Any]:
        """Get value from cache"""
        if cache_type not in self.hits:
            self.hits[cache_type] = 0
            self.misses[cache_type] = 0

        table_name = self._get_table_name(cache_type)
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # For tmdb_search, use title as is
                if cache_type == 'tmdb_search':
                    cursor.execute(
                        f"SELECT value FROM {table_name} WHERE title = ?",
                        (key,)
                    )
                else:
                    cursor.execute(
                        f"SELECT value FROM {table_name} WHERE key = ?",
                        (key,)
                    )
                    
                result = cursor.fetchone()
                
                if result:
                    self.hits[cache_type] += 1
                    hit_rate = self._calculate_hit_rate(cache_type)
                    self.logger.debug(f"Cache HIT for {cache_type} (Hit rate: {hit_rate:.1f}%)")
                    return json.loads(result[0])
                else:
                    self.misses[cache_type] += 1
                    hit_rate = self._calculate_hit_rate(cache_type)
                    self.logger.debug(f"Cache MISS for {cache_type} (Hit rate: {hit_rate:.1f}%)")
                    return None
                    
        except sqlite3.Error as e:
            self.logger.error(f"Database error: {str(e)}")
            return None

    def set(self, cache_type: str, key: str, value: Any) -> None:
        """Set value in cache"""
        table_name = self._get_table_name(cache_type)
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                
                # For tmdb_search, use title as is
                if cache_type == 'tmdb_search':
                    cursor.execute(
                        f"INSERT OR REPLACE INTO {table_name} (title, value) VALUES (?, ?)",
                        (key, json.dumps(value))
                    )
                else:
                    cursor.execute(
                        f"INSERT OR REPLACE INTO {table_name} (key, value) VALUES (?, ?)",
                        (key, json.dumps(value))
                    )
                    
                conn.commit()
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error: {str(e)}")

    def search_by_title(self, title: str) -> Optional[Dict]:
        """Search for show/movie metadata by title"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT value FROM tmdb_search_cache WHERE title = ?",
                    (title,)
                )
                result = cursor.fetchone()
                
                if result:
                    return json.loads(result[0])
                return None
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error in search_by_title: {str(e)}")
            return None

    def list_cached_titles(self) -> List[str]:
        """List all cached show/movie titles"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT title FROM tmdb_search_cache ORDER BY title")
                return [row[0] for row in cursor.fetchall()]
                
        except sqlite3.Error as e:
            self.logger.error(f"Database error in list_cached_titles: {str(e)}")
            return []

    def _calculate_hit_rate(self, cache_type: str) -> float:
        """Calculate hit rate for cache type"""
        total = self.hits[cache_type] + self.misses[cache_type]
        return (self.hits[cache_type] / total * 100) if total > 0 else 0

    def report_stats(self) -> None:
        """Report cache statistics"""
        total_hits = sum(self.hits.values())
        total_misses = sum(self.misses.values())
        total = total_hits + total_misses
        hit_rate = (total_hits / total * 100) if total > 0 else 0
        
        self.logger.debug(
            f"Cache Statistics - "
            f"Hits: {total_hits} "
            f"Misses: {total_misses} "
            f"Hit Rate: {hit_rate:.1f}%"
        )

cache_manager = CacheManager()
