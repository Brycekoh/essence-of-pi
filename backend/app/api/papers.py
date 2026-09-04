import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from ..config import Settings, get_settings
from ..models import Paper, PageText, PaperSummary, PaperText
from ..services.pdf_parser import (
    NotAPdfError,
    PdfParseError,
    extract_pages,
    looks_like_pdf,
)
from ..services.store import PaperNotFoundError, PaperStore, get_store

router = APIRouter(prefix="/papers", tags=["papers"])


def _summary(paper: Paper) -> PaperSummary:
    return PaperSummary(**paper.model_dump())


@router.post("", response_model=Paper, status_code=status.HTTP_201_CREATED)
async def upload_paper(
    file: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    store: PaperStore = Depends(get_store),
) -> Paper:
    """Accept a PDF, extract its text, and return what we learned about it.

    Validation order matters: cheap checks first, so a 200 MB junk file is
    rejected before we spend a thread on parsing it.
    """
    data = await file.read()

    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Uploaded file is empty.")

    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"File is {len(data)} bytes; the limit is {settings.max_upload_bytes}.",
        )

    # Trust the bytes, not the client-supplied content-type header.
    if not looks_like_pdf(data):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "That file is not a PDF (missing %PDF- header).",
        )

    paper_id = uuid.uuid4().hex
    path = store.pdf_path(paper_id)
    path.write_bytes(data)

    try:
        pages, title = await extract_pages(path)
    except (NotAPdfError, PdfParseError) as exc:
        # Don't leave an orphaned file behind on a failed parse.
        path.unlink(missing_ok=True)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Could not read that PDF: {exc}",
        ) from exc

    paper = Paper(
        id=paper_id,
        filename=file.filename or "untitled.pdf",
        size_bytes=len(data),
        page_count=len(pages),
        char_count=sum(len(p.text) for p in pages),
        title=title,
    )
    return store.save(paper, pages)


@router.get("", response_model=list[PaperSummary])
async def list_papers(store: PaperStore = Depends(get_store)) -> list[PaperSummary]:
    return [_summary(p) for p in store.list_papers()]


@router.get("/{paper_id}", response_model=Paper)
async def get_paper(paper_id: str, store: PaperStore = Depends(get_store)) -> Paper:
    try:
        return store.get(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")


@router.get("/{paper_id}/text", response_model=PaperText)
async def get_paper_text(
    paper_id: str,
    page: int | None = Query(None, ge=1, description="Return only this page."),
    store: PaperStore = Depends(get_store),
) -> PaperText:
    """The whole point of milestone 1: the text we pulled out of the PDF.

    Milestone 2 feeds this into an LLM to extract concepts.
    """
    try:
        pages = store.pages(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")

    selected: list[PageText] = pages
    if page is not None:
        if page > len(pages):
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"Paper has {len(pages)} pages; asked for page {page}.",
            )
        selected = [pages[page - 1]]

    return PaperText(id=paper_id, page_count=len(pages), pages=selected)


@router.get("/{paper_id}/pdf")
async def get_paper_pdf(paper_id: str, store: PaperStore = Depends(get_store)):
    """Serve the original file back, for a PDF viewer in the frontend later."""
    try:
        paper = store.get(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")

    path = store.pdf_path(paper_id)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PDF file is missing on disk.")

    return FileResponse(path, media_type="application/pdf", filename=paper.filename)


@router.delete("/{paper_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paper(paper_id: str, store: PaperStore = Depends(get_store)) -> None:
    try:
        store.delete(paper_id)
    except PaperNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such paper.")
