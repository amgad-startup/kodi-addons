import json
import os
import re
import logging
import unicodedata
from typing import Any, Dict, Optional
from arabic_buckwalter_transliteration.transliteration import arabic_to_buckwalter

class MinimalFormatter(logging.Formatter):
    def format(self, record):
        if record.levelno == logging.INFO:
            return record.getMessage()
        return super().format(record)

class SummaryHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.shows_processed = 0
        self.shows_failed = 0
        self.current_show = None
    
    def emit(self, record):
        if "Processing shows" in record.msg:
            return  # Skip batch processing messages in summary
        if record.levelno == logging.INFO:
            if "✗" in record.msg:
                self.shows_processed += 1
                self.shows_failed += 1
            elif "✓" in record.msg:
                self.shows_processed += 1
    
    def get_summary(self):
        if self.shows_processed == 0:
            return None
            
        success_count = self.shows_processed - self.shows_failed
        success_rate = (success_count / self.shows_processed * 100) if self.shows_processed > 0 else 0
        
        # Create visual bar for success rate
        bar_length = 20
        filled_length = int(bar_length * success_rate / 100)
        bar = '█' * filled_length + '░' * (bar_length - filled_length)
        
        return f"""
╔══════════════ Processing Summary ══════════════╗
║                                               ║
║  Total Processed: {self.shows_processed:4d}                        ║
║  ✓ Successful:    {success_count:4d}                        ║
║  ✗ Failed:        {self.shows_failed:4d}                        ║
║                                               ║
║  Success Rate: {success_rate:6.1f}%                        ║
║  [{bar}] {success_rate:5.1f}%  ║
║                                               ║
╚═══════════════════════════════════════════════╝"""

def setup_logging() -> logging.Logger:
    """Configure and return logger with file and console handlers"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # File handler for detailed logs
    file_handler = logging.FileHandler('logs/detailed.log')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    
    # Console handler for minimal progress only
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(MinimalFormatter())
    
    # Summary handler
    summary_handler = SummaryHandler()
    summary_handler.setLevel(logging.INFO)
    
    # Add all handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.addHandler(summary_handler)
    
    return logger

def load_json_file(filepath: str, raise_on_error: bool = True) -> Optional[Dict[str, Any]]:
    """Load and parse JSON file"""
    try:
        with open(filepath, encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        if raise_on_error:
            logging.error(f"File not found: {filepath}")
            raise
        return None
    except json.JSONDecodeError:
        if raise_on_error:
            logging.error(f"Invalid JSON in file: {filepath}")
            raise
        return None

def save_json_file(filepath: str, data: Dict[str, Any]) -> None:
    """Save data to JSON file with proper UTF-8 encoding"""
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Failed to save file {filepath}: {str(e)}")
        raise

def load_env_var(key: str, default: str = None) -> str:
    """
    Load environment variable with error handling.
    Raises ValueError if required variable is missing.
    """
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value

def detect_language(text: str) -> str:
    """Detect if text contains Arabic characters"""
    # Arabic Unicode range
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
    return 'ar' if arabic_pattern.search(text) else 'en'

def has_arabic(text: str) -> bool:
    """Check if text contains Arabic characters"""
    arabic_pattern = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
    return bool(arabic_pattern.search(text))

def should_process_title(text: str) -> bool:
    """
    Determine if a title should be processed based on language.
    Returns True if title contains Arabic characters or mixed Arabic/English.
    Returns False for pure English, Spanish, Japanese, etc.
    """
    return has_arabic(text)

def arabic_to_english(text: str) -> str:
    """
    Convert Arabic text to a searchable English form using Buckwalter transliteration.
    This provides a standardized way to convert Arabic text to ASCII.
    """
    try:
        # Convert Arabic text to Buckwalter transliteration
        transliterated = arabic_to_buckwalter(text)
        # Clean up the result - remove double spaces and trailing spaces
        return ' '.join(transliterated.split())
    except Exception as e:
        logging.error(f"Error in arabic_to_english: {str(e)}")
        return text  # Return original text if conversion fails
