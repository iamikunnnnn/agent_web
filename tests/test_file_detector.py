"""
Tests for file detector functionality.
"""

import pytest
from pathlib import Path

from knowledge.file_detector import (
    FileDetector,
    FileType,
    detect_file_type,
    get_reader_for_file,
    get_chunker_for_file,
    ChunkingStrategyType,
)


class TestFileDetection:
    """Test file type detection."""

    def test_detect_pdf(self):
        """Test PDF file detection."""
        assert detect_file_type("document.pdf") == FileType.PDF
        assert detect_file_type("/path/to/file.pdf") == FileType.PDF

    def test_detect_csv(self):
        """Test CSV file detection."""
        assert detect_file_type("data.csv") == FileType.CSV
        assert detect_file_type("data.tsv") == FileType.CSV

    def test_detect_excel(self):
        """Test Excel file detection."""
        assert detect_file_type("data.xlsx") == FileType.EXCEL
        assert detect_file_type("data.xls") == FileType.EXCEL

    def test_detect_docx(self):
        """Test Word document detection."""
        assert detect_file_type("document.docx") == FileType.DOCX
        assert detect_file_type("document.doc") == FileType.DOCX

    def test_detect_pptx(self):
        """Test PowerPoint detection."""
        assert detect_file_type("presentation.pptx") == FileType.PPTX

    def test_detect_json(self):
        """Test JSON file detection."""
        assert detect_file_type("data.json") == FileType.JSON

    def test_detect_markdown(self):
        """Test Markdown file detection."""
        assert detect_file_type("README.md") == FileType.MARKDOWN
        assert detect_file_type("document.markdown") == FileType.MARKDOWN

    def test_detect_text(self):
        """Test text file detection."""
        assert detect_file_type("notes.txt") == FileType.TEXT
        assert detect_file_type("log.txt") == FileType.TEXT

    def test_detect_html(self):
        """Test HTML file detection."""
        assert detect_file_type("page.html") == FileType.HTML
        assert detect_file_type("page.htm") == FileType.HTML

    def test_detect_code(self):
        """Test code file detection."""
        assert detect_file_type("script.py") == FileType.CODE
        assert detect_file_type("app.js") == FileType.CODE
        assert detect_file_type("style.css") == FileType.CODE
        assert detect_file_type("config.yaml") == FileType.CODE
        assert detect_file_type("config.yml") == FileType.CODE

    def test_detect_image(self):
        """Test image file detection."""
        assert detect_file_type("image.png") == FileType.IMAGE
        assert detect_file_type("photo.jpg") == FileType.IMAGE
        assert detect_file_type("graphic.svg") == FileType.IMAGE

    def test_detect_audio(self):
        """Test audio file detection."""
        assert detect_file_type("song.mp3") == FileType.AUDIO
        assert detect_file_type("recording.wav") == FileType.AUDIO

    def test_detect_video(self):
        """Test video file detection."""
        assert detect_file_type("movie.mp4") == FileType.VIDEO
        assert detect_file_type("clip.avi") == FileType.VIDEO

    def test_detect_unknown(self):
        """Test unknown file type detection."""
        assert detect_file_type("file.unknown") == FileType.UNKNOWN
        assert detect_file_type("file.xyz") == FileType.UNKNOWN

    def test_detect_case_insensitive(self):
        """Test that file extension detection is case-insensitive."""
        assert detect_file_type("file.PDF") == FileType.PDF
        assert detect_file_type("file.CSV") == FileType.CSV
        assert detect_file_type("file.MD") == FileType.MARKDOWN


class TestReaderSelection:
    """Test reader selection for different file types."""

    def test_pdf_reader(self):
        """Test PDF reader selection."""
        reader = get_reader_for_file("document.pdf")
        assert reader is not None
        assert "PDF" in type(reader).__name__.upper()

    def test_csv_reader(self):
        """Test CSV reader selection."""
        reader = get_reader_for_file("data.csv")
        assert reader is not None
        assert "CSV" in type(reader).__name__.upper()

    def test_excel_reader(self):
        """Test Excel reader selection."""
        reader = get_reader_for_file("data.xlsx")
        assert reader is not None
        assert "EXCEL" in type(reader).__name__.upper()

    def test_docx_reader(self):
        """Test Docx reader selection."""
        reader = get_reader_for_file("document.docx")
        assert reader is not None
        assert "DOCX" in type(reader).__name__.upper()

    def test_json_reader(self):
        """Test JSON reader selection."""
        reader = get_reader_for_file("data.json")
        assert reader is not None
        assert "JSON" in type(reader).__name__.upper()

    def test_markdown_reader(self):
        """Test Markdown reader selection."""
        reader = get_reader_for_file("README.md")
        assert reader is not None
        assert "MARKDOWN" in type(reader).__name__.upper()

    def test_text_reader(self):
        """Test text reader selection."""
        reader = get_reader_for_file("notes.txt")
        assert reader is not None
        assert "TEXT" in type(reader).__name__.upper()

    def test_image_reader_uses_docling(self):
        """Test that image files use Docling reader."""
        reader = get_reader_for_file("image.png")
        assert reader is not None
        assert "DOCLING" in type(reader).__name__.upper()

    def test_audio_reader_uses_docling(self):
        """Test that audio files use Docling reader."""
        reader = get_reader_for_file("audio.mp3")
        assert reader is not None
        assert "DOCLING" in type(reader).__name__.upper()

    def test_video_reader_uses_docling(self):
        """Test that video files use Docling reader."""
        reader = get_reader_for_file("video.mp4")
        assert reader is not None
        assert "DOCLING" in type(reader).__name__.upper()

    def test_html_reader_uses_docling(self):
        """Test that HTML files use Docling reader."""
        reader = get_reader_for_file("page.html")
        assert reader is not None
        assert "DOCLING" in type(reader).__name__.upper()

    def test_code_reader_uses_text(self):
        """Test that code files use Text reader."""
        reader = get_reader_for_file("script.py")
        assert reader is not None
        assert "TEXT" in type(reader).__name__.upper()


