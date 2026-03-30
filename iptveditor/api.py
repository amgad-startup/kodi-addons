"""
This file is kept for backward compatibility.
Please use the new modular structure in the api/ directory.
"""

from api.tmdb import TMDBApi
from api.iptveditor import IPTVEditorApi

__all__ = ['TMDBApi', 'IPTVEditorApi']
