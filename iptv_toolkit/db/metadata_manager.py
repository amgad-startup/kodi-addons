"""Module for managing metadata in the database."""

class DBMetadataManager:
    def __init__(self, cursor):
        """Initialize metadata manager with database cursor."""
        self.cursor = cursor

    def insert_genres(self, genres, media_id, media_type='movie'):
        """Insert genres and link them to media."""
        # First remove any existing genre links
        self.cursor.execute("DELETE FROM genre_link WHERE media_id = ? AND media_type = ?", 
                          (media_id, media_type))
        
        for genre in genres:
            if not genre.strip():
                continue
            # Insert genre
            self.cursor.execute("INSERT OR IGNORE INTO genre (name) VALUES (?)", (genre.strip(),))
            self.cursor.execute("SELECT genre_id FROM genre WHERE name = ?", (genre.strip(),))
            genre_id = self.cursor.fetchone()[0]
            
            # Link genre to media
            self.cursor.execute("""
                INSERT OR IGNORE INTO genre_link (genre_id, media_id, media_type)
                VALUES (?, ?, ?)
            """, (genre_id, media_id, media_type))
        print(f"Inserted genres for {media_type} ID {media_id}: {genres}")

    def insert_actors(self, actors, media_id, media_type='movie'):
        """Insert actors and link them to media."""
        # First remove any existing actor links
        self.cursor.execute("DELETE FROM actor_link WHERE media_id = ? AND media_type = ?", 
                          (media_id, media_type))
        
        for order, actor in enumerate(actors, 1):
            if not actor.strip():
                continue
            # Insert actor
            self.cursor.execute("INSERT OR IGNORE INTO actor (name) VALUES (?)", (actor.strip(),))
            self.cursor.execute("SELECT actor_id FROM actor WHERE name = ?", (actor.strip(),))
            actor_id = self.cursor.fetchone()[0]
            
            # Link actor to media
            self.cursor.execute("""
                INSERT OR IGNORE INTO actor_link 
                (actor_id, media_id, media_type, role, cast_order)
                VALUES (?, ?, ?, ?, ?)
            """, (actor_id, media_id, media_type, '', order))
        print(f"Inserted actors for {media_type} ID {media_id}: {actors}")

    def insert_uniqueid(self, media_id, source, value, media_type='movie'):
        """Insert unique ID (e.g., TMDB ID)."""
        if not value:
            return
        self.cursor.execute("""
            INSERT OR REPLACE INTO uniqueid 
            (media_id, media_type, value, type)
            VALUES (?, ?, ?, ?)
        """, (media_id, media_type, value, source))
        print(f"Inserted unique ID for {media_type} ID {media_id}: {source}={value}")

    def insert_ratings(self, media_id, rating, media_type='movie', votes=0):
        """Insert media rating."""
        if not rating:
            return
        self.cursor.execute("""
            INSERT OR REPLACE INTO rating 
            (media_id, media_type, rating_type, rating, votes)
            VALUES (?, ?, ?, ?, ?)
        """, (media_id, media_type, 'tmdb', rating, votes))
        print(f"Inserted rating for {media_type} ID {media_id}: {rating}")

    def insert_tags(self, tags, media_id, media_type='movie'):
        """Insert tags and link them to media."""
        # First remove any existing tag links
        self.cursor.execute("DELETE FROM tag_link WHERE media_id = ? AND media_type = ?", 
                          (media_id, media_type))
        
        for tag in tags:
            if not tag.strip():
                continue
            # Insert tag
            self.cursor.execute("INSERT OR IGNORE INTO tag (name) VALUES (?)", (tag.strip(),))
            self.cursor.execute("SELECT tag_id FROM tag WHERE name = ?", (tag.strip(),))
            tag_id = self.cursor.fetchone()[0]
            
            # Link tag to media
            self.cursor.execute("""
                INSERT OR IGNORE INTO tag_link 
                (tag_id, media_id, media_type)
                VALUES (?, ?, ?)
            """, (tag_id, media_id, media_type))
        print(f"Inserted tags for {media_type} ID {media_id}: {tags}")

    def insert_all_metadata(self, media_data, media_id, media_type='movie'):
        """Insert all available metadata for a media item."""
        if media_data.get('genres'):
            self.insert_genres(media_data['genres'], media_id, media_type)
            
        if media_data.get('actors'):
            self.insert_actors(media_data['actors'], media_id, media_type)
            
        if media_data.get('tmdb_id'):
            self.insert_uniqueid(media_id, 'tmdb', media_data['tmdb_id'], media_type)
            
        if media_data.get('rating'):
            self.insert_ratings(media_id, media_data['rating'], media_type)
            
        if media_data.get('tags'):
            self.insert_tags(media_data['tags'], media_id, media_type)
