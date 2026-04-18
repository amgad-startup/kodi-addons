# Skip Intro Status

Last updated: 2026-04-17

## Automated Test Status

| Area | Status |
| --- | --- |
| Mocked unit suite | 137 tests passing with `python3 test_video_metadata.py -v` |
| Coverage suite | Passing with `./test-container/run-coverage.sh` |
| Linux ARM64 container | Passing through `./test-container/test-all.sh` |
| Linux AMD64 container | Passing through `./test-container/test-all.sh` |
| Headless Kodi E2E | 4 tests passing with `./test-container/run-e2e-container.sh` |

## Coverage Snapshot

Measured with `.coveragerc` against repo-owned Python files, excluding tests,
generated/container code, and vendored enzyme code.

| Module | Coverage |
| --- | ---: |
| Total | 55% |
| `resources/lib/ui.py` | 83% |
| `resources/lib/metadata.py` | 79% |
| `resources/lib/database.py` | 74% |
| `resources/lib/settings.py` | 62% |
| `resources/lib/database_manager.py` | 61% |
| `resources/lib/audio_intro.py` | 58% |
| `resources/lib/show.py` | 56% |
| `context.py` | 54% |
| `resources/lib/chapters.py` | 53% |
| `default.py` | 41% |
| `browse_path.py` / `database_tools.py` | 0% |

No hard coverage gate is currently enforced. CI now runs the unit suite with a
coverage report before building release artifacts.

## E2E Coverage

The current E2E suite runs inside a Kodi container under Xvfb, generates
synthetic media with `ffmpeg`, seeds the addon SQLite database, and drives Kodi
through JSON-RPC.

Scenarios covered:

1. Kodi JSON-RPC is reachable and `plugin.video.skipintro` is enabled.
2. A show with manual time-based config skips near the configured intro end.
3. An unconfigured video does not jump.
4. A chapter-configured MKV skips near the configured chapter end.

The latest local E2E run passed all 4 tests in 51.803 seconds. The run emitted
non-fatal container environment warnings for VA/VDPAU and missing `nmblookup`.

## Security And Platform Coverage

Covered now:

- URL credentials, query strings, and fragments are stripped before logging/display.
- STRM/ffmpeg error paths redact private stream URLs.
- Database import rejects oversized files before reading.
- Import validators reject invalid ranges and bools used as numeric values.
- Show titles containing SQL syntax are stored as data through parameterized SQL.
- Legacy SQLite schema migration preserves rows and adds missing columns.
- Backup/export VFS joins preserve Kodi URL paths and strip generated filenames to basenames.
- Filename parsing covers POSIX paths, Windows paths, and tokenized URLs.

Manual platform smoke tracking lives in `test-container/platform-matrix.md` for
Apple Silicon Mac, Intel Mac, Windows, Raspberry Pi, Android, and iOS feasibility.

## Remaining Gaps

- `default.py` needs more callback/timer coverage around `onAVStarted`, chapter autodetection, and main-loop failures.
- `database_manager.py` still needs broader restore/import-mode coverage.
- `browse_path.py` and `database_tools.py` are command wrappers and currently untested.
- Real-device smoke results still need to be recorded for Intel Mac, Windows, Raspberry Pi, Android, and iOS feasibility.
