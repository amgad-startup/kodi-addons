"""Module for managing Kodi database connections."""

import os
import time
import sqlite3
import psutil
from logger import get_logger

# Setup logger
logger = get_logger(__name__)

class DBConnection:
    def __init__(self, db_path):
        """Initialize database connection."""
        self.db_path = db_path
        logger.info(f"Using Kodi database at: {self.db_path}")
        
        if self._check_kodi_running():
            logger.warning("\nWarning: Kodi is running. Please close Kodi before proceeding.")
            logger.info("Waiting for Kodi to close...")
            while self._check_kodi_running():
                time.sleep(1)
            logger.info("Kodi closed. Proceeding...")

    def _check_kodi_running(self):
        """Check if Kodi is currently running."""
        kodi_processes = ['kodi', 'kodi.bin', 'Kodi']
        for proc in psutil.process_iter(['name']):
            try:
                if proc.info['name'] in kodi_processes:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return False

    def connect(self):
        """Create a connection to the Kodi database."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {str(e)}")
            return None

    def execute_query(self, query, params=None):
        """Execute a query and return results."""
        try:
            conn = self.connect()
            if conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                conn.commit()
                return cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Error executing query: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()

    def execute_many(self, query, params_list):
        """Execute multiple similar queries."""
        try:
            conn = self.connect()
            if conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Error executing multiple queries: {str(e)}")
            return False
        finally:
            if conn:
                conn.close()

    def get_single_value(self, query, params=None):
        """Get a single value from a query."""
        try:
            conn = self.connect()
            if conn:
                cursor = conn.cursor()
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Error getting single value: {str(e)}")
            return None
        finally:
            if conn:
                conn.close()

    def table_exists(self, table_name):
        """Check if a table exists in the database."""
        query = """
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name=?
        """
        result = self.get_single_value(query, (table_name,))
        return bool(result)

    def get_column_names(self, table_name):
        """Get column names for a table."""
        try:
            conn = self.connect()
            if conn:
                cursor = conn.cursor()
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 0")
                return [description[0] for description in cursor.description]
        except sqlite3.Error as e:
            logger.error(f"Error getting column names: {str(e)}")
            return []
        finally:
            if conn:
                conn.close()
