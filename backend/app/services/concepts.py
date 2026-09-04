"""Turning a paper's text into a short list of animatable concepts.

This module owns the prompt. The LLM layer underneath owns transport and
decoding, and knows nothing about papers.
"""

import uuid

from ..models import Concept, ConceptDraft, ConceptExtraction, PageText, Paper
from .llm.base import LLMClient

SYSTEM = """\
You are a research explainer in the mould of 3blue1brown. You read papers and \
identify the small number of ideas that, once understood, make the rest of the \
paper follow. You care about intuition and mechanism, not about summarising \
what the authors claim.

You never invent findings. If the excerpt does not support a claim, leave it out.\
"""

PROMPT = """\
Below is the text of a research paper titled "{title}". Each page is marked \
with [page N].

Identify the {max_concepts} most important concepts a newcomer would need in \
order to understand this paper. Prefer ideas that can be shown visually over \
ideas that are purely definitional. Order them so that a concept's \
prerequisites come before it.

For each concept, cite the pages it came from using the [page N] markers.

<paper>
{text}
</paper>\
"""

# Roughly 15k tokens. Gemini's context is far larger, but a long prompt costs
# latency and money on every retry, and papers bury their ideas in the first
# third anyway. Milestone 2 truncates and says so; smarter selection (section
# detection, chunk-then-merge) is a later problem.
DEFAULT_CHAR_BUDGET = 60_000


def build_document(pages: list[PageText], char_budget: int) -> tuple[str, bool]:
    """Join pages into one prompt-ready string with page markers.

    Returns the text and whether it had to be cut short. The markers are what
    let the model populate `source_pages`, which is how a concept stays
    traceable back to the paper.
    """
    chunks: list[str] = []
    used = 0
    truncated = False

    for page in pages:
        if not page.text.strip():
            continue
        chunk = f"[page {page.page}]\n{page.text}"
        if used + len(chunk) > char_budget:
            remaining = char_budget - used
            if remaining > 200:
                chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        used += len(chunk)

    return "\n\n".join(chunks), truncated


def _clean(draft: ConceptDraft, page_count: int) -> ConceptDraft:
    """Structured output guarantees the shape, not the sense.

    The schema cannot stop the model citing page 900 of a 12-page paper, or
    listing a concept as its own prerequisite, so those get fixed here.
    """
    pages = sorted({p for p in draft.source_pages if 1 <= p <= page_count})
    prerequisites = [
        p.strip()
        for p in draft.prerequisites
        if p.strip() and p.strip().lower() != draft.name.strip().lower()
    ]
    return draft.model_copy(update={"source_pages": pages, "prerequisites": prerequisites})


async def extract_concepts(
    llm: LLMClient,
    paper: Paper,
    pages: list[PageText],
    *,
    max_concepts: int = 6,
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> tuple[list[Concept], bool]:
    """Ask the model for concepts and return them ready to store.

    Raises `LLMError` if the model cannot be reached or its answer is unusable.
    """
    text, truncated = build_document(pages, char_budget)
    if not text.strip():
        return [], truncated

    extraction = await llm.structured(
        prompt=PROMPT.format(
            title=paper.title or paper.filename,
            max_concepts=max_concepts,
            text=text,
        ),
        schema=ConceptExtraction,
        system=SYSTEM,
        temperature=0.3,
    )

    concepts: list[Concept] = []
    seen: set[str] = set()
    for draft in extraction.concepts:
        name = draft.name.strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        cleaned = _clean(draft, paper.page_count)
        concepts.append(
            Concept(
                **cleaned.model_dump(),
                id=uuid.uuid4().hex,
                paper_id=paper.id,
            )
        )
        if len(concepts) == max_concepts:
            break

    return concepts, truncated
