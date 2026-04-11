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
        ├── live_processor.py       # working (all modes)
        ├── vod_processor.py        # working (--mode local); kodi mode NotImplementedError
        └── series_processor.py     # working (--mode local); kodi mode NotImplementedError
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

## Known limitations

- **Xtream `--mode kodi` on VOD/Series:** not implemented. The original
  `xtream-api` project depended on unfinished `processors.{vod,series}.*`
  helper modules that were never committed. As part of the merge, `_process_stream`
  was rewritten to delegate to the shared `STRMProcessor` + `iptv_toolkit.media.nfo`,
  which covers `--mode local` (STRM + NFO generation) fully. Kodi DB insertion
  for VOD/Series would require wiring the result shapes into `KodiDBManager`;
  it currently raises `NotImplementedError` with a clear message.
- **Live TV `--mode kodi`:** no-op (LiveProcessor has a placeholder for PVR
  integration). Use `--mode local` for live streams, or point Kodi's PVR IPTV
  Simple Client at the generated `live.m3u`.
