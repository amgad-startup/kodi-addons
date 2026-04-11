"""Processor for TV series streams.

Rewritten during the iptv_toolkit merge to delegate all file generation to the
shared ``STRMProcessor`` + ``iptv_toolkit.media.nfo`` rather than go through the
``processors.series.*`` submodules that were never committed to the original
repo. ``--mode kodi`` is not implemented on this path; use ``--mode local``.
"""

from time import sleep

from iptv_toolkit.xtream.processors.base_processor import BaseProcessor
from iptv_toolkit.xtream.strm_processor import STRMProcessor
from iptv_toolkit.core import config
from iptv_toolkit.core.logger import get_logger
from iptv_toolkit.core.utils import (
    should_skip_title,
    reorder_mixed_language,
    sanitize_filename,
    sanitize_category_name,
)

logger = get_logger(__name__)


class SeriesProcessor(BaseProcessor):
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, max_episodes=None, mode='local'):
        super().__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
        if mode == 'kodi':
            raise NotImplementedError(
                "Series --mode kodi is not supported. Use --mode local to generate "
                "STRM/NFO files, or implement KodiDBManager-backed series insertion."
            )
        self.mode = mode
        self.max_episodes = max_episodes
        self.episodes_processed = 0
        self.strm_processor = STRMProcessor(max_episodes=max_episodes)

    def _process_stream(self, stream, batch_content, output_folder=None):
        self.episodes_processed = 0

        series_id = stream.get("series_id")
        raw_name = stream.get("name", "Unknown Series")
        category = sanitize_category_name(stream.get("category_name", ""))

        if should_skip_title(raw_name):
            self.skipped_count += 1
            return

        if not series_id:
            return

        series_info = self.api.get_series_info(series_id)
        if not series_info:
            return

        # Propagate category into series_info so STRMProcessor/NFO sees it.
        series_info.setdefault('info', {})['category_name'] = category

        clean_name = sanitize_filename(reorder_mixed_language(raw_name))

        # Delegate all STRM + NFO creation to STRMProcessor's series branch,
        # which handles the full season/episode tree with Kodi-format filenames.
        stream_data = {
            'series_id': series_id,
            'name': clean_name,
            'category_name': category,
            'category_id': stream.get('category_id', ''),
            'series_info': series_info,
        }
        self.strm_processor.process_stream(
            movie_dir=None,  # unused for series; STRMProcessor uses "series-flat"
            stream_data=stream_data,
            stream_type='series',
            api_client=self.api,
        )
        self.episodes_processed = self.strm_processor.episodes_processed

        # Build a single m3u entry pointing at the series landing URL so the
        # playlist remains consistent with the VOD/live entries.
        m3u_url = (
            f"{self.api.base_url}/series/{self.api.username}/"
            f"{self.api.password}/{series_id}"
        )
        metadata = [
            f'CUID="s{series_id}"',
            f'tvg-name="{raw_name}"',
            f'group-title="{category}"',
        ]
        if stream.get('cover'):
            metadata.append(f'tvg-logo="{stream["cover"]}"')
        batch_content.append(f'#EXTINF:-1 {" ".join(metadata)},{raw_name}')
        batch_content.append(m3u_url)

        self.processed_count += 1
        sleep(config.SERIES_PROCESSING_DELAY)
        return clean_name, category
