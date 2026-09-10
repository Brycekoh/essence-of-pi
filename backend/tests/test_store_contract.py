"""One suite, every PaperStore implementation.

Milestone 1 promised that swapping the in-memory store for Postgres would change
no router. That is only true if both stores *behave* identically, so the same
tests run against in-memory, SQLite and a real Postgres. The Postgres leg skips
itself when nothing is listening on TEST_DATABASE_URL.

SQLite is here because it runs everywhere with no setup. It is not trusted on
its own: it ignores foreign keys unless told otherwise, and it hands back rows
in insertion order often enough to hide a missing ORDER BY. Postgres is the
leg that catches those.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.models import Concept, PageText, Paper
from app.services.sql_store import SqlPaperStore, make_engine, metadata
from app.services.store import ConceptNotFoundError, InMemoryPaperStore, PaperNotFoundError

PG_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://eop:eop@localhost:55432/eop_test"
)


def _postgres_available() -> bool:
    try:
        engine = create_engine(PG_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("select 1"))
        engine.dispose()
        return True
    except Exception:
        return False


POSTGRES = _postgres_available()

PAGES = [PageText(page=1, text="one"), PageText(page=2, text="two")]


def _paper(uploaded: datetime | None = None, title: str | None = "A paper") -> Paper:
    return Paper(
        id=uuid.uuid4().hex,
        filename="paper.pdf",
        size_bytes=1234,
        page_count=2,
        char_count=6,
        title=title,
        uploaded_at=uploaded or datetime.now(timezone.utc),
    )


def _concept(cid: str, paper_id: str, name: str, video: str | None = None) -> Concept:
    return Concept(
        id=cid,
        paper_id=paper_id,
        name=name,
        summary="summary",
        explanation="explanation",
        prerequisites=["dot products", "gradients"],
        visual_hint="arrows",
        source_pages=[1, 2],
        video_url=video,
    )


@pytest.fixture(params=["memory", "sqlite", "postgres"])
def store(request, tmp_path):
    if request.param == "memory":
        yield InMemoryPaperStore(tmp_path / "uploads", tmp_path / "videos")
        return

    if request.param == "sqlite":
        engine = make_engine(f"sqlite:///{(tmp_path / 'store.db').as_posix()}")
    else:
        if not POSTGRES:
            pytest.skip("needs Postgres on TEST_DATABASE_URL")
        engine = make_engine(PG_URL)

    metadata.drop_all(engine)
    metadata.create_all(engine)
    yield SqlPaperStore(engine, tmp_path / "uploads", tmp_path / "videos")
    metadata.drop_all(engine)
    engine.dispose()


# --- papers ---------------------------------------------------------------


def test_a_paper_round_trips_every_field(store):
    paper = _paper(title=None)
    store.save(paper, PAGES)
    assert store.get(paper.id) == paper


def test_an_unknown_paper_raises_everywhere(store):
    for call in (
        lambda: store.get("nope"),
        lambda: store.pages("nope"),
        lambda: store.concepts("nope"),
        lambda: store.concept("nope", "c"),
        lambda: store.set_video("nope", "c", "/v"),
        lambda: store.save_concepts("nope", []),
        lambda: store.delete("nope"),
    ):
        with pytest.raises(PaperNotFoundError):
            call()


def test_pages_come_back_in_page_order(store):
    paper = _paper()
    store.save(paper, [PageText(page=2, text="two"), PageText(page=1, text="one")])
    assert [p.page for p in store.pages(paper.id)] == [1, 2]


def test_papers_are_listed_newest_first(store):
    now = datetime.now(timezone.utc)
    old = _paper(uploaded=now - timedelta(hours=2))
    mid = _paper(uploaded=now - timedelta(hours=1))
    new = _paper(uploaded=now)
    for paper in (mid, new, old):
        store.save(paper, PAGES)
    assert [p.id for p in store.list_papers()] == [new.id, mid.id, old.id]


def test_unicode_survives_the_trip(store):
    """repr-vs-json.dumps taught this project to test emoji on purpose."""
    paper = _paper(title="Attention 🥧 — naïve")
    store.save(paper, [PageText(page=1, text="∂L/∂w ≈ 0")])
    assert store.get(paper.id).title == "Attention 🥧 — naïve"
    assert store.pages(paper.id)[0].text == "∂L/∂w ≈ 0"


# --- concepts -------------------------------------------------------------


def test_concepts_are_empty_before_extraction(store):
    paper = _paper()
    store.save(paper, PAGES)
    assert store.concepts(paper.id) == []


def test_concept_order_is_stored_not_assumed(store):
    """Order is meaning here: prerequisites come first.

    The saved order matches neither id order nor name order. Then an UPDATE
    moves the first row to the end of a Postgres heap, so a store that forgot
    ORDER BY would now return Zeta last and fail -- rather than passing by
    coincidence, which insertion order makes very easy.
    """
    paper = _paper()
    store.save(paper, PAGES)
    store.save_concepts(
        paper.id,
        [
            _concept("c-b", paper.id, "Zeta"),
            _concept("c-c", paper.id, "Alpha"),
            _concept("c-a", paper.id, "Mu"),
        ],
    )
    store.set_video(paper.id, "c-b", "/api/video")
    assert [c.name for c in store.concepts(paper.id)] == ["Zeta", "Alpha", "Mu"]


def test_re_extraction_replaces_the_previous_set(store):
    paper = _paper()
    store.save(paper, PAGES)
    store.save_concepts(paper.id, [_concept("old", paper.id, "Old")])
    store.save_concepts(paper.id, [_concept("new", paper.id, "New")])
    assert [c.id for c in store.concepts(paper.id)] == ["new"]
    with pytest.raises(ConceptNotFoundError):
        store.concept(paper.id, "old")


def test_list_fields_round_trip(store):
    paper = _paper()
    store.save(paper, PAGES)
    store.save_concepts(paper.id, [_concept("c1", paper.id, "x")])
    got = store.concept(paper.id, "c1")
    assert got.prerequisites == ["dot products", "gradients"]
    assert got.source_pages == [1, 2]


def test_set_video_persists(store):
    paper = _paper()
    store.save(paper, PAGES)
    store.save_concepts(paper.id, [_concept("c1", paper.id, "x")])

    returned = store.set_video(paper.id, "c1", "/api/video")

    assert returned.video_url == "/api/video"
    assert store.concept(paper.id, "c1").video_url == "/api/video", "re-read, not just returned"
    with pytest.raises(ConceptNotFoundError):
        store.set_video(paper.id, "missing", "/v")


def test_a_concept_is_not_reachable_through_another_paper(store):
    a, b = _paper(), _paper()
    store.save(a, PAGES)
    store.save(b, PAGES)
    store.save_concepts(a.id, [_concept("c1", a.id, "Only on A")])

    with pytest.raises(ConceptNotFoundError):
        store.concept(b.id, "c1")
    with pytest.raises(ConceptNotFoundError):
        store.set_video(b.id, "c1", "/v")
    assert store.concept(a.id, "c1").video_url is None, "the refused update changed nothing"


# --- delete ---------------------------------------------------------------


def test_delete_removes_rows_files_and_orphans(store):
    paper = _paper()
    store.save(paper, PAGES)
    store.save_concepts(paper.id, [_concept("c1", paper.id, "x")])
    store.pdf_path(paper.id).write_bytes(b"%PDF-")
    store.video_path("c1").write_bytes(b"mp4")

    store.delete(paper.id)

    assert not store.pdf_path(paper.id).exists()
    assert not store.video_path("c1").exists()
    with pytest.raises(PaperNotFoundError):
        store.get(paper.id)

    # Re-saving the same id proves the concept rows really went. On SQLite
    # without foreign keys switched on, the cascade silently does nothing and
    # the old concept would reappear here.
    store.save(paper, PAGES)
    assert store.concepts(paper.id) == [], "no orphaned concept rows came back"


# --- the reason milestone 8 exists ----------------------------------------


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_a_restarted_store_still_has_everything(backend, tmp_path):
    """Restart the backend and the paper list is empty. Not any more."""
    if backend == "postgres" and not POSTGRES:
        pytest.skip("needs Postgres on TEST_DATABASE_URL")
    url = (
        f"sqlite:///{(tmp_path / 'restart.db').as_posix()}" if backend == "sqlite" else PG_URL
    )

    engine = make_engine(url)
    metadata.drop_all(engine)
    metadata.create_all(engine)
    before = SqlPaperStore(engine, tmp_path / "uploads", tmp_path / "videos")
    paper = _paper()
    before.save(paper, PAGES)
    before.save_concepts(
        paper.id, [_concept("c2", paper.id, "Second"), _concept("c1", paper.id, "First")]
    )
    before.set_video(paper.id, "c1", "/api/video")
    engine.dispose()  # the process goes away

    engine = make_engine(url)
    after = SqlPaperStore(engine, tmp_path / "uploads", tmp_path / "videos")
    try:
        assert after.get(paper.id) == paper
        assert after.pages(paper.id) == PAGES
        assert [c.name for c in after.concepts(paper.id)] == ["Second", "First"]
        assert after.concept(paper.id, "c1").video_url == "/api/video"
    finally:
        metadata.drop_all(engine)
        engine.dispose()
