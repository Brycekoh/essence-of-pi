from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PageText(BaseModel):
    """One page of extracted text."""

    page: int = Field(..., ge=1, description="1-indexed page number")
    text: str


class Paper(BaseModel):
    """A single uploaded PDF and everything we know about it.

    Milestone 1 stops at the text. Later milestones hang concepts, scenes and
    rendered clips off this same object.
    """

    id: str
    filename: str
    size_bytes: int
    page_count: int
    char_count: int
    title: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=_now)


class PaperSummary(BaseModel):
    """What the list endpoint returns: metadata without the text payload."""

    id: str
    filename: str
    page_count: int
    char_count: int
    title: Optional[str] = None
    uploaded_at: datetime


class PaperText(BaseModel):
    id: str
    page_count: int
    pages: list[PageText]

    @property
    def full_text(self) -> str:
        return "\n\n".join(p.text for p in self.pages)
