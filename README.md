# Kodi Addons

Monorepo for Kodi-related addons and tools.

## Projects

| Directory | What it does |
|---|---|
| [`plugin.video.skipintro/`](plugin.video.skipintro/) | **Skip Intro Addon** — detects, remembers, and skips TV show intros/outros. The main product users install. |
| [`repository.skipintro/`](repository.skipintro/) | Kodi repository for Skip Intro — build scripts and auto-update infrastructure. |
| [`xtream-api/`](xtream-api/) | Xtream API to Kodi integration — processes streams into STRM/NFO files or direct DB insertion. |
| [`m3y2strm/`](m3y2strm/) | M3U to STRM converter — converts M3U playlists into STRM file structures. |
| [`iptveditor/`](iptveditor/) | IPTV Editor — playlist editing and management tool. |

## Quick Start

```bash
# Run Skip Intro tests
cd plugin.video.skipintro
python3 test_video_metadata.py -v

# Build Skip Intro release
cd repository.skipintro
./build.sh
```
