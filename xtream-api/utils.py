"""Utility functions for text processing and file operations."""

import re
from db_connection import DBConnection

class VODTitleCleaner:
    @staticmethod
    def clean_title(title):
        """Clean up title by removing common suffixes and extra characters."""
        if not title:
            return ""
        # Remove extra characters
        title = re.sub(r'[-_.]+', ' ', title)
        
        # Remove multiple spaces and trim
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Remove any remaining dashes at start/end
        title = re.sub(r'^-+|-+$', '', title).strip()
        
        return title

def clean_kodi_database():
    """Clean Kodi's video database for fresh run.
    
    This function:
    1. Connects to Kodi's video database
    2. Deletes all content from relevant tables
    3. Handles database locking and access
    
    Note: Kodi must be closed before running this function
    """
    try:
        # Get database connection
        conn = DBConnection()
        cursor = conn.get_connection().cursor()
        
        # Delete all content
        tables = [
            'movie', 'episode', 'tvshow', 'files', 'path',
            'actor_link', 'genre_link', 'tag_link', 'uniqueid',
            'rating', 'art', 'tvshowlinkpath'
        ]
        
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
        
        cursor.connection.commit()
        cursor.connection.close()
        print("Cleaned Kodi database")
    except Exception as e:
        print(f"Error cleaning Kodi database: {str(e)}")


def should_skip_title(title):
    """
    Check if the title contains Arabic content or specific Arabic suffixes.
    
    Args:
        title: str - The title to check
        
    Returns:
        bool - True if the title contains Arabic suffixes or Arabic characters
    """
    # Define suffixes as a set for faster lookup
    ARABIC_SUFFIXES = {
        'مترجم',
        'مدبلج',
        'مدبلجة',
        'تصوير سينما',
        'القديس',
        'البابا',
        'ابونا'
    }
    
    # Compile patterns once for better performance
    SUFFIX_PATTERN = '|'.join(f'({suffix})$' for suffix in ARABIC_SUFFIXES)
    ARABIC_PATTERN = re.compile(r'[\u0600-\u06FF]')
    
    # Check for suffixes first
    if re.search(SUFFIX_PATTERN, title, flags=re.IGNORECASE):
        return True
        
    # Check for Arabic characters
    return not bool(ARABIC_PATTERN.search(str(title)))


def reorder_mixed_language(text):
    """Reorder mixed language text to handle RTL/LTR properly."""
    # Split into Arabic and non-Arabic parts
    parts = re.split(r'([\u0600-\u06FF]+)', str(text))
    
    # Remove empty parts and strip whitespace
    parts = [p.strip() for p in parts if p.strip()]
    
    # Put Arabic parts first, followed by non-Arabic parts
    arabic_parts = [p for p in parts if re.match(r'^[\u0600-\u06FF]+$', p)]
    other_parts = [p for p in parts if not re.match(r'^[\u0600-\u06FF]+$', p)]
    
    # Join parts with spaces
    return ' '.join(arabic_parts + other_parts)

def sanitize_category_name(category):
    """Sanitize category name for consistent folder naming.
    
    Args:
        category: The category name to sanitize
        
    Returns:
        Sanitized category name safe for use as folder name
    """
    if not category:
        return "uncategorized"
        
    # Convert to string
    category = str(category)
    
    # Remove year patterns (e.g., "2024")
    category = re.sub(r'\b\d{4}\b', '', category)
    
    # Handle common category prefixes
    prefixes = ['مسلسلات', 'افلام', 'برامج']
    for prefix in prefixes:
        # If category starts with prefix + space, keep only the prefix
        if category.startswith(f"{prefix} "):
            remaining = category[len(prefix):].strip()
            # If what remains is just a language/region qualifier, merge it
            if len(remaining.split()) <= 2:
                category = f"{prefix} {remaining}"
            else:
                category = prefix
            break
    
    # Remove or replace invalid characters
    invalid_chars = r'[<>:"/\\|?*]'
    category = re.sub(invalid_chars, '', category)
    
    # Handle parentheses content
    category = re.sub(r'\s*\((.*?)\)', r' \1', category)
    
    # Remove leading/trailing spaces and dots
    category = category.strip('. ')
    
    # Replace multiple spaces or dashes with single space
    category = re.sub(r'[\s\-]+', ' ', category)
    
    # Remove any remaining problematic characters
    category = re.sub(r'[^\w\s\-\u0600-\u06FF]', '', category)
    
    # Final trim
    category = category.strip()
    
    return category or "uncategorized"

def sanitize_filename(filename):
    """Sanitize filename by removing/replacing invalid characters.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename safe for use in filesystem
    """
    if not filename:
        return "unnamed"
        
    # Convert to string
    filename = str(filename)
    
    # Remove or replace invalid filename characters
    invalid_chars = r'[<>:"/\\|?*]'
    filename = re.sub(invalid_chars, '', filename)
    
    # Handle parentheses content
    # If content is in parentheses, merge it with previous text without parentheses
    filename = re.sub(r'\s*\((.*?)\)', r' \1', filename)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Replace multiple spaces or dashes with single space
    filename = re.sub(r'[\s\-]+', ' ', filename)
    
    # Remove any remaining problematic characters
    filename = re.sub(r'[^\w\s\-\u0600-\u06FF]', '', filename)
    
    # Final trim
    filename = filename.strip()
    
    return filename or "unnamed"

def format_season_number(season_num, with_leading_zero=True):
    """Format season number according to Kodi standards.
    
    Args:
        season_num: The season number to format
        with_leading_zero: If True, adds leading zero for numbers < 10
        
    Returns:
        Formatted season number as string (e.g., "01" or "1" depending on with_leading_zero)
    """
    try:
        # Convert to integer first to handle various input formats
        num = int(str(season_num).strip())
        # Format with or without leading zero
        return f"{num:02d}" if with_leading_zero else str(num)
    except (ValueError, TypeError):
        # If conversion fails, return original value
        return str(season_num)

def format_episode_number(episode_num):
    """Format episode number according to Kodi standards.
    
    Args:
        episode_num: The episode number to format
        
    Returns:
        Formatted episode number as string with leading zero (e.g., "01")
    """
    try:
        # Convert to integer first to handle various input formats
        num = int(str(episode_num).strip())
        # Always use leading zero for episodes
        return f"{num:02d}"
    except (ValueError, TypeError):
        # If conversion fails, return original value
        return str(episode_num)
