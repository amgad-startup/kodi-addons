import os
from datetime import datetime

def _format_cast(cast_list):
    """Format cast list into XML elements"""
    if not cast_list:
        return ""
        
    cast_xml = []
    for i, actor in enumerate(cast_list, 1):
        # Split "name as character" format
        if ' as ' in actor:
            name, character = actor.split(' as ', 1)
        else:
            name = actor
            character = ''
            
        cast_xml.append(f"""    <actor>
        <name>{name}</name>
        <role>{character}</role>
        <order>{i}</order>
        <thumb>actors/actor{i}.jpg</thumb>
    </actor>""")
    return "\n".join(cast_xml)

def _format_title_elements(metadata, alt_metadata, title):
    """Format title elements with language support"""
    main_title = metadata.get('title', title)
    orig_title = metadata.get('original_title', title)
    trans_title = metadata.get('transliterated_title', '')
    
    # If we have alternate metadata (usually English), include those titles too
    if alt_metadata:
        alt_title = alt_metadata.get('title', '')
        if alt_title and alt_title != main_title:
            main_title = f"{main_title} | {alt_title}"
    
    return f"""    <title>{main_title}</title>
    <originaltitle>{orig_title}</originaltitle>
    <sorttitle>{trans_title or title}</sorttitle>"""

def _format_plot_elements(metadata, alt_metadata):
    """Format plot elements with language support"""
    main_plot = metadata.get('plot', '')
    
    # If we have alternate metadata (usually English), include that plot too
    if alt_metadata and alt_metadata.get('plot'):
        alt_plot = alt_metadata.get('plot', '')
        if alt_plot and alt_plot != main_plot:
            return f"{main_plot}\n\n[EN]\n{alt_plot}"
    
    return main_plot

def _format_uniqueid(metadata):
    """Format uniqueid elements"""
    tmdb_id = metadata.get('tmdb_id', '')
    external_ids = metadata.get('external_ids', {})
    imdb_id = external_ids.get('imdb_id', '')
    
    uniqueid = [f'    <uniqueid type="tmdb">{tmdb_id}</uniqueid>']
    if imdb_id:
        uniqueid.append(f'    <uniqueid type="imdb">{imdb_id}</uniqueid>')
    
    return "\n".join(uniqueid)

def generate_movie_nfo(movie_dir, title, metadata=None, alt_metadata=None):
    """Generate a comprehensive movie NFO file with language support"""
    if metadata is None:
        metadata = {}
        
    # Format titles and plot with language support
    title_elements = _format_title_elements(metadata, alt_metadata, title)
    plot = _format_plot_elements(metadata, alt_metadata)
    
    # Get production company
    companies = metadata.get('production_companies', [])
    production = companies[0] if companies else ''
    
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<movie>
{title_elements}
    <dateadded>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</dateadded>
    
    <rating>{metadata.get('rating', '')}</rating>
    <plot>{plot}</plot>
    <mpaa>{metadata.get('mpaa', '')}</mpaa>
    <id>{metadata.get('tmdb_id', '')}</id>
{_format_uniqueid(metadata)}
    <genre>{metadata.get('genre', '')}</genre>
    <director>{metadata.get('director', '')}</director>
    <premiered>{metadata.get('release_date', '')}</premiered>
    <year>{metadata.get('year', '')}</year>
    
    <!-- Movie details -->
    <runtime>{metadata.get('runtime', '')}</runtime>
    <country>{metadata.get('country', '')}</country>
    <studio>{production}</studio>
    
    <!-- Artwork paths -->
    <thumb aspect="poster">{metadata.get('poster', 'poster.jpg')}</thumb>
    <thumb aspect="landscape">landscape.jpg</thumb>
    <fanart>
        <thumb>{metadata.get('fanart', 'fanart.jpg')}</thumb>
    </fanart>
    
    <!-- Actor information -->
{_format_cast(metadata.get('cast', []))}
    
    <!-- Additional features -->
    <languages>Arabic{' | English' if alt_metadata else ''}</languages>
    <productioncompany>{production}</productioncompany>
    <watched>false</watched>
    <playcount>0</playcount>
    <resume>
        <position>0</position>
        <total>0</total>
    </resume>
