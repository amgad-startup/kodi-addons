"""Module for generating NFO files with comprehensive metadata."""

import os
from datetime import datetime
import xml.etree.ElementTree as ET
from xml.dom import minidom
import re
import urllib.parse

def _is_valid_image_url(url):
    """Check if image URL is valid."""
    if not url:
        return False
        
    # Must start with http:// or https://
    if not url.startswith(('http://', 'https://')):
        return False
        
    # Parse URL to handle special characters
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    
    # Check for common image extensions in path
    if re.search(r'\.(jpg|jpeg|png|gif|webp)$', path):
        return True
        
    # Check for image-like URLs (e.g. CDN URLs that might not have extensions)
    image_indicators = [
        'image', 'img', 'photo', 'picture', 'thumb', 'cover', 'poster',
        'ArticleImgs'  # Specific to youm7.com
    ]
    return any(indicator in parsed.path.lower() for indicator in image_indicators)

def _split_arabic_names(name_str):
    """Split Arabic names that are separated by spaces."""
    # First try to split by common Arabic name separators
    names = re.split(r'\s+و\s+|\s+،\s*|\s*,\s*', name_str)
    if len(names) > 1:
        return [n.strip() for n in names if n.strip()]
    
    # If no common separators found, try to identify multi-word names
    words = name_str.split()
    names = []
    current_name = []
    
    for word in words:
        current_name.append(word)
        
        # Check if this could be a complete name
        # Names typically have 2-3 words
        if len(current_name) >= 2:
            # Look ahead to see if next word starts with capital (indicating new name)
            next_idx = len(names) + len(current_name)
            if next_idx >= len(words) or (words[next_idx][0].isupper() and len(current_name) >= 2):
                names.append(' '.join(current_name))
                current_name = []
                
    # Add any remaining words as a name
    if current_name:
        names.append(' '.join(current_name))
    
    return names if names else [name_str]

def _format_cast(cast_list):
    """Format cast list into XML elements."""
    if not cast_list:
        return []
        
    cast_elements = []
    order = 1
    
    for actor_name in cast_list:
        # Split "name as character" format
        if ' as ' in actor_name:
            name, character = actor_name.split(' as ', 1)
        else:
            name = actor_name
            character = ''
        
        # Split Arabic names that might be concatenated
        individual_names = _split_arabic_names(name)
        
        for name in individual_names:
            actor = ET.Element('actor')
            name_elem = ET.SubElement(actor, 'name')
            name_elem.text = name.strip()
            role = ET.SubElement(actor, 'role')
            role.text = character.strip()
            order_elem = ET.SubElement(actor, 'order')
            order_elem.text = str(order)
            thumb = ET.SubElement(actor, 'thumb')
            # Only add actor thumb if we have a real path
            if os.path.exists(f'actors/{name.strip()}.jpg'):
                thumb.text = f'actors/{name.strip()}.jpg'
            cast_elements.append(actor)
            order += 1
    
    return cast_elements

