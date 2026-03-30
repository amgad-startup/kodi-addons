# Skip Intro Addon

The Skip Intro Addon for Kodi intelligently detects, remembers, and skips TV show intros using multiple detection methods and a smart database system.

## Features

- **Smart Show Detection**

  - Automatically identifies TV shows and episodes
  - Works with both Kodi metadata and filename parsing
  - Supports common naming formats (SxxExx, xxXxx)

- **Intro/Outro Management**

  - Saves intro/outro times for each episode
  - Reuses saved times for future playback
  - Multiple detection methods:
    - Database of saved times
    - Chapter markers
    - Configurable default timing
    - Online API support (coming soon)

- **User-Friendly Interface**

  - Clean, focused skip button in bottom right
  - Auto-focused for immediate skipping
  - Works with remote control, keyboard, and mouse
  - Smooth fade in/out animations
  - Non-intrusive design

- **Technical Features**
  - Efficient time tracking using native Kodi events
  - SQLite database for efficient storage
  - Smart duration parsing (HH:MM:SS, MM:SS)
  - Comprehensive error handling
  - Detailed logging
  - Full localization support

## Installation

1. **Download the Addon:**

   - Go to the [Releases](https://github.com/amgadabdelhafez/plugin.video.skipintro/releases) section
   - Download the latest release zip file

2. **Install in Kodi:**

   - Open Kodi > Add-ons
   - Click the "Package" icon (top-left)
   - Select "Install from zip file"
   - Navigate to the downloaded zip file
   - Wait for installation confirmation

3. **Enable the Addon:**
   - Go to Settings > Add-ons
   - Find "Skip Intro" under Video Add-ons
   - Enable the addon

## Configuration

The addon provides three categories of settings:

1. **Intro Skipping Settings**

   - **Delay Before Prompt** (0-300 seconds)
     - How long to wait before showing the skip prompt
     - Default: 30 seconds
   - **Skip Duration** (10-300 seconds)
     - How far forward to skip when using default skip
     - Default: 60 seconds

2. **Database Settings**

   - **Database Location**
     - Where to store the show database
     - Default: special://userdata/addon_data/plugin.video.skipintro/shows.db
   - **Use Chapter Markers**
     - Enable/disable chapter-based detection
     - Default: Enabled
   - **Use Online API**
     - Enable/disable online time source (coming soon)
     - Default: Disabled
   - **Save Times**
     - Whether to save detected times for future use
     - Default: Enabled

3. **Show Settings**
   - **Use Show Defaults**
     - Use the same intro/outro times for all episodes
     - Default: Enabled
   - **Use Chapter Numbers**
     - Use chapter numbers instead of timestamps
     - Default: Disabled
   - **Default Intro Duration**
     - Duration of intro when using show defaults
     - Default: 60 seconds

## How It Works

The addon uses multiple methods to detect and skip intros:

1. **Database Lookup:**

   - Identifies current show and episode
   - Checks database for saved times
   - Uses saved times if available

2. **Chapter Detection:**

   - Looks for chapters named "Intro End"
   - When found, offers to skip to that point
   - Can save times for future use

3. **Manual Input:**

   There are two ways to access the time input feature:

   1. Through Skip Intro Button:

      - When the skip button appears, press menu/info
      - Choose chapters or enter manual times
      - Times are saved for future playback

   2. Through Library Context Menu:
      - In Kodi's TV show library, select a show or episode
      - Press 'C' or right-click to open context menu
      - Select "Set Show Times"
      - If the file has chapters:
        - Select chapters for intro start/end
        - Select chapter for outro start (optional)
        - Times are saved automatically
      * If no chapters available:
        - Enter intro start time and duration
        - Enter outro start time (optional)
        - Choose whether to use for all episodes

   When setting times, if chapters are available:

   - You'll be prompted to select chapters for:
     - Intro Start: Where the intro begins
     - Intro End: Where the intro finishes
     - Outro Start: Where the end credits begin
   - Chapter names and timestamps are shown
   - Selecting chapters automatically sets the times

   If no chapters are available, or if you prefer manual input:

   - Enter times in MM:SS format for:
     - Intro Start Time
     - Intro Duration
     - Outro Start Time (optional)
   - Choose whether to use these times for all episodes

   All times are saved in the database and used for future playback of the show.

4. **Default Skip:**

   - Falls back to configured delay if no other times found
   - Shows skip button after delay time
   - Option to save user-confirmed times

5. **Online API** (Coming Soon):
   - Will fetch intro/outro times from online database
   - Requires API key (not yet implemented)

## Repository Setup

To enable automatic updates:

1. **Add Repository:**

   - In Kodi > Add-ons > Package icon
   - Select "Install from zip file"
   - Navigate to `repository.plugin.video.skipintro.zip`
   - Wait for installation

2. **Updates:**
   - Kodi will automatically check for updates
   - Install updates through Kodi's addon manager

## Development

### Requirements

- Python 3.x
- Kodi 19 (Matrix) or newer

### Testing

The addon includes comprehensive unit tests:

```bash
python3 test_video_metadata.py -v
```

### Building

Use the included build script:

```bash
./build.sh
```

This will:

- Create addon zip file
- Generate repository files
- Update version information

### Project Structure

```
plugin.video.skipintro/
├── addon.xml           # Addon metadata and dependencies
├── default.py         # Main addon code
├── resources/
│   ├── lib/
│   │   ├── database.py   # Database operations
│   │   └── metadata.py   # Show detection
│   ├── settings.xml   # Settings definition
│   └── language/      # Localization files
├── tests/             # Unit tests
└── build.sh          # Build script
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add/update tests
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Changelog

### v1.3.8 (2025-02-19)

- Fixed settings parsing errors
- Improved database migration process
- Resolved issues with chapter-based skip time selection

### v1.3.7 (2025-02-19)

- Improved chapter-based skip time selection
- Enhanced database support for chapter-based configurations
- Fixed issues with saving and retrieving chapter-based settings

### v1.3.6 (2025-02-19)

- Fixed chapter-based skip time selection
- Improved reliability by using direct chapter number input

### v1.3.5 (2025-02-19)

- Recovered feature to set skip times based on chapters
- Added option to choose between manual time input and chapter-based selection
- Updated UI for improved user experience

### v1.3.4 (2025-02-19)

- Initial attempt at fixing database schema issues

### v1.3.3

- Fixed issue with setting manual skip times
- Improved database structure for new show entries
- Enhanced error handling and logging for better diagnostics
- Added verification of saved configurations
- Updated documentation

### v1.3.2

- Improved skip button UI and positioning
- Added smooth fade animations
- Switched to native Kodi event system
- Better performance and reliability
- Improved logging for troubleshooting
- Fixed timing issues during playback

### v1.3.0

- Added show-level default times
- Added duration-based skipping
- Added chapter number support
- Improved database persistence
- Better chapter name handling
- Fixed timing issues during playback
- Updated documentation

### v1.2.93

- Added HH:MM:SS duration parsing
- Improved settings with sliders and validation
- Added comprehensive error handling
- Added localization support
- Improved memory management
- Added unit tests

## Troubleshooting

If you encounter any issues with setting manual skip times:

1. Try setting manual skip times for a show again.
2. If problems persist, check the Kodi log file for detailed information about the process. Look for log entries starting with "SkipIntro:".
3. If you still experience issues, please report them on our GitHub issues page, including the relevant log entries for further investigation.
