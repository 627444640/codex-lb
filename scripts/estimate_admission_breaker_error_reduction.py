#!/usr/bin/env python3
"""Estimate how the admission breaker would have changed the v1.24.3 error rate.

The inputs are the seven-day production totals supplied with the change.
This is a bound, not a replay of request_logs. It assumes account A's
qualifying pre-output failures can move once onto account B, and that
requests pinned to A cannot move.

Run: python scripts/estimate_admission_breaker_error_reduction.py
"""

from __future__ import annotations


def main() -> None:
    requests = 8519
    errors = 579
    account_a_rate = 0.19
    account_b_rate = 0.03
    model_a_rate = 0.26
    model_b_rate = 0.018
    server_error = 307
    overloaded = 85
    pre_output_incomplete = 99

    overall = errors / requests
    # Two-account blend: overall = share_a * rate_a + (1 - share_a) * rate_b.
    share_a = (overall - account_b_rate) / (account_a_rate - account_b_rate)
    model_share_a = (overall - model_b_rate) / (model_a_rate - model_b_rate)
    movable = server_error + overloaded + pre_output_incomplete

    def blend(share: float, rate_a: float, rate_b: float) -> float:
        return share * rate_a + (1.0 - share) * rate_b

    # Isolation without failover leaves A's pinned residue and B's own rate.
    # Failover moves the counted pre-output failures onto B, which still fails
    # at B's rate. Continuity-pinned requests stay in A's residue.
    isolated = blend(0.0, account_a_rate, account_b_rate)
    moved_errors = errors - movable + movable * account_b_rate
    moved_rate = moved_errors / requests
    model_moved_errors = errors - movable + movable * model_b_rate
    model_moved_rate = model_moved_errors / requests

    print(f"observed requests={requests} errors={errors} rate={overall:.1%}")
    print(f"implied account A share from overall rates={share_a:.1%}")
    print(f"implied account A share if the blend is the model rates={model_share_a:.1%}")
    print(f"qualifying pre-output failures treated as movable={movable}")
    print(f"if new work leaves A and only B's {account_b_rate:.1%} remains={isolated:.1%}")
    print(f"if those {movable} failures are retried once at B's overall rate={moved_rate:.1%}")
    print(f"if those {movable} failures are retried once at B's model rate={model_moved_rate:.1%}")
    print(
        "Stopping new assignment without moving those failures leaves about B's "
        f"{account_b_rate:.1%} overall rate, which stays above 2%. Retrying the "
        f"{movable} pre-output failures once onto B reaches about {moved_rate:.1%} "
        f"at B's overall rate, or {model_moved_rate:.1%} at B's model rate. "
        "Pinned previous_response_id turns cannot move, so the realized rate sits between those bounds."
    )


if __name__ == "__main__":
    main()
