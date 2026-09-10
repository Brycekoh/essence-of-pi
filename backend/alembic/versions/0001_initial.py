"""Initial schema: papers, pages, concepts.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-10

Written by hand to match app/services/sql_store.py, then held to it by
tests/test_migrations.py, which fails if the two ever disagree.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "papers",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(1024), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "pages",
        sa.Column(
            "paper_id",
            sa.String(64),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("page", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=False),
    )
    op.create_table(
        "concepts",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "paper_id",
            sa.String(64),
            sa.ForeignKey("papers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("prerequisites", sa.JSON(), nullable=False),
        sa.Column("visual_hint", sa.Text(), nullable=False),
        sa.Column("source_pages", sa.JSON(), nullable=False),
        sa.Column("video_url", sa.String(1024), nullable=True),
    )
    op.create_index("ix_concepts_paper_position", "concepts", ["paper_id", "position"])


def downgrade() -> None:
    op.drop_index("ix_concepts_paper_position", table_name="concepts")
    op.drop_table("concepts")
    op.drop_table("pages")
    op.drop_table("papers")
