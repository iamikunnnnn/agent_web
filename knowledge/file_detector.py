"""
File Type Detector

Automatically detects file types and selects appropriate readers and chunkers.
This module provides a centralized, hard-coded mapping that users cannot modify.
"""

from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union, Callable, TYPE_CHECKING
from enum import Enum

from agno.knowledge.chunking.strategy import ChunkingStrategyType, ChunkingStrategy
from agno.knowledge.chunking.document import DocumentChunking
from agno.knowledge.chunking.fixed import FixedSizeChunking

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

from agno.knowledge.chunking.row import RowChunking

try:
    from agno.knowledge.chunking.code import CodeChunking
    CODE_CHUNKER_AVAILABLE = True
except ImportError:
    CODE_CHUNKER_AVAILABLE = False

from agno.knowledge.chunking.recursive import RecursiveChunking

try:
    from agno.knowledge.chunking.agentic import AgenticChunking
    AGENTIC_CHUNKER_AVAILABLE = True
except ImportError:
    AGENTIC_CHUNKER_AVAILABLE = False

# Reader imports - all optional with fallbacks
try:
    from agno.knowledge.reader.pdf_reader import PDFReader
    PDF_READER_AVAILABLE = True
except ImportError:
    PDF_READER_AVAILABLE = False

from agno.knowledge.reader.csv_reader import CSVReader
from agno.knowledge.reader.excel_reader import ExcelReader
from agno.knowledge.reader.field_labeled_csv_reader import FieldLabeledCSVReader

try:
    from agno.knowledge.reader.docx_reader import DocxReader
    DOCX_READER_AVAILABLE = True
except ImportError:
    DOCX_READER_AVAILABLE = False

try:
    from agno.knowledge.reader.pptx_reader import PPTXReader
    PPTX_READER_AVAILABLE = True
except ImportError:
    PPTX_READER_AVAILABLE = False

from agno.knowledge.reader.json_reader import JSONReader
from agno.knowledge.reader.markdown_reader import MarkdownReader
from agno.knowledge.reader.text_reader import TextReader

try:
    from agno.knowledge.reader.website_reader import WebsiteReader
    WEBSITE_READER_AVAILABLE = True
except ImportError:
    WEBSITE_READER_AVAILABLE = False

try:
    from agno.knowledge.reader.docling_reader import DoclingReader
    DOCLING_READER_AVAILABLE = True
except ImportError:
    DOCLING_READER_AVAILABLE = False

from agno.utils.log import logger


class FileType(Enum):
    """Supported file types."""

    PDF = "pdf"
    CSV = "csv"
    EXCEL = "excel"
    DOCX = "docx"
    PPTX = "pptx"
    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"
    CODE = "code"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


# File extension to file type mapping
EXTENSION_MAP: Dict[str, FileType] = {
    # PDF files
    ".pdf": FileType.PDF,

    # CSV files
    ".csv": FileType.CSV,
    ".tsv": FileType.CSV,

    # Excel files
    ".xlsx": FileType.EXCEL,
    ".xls": FileType.EXCEL,
    ".xlsm": FileType.EXCEL,

    # Word documents
    ".docx": FileType.DOCX,
    ".doc": FileType.DOCX,

    # PowerPoint presentations
    ".pptx": FileType.PPTX,
    ".ppt": FileType.PPTX,
    ".potx": FileType.PPTX,
    ".ppsx": FileType.PPTX,

    # JSON files
    ".json": FileType.JSON,

    # Markdown files
    ".md": FileType.MARKDOWN,
    ".markdown": FileType.MARKDOWN,

    # Text files
    ".txt": FileType.TEXT,
    ".text": FileType.TEXT,
    ".log": FileType.TEXT,

    # HTML files
    ".html": FileType.HTML,
    ".htm": FileType.HTML,
    ".xhtml": FileType.HTML,

    # Code files
    ".py": FileType.CODE,
    ".js": FileType.CODE,
    ".ts": FileType.CODE,
    ".java": FileType.CODE,
    ".c": FileType.CODE,
    ".cpp": FileType.CODE,
    ".h": FileType.CODE,
    ".hpp": FileType.CODE,
    ".cs": FileType.CODE,
    ".go": FileType.CODE,
    ".rs": FileType.CODE,
    ".php": FileType.CODE,
    ".rb": FileType.CODE,
    ".swift": FileType.CODE,
    ".kt": FileType.CODE,
    ".scala": FileType.CODE,
    ".sh": FileType.CODE,
    ".bash": FileType.CODE,
    ".zsh": FileType.CODE,
    ".fish": FileType.CODE,
    ".ps1": FileType.CODE,
    ".bat": FileType.CODE,
    ".sql": FileType.CODE,
    ".xml": FileType.CODE,
    ".yaml": FileType.CODE,
    ".yml": FileType.CODE,
    ".toml": FileType.CODE,
    ".ini": FileType.CODE,
    ".cfg": FileType.CODE,
    ".conf": FileType.CODE,
    ".dockerfile": FileType.CODE,
    ".makefile": FileType.CODE,
    ".cmake": FileType.CODE,
    ".gradle": FileType.CODE,
    ".json5": FileType.CODE,
    ".jsonc": FileType.CODE,

    # Image files
    ".png": FileType.IMAGE,
    ".jpg": FileType.IMAGE,
    ".jpeg": FileType.IMAGE,
    ".gif": FileType.IMAGE,
    ".bmp": FileType.IMAGE,
    ".webp": FileType.IMAGE,
    ".svg": FileType.IMAGE,
    ".tiff": FileType.IMAGE,
    ".tif": FileType.IMAGE,
    ".ico": FileType.IMAGE,

    # Audio files
    ".mp3": FileType.AUDIO,
    ".wav": FileType.AUDIO,
    ".m4a": FileType.AUDIO,
    ".aac": FileType.AUDIO,
    ".ogg": FileType.AUDIO,
    ".flac": FileType.AUDIO,
    ".wma": FileType.AUDIO,

    # Video files
    ".mp4": FileType.VIDEO,
    ".avi": FileType.VIDEO,
    ".mov": FileType.VIDEO,
    ".wmv": FileType.VIDEO,
    ".flv": FileType.VIDEO,
    ".webm": FileType.VIDEO,
    ".mkv": FileType.VIDEO,
}


