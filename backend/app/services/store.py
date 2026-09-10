"""Paper storage.

`PaperStore` is the seam milestone 1 promised: every caller goes through these
ten methods, so swapping the in-memory implementation for Postgres in
milestone 8 changes no router. It now has two implementations, and
`tests/test_store_contract.py` runs one suite against both -- the promise is a
test, not a comment.

The interface stays synchronous on purpose. Milestone 1 moved pdfplumber off
the event loop because it blocked for seconds; these are single-row lookups
that take well under a millisecond against a local database. The principle was
always about *long* blocking work, and making the seam async would have meant
editing every router to honour it.
"""

from pathlib import Path
from typing import Optional, Protocol

from ..models import Concept, Paper, PageText


class PaperNotFoundError(KeyError):
    """Raised when a paper id does not exist."""


class ConceptNotFoundError(KeyError):
    """Raised when a concept id does not exist on that paper."""


class PaperStore(Protocol):
    """What every store must do. Files on disk; metadata wherever it likes."""

    upload_dir: Path
    videos_dir: Path

    def pdf_path(self, paper_id: str) -> Path: ...
    def video_path(self, concept_id: str) -> Path: ...
    def save(self, paper: Paper, pages: list[PageText]) -> Paper: ...
    def get(self, paper_id: str) -> Paper: ...
    def pages(self, paper_id: str) -> list[PageText]: ...
    def list_papers(self) -> list[Paper]: ...
    def save_concepts(self, paper_id: str, concepts: list[Concept]) -> list[Concept]: ...
    def concepts(self, paper_id: str) -> list[Concept]: ...
    def concept(self, paper_id: str, concept_id: str) -> Concept: ...
    def set_video(self, paper_id: str, concept_id: str, url: str) -> Concept: ...
    def delete(self, paper_id: str) -> None: ...


class FileLayout:
    """Where the bytes live. Shared, so both stores agree on every path."""

    def __init__(self, upload_dir: Path, videos_dir: Path | None = None):
        self.upload_dir = upload_dir
        self.videos_dir = videos_dir or upload_dir.parent / "videos"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)

    def pdf_path(self, paper_id: str) -> Path:
        return self.upload_dir / f"{paper_id}.pdf"

    def video_path(self, concept_id: str) -> Path:
        return self.videos_dir / f"{concept_id}.mp4"

    def remove_files(self, paper_id: str, concept_ids: list[str]) -> None:
        for concept_id in concept_ids:
            self.video_path(concept_id).unlink(missing_ok=True)
        self.pdf_path(paper_id).unlink(missing_ok=True)


class InMemoryPaperStore(FileLayout):
    """Dicts in a process. Loses everything on restart; ideal for tests."""

    def __init__(self, upload_dir: Path, videos_dir: Path | None = None):
        super().__init__(upload_dir, videos_dir)
        self._papers: dict[str, Paper] = {}
        self._pages: dict[str, list[PageText]] = {}
        self._concepts: dict[str, list[Concept]] = {}

    def save(self, paper: Paper, pages: list[PageText]) -> Paper:
        self._papers[paper.id] = paper
        self._pages[paper.id] = list(pages)
        return paper

    def get(self, paper_id: str) -> Paper:
        try:
            return self._papers[paper_id]
        except KeyError as exc:
            raise PaperNotFoundError(paper_id) from exc

    def pages(self, paper_id: str) -> list[PageText]:
        # Sorted, not merely stored. This returned insertion order from
        # milestone 1 until the contract suite ran it beside the SQL store on
        # day one of milestone 8 -- it only ever looked right because
        # pdfplumber happens to emit pages in order.
        try:
            return sorted(self._pages[paper_id], key=lambda p: p.page)
        except KeyError as exc:
            raise PaperNotFoundError(paper_id) from exc

    def list_papers(self) -> list[Paper]:
        """Newest first.

        Named `list_papers`, not `list`: a method called `list` shadows the
        builtin inside the class body, so any later `list[Thing]` annotation
        in this class would resolve to the method and raise at import time.
        """
        return sorted(self._papers.values(), key=lambda p: p.uploaded_at, reverse=True)

    def save_concepts(self, paper_id: str, concepts: list[Concept]) -> list[Concept]:
        """Replace this paper's concepts, preserving order. Re-extraction overwrites."""
        self.get(paper_id)
        self._concepts[paper_id] = list(concepts)
        return list(concepts)

    def concepts(self, paper_id: str) -> list[Concept]:
        """Empty list means 'not extracted yet' -- an unknown paper raises."""
        self.get(paper_id)
        return list(self._concepts.get(paper_id, []))

    def concept(self, paper_id: str, concept_id: str) -> Concept:
        for concept in self.concepts(paper_id):
            if concept.id == concept_id:
                return concept
        raise ConceptNotFoundError(concept_id)

    def set_video(self, paper_id: str, concept_id: str, url: str) -> Concept:
        self.get(paper_id)
        stored = self._concepts.get(paper_id, [])
        for index, concept in enumerate(stored):
            if concept.id == concept_id:
                updated = concept.model_copy(update={"video_url": url})
                stored[index] = updated
                return updated
        raise ConceptNotFoundError(concept_id)

    def delete(self, paper_id: str) -> None:
        self.get(paper_id)
        concept_ids = [c.id for c in self._concepts.get(paper_id, [])]
        del self._papers[paper_id]
        self._pages.pop(paper_id, None)
        self._concepts.pop(paper_id, None)
        self.remove_files(paper_id, concept_ids)


_store: Optional[PaperStore] = None


def get_store() -> PaperStore:
    """FastAPI dependency. One store per process; tests override it.

    `DATABASE_URL` set means Postgres; unset means in-memory, so a fresh clone
    with no database still runs.
    """
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        if settings.database_url:
            from .sql_store import SqlPaperStore

            _store = SqlPaperStore(
                settings.database_url, settings.upload_dir, settings.videos_dir
            )
        else:
            _store = InMemoryPaperStore(settings.upload_dir, settings.videos_dir)
    return _store
