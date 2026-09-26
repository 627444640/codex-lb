from __future__ import annotations

import pytest

from app.core.usage.logs import total_tokens_from_log, usage_status_from_log
from app.db.models import RequestLog


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "reasoning_tokens", "total", "status"),
    [
        (100, 40, 20, 140, "complete"),
        (100, None, 20, 120, "partial"),
        (None, 40, 20, 40, "partial"),
        (None, None, 20, 20, "partial"),
        (100, None, None, 100, "partial"),
        (0, 0, None, 0, "complete"),
        (0, None, None, 0, "partial"),
        (None, None, None, None, "missing"),
    ],
)
def test_usage_completeness_is_derived_from_reported_base_counts(
    input_tokens, output_tokens, reasoning_tokens, total, status
):
    row = RequestLog(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        cached_input_tokens=30,
        cache_write_tokens=10,
    )
    assert total_tokens_from_log(row) == total
    assert usage_status_from_log(row) == status
