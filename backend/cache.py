"""Compatibility exports for the content-addressed audio cache."""

from backend.storage.cache import SegmentCache, cache_key

__all__ = ["SegmentCache", "cache_key"]
