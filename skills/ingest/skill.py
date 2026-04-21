"""
Document ingestion skill — converts any file or URL to clean markdown.
Powered by markitdown (Microsoft). Handles PDF, Word, Excel, PowerPoint,
images, audio, HTML, CSV, JSON, XML, ZIP.

Setup:
  pip install markitdown

Usage:
  /ingest /path/to/document.pdf
  /ingest https://example.com/report.pdf
  /ingest /path/to/spreadsheet.xlsx summarise the key metrics
"""

DESCRIPTION = "Convert any file or URL to markdown (PDF, Word, Excel, images, web pages)"


def run(query: str, context: str = "") -> str:
    parts  = query.strip().split(None, 1)
    target = parts[0] if parts else ""
    prompt = parts[1] if len(parts) > 1 else ""

    if not target:
        return (
            "Usage: /ingest <file_path_or_url> [optional question]\n\n"
            "Examples:\n"
            "  /ingest ~/Downloads/report.pdf\n"
            "  /ingest https://example.com/doc.pdf summarise the key points\n"
            "  /ingest ~/data.xlsx what are the top 5 rows by revenue"
        )

    try:
        from markitdown import MarkItDown
    except ImportError:
        return (
            "markitdown not installed.\n"
            "Run: pip install markitdown\n"
            "Then try again."
        )

    try:
        md     = MarkItDown()
        result = md.convert(target)
        text   = result.text_content.strip()
    except Exception as e:
        return f"Conversion error: {e}"

    if not text:
        return f"No content extracted from: {target}"

    # If user asked a follow-up question, prepend it as context for the caller
    if prompt:
        return (
            f"**File:** {target}\n"
            f"**Question:** {prompt}\n\n"
            f"---\n\n"
            f"{text[:8000]}"
        )

    return f"**File:** {target}\n\n---\n\n{text[:8000]}"
