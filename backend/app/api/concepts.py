from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..models import Concept
from ..services.concepts import extract_concepts
from ..services.llm import LLMError
from ..services.llm.base import LLMClient
from .deps import provide_llm
from ..services.store import (
    ConceptNotFoundError,
    PaperNotFoundError,
    PaperStore,
    get_store,
)

router = APIRouter(prefix="/papers/{paper_id}/concepts", tags=["concepts"])


class ExtractionResult(BaseModel):
    paper_id: str
    concepts: list[Concept]
    truncated: bool  # true if the paper was longer than the model budget
    model: str


@router.post("", response_model=ExtractionResult, status_code=status.HTTP_201_CREATED)
async def create_concepts(
    paper_id: str,
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
    llm: LLMClient = Depends(provide_llm),
) -> ExtractionResult:
    """Extract concepts from an already-uploaded paper.

    Idempotent in effect, not in cost: calling it again re-runs the model and
    replaces the previous set.
    """
    try:
        paper = store.get(paper_id)
        pages = store.pages(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")

    try:
        concepts, truncated = await extract_concepts(
            llm,
            paper,
            pages,
            max_concepts=settings.max_concepts,
            char_budget=settings.max_chars_to_model,
        )
    except LLMError as exc:
        # 502: we are the client of an upstream service and it let us down.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    if not concepts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "No concepts could be extracted -- the PDF may have no readable text.",
        )

    store.save_concepts(paper_id, concepts)
    return ExtractionResult(
        paper_id=paper_id,
        concepts=concepts,
        truncated=truncated,
        model=getattr(llm, "last_model", llm.model),
    )


@router.get("", response_model=list[Concept])
async def list_concepts(
    paper_id: str, store: PaperStore = Depends(get_store)
) -> list[Concept]:
    """Concepts extracted so far. Empty until the POST above has run."""
    try:
        return store.concepts(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")


@router.get("/{concept_id}", response_model=Concept)
async def get_concept(
    paper_id: str, concept_id: str, store: PaperStore = Depends(get_store)
) -> Concept:
    try:
        return store.concept(paper_id, concept_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
    except ConceptNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such concept.")
