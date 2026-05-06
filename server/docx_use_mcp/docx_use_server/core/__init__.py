"""
Core functionality for the Word Document Server.

This package contains the core functionality modules used by the Word Document Server.
"""

from server.docx_use_mcp.docx_use_server.core.footnotes import (
    add_endnote,
    add_footnote,
    convert_footnotes_to_endnotes,
    customize_footnote_formatting,
    find_footnote_references,
    get_format_symbols,
)
from server.docx_use_mcp.docx_use_server.core.protection import (
    add_protection_info,
    create_signature_info,
    is_section_editable,
    verify_document_protection,
    verify_signature,
)
from server.docx_use_mcp.docx_use_server.core.styles import (
    create_style,
    ensure_heading_style,
    ensure_table_style,
)
from server.docx_use_mcp.docx_use_server.core.tables import (
    apply_table_style,
    copy_table,
    set_cell_border,
)
