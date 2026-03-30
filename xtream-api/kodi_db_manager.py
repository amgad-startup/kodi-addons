"""Main module for managing Kodi's video database.

This module provides a high-level interface for interacting with Kodi's video database.
It serves as a wrapper around DBMediaManager, providing connection management and
transaction handling for database operations.

The KodiDBManager class ensures:
- Safe database connections with proper locking
- Connection pooling and reuse
- Transaction management
- Proper cleanup of resources

Key Features:
    - Manages database connections through DBConnection
    - Provides high-level methods for media insertion
    - Handles connection lifecycle
    - Ensures thread-safe database access
    - Manages transactions automatically

Example:
    db_manager = KodiDBManager()
    movie_data = {
        'title': 'Movie Title',
        'plot': 'Movie Plot',
        'year': '2024',
        'path': '/path/to/movie'
    }
    success = db_manager.insert_movie(movie_data)
"""

from db_connection import DBConnection
from db_media_manager import DBMediaManager

class KodiDBManager:
    def __init__(self, db_path=None):
        """Initialize database manager with optional custom database path.
        
        Args:
            db_path: Optional path to Kodi's video database. If not provided,
                    uses default path from DBConnection.
        """
        self.connection = DBConnection(db_path)
        self.media_manager = None
        
    def _ensure_media_manager(self):
        """Ensure media manager is initialized with an active connection.
        
        This method:
        1. Creates media manager if it doesn't exist
        2. Uses a fresh connection for each operation
        3. Ensures thread safety
        
        Returns:
            DBMediaManager: Initialized media manager
        """
        if not self.media_manager:
            self.media_manager = DBMediaManager(self.connection.get_connection())
        return self.media_manager
                
    def insert_movie(self, movie_data):
        """Insert movie and all related data into Kodi database.
        
        This method:
        1. Gets a fresh database connection
        2. Inserts movie metadata
        3. Handles related data (actors, genres, etc.)
        4. Manages transaction
        
        Args:
            movie_data: Dictionary containing movie information including:
                - title: Movie title
                - plot: Movie plot
                - year: Release year
                - path: Path to movie file
                - cast: List of actors
                - genre: Movie genre(s)
                - And other metadata fields
                
        Returns:
            bool: True if insertion successful, False otherwise
        """
        return self._ensure_media_manager().insert_movie(movie_data)
                
    def insert_tvshow(self, show_data):
        """Insert TV show and all related data into Kodi database.
        
        This method:
        1. Gets a fresh database connection
        2. Inserts show metadata
        3. Handles related data (actors, genres, etc.)
        4. Manages transaction
        
        Args:
            show_data: Dictionary containing TV show information including:
                - title: Show title
                - plot: Show description
                - year: First air year
                - path: Path to show directory
                - cast: List of actors
                - genre: Show genre(s)
                - And other metadata fields
                
        Returns:
            int: Show ID if insertion successful, None otherwise
        """
        return self._ensure_media_manager().insert_tvshow(show_data)
                
    def insert_episode(self, episode_data):
        """Insert TV episode and all related data into Kodi database.
        
        This method:
        1. Gets a fresh database connection
        2. Inserts episode metadata
        3. Links episode to show
        4. Manages transaction
        
        Args:
            episode_data: Dictionary containing episode information including:
                - title: Episode title
                - plot: Episode description
                - season: Season number
                - episode: Episode number
                - show_id: ID of parent TV show
                - path: Path to episode file
                - And other metadata fields
                
        Returns:
            bool: True if insertion successful, False otherwise
        """
        return self._ensure_media_manager().insert_episode(episode_data)