# Reader factory functions
def _create_pdf_reader():
    """Create PDF reader."""
    if not PDF_READER_AVAILABLE:
        logger.warning("PDFReader not available, falling back to TextReader")
        return _create_text_reader()
    from agno.knowledge.reader.pdf_reader import PDFReader
    return PDFReader()


def _create_csv_reader():
    """Create CSV reader."""
    return CSVReader()


def _create_excel_reader():
    """Create Excel reader."""
    return ExcelReader()


def _create_docx_reader():
    """Create Docx reader."""
    if not DOCX_READER_AVAILABLE:
        logger.warning("DocxReader not available, falling back to TextReader")
        return _create_text_reader()
    from agno.knowledge.reader.docx_reader import DocxReader
    return DocxReader()


def _create_pptx_reader():
    """Create PPTX reader."""
    if not PPTX_READER_AVAILABLE:
        logger.warning("PPTXReader not available, falling back to TextReader")
        return _create_text_reader()
    from agno.knowledge.reader.pptx_reader import PPTXReader
    return PPTXReader()


def _create_json_reader():
    """Create JSON reader."""
    return JSONReader()


def _create_markdown_reader():
    """Create Markdown reader."""
    return MarkdownReader()


def _create_text_reader():
    """Create Text reader."""
    return TextReader()


def _create_docling_reader():
    """Create Docling reader (universal)."""
    if not DOCLING_READER_AVAILABLE:
        logger.warning("DoclingReader not available, falling back to TextReader")
        return _create_text_reader()
    from agno.knowledge.reader.docling_reader import DoclingReader
    return DoclingReader()


# File type to reader factory mapping
READER_FACTORY_MAP: Dict[FileType, Callable] = {  # type: ignore
    FileType.PDF: _create_pdf_reader,
    FileType.CSV: _create_csv_reader,
    FileType.EXCEL: _create_excel_reader,
    FileType.DOCX: _create_docx_reader,
    FileType.PPTX: _create_pptx_reader,
    FileType.JSON: _create_json_reader,
    FileType.MARKDOWN: _create_markdown_reader,
    FileType.TEXT: _create_text_reader,
    FileType.HTML: _create_docling_reader,
    FileType.IMAGE: _create_docling_reader,
    FileType.AUDIO: _create_docling_reader,
    FileType.VIDEO: _create_docling_reader,
    FileType.CODE: _create_text_reader,
}


# Chunker factory functions with default parameters
def _create_document_chunker(chunk_size: int = 5000, overlap: int = 200, **kwargs) -> DocumentChunking:
    """Create document chunker."""
    return DocumentChunking(chunk_size=chunk_size, overlap=overlap)


def _create_fixed_chunker(chunk_size: int = 5000, overlap: int = 200, **kwargs) -> FixedSizeChunking:
    """Create fixed size chunker."""
    return FixedSizeChunking(chunk_size=chunk_size, overlap=overlap)


