# Xtream API to Kodi Integration

A Python application that processes Xtream API streams and integrates them with Kodi, either through direct database insertion or by creating STRM/NFO files.

## Core Components

### Main Files

- `main.py`: Entry point of the application. Handles command-line arguments, initializes components, and orchestrates the stream processing workflow.
- `config.py`: Configuration settings including API credentials, timeouts, and default stream types.
- `api_client.py`: Handles communication with the Xtream API, including authentication and stream information retrieval.

### Database Management

- `db_connection.py`: Manages connections to Kodi's SQLite database, handling connection pooling and access control.
- `db_media_manager.py`: Core database operations for inserting movies, TV shows, and episodes into Kodi's database.
- `db_metadata_manager.py`: Handles metadata-specific database operations (genres, actors, ratings, etc.).
- `db_path_manager.py`: Manages file paths and their relationships in Kodi's database.
- `kodi_db_manager.py`: High-level wrapper providing a simplified interface to database operations.

### Stream Processing

- `stream_processor.py`: Main coordinator for processing different types of streams (VOD, Series, Live).
- `processors/base_processor.py`: Base class defining common functionality for all stream processors.

#### VOD Processing

- `processors/vod_processor.py`: Main processor for Video-on-Demand content.
- `processors/vod/metadata_extractor.py`: Extracts and formats VOD metadata.
- `processors/vod/title_cleaner.py`: Handles cleaning and formatting of VOD titles.
- `processors/vod/file_generator.py`: Generates STRM and NFO files for VOD content.

#### Series Processing

- `processors/series_processor.py`: Main processor for TV series content.
- `processors/series/metadata_extractor.py`: Extracts and formats series metadata.
- `processors/series/cast_cleaner.py`: Handles cleaning and formatting of cast information.
- `processors/series/file_generator.py`: Generates STRM and NFO files for series content.

#### Live TV Processing

- `processors/live_processor.py`: Handles live TV stream processing.

### File and Metadata Management

- `nfo_generator.py`: Generates NFO files containing metadata for movies, TV shows, and episodes.
- `file_operations.py`: Common file system operations like creating directories and handling paths.
- `catalog_manager.py`: Manages stream catalogs for tracking processed content.
- `progress_manager.py`: Tracks processing progress for resumable operations.
- `utils.py`: Utility functions for text processing, sanitization, and common operations.

### Cache Management

- `cache_manager.py`: Handles caching of API responses to reduce server load.
- `cache/`: Directory containing cached API responses.

## Directory Structure

```
.
├── main.py                 # Application entry point
├── api_client.py           # Xtream API client
├── config.py              # Configuration settings
├── processors/            # Stream processors
│   ├── __init__.py
│   ├── base_processor.py  # Base processor class
│   ├── live_processor.py  # Live TV processor
│   ├── vod_processor.py   # Main VOD processor
│   ├── series_processor.py # Main series processor
│   ├── vod/              # VOD processing modules
│   │   ├── metadata_extractor.py
│   │   ├── title_cleaner.py
│   │   └── file_generator.py
│   └── series/           # Series processing modules
│       ├── metadata_extractor.py
│       ├── cast_cleaner.py
│       └── file_generator.py
├── db/                    # Database management
│   ├── db_connection.py   # Database connection handler
│   ├── db_media_manager.py # Media insertion operations
│   ├── db_metadata_manager.py # Metadata operations
│   └── db_path_manager.py # Path management
└── output/               # Generated files
    ├── vod-flat/         # VOD content
    ├── series-flat/      # TV series content
    └── live/             # Live TV content
```

## Features

- Processes VOD, Series, and Live TV content from Xtream API
- Two operation modes:
  - Direct Kodi database integration
  - Local STRM/NFO file creation
- Handles Arabic content with proper text processing
- Caches API responses for better performance
- Tracks progress for resumable operations
- Generates complete metadata in NFO files
- Creates proper directory structure for Kodi compatibility
- Modular architecture for easy maintenance and extensibility

## Usage

```bash
python main.py [options]

Options:
  --max-titles MAX     Maximum number of titles to process
  --max-episodes MAX   Maximum episodes per series
  --timeout SECONDS    API request timeout
  --types TYPES       Stream types to process (live_streams, vod, series)
  --skip-series       Skip processing series
  --clear-files       Start fresh (clean existing data)
  --mode MODE         Operation mode (kodi or local)
  --name NAME         Filter content by name (case-insensitive partial match)
  --retry-failed      Retry processing previously failed streams
```

## Argument Interactions

The command-line arguments can be combined in various ways:

### Content Selection

- `--max-titles` with `--name`: Takes the first N matching titles
- `--max-titles` with `--retry-failed`: Limits number of failed streams to retry
- `--name` provides case-insensitive partial matching across all content types

### Processing Control

- `--clear-files` with `--retry-failed`: Preserves failed streams for retry before cleaning
- `--skip-series` affects both normal processing and retries
- `--mode` applies to all operations including retries

### Examples

```bash
# Process up to 10 titles matching a name
python main.py --name "Game of Thrones" --max-titles 10

# Fresh run with name filter, limited to 5 matches
python main.py --clear-files --name "Breaking Bad" --max-titles 5

# Retry failed streams with limit
python main.py --retry-failed --max-titles 20

# Fresh run including retry of failed streams
python main.py --clear-files --retry-failed
```
