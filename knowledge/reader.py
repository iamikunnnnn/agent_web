"""
Reader module - provides document readers with automatic file type detection.

This module now uses FileDetector to automatically select the appropriate
reader based on file type. Users cannot override this selection.
"""

from pathlib import Path
from typing import Optional, Union


def get_reader(
    file_path: Optional[Union[str, Path]] = None,
    chunker: Optional["ChunkingStrategy"] = None,
    url: Optional[str] = None,
):
    """
    Get the appropriate reader for a file or URL.

    The reader is automatically selected based on file type detection.
    Users cannot override the reader selection.

    Args:
        file_path: Path to the file (for local files)
        chunker: Chunking strategy to use with the reader (ignored, kept for backward compatibility)
        url: URL to process (for web content)

    Returns:
        Reader instance

    Raises:
        ValueError: If neither file_path nor url is provided
    """
    from knowledge.file_detector import FileDetector, get_reader_for_file

    if url:
        # For URLs, use URL-based reader detection
        return FileDetector.get_reader_for_url(url)

    if file_path:
        # For local files, use file extension detection
        return get_reader_for_file(file_path)

    raise ValueError("Either file_path or url must be provided")


def get_reader_and_chunker(
    file_path: Union[str, Path],
    chunk_size: int = 5000,
    overlap: int = 200,
    **kwargs
):
    """
    Get both reader and chunker for a file.

    This is a convenience function that automatically selects the appropriate
    reader and chunker based on file type.

    Args:
        file_path: Path to the file
        chunk_size: Desired chunk size
        overlap: Desired overlap
        **kwargs: Additional parameters

    Returns:
        Tuple of (reader, chunker)
    """
    from knowledge.file_detector import get_reader_and_chunker as get_both

    reader, chunker, file_type = get_both(file_path, chunk_size, overlap, **kwargs)
    return reader, chunker
