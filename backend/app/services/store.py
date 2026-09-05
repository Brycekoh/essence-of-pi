"""Paper storage.

Deliberately a single small interface with one in-memory implementation. The
extracted text lives in a dict and the PDF bytes live on disk, which means a
restart loses everything -- fine for milestone 1, replaced by Postgres in a
later milestone. Keeping every caller behind `PaperStore` is what makes that
swap a one-file change instead of a rewrite.
"""

from pathlib import Path
from typing import Optional

from ..models import Concept, Paper, PageText


class PaperNotFoundError(KeyError):
    """Raised when a paper id does not exist."""


class ConceptNotFoundError(KeyError):
    """Raised when a concept id does not exist on that paper."""


class PaperStore:
    def __init__(self, upload_dir: Path, videos_dir: Path | None = None):
        self.upload_dir = upload_dir
        self.videos_dir = videos_dir or upload_dir.parent / "videos"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.videos_dir.mkdir(parents=True, exist_ok=True)
        self._papers: dict[str, Paper] = {}
        self._pages: dict[str, list[PageText]] = {}
        self._concepts: dict[str, list[Concept]] = {}

    def pdf_path(self, paper_id: str) -> Path:
        return self.upload_dir / f"{paper_id}.pdf"

    def video_path(self, concept_id: str) -> Path:
        return self.videos_dir / f"{concept_id}.mp4"

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

    def list_papers(self) -> list[Paper]:
        """Newest first.

        Named `list_papers`, not `list`: a method called `list` shadows the
        builtin inside the class body, so any later `list[Thing]` annotation
        in this class would resolve to the method and raise at import time.
        """
        return sorted(self._papers.values(), key=lambda p: p.uploaded_at, reverse=True)

    def save_concepts(self, paper_id: str, concepts: list[Concept]) -> list[Concept]:
        """Replace this paper's concepts. Re-extraction overwrites."""
        if paper_id not in self._papers:
            raise PaperNotFoundError(paper_id)
        self._concepts[paper_id] = concepts
        return concepts

    def concepts(self, paper_id: str) -> list[Concept]:
        """Empty list means 'not extracted yet' -- an unknown paper raises."""
        if paper_id not in self._papers:
            raise PaperNotFoundError(paper_id)
        return self._concepts.get(paper_id, [])

    def concept(self, paper_id: str, concept_id: str) -> Concept:
        for concept in self.concepts(paper_id):
            if concept.id == concept_id:
                return concept
        raise ConceptNotFoundError(concept_id)

    def set_video(self, paper_id: str, concept_id: str, url: str) -> Concept:
        """Attach a rendered video to a concept, in place."""
        concepts = self.concepts(paper_id)
        for index, concept in enumerate(concepts):
            if concept.id == concept_id:
                updated = concept.model_copy(update={"video_url": url})
                concepts[index] = updated
                return updated
        raise ConceptNotFoundError(concept_id)

    def delete(self, paper_id: str) -> None:
        if paper_id not in self._papers:
            raise PaperNotFoundError(paper_id)
        for concept in self._concepts.get(paper_id, []):
            self.video_path(concept.id).unlink(missing_ok=True)
        del self._papers[paper_id]
        self._pages.pop(paper_id, None)
        self._concepts.pop(paper_id, None)
        self.pdf_path(paper_id).unlink(missing_ok=True)


_store: Optional[PaperStore] = None


def get_store() -> PaperStore:
    """FastAPI dependency. One store per process; tests override it."""
    global _store
    if _store is None:
        from ..config import get_settings

        settings = get_settings()
        _store = PaperStore(settings.upload_dir, settings.videos_dir)
    return _store
