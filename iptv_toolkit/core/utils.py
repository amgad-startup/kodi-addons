"""Shared utilities across iptv_toolkit: text, language, JSON, logging, env."""

import json
import logging
import os
import re
import unicodedata
from typing import Any, Dict, Optional, Tuple, List

try:
    from arabic_buckwalter_transliteration.transliteration import arabic_to_buckwalter
except ImportError:
    arabic_to_buckwalter = None


ARABIC_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]+')
ARABIC_CHAR_RE = re.compile(r'[\u0600-\u06FF]')
ARABIC_SUFFIXES = {
    'مترجم', 'مدبلج', 'مدبلجة', 'تصوير سينما',
    'القديس', 'البابا', 'ابونا',
}
_SUFFIX_PATTERN = re.compile('|'.join(f'({s})$' for s in ARABIC_SUFFIXES), re.IGNORECASE)
_SPANISH_CHARS = set('ñáéíóúüÑÁÉÍÓÚÜ¿¡')


def has_arabic(text: str) -> bool:
    return bool(ARABIC_RE.search(text or ''))


def detect_language(text: str) -> str:
    return 'ar' if has_arabic(text) else 'en'


def is_arabic_char(char: str) -> bool:
    return '\u0600' <= char <= '\u06FF'


def is_japanese_char(char: str) -> bool:
    return ('\u3040' <= char <= '\u309F' or
            '\u30A0' <= char <= '\u30FF' or
            '\u4E00' <= char <= '\u9FFF')


def should_process_title(text: str) -> bool:
    """True for titles worth processing (contain Arabic)."""
    return has_arabic(text)


def should_skip_title(text: str) -> bool:
    """
    True when a title should be skipped as non-Arabic content.
    Handles Arabic suffixes, Japanese, Spanish, and English-majority titles.
    """
    if not text:
        return True
    if text.strip().endswith('مدبلج') or any(is_arabic_char(c) for c in text):
        return False
    if _SUFFIX_PATTERN.search(text):
        return False

    cleaned = re.sub(r'[0-9\s\-_\(\)\[\]\.]+', '', text)
    if not cleaned:
        return True
    if any(is_japanese_char(c) for c in text):
        return True
    if any(c in _SPANISH_CHARS for c in text):
        return True

    english = sum(1 for c in cleaned if c.isascii() and c.isalpha())
    total = len(cleaned)
    return english / total > 0.8 if total else True


def split_arabic_english(text: str) -> Tuple[List[str], List[str]]:
    """Split text into (arabic_parts, english_parts), preserving order within each."""
    arabic_parts: List[str] = []
    english_parts: List[str] = []
    current = ""
    current_type: Optional[str] = None

    def flush():
        nonlocal current, current_type
        if current:
            (arabic_parts if current_type == 'arabic' else english_parts).append(current)
            current = ""
            current_type = None

    for char in text:
        if char.isspace():
            flush()
            continue
        is_ar = is_arabic_char(char)
        new_type = 'arabic' if is_ar else 'english'
        if current_type is None or new_type != current_type:
            flush()
            current_type = new_type
        current += char
    flush()

    if len(arabic_parts) > 1:
        arabic_parts = [p for p in arabic_parts if len(p.strip()) > 1]
    if len(english_parts) > 1:
        english_parts = [p for p in english_parts if len(p.strip()) > 1]
    return arabic_parts, english_parts


def reorder_mixed_language(text: str) -> str:
    """Reorder mixed Arabic/English text to put Arabic first, preserving مدبلج suffix."""
    text = str(text)
    dubbed_suffix = ""
    if text.strip().endswith('مدبلج'):
        text = text.strip()[:-4].strip()
        dubbed_suffix = " مدبلج"

    arabic_parts, english_parts = split_arabic_english(text)
    result = " ".join(arabic_parts)
    if english_parts and arabic_parts:
        result += " - "
    if english_parts:
        result += " ".join(english_parts)
    if dubbed_suffix:
        result += dubbed_suffix
    return result.strip()


