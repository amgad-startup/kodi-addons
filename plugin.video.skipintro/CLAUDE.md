# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kodi addon (`plugin.video.skipintro`) that detects, remembers, and skips TV show intros/outros. Runs as a Kodi service (background process) and also provides a context menu item for manually setting skip times. Requires Kodi 19 (Matrix)+ and Python 3.x.

## Commands

```bash
# Run tests (mocks Kodi modules so no Kodi installation needed)
python3 test_video_metadata.py -v

# Run tests on ARM64 container (matches Android TV)
docker run --rm -v $(pwd):/addon kodi-skipintro-test:arm64 test

# Build release zip (from sibling directory)
cd ../repository.skipintro && ./build.sh
```

## Architecture

The addon registers three Kodi extension points (see `addon.xml`):
- **`xbmc.service`** → `default.py` — background service that monitors playback
- **`kodi.context.item`** → `context.py` — right-click "Set Skip Intro Times" for episodes/shows in the library
- **`xbmc.gui.skin`** — custom XML-based skip button overlay

### Entry Points

**`default.py`** — `SkipIntroPlayer(xbmc.Player)` subclass runs in a main loop polling every 500ms. On `onAVStarted`, it detects the show, looks up saved times, falls back to chapter detection or default delay, then sets a timer to show the skip button at the right moment. The intro detection priority is: saved DB times → chapter markers (via ffmpeg) → configurable default delay.

**`context.py`** — Standalone script invoked from Kodi's context menu. Lets users choose between manual time input (MM:SS) or chapter number selection, then saves to the database.

**`reload.py`** — Developer utility that uses Kodi JSON-RPC to stop video and toggle the addon on/off for quick reload during development (connects to `localhost:1984`).

### Library Modules (`resources/lib/`)

| Module | Class | Role |
|---|---|---|
| `database.py` | `ShowDatabase` | SQLite persistence. Tables: `shows`, `shows_config`, `episodes`. Auto-migrates schema on init. |
| `metadata.py` | `ShowMetadata` | Identifies current show via Kodi info labels, falls back to filename regex (`SxxExx` / `xxXxx`). Also has a `get_chapters()` method using Kodi JSON-RPC. |
| `chapters.py` | `ChapterManager` | Gets chapter data via **ffmpeg** subprocess (`-f ffmetadata`), caches results per file. Uses `shutil.which('ffmpeg')` for cross-platform path discovery. |
| `settings.py` | `Settings` | Reads/validates addon settings from `resources/settings.xml`, enforces bounds, provides defaults. |
| `ui.py` | `PlayerUI`, `SkipIntroDialog` | `WindowXMLDialog` overlay for the skip button (`skip_button.xml`). |
| `show.py` | `ShowManager` | Higher-level facade combining `ShowMetadata` + `ShowDatabase`. |

### Key Design Details

- **Two chapter detection paths**: `ChapterManager` uses ffmpeg subprocess; `ShowMetadata.get_chapters()` uses Kodi JSON-RPC. The player uses `ChapterManager` (ffmpeg) via `getChapters()`.
- **Database schema**: `shows` (id, title) → `shows_config` (show-level intro/outro settings, supports both time-based and chapter-based) → `episodes` (per-episode overrides). The `get_show()` method auto-creates entries.
- **Skip button timing**: Uses `show_from_start` flag for chapter-only mode (button visible from start), otherwise waits until `intro_start` time is reached.
- **Localization**: String IDs defined in `resources/language/resource.language.en_gb/strings.po`, referenced by numeric ID (32000+) in `settings.xml`.

## Kodi API Patterns

- All logging uses `xbmc.log()` with `'SkipIntro: '` prefix
- Settings read via `xbmcaddon.Addon().getSetting()` / `.getSettingBool()`
- Paths translated via `xbmcvfs.translatePath()` (Kodi special:// protocol)
- UI dialogs via `xbmcgui.Dialog()` and `xbmcgui.WindowXMLDialog`
- Player events via `xbmc.Player` callback methods (`onAVStarted`, `onPlayBackStopped`, etc.)