def _add_common_elements(root, info, title, category=None, tags=None):
    """Add common metadata elements to NFO."""
    # Basic info
    title_elem = ET.SubElement(root, 'title')
    title_elem.text = info.get('name', title)
    
    # Add sorttitle for better organization
    sorttitle = ET.SubElement(root, 'sorttitle')
    sorttitle.text = info.get('name', title)
    
    # Always include plot and outline, even if empty
    plot = ET.SubElement(root, 'plot')
    plot.text = info.get('plot', '')
    outline = ET.SubElement(root, 'outline')
    outline.text = info.get('plot', '')[:200] + '...' if info.get('plot', '') else ''
        
    if info.get('rating'):
        # Add ratings element with source
        ratings = ET.SubElement(root, 'ratings')
        rating = ET.SubElement(ratings, 'rating')
        rating.set('name', 'tmdb')
        rating.set('max', '10')
        rating.set('default', 'true')
        value = ET.SubElement(rating, 'value')
        value.text = str(info['rating'])
        
    if info.get('director'):
        director = ET.SubElement(root, 'director')
        director.text = info['director']
        
    # Handle genres
    genre_str = info.get('genre', '')
    if genre_str:
        if isinstance(genre_str, str):
            # Split by both / and space
            genres = [g.strip() for g in re.split(r'[/\s]+', genre_str) if g.strip()]
        elif isinstance(genre_str, (list, tuple)):
            genres = genre_str
        else:
            genres = []
            
        for genre_name in genres:
            genre = ET.SubElement(root, 'genre')
            genre.text = genre_name
                
    # Add category and tags
    if category:
        tag = ET.SubElement(root, 'tag')
        tag.text = category
    
    # Add extracted tags
    if tags:
        for tag_text in tags:
            tag = ET.SubElement(root, 'tag')
            tag.text = tag_text
                
    # Handle artwork - use poster as backdrop if no backdrop, and vice versa
    cover_url = info.get('cover', '')
    backdrop_urls = info.get('backdrop_path', [])
    if isinstance(backdrop_urls, str):
        backdrop_urls = [url.strip() for url in backdrop_urls.split('\n') if url.strip()]
    
    # Add thumb/poster if valid URL
    if cover_url and _is_valid_image_url(cover_url):
        # Add as thumb
        thumb = ET.SubElement(root, 'thumb')
        thumb.text = cover_url
        thumb.set('aspect', 'poster')
        
        # Add as poster
        poster = ET.SubElement(root, 'art')
        poster_url = ET.SubElement(poster, 'poster')
        poster_url.text = cover_url
        
        # If no valid backdrops, use poster as fanart
        if not any(_is_valid_image_url(url) for url in backdrop_urls):
            fanart = ET.SubElement(root, 'fanart')
            thumb = ET.SubElement(fanart, 'thumb')
            thumb.text = cover_url
    
    # Add fanart/backdrops if valid URLs
    valid_backdrops = [url for url in backdrop_urls if _is_valid_image_url(url)]
    if valid_backdrops:
        # Add as fanart
        fanart = ET.SubElement(root, 'fanart')
        for backdrop in valid_backdrops:
            thumb = ET.SubElement(fanart, 'thumb')
            thumb.text = backdrop
            
        # Add to art
        art = root.find('art')
        if art is None:
            art = ET.SubElement(root, 'art')
        fanart_url = ET.SubElement(art, 'fanart')
        fanart_url.text = valid_backdrops[0]
            
        # If no valid poster, use first backdrop
        if not cover_url or not _is_valid_image_url(cover_url):
            # Add as thumb
            thumb = ET.SubElement(root, 'thumb')
            thumb.text = valid_backdrops[0]
            thumb.set('aspect', 'poster')
            
            # Add as poster
            poster_url = ET.SubElement(art, 'poster')
            poster_url.text = valid_backdrops[0]
                
    # Cast
    if info.get('cast'):
        cast_list = info['cast'].split(',') if isinstance(info['cast'], str) else info['cast']
        for actor_elem in _format_cast(cast_list):
            root.append(actor_elem)
            
    # Add dateadded
    dateadded = ET.SubElement(root, 'dateadded')
    dateadded.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Add language
    language = ET.SubElement(root, 'language')
    language.text = 'ar'  # Arabic
    
    # Add country
    country = ET.SubElement(root, 'country')
    country.text = info.get('country', 'EG')  # Default to Egypt if not specified

