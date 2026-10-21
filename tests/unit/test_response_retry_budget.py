from __future__ import annotations

import contextvars

import pytest

from app.modules.proxy._load_balancer.response_retry_budget import (
    mark_transparent_retry,
    reset_transparent_retry,
    transparent_retry_used,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_budget() -> None:
    reset_transparent_retry()
    yield
    reset_transparent_retry()


def test_budget_is_scoped_per_request_on_a_long_lived_task() -> None:
    mark_transparent_retry("request-a")

    assert transparent_retry_used("request-a") is True
    assert transparent_retry_used("request-b") is False
    assert transparent_retry_used() is True


def test_marking_one_request_does_not_consume_a_sibling_budget() -> None:
    mark_transparent_retry("request-a")
    mark_transparent_retry("request-b")

    assert transparent_retry_used("request-a") is True
    assert transparent_retry_used("request-b") is True
    assert transparent_retry_used("request-c") is False


def test_reset_restores_a_fresh_request_budget() -> None:
    mark_transparent_retry("request-a")
    reset_transparent_retry()

    assert transparent_retry_used("request-a") is False
    assert transparent_retry_used() is False


def test_mark_is_idempotent_for_the_same_request() -> None:
    mark_transparent_retry("request-a")
    mark_transparent_retry("request-a")

    assert transparent_retry_used("request-a") is True


def test_budget_does_not_leak_out_of_an_isolated_context() -> None:
    isolated = contextvars.copy_context()
    isolated.run(mark_transparent_retry, "isolated-request")

    assert isolated.run(transparent_retry_used, "isolated-request") is True
    assert transparent_retry_used("isolated-request") is False