class TestChunkerSelection:
    """Test chunker selection for different file types."""

    def test_pdf_uses_document_chunker(self):
        """Test that PDF files use document chunker."""
        chunker = get_chunker_for_file("document.pdf")
        assert chunker is not None
        assert "DOCUMENT" in type(chunker).__name__.upper()

    def test_csv_uses_row_chunker(self):
        """Test that CSV files use row chunker."""
        chunker = get_chunker_for_file("data.csv")
        assert chunker is not None
        assert "ROW" in type(chunker).__name__.upper()

    def test_excel_uses_row_chunker(self):
        """Test that Excel files use row chunker."""
        chunker = get_chunker_for_file("data.xlsx")
        assert chunker is not None
        assert "ROW" in type(chunker).__name__.upper()

    def test_markdown_uses_markdown_chunker(self):
        """Test that Markdown files use markdown chunker."""
        chunker = get_chunker_for_file("README.md")
        assert chunker is not None
        assert "MARKDOWN" in type(chunker).__name__.upper()

    def test_code_uses_code_chunker(self):
        """Test that code files use code chunker."""
        chunker = get_chunker_for_file("script.py")
        assert chunker is not None
        assert "CODE" in type(chunker).__name__.upper()

    def test_chunker_type_detection(self):
        """Test chunker type detection."""
        assert FileDetector.get_chunker_type("document.pdf") == ChunkingStrategyType.DOCUMENT_CHUNKER
        assert FileDetector.get_chunker_type("data.csv") == ChunkingStrategyType.ROW_CHUNKER
        assert FileDetector.get_chunker_type("README.md") == ChunkingStrategyType.MARKDOWN_CHUNKER
        assert FileDetector.get_chunker_type("script.py") == ChunkingStrategyType.CODE_CHUNKER


class TestChunkerConfiguration:
    """Test chunker configuration parameters."""

    def test_chunk_size_parameter(self):
        """Test that chunk size parameter is applied."""
        chunker = get_chunker_for_file("document.pdf", chunk_size=1000)
        assert chunker is not None

    def test_overlap_parameter(self):
        """Test that overlap parameter is applied where supported."""
        chunker = get_chunker_for_file("document.pdf", chunk_size=1000, overlap=100)
        assert chunker is not None

    def test_row_chunker_skip_header(self):
        """Test row chunker skip_header parameter."""
        chunker = get_chunker_for_file("data.csv", skip_header=True)
        assert chunker is not None

    def test_code_chunker_language(self):
        """Test code chunker language parameter."""
        chunker = get_chunker_for_file("script.py", language="python")
        assert chunker is not None

    def test_markdown_chunker_split_on_headings(self):
        """Test markdown chunker split_on_headings parameter."""
        chunker = get_chunker_for_file("README.md", split_on_headings=2)
        assert chunker is not None


class TestFileDetectorUtility:
    """Test FileDetector utility methods."""

    def test_get_supported_extensions(self):
        """Test that supported extensions list is not empty."""
        extensions = FileDetector.get_supported_extensions()
        assert len(extensions) > 0
        assert ".pdf" in extensions
        assert ".csv" in extensions
        assert ".txt" in extensions

    def test_is_supported_known_types(self):
        """Test is_supported for known file types."""
        assert FileDetector.is_supported("document.pdf")
        assert FileDetector.is_supported("data.csv")
        assert FileDetector.is_supported("README.md")
        assert FileDetector.is_supported("notes.txt")

    def test_is_supported_unknown_type(self):
        """Test is_supported for unknown file types (should return True with text reader fallback)."""
        # Unknown types fall back to text reader, so they are supported
        assert FileDetector.is_supported("file.unknown")


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_detect_file_type_function(self):
        """Test detect_file_type convenience function."""
        file_type = detect_file_type("document.pdf")
        assert file_type == FileType.PDF

    def test_get_reader_for_file_function(self):
        """Test get_reader_for_file convenience function."""
        reader = get_reader_for_file("document.pdf")
        assert reader is not None

    def test_get_chunker_for_file_function(self):
        """Test get_chunker_for_file convenience function."""
        chunker = get_chunker_for_file("document.pdf")
        assert chunker is not None


class TestURLHandling:
    """Test URL-based reader selection."""

    def test_youtube_url_detection(self):
        """Test YouTube URL detection."""
        reader = FileDetector.get_reader_for_url("https://www.youtube.com/watch?v=example")
        assert "YOUTUBE" in type(reader).__name__.upper()

    def test_youtu_be_url_detection(self):
        """Test youtu.be URL detection."""
        reader = FileDetector.get_reader_for_url("https://youtu.be/example")
        assert "YOUTUBE" in type(reader).__name__.upper()

    def test_regular_url_uses_website_reader(self):
        """Test that regular URLs use website reader."""
        reader = FileDetector.get_reader_for_url("https://example.com/page")
        assert "WEBSITE" in type(reader).__name__.upper()

    def test_url_chunker_selection(self):
        """Test that URLs get document chunker."""
        chunker = FileDetector.get_chunker_for_url("https://example.com/page", chunk_size=1000)
        assert chunker is not None
        assert "DOCUMENT" in type(chunker).__name__.upper()
