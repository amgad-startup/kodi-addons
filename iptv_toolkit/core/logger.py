"""Module for setting up logging configuration."""

import logging
import os
from datetime import datetime
from iptv_toolkit.core.config import CONFIG

# Global debug flag
DEBUG = False

def set_debug(debug_mode):
    """Set the global debug flag."""
    global DEBUG
    DEBUG = debug_mode

def get_logger(name):
    """Get a logger instance with the current debug setting."""
    return setup_logger(name, debug=DEBUG)

def setup_logger(name, debug=False):
    """Setup logger with file and console handlers.
    
    Args:
        name: Name of the logger
        debug: If True, sets logging level to DEBUG, otherwise INFO
    """
    # Set root logger level based on debug flag
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    
    # Only add handlers if they haven't been added yet
    if not logger.handlers:
        # Create formatters
        console_formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
        file_formatter = logging.Formatter(
            CONFIG['logging']['format'],
            datefmt=CONFIG['logging']['date_format']
        )
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(console_handler)
        
        # Create file handler in the user's cwd (not the package directory).
        # Honors IPTV_TOOLKIT_LOG_DIR if set, otherwise defaults to ./logs/.
        log_dir = os.environ.get('IPTV_TOOLKIT_LOG_DIR', os.path.join(os.getcwd(), 'logs'))
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
        logger.addHandler(file_handler)
    
    return logger
