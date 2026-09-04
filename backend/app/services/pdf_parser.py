"""PDF text extraction.

pdfplumber is synchronous and CPU-bound. Calling it directly from an async
endpoint would block the event loop for the whole extraction, so every public
function here is async and hands the real work to a worker thread.
"""

import asyncio
from pathlib import Path
from typing import Optional

import pdfplumber

from ..models import PageText

# The first bytes of every valid PDF. Checked instead of trusting the
# browser-supplied content-type, which a client can set to anything.
PDF_MAGIC = b"%PDF-"


class NotAPdfError(ValueError):
    """Raised when the uploaded bytes are not a PDF."""


class PdfParseError(RuntimeError):
    """Raised when a real PDF cannot be read (encrypted, truncated, corrupt)."""


def looks_like_pdf(data: bytes) -> bool:
    return data[: len(PDF_MAGIC)] == PDF_MAGIC


def _extract_sync(path: Path) -> tuple[list[PageText], Optional[str]]:
    pages: list[PageText] = []
    title: Optional[str] = None

    try:
        with pdfplumber.open(path) as pdf:
            raw_title = (pdf.metadata or {}).get("Title")
            if isinstance(raw_title, str) and raw_title.strip():
                title = raw_title.strip()

            for index, page in enumerate(pdf.pages, start=1):
                pages.append(PageText(page=index, text=page.extract_text() or ""))
    except Exception as exc:  # pdfplumber raises a wide variety of types
        raise PdfParseError(str(exc)) from exc

    return pages, title


async def extract_pages(path: Path) -> tuple[list[PageText], Optional[str]]:
    """Extract per-page text and the embedded title, if the PDF declares one.

    Returns pages in document order. A page with no extractable text (a scan,
    a full-page figure) yields an empty string rather than being dropped, so
    page numbers always line up with the source document.
    """
    return await asyncio.to_thread(_extract_sync, path)
