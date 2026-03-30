"""Module for tracking failed stream processing attempts."""

import os
import json
import sqlite3
from datetime import datetime
from logger import get_logger

# Setup logger
logger = get_logger(__name__)

class FailedStreamsTracker:
    def __init__(self, db_path=".failed/failed_streams.db"):
        """Initialize the failed streams tracker."""
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS failed_streams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stream_type TEXT NOT NULL,
                    stream_data TEXT NOT NULL,
                    error TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error initializing failed streams database: {str(e)}")

    def add_failed_stream(self, stream, stream_type, error):
        """Add a failed stream to the tracker."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Convert stream data to JSON string
            stream_data = json.dumps(stream)
            
            cursor.execute("""
                INSERT INTO failed_streams (stream_type, stream_data, error)
                VALUES (?, ?, ?)
            """, (stream_type, stream_data, str(error)))
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding failed stream to tracker: {str(e)}")

    def get_failed_streams(self):
        """Get list of failed streams."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT stream_type, stream_data FROM failed_streams")
            rows = cursor.fetchall()
            
            failed_streams = []
            for stream_type, stream_data in rows:
                stream = json.loads(stream_data)
                failed_streams.append({
                    'stream_type': stream_type,
                    'stream': stream
                })
            
            conn.close()
            return failed_streams
        except Exception as e:
            logger.error(f"Error getting failed streams: {str(e)}")
            return []

    def clear_failed_streams(self):
        """Clear all failed streams from the tracker."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM failed_streams")
            
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error clearing failed streams: {str(e)}")
