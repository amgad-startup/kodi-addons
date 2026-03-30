"""Module for managing media entries in the database."""

from db_path_manager import DBPathManager
from db_metadata_manager import DBMetadataManager

class DBMediaManager:
    def __init__(self, connection):
        """Initialize media manager with database connection."""
        self.connection = connection
        self.cursor = connection.cursor()
        self.path_manager = DBPathManager(self.cursor)
        self.metadata_manager = DBMetadataManager(self.cursor)

    def insert_movie(self, movie_data):
        """Insert movie and all related data into Kodi database."""
        print("\nInserting movie:", movie_data.get('title', ''))
        try:
            # Insert path and file
            file_id = self.path_manager.get_file_id(movie_data['path'], movie_data['filename'])
            print(f"Got file ID: {file_id}")
            
            # Insert movie
            print("Inserting movie with data:", {
                'title': movie_data.get('title', ''),
                'plot': movie_data.get('plot', ''),
                'year': movie_data.get('year', ''),
                'thumbnail': movie_data.get('thumbnail', ''),
                'genres': movie_data.get('genres', []),
                'director': movie_data.get('director', '')
            })
            
            # Match Kodi's schema exactly
            self.cursor.execute("""
                INSERT INTO movie (
                    idFile, c00, c01, c02, c03, c04, c05, c06, c07, c08, c09,
                    c10, c11, c12, c13, c14, c15, c16, c17, c18, c19,
                    c20, c21, c22, c23,
                    idSet, userrating, premiered
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?
                )
            """, (
                file_id,                               # idFile
                movie_data.get('title', ''),          # c00 - Title
                movie_data.get('plot', ''),           # c01 - Plot
                '',                                   # c02
                '',                                   # c03
                '',                                   # c04
                '',                                   # c05
                '',                                   # c06
                movie_data.get('year', ''),          # c07 - Year
                movie_data.get('thumbnail', ''),      # c08 - Thumbnail URL
                '',                                   # c09
                '',                                   # c10
                '',                                   # c11
                '',                                   # c12
                '',                                   # c13
                '/'.join(movie_data.get('genres', [])), # c14 - Genre string
                movie_data.get('director', ''),       # c15 - Director
                '',                                   # c16
                '',                                   # c17
                '',                                   # c18
                movie_data.get('premiered', ''),      # c19 - Premiered date
                '',                                   # c20
                movie_data.get('country', 'Egypt'),   # c21 - Country
                '',                                   # c22
                '',                                   # c23
                0,                                    # idSet
                0,                                    # userrating
                movie_data.get('premiered', '')       # premiered
            ))
            
            # Get movie ID
            self.cursor.execute("SELECT last_insert_rowid()")
            movie_id = self.cursor.fetchone()[0]
            print(f"Inserted movie ID: {movie_id}")
            
            # Verify movie was inserted
            self.cursor.execute("SELECT idMovie, c00 FROM movie WHERE idMovie = ?", (movie_id,))
            result = self.cursor.fetchone()
            if result:
                print(f"Verified movie in database: ID={result[0]}, Title={result[1]}")
            else:
                print("WARNING: Movie not found in database after insert!")
            
            # Insert metadata
            self.metadata_manager.insert_all_metadata(movie_data, movie_id, 'movie')
            
            self.connection.commit()
            print("Movie inserted successfully")
            return True
            
        except Exception as e:
            print(f"Error inserting movie: {str(e)}")
            import traceback
            print("Traceback:", traceback.format_exc())
            self.connection.rollback()
            return False

    def insert_tvshow(self, show_data):
        """Insert TV show and all related data into Kodi database."""
        print("\nInserting TV show:", show_data.get('title', ''))
        try:
            # Insert path
            path_id = self.path_manager.insert_path(show_data['path'])
            
            # Insert TV show
            self.cursor.execute("""
                INSERT INTO tvshow (
                    c00, c01, c04, c05, c08, c09, c13, c14
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                show_data.get('title', ''),            # c00 - Title
                show_data.get('plot', ''),             # c01 - Plot
                show_data.get('rating', 0),            # c04 - Rating
                show_data.get('premiered', ''),        # c05 - First Aired
                '/'.join(show_data.get('genres', [])), # c08 - Genre string
                show_data.get('thumbnail', ''),        # c09 - Thumbnail URL
                show_data.get('status', 'Continuing'), # c13 - Status
                show_data.get('runtime', 0)            # c14 - Runtime
            ))
            
            # Get show ID
            self.cursor.execute("SELECT last_insert_rowid()")
            show_id = self.cursor.fetchone()[0]
            print(f"Inserted show ID: {show_id}")
            
            # Link path to show
            self.path_manager.link_tvshow_path(show_id, path_id)
            
            # Insert metadata
            self.metadata_manager.insert_all_metadata(show_data, show_id, 'tvshow')
            
            self.connection.commit()
            print("TV show inserted successfully")
            return show_id
            
        except Exception as e:
            print(f"Error inserting TV show: {str(e)}")
            import traceback
            print("Traceback:", traceback.format_exc())
            self.connection.rollback()
            return None

    def insert_episode(self, episode_data):
        """Insert TV episode and all related data into Kodi database."""
        print(f"\nInserting episode S{episode_data.get('season', '')}E{episode_data.get('episode', '')}")
        try:
            # Insert path and file
            file_id = self.path_manager.get_file_id(episode_data['path'], episode_data['filename'])
            print(f"Got file ID: {file_id}")
            
            # Insert episode
            print("Inserting episode with data:", {
                'title': episode_data.get('title', ''),
                'plot': episode_data.get('plot', ''),
                'season': episode_data.get('season', ''),
                'episode': episode_data.get('episode', ''),
                'show_id': episode_data.get('show_id', '')
            })
            
            self.cursor.execute("""
                INSERT INTO episode (
                    idFile, c00, c01, c03, c04, c05, c09, c10, c12, c13, idShow
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_id,                               # idFile
                episode_data.get('title', ''),         # c00 - Title
                episode_data.get('plot', ''),          # c01 - Plot
                episode_data.get('rating', 0),         # c03 - Rating
                str(episode_data['episode']),          # c04 - Episode number
                episode_data.get('premiered', ''),     # c05 - First aired
                episode_data.get('runtime', 0),        # c09 - Runtime
                episode_data.get('director', ''),      # c10 - Director
                str(episode_data['season']),           # c12 - Season number
                episode_data.get('thumbnail', ''),     # c13 - Thumbnail URL
                episode_data['show_id']                # idShow
            ))
            
            # Get episode ID
            self.cursor.execute("SELECT last_insert_rowid()")
            episode_id = self.cursor.fetchone()[0]
            print(f"Inserted episode ID: {episode_id}")
            
            # Verify episode was inserted
            self.cursor.execute("SELECT idEpisode, c00 FROM episode WHERE idEpisode = ?", (episode_id,))
            result = self.cursor.fetchone()
            if result:
                print(f"Verified episode in database: ID={result[0]}, Title={result[1]}")
            else:
                print("WARNING: Episode not found in database after insert!")
            
            # Insert metadata
            self.metadata_manager.insert_all_metadata(episode_data, episode_id, 'episode')
            
            self.connection.commit()
            print("Episode inserted successfully")
            return True
            
        except Exception as e:
            print(f"Error inserting episode: {str(e)}")
            import traceback
            print("Traceback:", traceback.format_exc())
            self.connection.rollback()
            return False
