import re

def is_arabic_char(char):
    """Check if a character is Arabic"""
    return '\u0600' <= char <= '\u06FF'

def is_japanese_char(char):
    """Check if a character is Japanese (Hiragana, Katakana, or Kanji)"""
    return ('\u3040' <= char <= '\u309F' or  # Hiragana
            '\u30A0' <= char <= '\u30FF' or  # Katakana
            '\u4E00' <= char <= '\u9FFF')    # Kanji

def should_skip_title(text):
    """
    Check if the title should be skipped.
    Returns True for non-Arabic titles (except those mixed with Arabic).
    """
    # Return True for empty strings
    if not text:
        return True
        
    # If text ends with مدبلج or contains Arabic, don't skip
    if text.strip().endswith('مدبلج') or any(is_arabic_char(c) for c in text):
        return False
        
    # Remove common non-letter characters, spaces, and numbers
    cleaned_text = re.sub(r'[0-9\s\-_\(\)\[\]\.]+', '', text)
    if not cleaned_text:
        return True
    
    # Check for Japanese characters
    if any(is_japanese_char(c) for c in text):
        return True
        
    # Check for Spanish/Latin characters (ñ, á, é, í, ó, ú, ü, ¿, ¡)
    spanish_chars = set('ñáéíóúüÑÁÉÍÓÚÜ¿¡')
    if any(c in spanish_chars for c in text):
        return True
    
    # Count English letters vs non-English characters
    english_chars = sum(1 for c in cleaned_text if c.isascii() and c.isalpha())
    total_chars = len(cleaned_text)
    
    # Consider it skippable if more than 80% of characters are English letters
    return english_chars / total_chars > 0.8 if total_chars > 0 else True

def split_arabic_english(text):
    """Split text into Arabic and English parts"""
    arabic_parts = []
    english_parts = []
    current_part = ""
    current_type = None  # None, 'arabic', or 'english'
    
    for char in text:
        if char.isspace():
            if current_part:
                if current_type == 'arabic':
                    arabic_parts.append(current_part)
                else:
                    english_parts.append(current_part)
                current_part = ""
                current_type = None
            continue
            
        is_arabic = is_arabic_char(char)
        
        # If we're starting a new part or switching scripts
        if current_type is None or (is_arabic and current_type == 'english') or (not is_arabic and current_type == 'arabic'):
            if current_part:
                if current_type == 'arabic':
                    arabic_parts.append(current_part)
                else:
                    english_parts.append(current_part)
                current_part = ""
            current_type = 'arabic' if is_arabic else 'english'
        
        current_part += char
    
    # Add the last part
    if current_part:
        if current_type == 'arabic':
            arabic_parts.append(current_part)
        else:
            english_parts.append(current_part)
    
    # Filter out single-letter parts unless they're the only part
    if len(arabic_parts) > 1:
        arabic_parts = [part for part in arabic_parts if len(part.strip()) > 1]
    if len(english_parts) > 1:
        english_parts = [part for part in english_parts if len(part.strip()) > 1]
    
    return arabic_parts, english_parts

def reorder_mixed_language(text):
    """Reorder mixed language text to put Arabic first"""
    # Handle special case for مدبلج
    dubbed_suffix = ""
    if text.strip().endswith('مدبلج'):
        text = text.strip()[:-4].strip()
        dubbed_suffix = " مدبلج"
    
    # Split into Arabic and English parts
    arabic_parts, english_parts = split_arabic_english(text)
    
    # Combine parts with Arabic first
    result = " ".join(arabic_parts)
    # Only add separator if we have both Arabic and English parts
    if english_parts and arabic_parts:
        result += " - "
    if english_parts:
        result += " ".join(english_parts)
    
    # Add back مدبلج if it was present
    if dubbed_suffix:
        result += dubbed_suffix
    
    return result.strip()

def sanitize_filename(filename):
    """Remove invalid characters from filenames"""
    invalid = '<>:"/\\|?*'
    for char in invalid:
        filename = filename.replace(char, '')
    return filename.strip()

def extract_show_info(stream_name):
    """
    Extract show name, season, and episode info from titles like "Show Name S01 E01"
    Returns (show_name, season, episode) or (None, None, None) if no match
    """
    pattern = r"(.*?)(?:\s+S(\d+)\s+E(\d+))"
    match = re.match(pattern, stream_name)
    
    if match:
        show_name = match.group(1).strip()
        # Reorder mixed language parts in show name
        show_name = reorder_mixed_language(show_name)
        season = match.group(2)
        episode = match.group(3)
        return show_name, season, episode
    return None, None, None
