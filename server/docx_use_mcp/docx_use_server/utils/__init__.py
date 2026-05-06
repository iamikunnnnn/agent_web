"""
Utility functions for the Word Document Server.

This package contains utility modules for file operations and document handling.
"""

from server.docx_use_mcp.docx_use_server.utils.document_utils import (
    extract_document_text,
    find_and_replace_text,
    find_paragraph_by_text,
    get_document_properties,
    get_document_structure,
)
from server.docx_use_mcp.docx_use_server.utils.file_utils import (
    check_file_writeable,
    create_document_copy,
    ensure_docx_extension,
)
