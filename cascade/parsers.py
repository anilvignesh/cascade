"""
File parsers — extract text from uploaded documents.
"""

import subprocess
from pathlib import Path


def parse_pdf(path: str) -> str:
    try:
        from pdfminer.high_level import extract_text
        return extract_text(path).strip()
    except Exception as e:
        return f"PDF parse error: {e}"


def parse_docx(path: str) -> str:
    try:
        from docx import Document
        doc  = Document(path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        return f"DOCX parse error: {e}"


def parse_text(path: str) -> str:
    try:
        return Path(path).read_text(errors="ignore").strip()
    except Exception as e:
        return f"Read error: {e}"


def transcribe_audio(path: str) -> str:
    try:
        r = subprocess.run(
            ["whisper", path, "--model", "tiny", "--output_format", "txt",
             "--output_dir", "/tmp", "--fp16", "False"],
            capture_output=True, text=True, timeout=120
        )
        txt_file = Path("/tmp") / (Path(path).stem + ".txt")
        if txt_file.exists():
            return txt_file.read_text().strip()
        return r.stdout.strip() or "Transcription failed"
    except Exception as e:
        return f"Transcription error: {e}"


def extract(path: str, mime: str = "") -> str:
    p = path.lower()
    if p.endswith(".pdf") or "pdf" in mime:
        return parse_pdf(path)
    if p.endswith(".docx") or "word" in mime:
        return parse_docx(path)
    if p.endswith((".mp3", ".ogg", ".wav", ".m4a")) or "audio" in mime:
        return transcribe_audio(path)
    return parse_text(path)
