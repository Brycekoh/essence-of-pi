import pytest

from app.models import ConceptDraft, ConceptExtraction, PageText, Paper
from app.services.concepts import build_document, extract_concepts
from app.services.llm import LLMError, StubLLM

from .conftest import upload


def draft(name: str = "Attention", **overrides) -> ConceptDraft:
    base = dict(
        name=name,
        summary="A way to weight inputs by relevance.",
        explanation=(
            "Each output position looks at every input position and assigns it "
            "a weight, then sums the inputs by those weights."
        ),
        prerequisites=["Dot products"],
        visual_hint="A grid of weights lighting up as one token queries all others.",
        source_pages=[1],
    )
    base.update(overrides)
    return ConceptDraft(**base)


# --- the endpoint ---------------------------------------------------------


def test_extract_returns_and_stores_concepts(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(ConceptExtraction(concepts=[draft(), draft("Softmax")]))

    response = client.post(f"/api/papers/{paper_id}/concepts")
    assert response.status_code == 201, response.text

    body = response.json()
    assert [c["name"] for c in body["concepts"]] == ["Attention", "Softmax"]
    assert body["truncated"] is False
    assert body["model"] == "stub"
    assert all(c["paper_id"] == paper_id for c in body["concepts"])
    assert all(c["id"] for c in body["concepts"])

    # And they are readable afterwards without paying for the model again.
    listed = client.get(f"/api/papers/{paper_id}/concepts").json()
    assert [c["id"] for c in listed] == [c["id"] for c in body["concepts"]]


def test_prompt_carries_page_markers_and_paper_text(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(ConceptExtraction(concepts=[draft()]))
    client.post(f"/api/papers/{paper_id}/concepts")

    call = stub_llm.calls[0]
    assert "[page 1]" in call["prompt"] and "[page 2]" in call["prompt"]
    assert "Essence of Pi page one" in call["prompt"]
    assert call["system"].startswith("You are a research explainer")
    assert call["schema"] is ConceptExtraction


def test_concepts_empty_before_extraction(client, sample_pdf):
    paper_id = upload(client, sample_pdf).json()["id"]
    assert client.get(f"/api/papers/{paper_id}/concepts").json() == []


def test_re_extraction_replaces_previous_set(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(ConceptExtraction(concepts=[draft("First")]))
    stub_llm.queue(ConceptExtraction(concepts=[draft("Second")]))

    client.post(f"/api/papers/{paper_id}/concepts")
    client.post(f"/api/papers/{paper_id}/concepts")

    names = [c["name"] for c in client.get(f"/api/papers/{paper_id}/concepts").json()]
    assert names == ["Second"]


def test_single_concept_lookup(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(ConceptExtraction(concepts=[draft()]))
    created = client.post(f"/api/papers/{paper_id}/concepts").json()["concepts"][0]

    found = client.get(f"/api/papers/{paper_id}/concepts/{created['id']}")
    assert found.json()["name"] == "Attention"
    assert client.get(f"/api/papers/{paper_id}/concepts/nope").status_code == 404


def test_upstream_failure_is_502_not_500(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(LLMError("Gemini unavailable after 3 attempts"))

    response = client.post(f"/api/papers/{paper_id}/concepts")
    assert response.status_code == 502
    assert "unavailable" in response.json()["detail"]


def test_unknown_paper_is_404(client):
    assert client.post("/api/papers/nope/concepts").status_code == 404
    assert client.get("/api/papers/nope/concepts").status_code == 404


def test_deleting_a_paper_drops_its_concepts(client, sample_pdf, stub_llm):
    paper_id = upload(client, sample_pdf).json()["id"]
    stub_llm.queue(ConceptExtraction(concepts=[draft()]))
    client.post(f"/api/papers/{paper_id}/concepts")

    client.delete(f"/api/papers/{paper_id}")
    assert client.get(f"/api/papers/{paper_id}/concepts").status_code == 404


# --- the service ----------------------------------------------------------


def test_build_document_marks_pages_and_skips_blanks():
    pages = [
        PageText(page=1, text="first"),
        PageText(page=2, text="   "),
        PageText(page=3, text="third"),
    ]
    text, truncated = build_document(pages, char_budget=10_000)

    assert "[page 1]" in text and "[page 3]" in text
    assert "[page 2]" not in text, "blank pages carry no signal, so they cost no tokens"
    assert truncated is False


def test_build_document_reports_truncation():
    pages = [PageText(page=n, text="x" * 500) for n in range(1, 20)]
    text, truncated = build_document(pages, char_budget=1_000)

    assert truncated is True
    assert len(text) <= 1_100  # the budget, plus the page markers


@pytest.mark.asyncio
async def test_extraction_cleans_up_what_the_schema_cannot():
    """Structured output guarantees the shape of an answer, not its sense."""
    paper = Paper(id="p1", filename="p.pdf", size_bytes=1, page_count=2, char_count=10)
    pages = [PageText(page=1, text="some text")]
    llm = StubLLM(
        [
            ConceptExtraction(
                concepts=[
                    # Cites a page the paper does not have, and lists itself as
                    # its own prerequisite.
                    draft(
                        "Attention",
                        source_pages=[1, 99],
                        prerequisites=["attention", "Dot products"],
                    ),
                    # Same concept again, differing only in case.
                    draft("ATTENTION"),
                    draft("Softmax"),
                ]
            )
        ]
    )

    concepts, _ = await extract_concepts(llm, paper, pages, max_concepts=6)

    assert [c.name for c in concepts] == ["Attention", "Softmax"]
    assert concepts[0].source_pages == [1]
    assert concepts[0].prerequisites == ["Dot products"]


@pytest.mark.asyncio
async def test_max_concepts_is_enforced_on_our_side():
    """The prompt asks for N. Nothing obliges the model to comply, so we trim."""
    paper = Paper(id="p1", filename="p.pdf", size_bytes=1, page_count=1, char_count=10)
    pages = [PageText(page=1, text="some text")]
    llm = StubLLM([ConceptExtraction(concepts=[draft(f"Concept {i}") for i in range(10)])])

    concepts, _ = await extract_concepts(llm, paper, pages, max_concepts=3)
    assert len(concepts) == 3
