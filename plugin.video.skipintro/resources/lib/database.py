import sqlite3
import os
import xbmc
import xbmcvfs

class ShowDatabase:
    def __init__(self, db_path):
        """Initialize database connection"""
        try:
            self.db_path = db_path
            xbmc.log(f'SkipIntro: Initializing database at: {db_path}', xbmc.LOGINFO)
            
            # Ensure directory exists
            db_dir = os.path.dirname(db_path)
            if not os.path.exists(db_dir):
                os.makedirs(db_dir)
                xbmc.log(f'SkipIntro: Created database directory: {db_dir}', xbmc.LOGINFO)
            
            # Always create tables and migrate database
            self._create_tables()
            self._migrate_database()
            xbmc.log('SkipIntro: Database initialized and migrated', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f'SkipIntro: Database initialization error: {str(e)}', xbmc.LOGERROR)
            raise
    
    def _migrate_database(self):
        """Migrate database to current schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                
                # Migrate shows_config table
                self._migrate_table(c, 'shows_config', {
                    'show_id': 'INTEGER PRIMARY KEY',
                    'use_chapters': 'BOOLEAN DEFAULT 0',
                    'intro_start_chapter': 'INTEGER',
                    'intro_end_chapter': 'INTEGER',
                    'intro_start_time': 'REAL',
                    'intro_end_time': 'REAL',
                    'outro_start_time': 'REAL',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }, 'FOREIGN KEY (show_id) REFERENCES shows(id)')
                
                # Migrate episodes table
                self._migrate_table(c, 'episodes', {
                    'id': 'INTEGER PRIMARY KEY AUTOINCREMENT',
                    'show_id': 'INTEGER',
                    'season': 'INTEGER',
                    'episode': 'INTEGER',
                    'intro_start_chapter': 'INTEGER',
                    'intro_end_chapter': 'INTEGER',
                    'intro_start_time': 'REAL',
                    'intro_end_time': 'REAL',
                    'outro_start_time': 'REAL',
                    'source': 'TEXT',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }, 'FOREIGN KEY (show_id) REFERENCES shows(id), UNIQUE(show_id, season, episode)')
                
                conn.commit()
                xbmc.log('SkipIntro: Database migration completed successfully', xbmc.LOGINFO)
        except Exception as e:
            xbmc.log(f'SkipIntro: Database migration error: {str(e)}', xbmc.LOGERROR)

    def _migrate_table(self, cursor, table_name, columns, additional_sql=''):
        """Migrate a single table"""
        xbmc.log(f'SkipIntro: Migrating {table_name} table', xbmc.LOGINFO)
        
        # Check if the table exists
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        table_exists = cursor.fetchone() is not None

        if table_exists:
            # Get existing columns
            cursor.execute(f"PRAGMA table_info({table_name})")
            existing_columns = {column[1] for column in cursor.fetchall()}
            
            # Add missing columns
            for col_name, col_type in columns.items():
                if col_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
        else:
            # Create the table if it doesn't exist
            columns_sql = ', '.join(f"{col_name} {col_type}" for col_name, col_type in columns.items())
            cursor.execute(f"CREATE TABLE {table_name} ({columns_sql}, {additional_sql})")

        xbmc.log(f'SkipIntro: {table_name} table migration completed', xbmc.LOGINFO)
    
    def _create_tables(self):
        """Create database tables with current schema"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                
                # Shows table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS shows (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Shows config table
                c.execute('''
                    CREATE TABLE IF NOT EXISTS shows_config (
                        show_id INTEGER PRIMARY KEY,
                        use_chapters BOOLEAN DEFAULT 0,
                        intro_start_chapter INTEGER,
                        intro_end_chapter INTEGER,
                        intro_start_time REAL,
                        intro_end_time REAL,
                        outro_start_time REAL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (show_id) REFERENCES shows(id)
                    )
                ''')
                
                conn.commit()
        except Exception as e:
            xbmc.log(f'SkipIntro: Database error: {str(e)}', xbmc.LOGERROR)

    def get_show_config(self, show_id):
        """Get show configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''
                    SELECT use_chapters, intro_start_chapter, intro_end_chapter,
                           intro_start_time, intro_end_time, outro_start_time
                    FROM shows_config 
                    WHERE show_id = ?
                ''', (show_id,))
                result = c.fetchone()
                
                if result:
                    config = {
                        'use_chapters': bool(result[0]),
                        'intro_start_chapter': result[1],
                        'intro_end_chapter': result[2],
                        'intro_start_time': result[3],
                        'intro_end_time': result[4],
                        'outro_start_time': result[5]
                    }
                    xbmc.log(f'SkipIntro: Found show config: {config}', xbmc.LOGINFO)
                    return config
                
                return None
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show config: {str(e)}', xbmc.LOGERROR)
            return None

    def save_show_config(self, show_id, config):
        """Save show configuration"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT OR REPLACE INTO shows_config 
                    (show_id, use_chapters, intro_start_chapter, intro_end_chapter,
                     intro_start_time, intro_end_time, outro_start_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    show_id,
                    config.get('use_chapters', False),
                    config.get('intro_start_chapter'),
                    config.get('intro_end_chapter'),
                    config.get('intro_start_time'),
                    config.get('intro_end_time'),
                    config.get('outro_start_time')
                ))
                conn.commit()
                xbmc.log(f'SkipIntro: Successfully saved show config: {config}', xbmc.LOGINFO)
                return True
        except Exception as e:
            xbmc.log(f'SkipIntro: Error saving show config: {str(e)}', xbmc.LOGERROR)
            return False

    def get_show(self, title):
        """Get show by title, create if doesn't exist"""
        try:
            xbmc.log(f'SkipIntro: Looking up show: {title}', xbmc.LOGINFO)
            with sqlite3.connect(self.db_path) as conn:
                c = conn.cursor()
                c.execute('SELECT id FROM shows WHERE title = ?', (title,))
                result = c.fetchone()
                
                if result:
                    xbmc.log(f'SkipIntro: Found existing show ID: {result[0]}', xbmc.LOGINFO)
                    return result[0]
                
                xbmc.log(f'SkipIntro: Creating new show entry for: {title}', xbmc.LOGINFO)
                c.execute('INSERT INTO shows (title) VALUES (?)', (title,))
                conn.commit()
                show_id = c.lastrowid
                
                # Create empty show config without default values
                self.save_show_config(show_id, {
                    'use_chapters': False,
                    'intro_start_time': None,
                    'intro_end_time': None,
                    'outro_start_time': None
                })
                
                xbmc.log(f'SkipIntro: Created show with ID: {show_id}', xbmc.LOGINFO)
                return show_id
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show: {str(e)}', xbmc.LOGERROR)
            return None

    def set_manual_show_times(self, show_id, intro_start, intro_end, outro_start=None):
        """Manually set intro/outro times for a show"""
        try:
            config = {
                'use_chapters': False,
                'intro_start_time': intro_start,
                'intro_end_time': intro_end,
                'outro_start_time': outro_start,
                'intro_start_chapter': None,
                'intro_end_chapter': None,
                'outro_start_chapter': None
            }
            return self.save_show_config(show_id, config)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error setting manual show times: {str(e)}', xbmc.LOGERROR)
            return False

    def set_manual_show_chapters(self, show_id, use_chapters, intro_start_chapter, intro_end_chapter, outro_start_chapter=None):
        """Manually set intro/outro chapters for a show"""
        try:
            config = {
                'use_chapters': use_chapters,
                'intro_start_chapter': intro_start_chapter,
                'intro_end_chapter': intro_end_chapter,
                'outro_start_chapter': outro_start_chapter,
                'intro_start_time': None,
                'intro_end_time': None,
                'outro_start_time': None
            }
            return self.save_show_config(show_id, config)
        except Exception as e:
            xbmc.log(f'SkipIntro: Error setting manual show chapters: {str(e)}', xbmc.LOGERROR)
            return False

    def get_show_times(self, show_id):
        """Get intro/outro times or chapters for a show"""
        try:
            xbmc.log(f'SkipIntro: Getting times/chapters for show {show_id}', xbmc.LOGINFO)
            
            config = self.get_show_config(show_id)
            if config:
                if config.get('use_chapters'):
                    times = {
                        'use_chapters': True,
                        'intro_start_chapter': config.get('intro_start_chapter'),
                        'intro_end_chapter': config.get('intro_end_chapter'),
                        'outro_start_chapter': config.get('outro_start_chapter')
                    }
                else:
                    times = {
                        'use_chapters': False,
                        'intro_start_time': config.get('intro_start_time'),
                        'intro_end_time': config.get('intro_end_time'),
                        'outro_start_time': config.get('outro_start_time')
                    }
                xbmc.log(f'SkipIntro: Found show times/chapters: {times}', xbmc.LOGINFO)
                return times
            
            xbmc.log('SkipIntro: No times/chapters found for show', xbmc.LOGINFO)
            return None
        except Exception as e:
            xbmc.log(f'SkipIntro: Error getting show times/chapters: {str(e)}', xbmc.LOGERROR)
            return None