def generate_movie_nfo(movie_dir, title, info=None, category=None, tags=None):
    """Generate movie NFO file with metadata."""
    if info is None:
        info = {}
        
    try:
        movie = ET.Element('movie')
        _add_common_elements(movie, info, title, category, tags)
        
        # Movie-specific elements
        if info.get('premiered'):
            premiered = ET.SubElement(movie, 'premiered')
            premiered.text = info['premiered']
            year = ET.SubElement(movie, 'year')
            year.text = info['premiered'][:4]  # Extract year from YYYY-MM-DD
            
        # Add duration from info if available
        if info.get('duration_secs'):
            runtime = ET.SubElement(movie, 'runtime')
            runtime.text = str(int(info['duration_secs'] / 60))  # Convert to minutes
            
        # Add TMDB ID if available
        if info.get('tmdb_id'):
            uniqueid = ET.SubElement(movie, 'uniqueid')
            uniqueid.set('type', 'tmdb')
            uniqueid.set('default', 'true')
            uniqueid.text = str(info['tmdb_id'])
            
        # Add trailer if available and valid
        if info.get('trailer') and info['trailer'] != 'https://www.youtube.com/watch?v=':
            trailer = ET.SubElement(movie, 'trailer')
            trailer.text = info['trailer']
            
        # Add set info if available
        if info.get('set'):
            set_elem = ET.SubElement(movie, 'set')
            name = ET.SubElement(set_elem, 'name')
            name.text = info['set']
            if info.get('set_overview'):
                overview = ET.SubElement(set_elem, 'overview')
                overview.text = info['set_overview']
            
        # Add fileinfo if available
        if info.get('fileinfo'):
            fileinfo = ET.SubElement(movie, 'fileinfo')
            streamdetails = ET.SubElement(fileinfo, 'streamdetails')
            
            # Video details
            if info['fileinfo'].get('video'):
                video = ET.SubElement(streamdetails, 'video')
                for key, value in info['fileinfo']['video'].items():
                    elem = ET.SubElement(video, key)
                    elem.text = str(value)
                    
            # Audio details
            if info['fileinfo'].get('audio'):
                audio = ET.SubElement(streamdetails, 'audio')
                for key, value in info['fileinfo']['audio'].items():
                    elem = ET.SubElement(audio, key)
                    elem.text = str(value)
        
        # Save the NFO file
        os.makedirs(movie_dir, exist_ok=True)
        nfo_path = os.path.join(movie_dir, "movie.nfo")
        xml_str = minidom.parseString(ET.tostring(movie)).toprettyxml(indent="  ")
        # Remove empty lines
        xml_str = '\n'.join([line for line in xml_str.split('\n') if line.strip()])
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        # print(f"Created NFO: {nfo_path}")
        return True
    except Exception as e:
        print(f"Error creating movie NFO: {str(e)}")
        return False

def generate_tvshow_nfo(show_dir, title, info=None, category=None, tags=None):
    """Generate TV show NFO file with metadata."""
    if info is None:
        info = {}
        
    try:
        tvshow = ET.Element('tvshow')
        _add_common_elements(tvshow, info, title, category, tags)
        
        # TV show specific elements
        if info.get('status'):
            status = ET.SubElement(tvshow, 'status')
            status.text = info['status']
            
        if info.get('episode_run_time'):
            runtime = ET.SubElement(tvshow, 'runtime')
            runtime.text = str(info['episode_run_time'])
            
        # Add premiered date and year
        if info.get('premiered'):
            premiered = ET.SubElement(tvshow, 'premiered')
            premiered.text = info['premiered']
            
        if info.get('year'):
            year = ET.SubElement(tvshow, 'year')
            year.text = info['year']
            
        # Add studio if available
        if info.get('studio'):
            studio = ET.SubElement(tvshow, 'studio')
            studio.text = info['studio']
            
        # Add content rating if available
        if info.get('content_rating'):
            mpaa = ET.SubElement(tvshow, 'mpaa')
            mpaa.text = info['content_rating']
            
        # Save the NFO file
        os.makedirs(show_dir, exist_ok=True)
        nfo_path = os.path.join(show_dir, "tvshow.nfo")
        xml_str = minidom.parseString(ET.tostring(tvshow)).toprettyxml(indent="  ")
        # Remove empty lines
        xml_str = '\n'.join([line for line in xml_str.split('\n') if line.strip()])
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        # print(f"Created NFO: {nfo_path}")
        return True
    except Exception as e:
        print(f"Error creating TV show NFO: {str(e)}")
        return False

