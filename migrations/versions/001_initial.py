"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    campaign_status = sa.Enum(
        "draft", "queued", "processing", "completed", "completed_with_errors", "failed", "cancelled",
        name="campaign_status",
    )
    recipient_status = sa.Enum(
        "pending", "processing", "sent", "failed", "invalid", "skipped",
        name="recipient_status",
    )
    job_type = sa.Enum("prepare_campaign", "dispatch_campaign", "retry_failed", name="job_type")
    job_status = sa.Enum("pending", "processing", "done", "failed", name="job_status")
    error_stage = sa.Enum("normalize", "qr", "upload", "whatsapp", "internal", name="error_stage")

    campaign_status.create(op.get_bind(), checkfirst=True)
    recipient_status.create(op.get_bind(), checkfirst=True)
    job_type.create(op.get_bind(), checkfirst=True)
    job_status.create(op.get_bind(), checkfirst=True)
    error_stage.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("organizer_name", sa.String(255), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("template_name", sa.String(128), nullable=False, server_default="confirmacion_registro"),
        sa.Column("template_language", sa.String(16), nullable=False, server_default="es_CL"),
        sa.Column("status", campaign_status, nullable=False, server_default="draft"),
        sa.Column("source_filename", sa.String(512), nullable=True),
        sa.Column("source_content_type", sa.String(128), nullable=True),
        sa.Column("total_rows", sa.Integer(), server_default="0"),
        sa.Column("total_unique_recipients", sa.Integer(), server_default="0"),
        sa.Column("total_sent", sa.Integer(), server_default="0"),
        sa.Column("total_failed", sa.Integer(), server_default="0"),
        sa.Column("total_invalid", sa.Integer(), server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.create_table(
        "campaign_import_rows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("raw_phone", sa.Text(), nullable=False),
        sa.Column("normalized_group_key", sa.Text(), nullable=True),
        sa.Column("normalized_to_digits", sa.Text(), nullable=True),
        sa.Column("button_phone", sa.Text(), nullable=True),
        sa.Column("normalization_error", sa.Text(), nullable=True),
        sa.Column("was_grouped", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "campaign_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("group_key", sa.Text(), nullable=False),
        sa.Column("to_e164_digits", sa.Text(), nullable=False),
        sa.Column("button_phone", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default="Hola"),
        sa.Column("names_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_lines_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("entry_code", sa.Text(), nullable=True),
        sa.Column("status", recipient_status, nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("whatsapp_message_id", sa.Text(), nullable=True),
        sa.Column("whatsapp_message_status", sa.Text(), nullable=True),
        sa.Column("uploaded_qr_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_campaign_recipients_campaign_status", "campaign_recipients", ["campaign_id", "status"])
    op.create_index("ix_campaign_recipients_group_key", "campaign_recipients", ["group_key"])

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True),
        sa.Column("job_type", job_type, nullable=False),
        sa.Column("status", job_status, nullable=False, server_default="pending"),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lock_token", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0"),
        sa.Column("max_attempts", sa.Integer(), server_default="5"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_jobs_status_available", "jobs", ["status", "available_at"])

    op.create_table(
        "message_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("campaign_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("campaign_recipients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("request_payload_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body_text", sa.Text(), nullable=True),
        sa.Column("success", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("error_stage", error_stage, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("message_attempts")
    op.drop_index("ix_jobs_status_available", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_campaign_recipients_group_key", table_name="campaign_recipients")
    op.drop_index("ix_campaign_recipients_campaign_status", table_name="campaign_recipients")
    op.drop_table("campaign_recipients")
    op.drop_table("campaign_import_rows")
    op.drop_table("campaigns")

    sa.Enum(name="error_stage").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="job_type").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="recipient_status").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="campaign_status").drop(op.get_bind(), checkfirst=True)
