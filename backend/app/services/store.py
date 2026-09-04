"""Paper storage.

Deliberately a single small interface with one in-memory implementation. The
extracted text lives in a dict and the PDF bytes live on disk, which means a
restart loses everything -- fine for milestone 1, replaced by Postgres in a
later milestone. Keeping every caller behind `PaperStore` is what makes that
swap a one-file change instead of a rewrite.
"""

from pathlib import Path
from typing import Optional

from ..models import Paper, PageText


class PaperNotFoundError(KeyError):
    """Raised when a paper id does not exist."""


class PaperStore:
    def __init__(self, upload_dir: Path):
        self.upload_dir = upload_dir
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._papers: dict[str, Paper] = {}
        self._pages: dict[str, list[PageText]] = {}

    def pdf_path(self, paper_id: str) -> Path:
        return self.upload_dir / f"{paper_id}.pdf"

    def save(self, paper: Paper, pages: list[PageText]) -> Paper:
        self._papers[paper.id] = paper
        self._pages[paper.id] = pages
        return paper

    def get(self, paper_id: str) -> Paper:
        try:
            return self._papers[paper_id]
        except KeyError as exc:
            raise PaperNotFoundError(paper_id) from exc

    def pages(self, paper_id: str) -> list[PageText]:
        try:
            return self._pages[paper_id]
        except KeyError as exc:
            raise PaperNotFoundError(paper_id) from exc

    def list(self) -> list[Paper]:
        """Newest first."""
        return sorted(self._papers.values(), key=lambda p: p.uploaded_at, reverse=True)

    def delete(self, paper_id: str) -> None:
        if paper_id not in self._papers:
            raise PaperNotFoundError(paper_id)
        del self._papers[paper_id]
        self._pages.pop(paper_id, None)
        self.pdf_path(paper_id).unlink(missing_ok=True)


_store: Optional[PaperStore] = None


def get_store() -> PaperStore:
    """FastAPI dependency. One store per process; tests override it."""
    global _store
    if _store is None:
        from ..config import get_settings

        _store = PaperStore(get_settings().upload_dir)
    return _store