def _create_semantic_chunker(chunk_size: int = 5000, overlap: int = 200, **kwargs) -> ChunkingStrategy:
    """Create semantic chunker."""
    if not SEMANTIC_CHUNKER_AVAILABLE:
        logger.warning("SemanticChunking not available, falling back to DocumentChunking")
        return _create_document_chunker(chunk_size, overlap, **kwargs)

    from agno.knowledge.chunking.semantic import SemanticChunking
    from config.model_config import get_ai_model
    embedder = kwargs.get("embedder") or get_ai_model()
    return SemanticChunking(
        embedder=embedder,
        chunk_size=chunk_size,
        similarity_threshold=kwargs.get("similarity_threshold", 0.5),
    )


def _create_markdown_chunker(chunk_size: int = 5000, overlap: int = 0, **kwargs) -> ChunkingStrategy:
    """Create markdown chunker."""
    if not MARKDOWN_CHUNKER_AVAILABLE:
        logger.warning("MarkdownChunking not available, falling back to DocumentChunking")
        return _create_document_chunker(chunk_size, overlap, **kwargs)

    return MarkdownChunking(
        chunk_size=chunk_size,
        overlap=overlap,
        split_on_headings=kwargs.get("split_on_headings", True),
    )


def _create_row_chunker(chunk_size: int = 5000, overlap: int = 0, **kwargs) -> RowChunking:
    """Create row chunker for CSV/Excel."""
    return RowChunking(
        skip_header=kwargs.get("skip_header", False),
        clean_rows=kwargs.get("clean_rows", True),
    )


def _create_code_chunker(chunk_size: int = 2000, overlap: int = 0, **kwargs) -> ChunkingStrategy:
    """Create code chunker."""
    if not CODE_CHUNKER_AVAILABLE:
        logger.warning("CodeChunking not available, falling back to DocumentChunking")
        return _create_document_chunker(chunk_size, overlap, **kwargs)

    from agno.knowledge.chunking.code import CodeChunking
    return CodeChunking(
        chunk_size=chunk_size,
        language=kwargs.get("language", "auto"),
    )


def _create_recursive_chunker(chunk_size: int = 5000, overlap: int = 200, **kwargs) -> RecursiveChunking:
    """Create recursive chunker."""
    return RecursiveChunking(chunk_size=chunk_size, overlap=overlap)


def _create_agentic_chunker(chunk_size: int = 5000, overlap: int = 0, **kwargs) -> ChunkingStrategy:
    """Create agentic chunker."""
    if not AGENTIC_CHUNKER_AVAILABLE:
        logger.warning("AgenticChunking not available, falling back to DocumentChunking")
        return _create_document_chunker(chunk_size, overlap, **kwargs)

    return AgenticChunking(max_chunk_size=chunk_size)


