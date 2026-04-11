# Kodi Addons

Monorepo for Kodi-related addons and tools.

## Projects

| Directory | What it does |
|---|---|
| [`plugin.video.skipintro/`](plugin.video.skipintro/) | **Skip Intro Addon** — detects, remembers, and skips TV show intros/outros. The main product users install. |
| [`repository.skipintro/`](repository.skipintro/) | Kodi repository for Skip Intro — build scripts and auto-update infrastructure. |
| [`iptv_toolkit/`](iptv_toolkit/) | Unified Python package merging the former `xtream-api`, `m3y2strm`, and `iptveditor` projects. Three CLIs share one set of core/media/db modules. See [`iptv_toolkit/README.md`](iptv_toolkit/README.md). |

## Quick Start

```bash
# Run Skip Intro tests
cd plugin.video.skipintro
python3 test_video_metadata.py -v

# Build Skip Intro release
cd repository.skipintro
./build.sh

# Run an iptv_toolkit CLI (from repo root)
python3 -m iptv_toolkit.cli.xtream --help
python3 -m iptv_toolkit.cli.m3u2strm --help
python3 -m iptv_toolkit.cli.editor --help
```
