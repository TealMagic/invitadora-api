"""whatsapp delivery status columns

Revision ID: 002
Revises: 001
Create Date: 2026-05-25
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            CREATE TYPE whatsapp_delivery_status_enum AS ENUM (
                'pending_ack', 'sent', 'delivered', 'read', 'failed'
            );
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END $$;
        """
    )

    enum_type = postgresql.ENUM(
        "pending_ack",
        "sent",
        "delivered",
        "read",
        "failed",
        name="whatsapp_delivery_status_enum",
        create_type=False,
    )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {c["name"] for c in inspector.get_columns("campaign_recipients")}

    if "whatsapp_delivery_status" in existing_columns:
        return

    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_delivery_status", enum_type, nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_delivery_status_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_failed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_error_code", sa.Integer(), nullable=True),
    )
    op.add_column(
        "campaign_recipients",
        sa.Column("whatsapp_error_title", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_campaign_recipients_whatsapp_message_id",
        "campaign_recipients",
        ["whatsapp_message_id"],
        unique=False,
        postgresql_where=sa.text("whatsapp_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_campaign_recipients_whatsapp_message_id",
        table_name="campaign_recipients",
        postgresql_where=sa.text("whatsapp_message_id IS NOT NULL"),
    )
    op.drop_column("campaign_recipients", "whatsapp_error_title")
    op.drop_column("campaign_recipients", "whatsapp_error_code")
    op.drop_column("campaign_recipients", "whatsapp_failed_at")
    op.drop_column("campaign_recipients", "whatsapp_read_at")
    op.drop_column("campaign_recipients", "whatsapp_delivered_at")
    op.drop_column("campaign_recipients", "whatsapp_sent_at")
    op.drop_column("campaign_recipients", "whatsapp_delivery_status_at")
    op.drop_column("campaign_recipients", "whatsapp_delivery_status")
    sa.Enum(name="whatsapp_delivery_status_enum").drop(op.get_bind(), checkfirst=True)