def extract_show_info(stream_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse 'Show Name S01 E01' → (show_name, season, episode)."""
    match = re.match(r"(.*?)(?:\s+S(\d+)\s+E(\d+))", stream_name)
    if not match:
        return None, None, None
    return reorder_mixed_language(match.group(1).strip()), match.group(2), match.group(3)


class VODTitleCleaner:
    @staticmethod
    def clean_title(title: str) -> str:
        if not title:
            return ""
        title = re.sub(r'[-_.]+', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        return re.sub(r'^-+|-+$', '', title).strip()


def sanitize_filename(filename: Any) -> str:
    """Remove invalid filename characters; return 'unnamed' if empty."""
    if not filename:
        return "unnamed"
    filename = str(filename)
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    filename = re.sub(r'\s*\((.*?)\)', r' \1', filename)
    filename = filename.strip('. ')
    filename = re.sub(r'[\s\-]+', ' ', filename)
    filename = re.sub(r'[^\w\s\-\u0600-\u06FF]', '', filename)
    return filename.strip() or "unnamed"


def sanitize_category_name(category: Any) -> str:
    """Sanitize category for folder naming."""
    if not category:
        return "uncategorized"
    category = str(category)
    category = re.sub(r'\b\d{4}\b', '', category)
    for prefix in ('مسلسلات', 'افلام', 'برامج'):
        if category.startswith(f"{prefix} "):
            remaining = category[len(prefix):].strip()
            category = f"{prefix} {remaining}" if len(remaining.split()) <= 2 else prefix
            break
    category = re.sub(r'[<>:"/\\|?*]', '', category)
    category = re.sub(r'\s*\((.*?)\)', r' \1', category)
    category = category.strip('. ')
    category = re.sub(r'[\s\-]+', ' ', category)
    category = re.sub(r'[^\w\s\-\u0600-\u06FF]', '', category)
    return category.strip() or "uncategorized"


def format_season_number(season_num: Any, with_leading_zero: bool = True) -> str:
    try:
        num = int(str(season_num).strip())
        return f"{num:02d}" if with_leading_zero else str(num)
    except (ValueError, TypeError):
        return str(season_num)


def format_episode_number(episode_num: Any) -> str:
    try:
        return f"{int(str(episode_num).strip()):02d}"
    except (ValueError, TypeError):
        return str(episode_num)


def arabic_to_english(text: str) -> str:
    """Buckwalter transliteration for Arabic → ASCII; returns original on failure."""
    if arabic_to_buckwalter is None:
        return text
    try:
        return ' '.join(arabic_to_buckwalter(text).split())
    except Exception as e:
        logging.error(f"arabic_to_english failed: {e}")
        return text


def load_json_file(filepath: str, raise_on_error: bool = True) -> Optional[Dict[str, Any]]:
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
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_env_var(key: str, default: Optional[str] = None) -> str:
    value = os.getenv(key, default)
    if value is None:
        raise ValueError(f"Required environment variable {key} is not set")
    return value


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
            return
        if record.levelno == logging.INFO:
            if "✗" in record.msg:
                self.shows_processed += 1
                self.shows_failed += 1
            elif "✓" in record.msg:
                self.shows_processed += 1

    def get_summary(self) -> Optional[str]:
        if self.shows_processed == 0:
            return None
        success = self.shows_processed - self.shows_failed
        rate = success / self.shows_processed * 100
        bar_len = 20
        filled = int(bar_len * rate / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        return (
            f"\nProcessed: {self.shows_processed}  ✓ {success}  ✗ {self.shows_failed}  "
            f"[{bar}] {rate:.1f}%"
        )


def setup_logging() -> logging.Logger:
    """Minimal file + console logging (editor CLI style)."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    os.makedirs('logs', exist_ok=True)

    fh = logging.FileHandler('logs/detailed.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(MinimalFormatter())

    sh = SummaryHandler()
    sh.setLevel(logging.INFO)

    for h in (fh, ch, sh):
        logger.addHandler(h)
    return logger


def clean_kodi_database():
    """Wipe Kodi's video DB tables for a fresh run.

    Kodi must be closed first. Imported lazily to avoid a hard core→db dependency.
    """
    from iptv_toolkit.db.connection import DBConnection
    try:
        conn = DBConnection()
        cursor = conn.get_connection().cursor()
        for table in (
            'movie', 'episode', 'tvshow', 'files', 'path',
            'actor_link', 'genre_link', 'tag_link', 'uniqueid',
            'rating', 'art', 'tvshowlinkpath',
        ):
            cursor.execute(f"DELETE FROM {table}")
        cursor.connection.commit()
        cursor.connection.close()
        print("Cleaned Kodi database")
    except Exception as e:
        print(f"Error cleaning Kodi database: {e}")
