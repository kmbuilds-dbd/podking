"""per-user analysis prompt styles and queue-time prompt snapshots

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_styles",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "label", name="uq_prompt_style_user_label"),
    )
    op.execute(
        "INSERT INTO prompt_styles (user_id, label, prompt_text) "
        "SELECT u.id, 'general', COALESCE(us.system_prompt, '') "
        "FROM users u LEFT JOIN user_settings us ON us.user_id = u.id"
    )

    op.add_column(
        "subscriptions",
        sa.Column("prompt_style_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        "UPDATE subscriptions s "
        "SET prompt_style_id = ps.id "
        "FROM prompt_styles ps "
        "WHERE ps.user_id = s.user_id AND ps.label = 'general'"
    )
    op.alter_column("subscriptions", "prompt_style_id", nullable=False)
    op.create_foreign_key(
        "fk_subscriptions_prompt_style_id",
        "subscriptions",
        "prompt_styles",
        ["prompt_style_id"],
        ["id"],
    )
    op.add_column("jobs", sa.Column("analysis_prompt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "analysis_prompt")
    op.drop_constraint(
        "fk_subscriptions_prompt_style_id", "subscriptions", type_="foreignkey"
    )
    op.drop_column("subscriptions", "prompt_style_id")
    op.drop_table("prompt_styles")
