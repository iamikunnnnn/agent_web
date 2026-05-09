"""
Chunk module - provides chunking strategies with automatic file type detection.

This module now uses FileDetector to automatically select the appropriate
chunking strategy based on file type. Users cannot override this selection.
"""

from pathlib import Path
from typing import Optional, Union

from agno.knowledge.chunking.document import DocumentChunking
from agno.knowledge.chunking.fixed import FixedSizeChunking
from agno.knowledge.chunking.recursive import RecursiveChunking
from agno.knowledge.chunking.row import RowChunking

# Optional imports for chunkers that may have extra dependencies
try:
    from agno.knowledge.chunking.semantic import SemanticChunking
    SEMANTIC_CHUNKER_AVAILABLE = True
except ImportError:
    SEMANTIC_CHUNKER_AVAILABLE = False

try:
    from agno.knowledge.chunking.markdown import MarkdownChunking
    MARKDOWN_CHUNKER_AVAILABLE = True
except ImportError:
    MARKDOWN_CHUNKER_AVAILABLE = False

try:
    from agno.knowledge.chunking.code import CodeChunking
    CODE_CHUNKER_AVAILABLE = True
except ImportError:
    CODE_CHUNKER_AVAILABLE = False

try:
    from agno.knowledge.chunking.agentic import AgenticChunking
    AGENTIC_CHUNKER_AVAILABLE = True
except ImportError:
    AGENTIC_CHUNKER_AVAILABLE = False

from knowledge.file_detector import (
    FileDetector,
    get_chunker_for_file,
    ChunkingStrategyType,
)


class Chunk:
    """
    Chunking configuration class.

    This class provides a unified interface for chunking strategies.
    The chunking strategy is automatically selected based on file type.
    """

    def __init__(
        self,
        mode: str = "auto",
        chunk_size: int = 5000,
        overlap: int = 200,
        file_path: Optional[Union[str, Path]] = None,
        **kwargs
    ):
        """
        Initialize chunking configuration.

        Args:
            mode: Chunking mode. "auto" automatically detects file type,
                  or use specific modes: "document", "fixed", "semantic",
                  "markdown", "row", "code", "recursive", "agentic"
            chunk_size: Size of each chunk
            overlap: Overlap between chunks
            file_path: Path to the file (required for auto mode)
            **kwargs: Additional parameters for chunkers
        """
        self.mode = mode
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.file_path = file_path
        self.kwargs = kwargs

    def get_chunker(self):
        """
        Get the chunker instance based on mode and file type.

        For "auto" mode, uses FileDetector to select the appropriate chunker.
        For specific modes, creates the requested chunker directly.

        Returns:
            ChunkingStrategy instance

        Raises:
            ValueError: If mode is "auto" but file_path is not provided
            ValueError: If mode is unknown
        """
        if self.mode == "auto":
            if not self.file_path:
                raise ValueError("file_path is required when mode='auto'")

            # Use FileDetector to get the recommended chunker
            return get_chunker_for_file(
                self.file_path,
                chunk_size=self.chunk_size,
                overlap=self.overlap,
                **self.kwargs
            )

        # Manual mode selection
        if self.mode == "document":
            return DocumentChunking(chunk_size=self.chunk_size, overlap=self.overlap, **self.kwargs)
        elif self.mode == "fixed":
            return FixedSizeChunking(chunk_size=self.chunk_size, overlap=self.overlap, **self.kwargs)
        elif self.mode == "semantic":
            if not SEMANTIC_CHUNKER_AVAILABLE:
                raise ValueError("SemanticChunking not available, please install chonkie")
            from config.model_config import get_ai_model
            embedder = self.kwargs.get("embedder") or get_ai_model()
            return SemanticChunking(
                embedder=embedder,
                chunk_size=self.chunk_size,
                similarity_threshold=self.kwargs.get("similarity_threshold", 0.5),
            )
        elif self.mode == "markdown":
            if not MARKDOWN_CHUNKER_AVAILABLE:
                raise ValueError("MarkdownChunking not available, please install unstructured and markdown")
            return MarkdownChunking(
                chunk_size=self.chunk_size,
                overlap=self.overlap,
                split_on_headings=self.kwargs.get("split_on_headings", True),
            )
        elif self.mode == "row":
            return RowChunking(
                skip_header=self.kwargs.get("skip_header", False),
                clean_rows=self.kwargs.get("clean_rows", True),
            )
        elif self.mode == "code":
            if not CODE_CHUNKER_AVAILABLE:
                raise ValueError("CodeChunking not available, please install chonkie")
            return CodeChunking(
                chunk_size=self.chunk_size,
                language=self.kwargs.get("language", "auto"),
            )
        elif self.mode == "recursive":
            return RecursiveChunking(chunk_size=self.chunk_size, overlap=self.overlap, **self.kwargs)
        elif self.mode == "agentic":
            if not AGENTIC_CHUNKER_AVAILABLE:
                raise ValueError("AgenticChunking not available, please install required dependencies")
            return AgenticChunking(max_chunk_size=self.chunk_size)
        else:
            raise ValueError(f"Unknown chunking mode: {self.mode}")

    @staticmethod
    def get_chunker(mode: str = "document", **kwargs) -> Union[DocumentChunking, FixedSizeChunking]:
        """
        Static method to get a chunker (deprecated, use instance method instead).

        This method is kept for backward compatibility.
        Use `Chunk(file_path=..., mode='auto').get_chunker()` instead.
        """
        chunk = Chunk(mode=mode, **kwargs)
        return chunk.get_chunker()
