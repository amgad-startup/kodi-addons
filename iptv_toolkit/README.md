# iptv_toolkit

Unified Python package merging three formerly independent projects:

- **xtream-api** → `iptv_toolkit/{xtream,db,media}/`
- **iptveditor** → `iptv_toolkit/{editor,db/cache.py}`
- **m3y2strm**  → `iptv_toolkit/m3u/`

Shared across all three: `iptv_toolkit.core` (utils, config, logger) and `iptv_toolkit.media` (TMDB, NFO generation).

## Layout

```
iptv_toolkit/
├── cli/                 # three CLI entry points
│   ├── editor.py        # python -m iptv_toolkit.cli.editor
│   ├── m3u2strm.py      # python -m iptv_toolkit.cli.m3u2strm
│   └── xtream.py        # python -m iptv_toolkit.cli.xtream
├── core/                # shared utilities
│   ├── utils.py         # text, language, JSON, logging (union of 3 projects)
│   ├── config.py        # env vars + optional config.json
│   └── logger.py        # structured logger with debug flag
├── media/               # TMDB + NFO generation (canonical xtream-api versions)
│   ├── tmdb.py
│   └── nfo.py
├── m3u/                 # M3U parsing, STRM conversion, file ops
│   ├── parser.py
│   ├── converter.py
│   ├── media_processor.py
│   ├── file_ops.py
│   └── fetch.py
├── db/                  # Kodi videodb + editor cache
│   ├── connection.py
│   ├── media_manager.py
│   ├── metadata_manager.py
│   ├── path_manager.py
│   ├── kodi_manager.py
│   └── cache.py         # IPTVEditor local SQLite cache
├── editor/              # IPTVEditor metadata enrichment
│   ├── editor.py
│   ├── tmdb_api.py
│   ├── iptveditor_api.py
│   └── sample_collector.py
└── xtream/              # Xtream Codes API client + processors
    ├── api_client.py
    ├── stream_processor.py
    ├── strm_processor.py
    ├── catalog_manager.py
    ├── cache_manager.py
    ├── interactive_processor.py
    ├── failed_streams.py
    ├── progress_manager.py
    ├── file_operations.py
    └── processors/
        ├── base_processor.py
        ├── live_processor.py       # working
        ├── vod_processor.py        # broken: see Known Issues
        └── series_processor.py     # broken: see Known Issues
```

## Configuration

Credentials come from environment variables (`.env` loaded automatically):

```bash
# editor
TMDB_API_KEY=...
IPTVEDITOR_TOKEN=...
IPTVEDITOR_PLAYLIST_ID=...

# xtream
XTREAM_API_URL=...
XTREAM_USERNAME=...
XTREAM_PASSWORD=...
```

Xtream runtime options (output paths, batch delays, stream types) live in `config.json` at the repo root. A safe default is used when it's missing.

## Install

```bash
pip install -r iptv_toolkit/requirements.txt
```

## Known issues (pre-existing)

`xtream/processors/vod_processor.py` and `series_processor.py` import
`processors.vod.*` / `processors.series.*` submodules (`metadata_extractor`,
`cast_cleaner`, `file_generator`) that were **never committed to any of the
source repos**. These are stubbed with tolerant `try/except ImportError` so the
package imports cleanly and `LiveProcessor` works, but VOD and Series processing
will raise at runtime until the missing modules are written.

This is not caused by the merge — it exists on `main` in the old `xtream-api/`
directory. Tracking as its own follow-up.
