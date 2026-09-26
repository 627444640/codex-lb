from __future__ import annotations

import pytest

from app.core.openai.models import CompactResponsePayload, OpenAIEvent, OpenAIResponsePayload, ResponseUsage
from app.core.usage.validation import MAX_TOKEN_COUNT

pytestmark = pytest.mark.unit

_INVALID_COUNTS = [-1, True, False, 1.5, "7", [], {}, MAX_TOKEN_COUNT + 1]


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "total_tokens"])
@pytest.mark.parametrize("invalid", _INVALID_COUNTS)
def test_response_usage_marks_invalid_counts_unavailable_without_losing_valid_siblings(field, invalid):
    raw = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, field: invalid}
    usage = ResponseUsage.model_validate(raw)

    assert getattr(usage, field) is None
    for sibling, expected in {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}.items():
        if sibling != field:
            assert getattr(usage, sibling) == expected


@pytest.mark.parametrize("field", ["cached_tokens", "cache_write_tokens", "reasoning_tokens"])
@pytest.mark.parametrize("invalid", _INVALID_COUNTS)
def test_invalid_optional_token_detail_does_not_discard_measured_usage(field, invalid):
    usage = ResponseUsage.model_validate(
        {
            "input_tokens": 10,
            "output_tokens": 5,
            "input_tokens_details": {field: invalid},
        }
    )

    assert (usage.input_tokens, usage.output_tokens) == (10, 5)
    assert usage.input_tokens_details is not None
    assert getattr(usage.input_tokens_details, field) is None


@pytest.mark.parametrize("details", [None, "invalid-details", []])
def test_absent_or_malformed_optional_details_preserve_core_usage(details):
    usage = ResponseUsage.model_validate(
        {
            "input_tokens": 10,
            "output_tokens": 5,
            "input_tokens_details": details,
            "output_tokens_details": details,
        }
    )
    assert (usage.input_tokens, usage.output_tokens) == (10, 5)
    assert usage.input_tokens_details is None
    assert usage.output_tokens_details is None


@pytest.mark.parametrize("count", [0, MAX_TOKEN_COUNT])
def test_zero_and_supported_integer_boundary_remain_measured_counts(count):
    usage = ResponseUsage.model_validate(
        {
            "input_tokens": count,
            "output_tokens": count,
            "input_tokens_details": {"cached_tokens": count, "cache_write_tokens": count},
            "output_tokens_details": {"reasoning_tokens": count},
        }
    )
    assert (usage.input_tokens, usage.output_tokens) == (count, count)
    assert usage.input_tokens_details is not None
    assert usage.input_tokens_details.cached_tokens == count
    assert usage.input_tokens_details.cache_write_tokens == count
    assert usage.output_tokens_details is not None
    assert usage.output_tokens_details.reasoning_tokens == count


@pytest.mark.parametrize("surface", ["event", "response", "compact"])
def test_invalid_usage_does_not_turn_a_completed_response_into_a_parse_failure(surface):
    raw = {"id": "synthetic-completed", "status": "completed", "usage": {"input_tokens": -10, "output_tokens": 5}}
    if surface == "event":
        event = OpenAIEvent.model_validate({"type": "response.completed", "response": raw})
        assert event.type == "response.completed"
        response = event.response
    elif surface == "compact":
        response = CompactResponsePayload.model_validate({**raw, "object": "response.compact"})
    else:
        response = OpenAIResponsePayload.model_validate(raw)
    assert response is not None
    assert response.status == "completed"
    assert response.usage is not None
    assert response.usage.input_tokens is None
    assert response.usage.output_tokens == 5
