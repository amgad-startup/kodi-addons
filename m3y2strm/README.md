# M3U to STRM Converter

A Python script that converts M3U playlists into STRM files, organizing them into both grouped and flat directory structures while excluding English-named content.

## Features

- Converts M3U playlists to STRM files
- Creates both grouped and flat directory structures
- Automatically excludes English-named content
- Handles both movies and TV shows
- Reorders mixed language titles (Arabic text first)
- Provides detailed progress and completion statistics
- Safe handling of existing folders with size information
- Robust error handling and recovery
- Streamlined user interaction with upfront input gathering

## Directory Structure

The script creates two directory structures for each M3U file:

### For TV Shows (example: wetv_shows.m3u)

- Grouped structure (wetv_shows/):
  ```
  wetv_shows/
  ├── Group1/
  │   └── Show1/
  │       └── Season 01/
  │           └── S01E01.strm
  └── Group2/
      └── Show2/
          └── Season 01/
              └── S01E01.strm
  ```
- Flat structure (wetv_shows-flat/):
  ```
  wetv_shows-flat/
  ├── Show1/
  │   └── Season 01/
  │       └── S01E01.strm
  └── Show2/
      └── Season 01/
          └── S01E01.strm
  ```

### For Movies (example: wetv_movies-final.m3u)

- Grouped structure (wetv_movies-final/):
  ```
  wetv_movies-final/
  ├── Group1/
  │   └── Movie1/
  │       └── movie.strm
  └── Group2/
      └── Movie2/
          └── movie.strm
  ```
- Flat structure (wetv_movies-final-flat/):
  ```
  wetv_movies-final-flat/
  ├── Movie1/
  │   └── movie.strm
  └── Movie2/
      └── movie.strm
  ```

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/m3y2strm.git
   cd m3y2strm
   ```

2. No additional dependencies required - uses Python standard library only.

## Usage

1. Place your M3U files in the same directory as the script
2. Run the script:
   ```bash
   python3 main.py
   ```
3. The script will:
   - First check all M3U files and show their content counts
   - Ask how many items to process from each file
   - Then start processing each file:
     - Check for existing output folders
     - Process the entries, creating STRM files
     - Show progress and completion statistics

## File Structure

- `main.py`: Main entry point and orchestration
- `utils.py`: Common utility functions
- `file_operations.py`: File and directory operations
- `media_processor.py`: Core media processing logic

## Features in Detail

### Streamlined User Interaction

- Gathers all user input upfront
- Shows clear content counts before processing
- Allows setting different quantities for each file
- Provides uninterrupted processing after input

### Mixed Language Handling

- Automatically detects Arabic and English parts in titles
- Moves Arabic text to the beginning of the name
- Preserves special suffixes like مدبلج
- Example: "The Movie عربي" becomes "عربي - The Movie"

### English Content Exclusion

- Automatically detects and skips English-named content
- Handles mixed-language content appropriately
- Preserves Arabic-dubbed content (marked with مدبلج)

### Folder Management

- Detects existing output folders
- Shows folder sizes in human-readable format
- Provides options to:
  1. Delete old content and start fresh
  2. Keep old content and add to it
  3. Cancel operation

### Progress Tracking

- Real-time progress updates
- Shows number of processed items
- Tracks skipped English content
- Reports any errors encountered
- Provides detailed completion summary

### Error Handling

- Safe file operations
- Directory permission handling
- Proper cleanup on errors
- Keyboard interrupt handling

## Contributing

Feel free to submit issues and enhancement requests!
