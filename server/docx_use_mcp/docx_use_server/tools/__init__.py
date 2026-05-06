"""
MCP tool implementations for the Word Document Server.

This package contains the MCP tool implementations that expose functionality
to clients through the Model Context Protocol.
"""

# Document tools
# Comment tools
from server.docx_use_mcp.docx_use_server.tools.comment_tools import (
    get_all_comments,
    get_comments_by_author,
    get_comments_for_paragraph,
)

# Content tools
from server.docx_use_mcp.docx_use_server.tools.content_tools import (
    add_heading,
    add_page_break,
    add_paragraph,
    add_picture,
    add_table,
    add_table_of_contents,
    delete_paragraph,
    search_and_replace,
)
from server.docx_use_mcp.docx_use_server.tools.document_tools import (
    copy_document,
    create_document,
    get_document_info,
    get_document_outline,
    get_document_text,
    list_available_documents,
    merge_documents,
)

# Footnote tools
from server.docx_use_mcp.docx_use_server.tools.footnote_tools import (
    add_endnote_to_document,
    add_footnote_to_document,
    convert_footnotes_to_endnotes_in_document,
    customize_footnote_style,
)

# Format tools
from server.docx_use_mcp.docx_use_server.tools.format_tools import (
    create_custom_style,
    format_table,
    format_text,
)

# Protection tools
from server.docx_use_mcp.docx_use_server.tools.protection_tools import (
    add_digital_signature,
    add_restricted_editing,
    protect_document,
    verify_document,
)
