"""Join the deployed pricing/timing lineage with stale-anchor admission fencing."""

from __future__ import annotations

revision = "20260921_000000_merge_local_timing_and_stale_recovery"
down_revision = (
    "20260915_000000_add_request_log_output_timing",
    "20260821_000000_add_retry_circuit_admission_generation",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
