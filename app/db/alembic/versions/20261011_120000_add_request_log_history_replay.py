"""Record a full-history replay reason and the extra input tokens it spent."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261011_120000_add_request_log_history_replay"
down_revision = "20261011_000000_add_request_log_admission_failover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        if "history_replay_reason" not in columns:
            batch_op.add_column(sa.Column("history_replay_reason", sa.String(), nullable=True))
        if "history_replay_extra_tokens" not in columns:
            batch_op.add_column(sa.Column("history_replay_extra_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        if "history_replay_extra_tokens" in columns:
            batch_op.drop_column("history_replay_extra_tokens")
        if "history_replay_reason" in columns:
            batch_op.drop_column("history_replay_reason")