def generate_episode_nfo(episode_dir, show_name, season_num, episode_num, info=None, season_info=None, filename=None, category=None, tags=None):
    """Generate episode NFO file with metadata.
    
    Args:
        episode_dir: Directory to save the NFO file
        show_name: Name of the TV show
        season_num: Season number
        episode_num: Episode number
        info: Episode metadata
        season_info: Season metadata
        filename: Optional filename for the NFO file (if None, uses default format)
        category: Optional category name to add as tag
        tags: Optional list of additional tags
    """
    if info is None:
        info = {}
    if season_info is None:
        season_info = {}
        
    try:
        episodedetails = ET.Element('episodedetails')
        
        # Basic episode info
        title = ET.SubElement(episodedetails, 'title')
        title.text = info.get('title', f'Episode {episode_num}')
        
        showtitle = ET.SubElement(episodedetails, 'showtitle')
        showtitle.text = show_name
        
        season = ET.SubElement(episodedetails, 'season')
        season.text = str(season_num)
        
        episode = ET.SubElement(episodedetails, 'episode')
        episode.text = str(episode_num)
        
        # Add plot/description
        plot = ET.SubElement(episodedetails, 'plot')
        plot.text = info.get('plot') or season_info.get('overview', '')
            
        # Add runtime if available
        if info.get('duration_secs'):
            runtime = ET.SubElement(episodedetails, 'runtime')
            runtime.text = str(int(info['duration_secs'] / 60))  # Convert to minutes
            
        # Add aired date
        if season_info.get('air_date'):
            aired = ET.SubElement(episodedetails, 'aired')
            aired.text = season_info['air_date']
            premiered = ET.SubElement(episodedetails, 'premiered')
            premiered.text = season_info['air_date']
            
        # Add rating if available
        if info.get('rating') or season_info.get('vote_average'):
            ratings = ET.SubElement(episodedetails, 'ratings')
            rating = ET.SubElement(ratings, 'rating')
            rating.set('name', 'tmdb')
            rating.set('max', '10')
            rating.set('default', 'true')
            value = ET.SubElement(rating, 'value')
            value.text = str(info.get('rating') or season_info.get('vote_average', '0'))
            
        # Add director if available
        if info.get('director'):
            director = ET.SubElement(episodedetails, 'director')
            director.text = info['director']
            
        # Add cast
        if info.get('cast'):
            cast_list = info['cast'].split(',') if isinstance(info['cast'], str) else info['cast']
            for actor_elem in _format_cast(cast_list):
                episodedetails.append(actor_elem)
                
        # Add artwork if valid URL
        if info.get('cover') and _is_valid_image_url(info['cover']):
            thumb = ET.SubElement(episodedetails, 'thumb')
            thumb.text = info['cover']
            
        # Add dateadded
        dateadded = ET.SubElement(episodedetails, 'dateadded')
        dateadded.text = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Add category and tags
        if category:
            tag = ET.SubElement(episodedetails, 'tag')
            tag.text = category
            
        if tags:
            for tag_text in tags:
                tag = ET.SubElement(episodedetails, 'tag')
                tag.text = tag_text
        
        # Save the NFO file
        os.makedirs(episode_dir, exist_ok=True)
        if filename:
            nfo_path = os.path.join(episode_dir, filename)
        else:
            nfo_path = os.path.join(episode_dir, f"episode{episode_num}.nfo")
            
        xml_str = minidom.parseString(ET.tostring(episodedetails)).toprettyxml(indent="  ")
        # Remove empty lines
        xml_str = '\n'.join([line for line in xml_str.split('\n') if line.strip()])
        with open(nfo_path, "w", encoding="utf-8") as f:
            f.write(xml_str)
        # print(f"Created NFO: {nfo_path}")
        return True
    except Exception as e:
        print(f"Error creating episode NFO: {str(e)}")
        return False
