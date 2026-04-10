# Skip Intro Repository

Kodi repository for the Skip Intro Addon — automatic updates via Kodi's addon manager.

## What this repo contains

- `build.sh` / `build.py` — Build scripts to package the addon and generate repository XML
- `repo/` — Generated repository structure served to Kodi
- `release/` — Release artifacts

## The Addon

The Skip Intro Addon (`plugin.video.skipintro`) detects, remembers, and skips TV show intros/outros. Source code is in the sibling `plugin.video.skipintro/` directory.

**Detection methods (in priority order):**
1. Saved times from SQLite database (per-show or per-episode)
2. Chapter markers via ffmpeg (`-f ffmetadata`)
3. Configurable default delay (fallback)

**Features:**
- Context menu "Set Skip Intro Times" for manual time or chapter input
- Skip button overlay during playback
- Show-level and episode-level configuration
- Supports both time-based and chapter-based skip points

## Installation

1. Download the repository zip from [Releases](https://github.com/amgadabdelhafez/plugin.video.skipintro/releases)
2. In Kodi: Add-ons → Package icon → Install from zip file
3. Select the repository zip — Kodi will check for addon updates automatically

## Building

```bash
./build.sh
```

This packages the addon from `../plugin.video.skipintro/`, generates the repository XML, and places artifacts in `repo/`.

## License

MIT License
