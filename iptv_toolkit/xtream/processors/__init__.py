"""Xtream stream processors.

Note: VODProcessor and SeriesProcessor depend on pre-existing
``processors.vod.*`` / ``processors.series.*`` subpackages that were never
committed to any of the source projects. These imports are attempted lazily
so the package can still be imported for its working components (LiveProcessor).
See TODO in the merge README.
"""

from iptv_toolkit.xtream.processors.live_processor import LiveProcessor

try:
    from iptv_toolkit.xtream.processors.vod_processor import VODProcessor
except ImportError:
    VODProcessor = None  # type: ignore

try:
    from iptv_toolkit.xtream.processors.series_processor import SeriesProcessor
except ImportError:
    SeriesProcessor = None  # type: ignore

__all__ = ['VODProcessor', 'SeriesProcessor', 'LiveProcessor']