</movie>"""
    
    nfo_path = os.path.join(movie_dir, "movie.nfo")
    return nfo_path, nfo_content

def generate_tvshow_nfo(show_dir, title, metadata=None, alt_metadata=None):
    """Generate a comprehensive TV show NFO file with language support"""
    if metadata is None:
        metadata = {}
        
    # Format titles and plot with language support
    title_elements = _format_title_elements(metadata, alt_metadata, title)
    plot = _format_plot_elements(metadata, alt_metadata)
    
    # Get studio/network info
    networks = metadata.get('networks', [])
    studio = networks[0] if networks else ''
    
    # Get production company
    companies = metadata.get('production_companies', [])
    production = companies[0] if companies else ''
    
    # Get season details
    season_details = metadata.get('season_details', [])
    season_count = metadata.get('number_of_seasons', 1)
    
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<tvshow>
{title_elements}
    <dateadded>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</dateadded>
    
    <rating>{metadata.get('rating', '')}</rating>
    <plot>{plot}</plot>
    <mpaa></mpaa>
    <id>{metadata.get('tmdb_id', '')}</id>
{_format_uniqueid(metadata)}
    <genre>{metadata.get('genre', '')}</genre>
    <director>{metadata.get('director', '')}</director>
    <premiered>{metadata.get('premiered', '')}</premiered>
    <studio>{studio}</studio>
    <status>{metadata.get('status', 'Continuing')}</status>
    
    <!-- Show details -->
    <episodeguide>
        <url cache="tmdb">show/{metadata.get('tmdb_id', '')}</url>
    </episodeguide>
    <runtime>{metadata.get('episode_run_time', '')}</runtime>
    <type>{metadata.get('type', '')}</type>
    <numseasons>{season_count}</numseasons>
    <numenpisodes>{metadata.get('number_of_episodes', '')}</numenpisodes>
    
    <!-- Artwork paths -->
    <thumb aspect="poster">{metadata.get('poster', 'poster.jpg')}</thumb>
    <thumb aspect="banner">banner.jpg</thumb>
    <thumb aspect="landscape">landscape.jpg</thumb>
    <fanart>
        <thumb>{metadata.get('fanart', 'fanart.jpg')}</thumb>
    </fanart>
    
    <!-- Actor information -->
{_format_cast(metadata.get('cast', []))}
    
    <!-- Additional features -->
    <languages>Arabic{' | English' if alt_metadata else ''}</languages>
    <productioncompany>{production}</productioncompany>
"""

    # Add season information
    for i in range(1, season_count + 1):
        season_info = next((s for s in season_details if s.get('season_number') == i), {})
        name = season_info.get('name', f'Season {i}')
        nfo_content += f'    <namedseason number="{i}">{name}</namedseason>\n'
    
    nfo_content += "</tvshow>"
    
    nfo_path = os.path.join(show_dir, "tvshow.nfo")
    return nfo_path, nfo_content

def generate_episode_nfo(season_dir, title, season, episode, metadata=None, alt_metadata=None):
    """Generate a comprehensive episode NFO file with language support"""
    if metadata is None:
        metadata = {}
        
    # Format titles and plot with language support
    title_elements = _format_title_elements(metadata, alt_metadata, title)
    plot = _format_plot_elements(metadata, alt_metadata)
    
    nfo_content = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<episodedetails>
{title_elements}
    <showtitle>{metadata.get('title', title)}</showtitle>
    <season>{season}</season>
    <episode>{episode}</episode>
    <displayseason>{season}</displayseason>
    <displayepisode>{episode}</displayepisode>
    <dateadded>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</dateadded>
    
    <rating>{metadata.get('rating', '')}</rating>
    <plot>{plot}</plot>
    <runtime>{metadata.get('episode_run_time', '')}</runtime>
    <director>{metadata.get('director', '')}</director>
    
    <!-- Artwork paths -->
    <thumb>episode.jpg</thumb>
    
    <!-- Additional features -->
    <watched>false</watched>
    <playcount>0</playcount>
    <resume>
        <position>0</position>
        <total>0</total>
    </resume>
    
    <!-- Actor information -->
{_format_cast(metadata.get('cast', []))}
    
    <!-- Episode-specific details -->
    <firstaired>{metadata.get('premiered', '')}</firstaired>
    <languages>Arabic{' | English' if alt_metadata else ''}</languages>
</episodedetails>"""
    
    nfo_filename = f"S{season.zfill(2)}E{episode.zfill(2)}.nfo"
    nfo_path = os.path.join(season_dir, nfo_filename)
    return nfo_path, nfo_content
