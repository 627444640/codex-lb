"""Record whether a request failed over once under the admission breaker."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261011_000000_add_request_log_admission_failover"
down_revision = "20260921_000000_merge_local_timing_and_stale_recovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        if "admission_failover_retried" not in columns:
            batch_op.add_column(sa.Column("admission_failover_retried", sa.Boolean(), nullable=True))
        if "admission_failover_from_account_id" not in columns:
            batch_op.add_column(sa.Column("admission_failover_from_account_id", sa.String(), nullable=True))


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("request_logs")}
    with op.batch_alter_table("request_logs") as batch_op:
        if "admission_failover_from_account_id" in columns:
            batch_op.drop_column("admission_failover_from_account_id")
        if "admission_failover_retried" in columns:
            batch_op.drop_column("admission_failover_retried")
