"""Preserve usage evidence and pricing provenance without repricing history."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260914_000000_add_request_log_pricing_metadata"
down_revision = "20260816_000000_add_model_source_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        for name, data_type in (
            ("actual_model", sa.String()),
            ("pricing_version", sa.String()),
            ("cache_write_tokens", sa.Integer()),
        ):
            if name not in columns:
                batch_op.add_column(sa.Column(name, data_type, nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        for name in ("cache_write_tokens", "pricing_version", "actual_model"):
            if name in columns:
                batch_op.drop_column(name)
