"""Module for managing paths and files in the database."""

import os
from datetime import datetime

class DBPathManager:
    def __init__(self, cursor):
        """Initialize path manager with database cursor."""
        self.cursor = cursor
        self.source_root = "/Users/Amgad/Projects/kodi/xtream-api"

    def normalize_path(self, path):
        """Normalize path to ensure proper format."""
        # Convert to absolute path with forward slashes
        abs_path = os.path.abspath(path).replace('\\', '/')
        
        # Make path relative to source root
        if abs_path.startswith(self.source_root):
            rel_path = abs_path[len(self.source_root):].lstrip('/')
        else:
            rel_path = abs_path.lstrip('/')
            
        # Remove any double slashes
        while '//' in rel_path:
            rel_path = rel_path.replace('//', '/')
            
        # Ensure path ends with /
        if not rel_path.endswith('/'):
            rel_path += '/'
            
        print(f"Normalized path: {rel_path}")
        return rel_path

    def insert_path(self, path):
        """Insert path and return its ID."""
        normalized_path = self.normalize_path(path)
        self.cursor.execute("""
            INSERT OR IGNORE INTO path (strPath, dateAdded)
            VALUES (?, ?)
        """, (normalized_path, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        self.cursor.execute("SELECT idPath FROM path WHERE strPath = ?", (normalized_path,))
        path_id = self.cursor.fetchone()[0]
        print(f"Inserted path ID: {path_id} for path: {normalized_path}")
        return path_id

    def insert_file(self, filename, path_id):
        """Insert file and return its ID."""
        self.cursor.execute("""
            INSERT OR IGNORE INTO files (idPath, strFilename, dateAdded)
            VALUES (?, ?, ?)
        """, (path_id, filename, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        self.cursor.execute("SELECT idFile FROM files WHERE idPath = ? AND strFilename = ?", 
                          (path_id, filename))
        file_id = self.cursor.fetchone()[0]
        print(f"Inserted file ID: {file_id} for file: {filename} in path ID: {path_id}")
        return file_id

    def get_file_id(self, path, filename):
        """Get file ID for given path and filename, creating if needed."""
        path_id = self.insert_path(path)
        return self.insert_file(filename, path_id)

    def link_tvshow_path(self, show_id, path_id):
        """Link a path to a TV show."""
        self.cursor.execute("""
            INSERT OR REPLACE INTO tvshowlinkpath (idShow, idPath)
            VALUES (?, ?)
        """, (show_id, path_id))
        print(f"Linked path ID: {path_id} to show ID: {show_id}")
        return True
