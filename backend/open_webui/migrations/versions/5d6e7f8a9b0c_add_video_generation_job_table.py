"""Add persistent video generation jobs.

Revision ID: 5d6e7f8a9b0c
Revises: 4c8d9e0f1a2b
"""

from alembic import op
import sqlalchemy as sa


revision = "5d6e7f8a9b0c"
down_revision = "4c8d9e0f1a2b"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "video_generation_job",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("model_selection_id", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("connection_id", sa.String(), nullable=True),
        sa.Column("connection_index", sa.String(), nullable=True),
        sa.Column("credential_entry_id", sa.String(), nullable=True),
        sa.Column("upstream_request_id", sa.String(), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("duration", sa.Integer(), nullable=False),
        sa.Column("aspect_ratio", sa.String(), nullable=False),
        sa.Column("resolution", sa.String(), nullable=False),
        sa.Column("reference_file_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_file_id", sa.String(), nullable=True),
        sa.Column("submitted_at", sa.BigInteger(), nullable=True),
        sa.Column("next_poll_at", sa.BigInteger(), nullable=True),
        sa.Column("last_polled_at", sa.BigInteger(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["reference_file_id"], ["file.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["result_file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_video_generation_job_user_id", "video_generation_job", ["user_id"])
    op.create_index("ix_video_generation_job_status", "video_generation_job", ["status"])
    op.create_index("ix_video_generation_job_next_poll_at", "video_generation_job", ["next_poll_at"])
    op.create_index(
        "ix_video_generation_job_upstream_request_id",
        "video_generation_job",
        ["upstream_request_id"],
    )


def downgrade():
    op.drop_index("ix_video_generation_job_upstream_request_id", table_name="video_generation_job")
    op.drop_index("ix_video_generation_job_next_poll_at", table_name="video_generation_job")
    op.drop_index("ix_video_generation_job_status", table_name="video_generation_job")
    op.drop_index("ix_video_generation_job_user_id", table_name="video_generation_job")
    op.drop_table("video_generation_job")
