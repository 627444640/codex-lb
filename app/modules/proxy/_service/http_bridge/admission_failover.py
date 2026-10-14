"""Move a soft-preferred HTTP bridge turn off an admission-blocked account.

A follow-up still carries ``previous_response_id``. That id is account-scoped,
so the replacement account receives the cached history with the id removed.
A cache miss stays on the existing 503 and is not forwarded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.proxy._load_balancer.admission_breaker import note_soft_preferred_admission_failover
from app.modules.proxy._service.support import _stage_websocket_history_replay, _WebSocketRequestState

SoftPreferredAdmissionAction = Literal["passthrough", "fallback", "replay", "unavailable"]


@dataclass(frozen=True, slots=True)
class SoftPreferredAdmissionDecision:
    action: SoftPreferredAdmissionAction
    excluded_account_id: str | None = None
    history_replay_reason: str | None = None


def apply_soft_preferred_admission_failover(
    request_state: _WebSocketRequestState,
    *,
    key_strength: str,
    owner_check_applied: bool,
    file_pinned: bool,
    single_account_routing: bool,
    admission_blocked: bool,
) -> SoftPreferredAdmissionDecision:
    """Apply one soft-preferred admission move, or leave the request unchanged.

    ``unavailable`` means the follow-up has no replayable history. The caller
    returns 503 and must not open a session on another account.
    """

    preferred_account_id = request_state.preferred_account_id
    if (
        not admission_blocked
        or preferred_account_id is None
        or key_strength == "hard"
        or owner_check_applied
        or file_pinned
        or single_account_routing
    ):
        return SoftPreferredAdmissionDecision("passthrough")
    if request_state.previous_response_id is None:
        request_state.excluded_account_ids.add(preferred_account_id)
        request_state.preferred_account_id = None
        note_soft_preferred_admission_failover(
            preferred_account_id,
            request_id=request_state.request_id,
        )
        return SoftPreferredAdmissionDecision("fallback", excluded_account_id=preferred_account_id)
    # Same planner as the HTTP previous_response_not_found replay. The reason
    # matches the bridge path that already treats an admission-blocked owner
    # as owner_unavailable before an upstream admission error code exists.
    staged = _stage_websocket_history_replay(
        request_state,
        account_id=preferred_account_id,
        reason="owner_unavailable",
        owner_blocked=True,
    )
    if not staged:
        return SoftPreferredAdmissionDecision("unavailable", excluded_account_id=preferred_account_id)
    note_soft_preferred_admission_failover(
        preferred_account_id,
        request_id=request_state.request_id,
        history_replay_reason="owner_unavailable",
    )
    return SoftPreferredAdmissionDecision(
        "replay",
        excluded_account_id=preferred_account_id,
        history_replay_reason="owner_unavailable",
    )
