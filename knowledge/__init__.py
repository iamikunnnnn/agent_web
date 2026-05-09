"""
Knowledge module - provides automatic file type detection, readers, and chunkers.

This module uses FileDetector to automatically select the appropriate reader
and chunking strategy based on file type. Users cannot override this selection.
"""

from .file_detector import (
    FileDetector,
    FileType,
    ChunkingStrategyType,
    detect_file_type,
    get_reader_for_file,
    get_chunker_for_file,
    get_reader_and_chunker,
)
from .chunk import Chunk
from .reader import get_reader, get_reader_and_chunker as get_reader_chunker

__all__ = [
    # File detector
    "FileDetector",
    "FileType",
    "ChunkingStrategyType",
    "detect_file_type",
    "get_reader_for_file",
    "get_chunker_for_file",
    "get_reader_and_chunker",
    # Chunk
    "Chunk",
    # Reader
    "get_reader",
    "get_reader_chunker",
]
