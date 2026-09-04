from typing import Optional

from pydantic import BaseModel, Field


class ConceptDraft(BaseModel):
    """A concept exactly as the model is asked to produce it.

    This class is handed to the LLM as a response schema, so every field name
    and description here is part of the prompt -- the model reads them. Keep
    them precise, and keep server-assigned data (ids, paper ids, timestamps)
    out: the model has no business inventing those.
    """

    name: str = Field(
        ...,
        description="Short title for the concept, at most six words.",
    )
    summary: str = Field(
        ...,
        description="One sentence a curious non-specialist would understand.",
    )
    explanation: str = Field(
        ...,
        description=(
            "Two to four sentences developing the idea, including the intuition "
            "behind it. This is the text that gets animated later, so favour "
            "concrete mechanism over restating the paper's abstract."
        ),
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Concepts a viewer must already know. Empty if none.",
    )
    visual_hint: str = Field(
        ...,
        description=(
            "What an animation of this concept should actually show -- objects, "
            "what moves, what the viewer should notice. One or two sentences."
        ),
    )
    source_pages: list[int] = Field(
        default_factory=list,
        description="1-indexed pages of the paper this concept was drawn from.",
    )


class ConceptExtraction(BaseModel):
    """Wrapper for the list.

    A top-level array works with Gemini, but every provider supports a single
    object, so the extra nesting is what keeps the LLM layer swappable.
    """

    concepts: list[ConceptDraft]


class Concept(ConceptDraft):
    """A stored concept: a draft plus the identity the server assigns it."""

    id: str
    paper_id: str
    video_url: Optional[str] = None  # filled in from milestone 5 onward
