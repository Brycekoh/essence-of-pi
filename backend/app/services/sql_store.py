"""Paper storage in a relational database -- Postgres in practice.

Core tables rather than ORM classes: every row becomes a pydantic model the
moment it is read, so a mapped class would be a third representation of the
same data. The tables here are also what Alembic's migration is checked
against, in `tests/test_migrations.py`.

Two things the in-memory store got for free and a table does not:

- **Order.** Concepts are ordered so prerequisites come first. A Python list
  keeps that implicitly; a SQL table has no order at all. Hence `position`.
- **Cascades.** Deleting a paper must delete its pages and concepts. Postgres
  enforces foreign keys; SQLite ignores them unless asked, so the SQLite
  engine used in tests turns them on explicitly. Without that the contract
  tests would pass on SQLite over a bug that only Postgres would catch.
"""

from datetime import timezone
from pathlib import Path

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine

from ..models import Concept, Paper, PageText
from .store import ConceptNotFoundError, FileLayout, PaperNotFoundError

metadata = MetaData()

papers = Table(
    "papers",
    metadata,
    Column("id", String(64), primary_key=True),
    Column("filename", String(512), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("char_count", Integer, nullable=False),
    Column("title", String(1024)),
    Column("uploaded_at", DateTime(timezone=True), nullable=False),
)

pages = Table(
    "pages",
    metadata,
    Column(
        "paper_id",
        String(64),
        ForeignKey("papers.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("page", Integer, primary_key=True),
    Column("text", Text, nullable=False),
)

concepts = Table(
    "concepts",
    metadata,
    Column("id", String(64), primary_key=True),
    Column(
        "paper_id",
        String(64),
        ForeignKey("papers.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # Concepts are ordered -- prerequisites first. A table has no order, so
    # the list's order is stored rather than assumed.
    Column("position", Integer, nullable=False),
    Column("name", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("explanation", Text, nullable=False),
    Column("prerequisites", JSON, nullable=False),
    Column("visual_hint", Text, nullable=False),
    Column("source_pages", JSON, nullable=False),
    Column("video_url", String(1024)),
    Index("ix_concepts_paper_position", "paper_id", "position"),
)


def make_engine(url: str) -> Engine:
    engine = create_engine(url, pool_pre_ping=True)
    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys -- and therefore ON DELETE CASCADE --
        # unless every connection opts in.
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class SqlPaperStore(FileLayout):
    def __init__(
        self,
        url_or_engine: str | Engine,
        upload_dir: Path,
        videos_dir: Path | None = None,
    ):
        super().__init__(upload_dir, videos_dir)
        self.engine = (
            make_engine(url_or_engine) if isinstance(url_or_engine, str) else url_or_engine
        )

    # --- papers -----------------------------------------------------------

    def save(self, paper: Paper, page_list: list[PageText]) -> Paper:
        with self.engine.begin() as conn:
            conn.execute(insert(papers).values(**paper.model_dump()))
            if page_list:
                conn.execute(
                    insert(pages),
                    [{"paper_id": paper.id, "page": p.page, "text": p.text} for p in page_list],
                )
        return paper

    def get(self, paper_id: str) -> Paper:
        with self.engine.connect() as conn:
            row = conn.execute(select(papers).where(papers.c.id == paper_id)).mappings().first()
        if row is None:
            raise PaperNotFoundError(paper_id)
        return _paper(row)

    def pages(self, paper_id: str) -> list[PageText]:
        with self.engine.connect() as conn:
            self._require_paper(conn, paper_id)
            rows = conn.execute(
                select(pages.c.page, pages.c.text)
                .where(pages.c.paper_id == paper_id)
                .order_by(pages.c.page)
            ).mappings()
            return [PageText(page=r["page"], text=r["text"]) for r in rows]

    def list_papers(self) -> list[Paper]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(papers).order_by(papers.c.uploaded_at.desc())).mappings()
            return [_paper(r) for r in rows]

    def delete(self, paper_id: str) -> None:
        with self.engine.begin() as conn:
            self._require_paper(conn, paper_id)
            concept_ids = list(
                conn.execute(select(concepts.c.id).where(concepts.c.paper_id == paper_id)).scalars()
            )
            conn.execute(delete(papers).where(papers.c.id == paper_id))
        # Files go after the commit: a failed delete must not leave a row
        # pointing at a video that has already been removed.
        self.remove_files(paper_id, concept_ids)

    # --- concepts ---------------------------------------------------------

    def save_concepts(self, paper_id: str, concept_list: list[Concept]) -> list[Concept]:
        with self.engine.begin() as conn:
            self._require_paper(conn, paper_id)
            conn.execute(delete(concepts).where(concepts.c.paper_id == paper_id))
            if concept_list:
                conn.execute(
                    insert(concepts),
                    [
                        {**c.model_dump(), "paper_id": paper_id, "position": i}
                        for i, c in enumerate(concept_list)
                    ],
                )
        return list(concept_list)

    def concepts(self, paper_id: str) -> list[Concept]:
        with self.engine.connect() as conn:
            self._require_paper(conn, paper_id)
            rows = conn.execute(
                select(concepts)
                .where(concepts.c.paper_id == paper_id)
                .order_by(concepts.c.position)
            ).mappings()
            return [_concept(r) for r in rows]

    def concept(self, paper_id: str, concept_id: str) -> Concept:
        with self.engine.connect() as conn:
            self._require_paper(conn, paper_id)
            row = conn.execute(
                select(concepts).where(
                    concepts.c.id == concept_id, concepts.c.paper_id == paper_id
                )
            ).mappings().first()
        if row is None:
            raise ConceptNotFoundError(concept_id)
        return _concept(row)

    def set_video(self, paper_id: str, concept_id: str, url: str) -> Concept:
        with self.engine.begin() as conn:
            self._require_paper(conn, paper_id)
            result = conn.execute(
                update(concepts)
                .where(concepts.c.id == concept_id, concepts.c.paper_id == paper_id)
                .values(video_url=url)
            )
            if result.rowcount == 0:
                raise ConceptNotFoundError(concept_id)
        return self.concept(paper_id, concept_id)

    # --- helpers ----------------------------------------------------------

    @staticmethod
    def _require_paper(conn, paper_id: str) -> None:
        if conn.execute(select(papers.c.id).where(papers.c.id == paper_id)).first() is None:
            raise PaperNotFoundError(paper_id)


def _paper(row) -> Paper:
    data = dict(row)
    # SQLite hands back naive datetimes even for timezone-aware columns.
    # Postgres does not. Normalising here keeps both stores identical.
    if data["uploaded_at"].tzinfo is None:
        data["uploaded_at"] = data["uploaded_at"].replace(tzinfo=timezone.utc)
    return Paper(**data)


def _concept(row) -> Concept:
    data = dict(row)
    data.pop("position", None)
    return Concept(**data)