# File type to recommended chunker mapping (hardcoded, user cannot change)
RECOMMENDED_CHUNKER_MAP: Dict[FileType, Tuple[Callable, ChunkingStrategyType]] = {  # type: ignore
    FileType.PDF: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.CSV: (_create_row_chunker, ChunkingStrategyType.ROW_CHUNKER),
    FileType.EXCEL: (_create_row_chunker, ChunkingStrategyType.ROW_CHUNKER),
    FileType.DOCX: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.PPTX: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.JSON: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.MARKDOWN: (_create_markdown_chunker, ChunkingStrategyType.MARKDOWN_CHUNKER),
    FileType.TEXT: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.HTML: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.IMAGE: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.AUDIO: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.VIDEO: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
    FileType.CODE: (_create_code_chunker, ChunkingStrategyType.CODE_CHUNKER),
    FileType.UNKNOWN: (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
}


class FileDetector:
    """
    File type detector that automatically selects appropriate reader and chunker.

    This class provides a centralized, hard-coded mapping that users cannot modify.
    """

    @staticmethod
    def detect_file_type(file_path: Union[str, Path]) -> FileType:
        """
        Detect file type from file path.

        Args:
            file_path: Path to the file

        Returns:
            Detected FileType
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        # Direct extension lookup
        file_type = EXTENSION_MAP.get(ext)
        if file_type:
            return file_type

        # Special cases for files without clear extensions
        # Check for common patterns
        stem = path.stem.lower()

        # Makefile, Dockerfile, etc.
        if stem in ["makefile", "dockerfile", "cmakelists", "readme", "license"]:
            if stem == "readme" or stem == "license":
                return FileType.MARKDOWN if ext in [".md", ".markdown"] else FileType.TEXT
            return FileType.CODE

        # Default to text for unknown files
        return FileType.UNKNOWN

    @staticmethod
    def get_reader(file_path: Union[str, Path]):
        """
        Get the appropriate reader for a file.

        Args:
            file_path: Path to the file

        Returns:
            Reader instance

        Raises:
            ValueError: If no reader is available for the file type
        """
        file_type = FileDetector.detect_file_type(file_path)
        reader_factory = READER_FACTORY_MAP.get(file_type)

        if not reader_factory:
            logger.warning(f"No reader configured for file type: {file_type}, falling back to text reader")
            reader_factory = _create_text_reader

        return reader_factory()

    @staticmethod
    def get_chunker(
        file_path: Union[str, Path],
        chunk_size: int = 5000,
        overlap: int = 200,
        **kwargs,
    ) -> ChunkingStrategy:
        """
        Get the recommended chunker for a file type.

        Args:
            file_path: Path to the file
            chunk_size: Desired chunk size (may be overridden by chunker defaults)
            overlap: Desired overlap (may be overridden by chunker defaults)
            **kwargs: Additional parameters for chunker

        Returns:
            ChunkingStrategy instance
        """
        file_type = FileDetector.detect_file_type(file_path)
        chunker_factory, strategy_type = RECOMMENDED_CHUNKER_MAP.get(
            file_type,
            (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
        )

        # Some chunkers don't use overlap parameter
        if strategy_type in [ChunkingStrategyType.ROW_CHUNKER, ChunkingStrategyType.CODE_CHUNKER]:
            return chunker_factory(chunk_size=chunk_size, **kwargs)

        return chunker_factory(chunk_size=chunk_size, overlap=overlap, **kwargs)

    @staticmethod
    def get_chunker_type(file_path: Union[str, Path]) -> ChunkingStrategyType:
        """
        Get the chunking strategy type for a file.

        Args:
            file_path: Path to the file

        Returns:
            ChunkingStrategyType
        """
        file_type = FileDetector.detect_file_type(file_path)
        _, strategy_type = RECOMMENDED_CHUNKER_MAP.get(
            file_type,
            (_create_document_chunker, ChunkingStrategyType.DOCUMENT_CHUNKER),
        )
        return strategy_type

    @staticmethod
    def get_supported_extensions() -> List[str]:
        """Get list of all supported file extensions."""
        return list(EXTENSION_MAP.keys())

    @staticmethod
    def is_supported(file_path: Union[str, Path]) -> bool:
        """
        Check if a file type is supported.

        Args:
            file_path: Path to the file

        Returns:
            True if supported, False otherwise
        """
        file_type = FileDetector.detect_file_type(file_path)
        return file_type != FileType.UNKNOWN or _create_text_reader is not None

    @staticmethod
    def get_reader_for_url(url: str):
        """
        Get the appropriate reader for a URL.

        Args:
            url: URL to process

        Returns:
            Reader instance
        """
        url_lower = url.lower()

        # YouTube URLs
        if "youtube.com" in url_lower or "youtu.be" in url_lower:
            try:
                from agno.knowledge.reader.youtube_reader import YouTubeReader
                return YouTubeReader()
            except ImportError:
                logger.warning("YouTubeReader not available, falling back to TextReader")
                return _create_text_reader()

        # Default to website reader (or fallback to text)
        if WEBSITE_READER_AVAILABLE:
            from agno.knowledge.reader.website_reader import WebsiteReader
            return WebsiteReader()
        return _create_text_reader()

    @staticmethod
    def get_chunker_for_url(url: str, chunk_size: int = 5000, overlap: int = 200) -> ChunkingStrategy:
        """
        Get the appropriate chunker for a URL.

        Args:
            url: URL to process
            chunk_size: Desired chunk size
            overlap: Desired overlap

        Returns:
            ChunkingStrategy instance
        """
        # For web content, use document chunking
        return _create_document_chunker(chunk_size=chunk_size, overlap=overlap)


# Convenience functions

def detect_file_type(file_path: Union[str, Path]) -> FileType:
    """Convenience function to detect file type."""
    return FileDetector.detect_file_type(file_path)


def get_reader_for_file(file_path: Union[str, Path]):
    """Convenience function to get reader for a file."""
    return FileDetector.get_reader(file_path)


def get_chunker_for_file(file_path: Union[str, Path], chunk_size: int = 5000, overlap: int = 200, **kwargs) -> ChunkingStrategy:
    """Convenience function to get chunker for a file."""
    return FileDetector.get_chunker(file_path, chunk_size, overlap, **kwargs)


def get_reader_and_chunker(
    file_path: Union[str, Path],
    chunk_size: int = 5000,
    overlap: int = 200,
    **kwargs,
) -> Tuple:
    """
    Get both reader and chunker for a file.

    Args:
        file_path: Path to the file
        chunk_size: Desired chunk size
        overlap: Desired overlap
        **kwargs: Additional parameters

    Returns:
        Tuple of (reader, chunker, file_type)
    """
    file_type = FileDetector.detect_file_type(file_path)
    reader = FileDetector.get_reader(file_path)
    chunker = FileDetector.get_chunker(file_path, chunk_size, overlap, **kwargs)

    return reader, chunker, file_type
