"""Processor for video-on-demand streams.

Rewritten during the iptv_toolkit merge to delegate all file generation to the
shared ``STRMProcessor`` + ``iptv_toolkit.media.nfo`` rather than go through the
``processors.vod.*`` submodules that were never committed to the original repo.
``--mode kodi`` is not implemented on this path; use ``--mode local``.
"""

from iptv_toolkit.xtream.processors.base_processor import BaseProcessor
from iptv_toolkit.xtream.strm_processor import STRMProcessor
from iptv_toolkit.core.utils import (
    should_skip_title,
    reorder_mixed_language,
    sanitize_filename,
    sanitize_category_name,
    VODTitleCleaner,
)


class VODProcessor(BaseProcessor):
    def __init__(self, api_client=None, max_titles=None, fresh_run=False, mode='local'):
        super().__init__(api_client=api_client, max_titles=max_titles, fresh_run=fresh_run)
        if mode == 'kodi':
            raise NotImplementedError(
                "VOD --mode kodi is not supported. Use --mode local to generate "
                "STRM/NFO files, or implement KodiDBManager-backed VOD insertion."
            )
        self.mode = mode
        self.title_cleaner = VODTitleCleaner()
        self.strm_processor = STRMProcessor()

    def _process_stream(self, stream, batch_content):
        stream_id = stream.get("stream_id")
        raw_name = stream.get("name", "")
        category = sanitize_category_name(stream.get("category_name", ""))

        if should_skip_title(raw_name):
            self.skipped_count += 1
            return

        if not stream_id:
            return

        clean_name = sanitize_filename(reorder_mixed_language(self.title_cleaner.clean_title(raw_name)))

        # Delegate STRM + NFO generation to STRMProcessor (handles both files).
        stream_data = {
            'stream_id': stream_id,
            'name': clean_name,
            'category_name': category,
            'category_id': stream.get('category_id', ''),
        }
        self.strm_processor.process_stream(
            movie_dir=f"vod-flat/{clean_name}",
            stream_data=stream_data,
            stream_type='vod',
            api_client=self.api,
        )

        # Build m3u EXTINF line
        stream_url = (
            f"{self.api.base_url}/movie/{self.api.username}/"
            f"{self.api.password}/{stream_id}.mp4"
        )
        metadata = [
            f'CUID="{stream_id}"',
            f'tvg-name="{raw_name}"',
            f'group-title="{category}"',
        ]
        if stream.get('stream_icon'):
            metadata.append(f'tvg-logo="{stream["stream_icon"]}"')
        batch_content.append(f'#EXTINF:-1 {" ".join(metadata)},{raw_name}')
        batch_content.append(stream_url)

        self.processed_count += 1
        return clean_name, category
