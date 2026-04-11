# Skip Intro for Kodi

Home of the Skip Intro addon and its distribution repository.

## Projects

| Directory | What it does |
|---|---|
| [`plugin.video.skipintro/`](plugin.video.skipintro/) | **Skip Intro Addon** — detects, remembers, and skips TV show intros/outros. The main product users install. |
| [`repository.skipintro/`](repository.skipintro/) | Kodi repository for Skip Intro — build scripts and auto-update infrastructure. |

## Quick Start

```bash
# Run Skip Intro tests
cd plugin.video.skipintro
python3 test_video_metadata.py -v

# Build Skip Intro release
cd repository.skipintro
./build.sh

```

The iptv_toolkit package (xtream panel integration, m3u→strm conversion, IPTVEditor metadata enrichment) was extracted into its own repository. See `~/dev_projects/iptv-toolkit` or the Gitea repo.
