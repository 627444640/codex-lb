from __future__ import annotations

import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, cast

from app.core.balancer.types import UpstreamError
from app.core.openai.models import OpenAIEvent
from app.core.openai.requests import ResponsesRequest
from app.core.types import JsonValue
from app.db.models import Account
from app.modules.proxy._service.streaming.helpers import (
    _note_upstream_stream_error,
    _raw_stream_error_code_or_upstream,
    _raw_stream_error_fields,
)
from app.modules.proxy._service.support import (
    _RequestLogFailureMetadata,
    _RetryableStreamError,
    _StreamSettlement,
    _TerminalStreamError,
    _TransientStreamError,
)
from app.modules.proxy.helpers import _normalize_error_code, _upstream_error_from_openai


def _facade() -> Any:
    return sys.modules["app.modules.proxy.service"]


@dataclass(slots=True)
class StreamErrorHandling:
    """State produced while handling one upstream terminal SSE error."""

    status: str = "error"
    error_code: str | None = None
    error_message: str | None = None
    response_id: str | None = None
    failure_metadata: _RequestLogFailureMetadata = field(default_factory=_RequestLogFailureMetadata)
    terminal_error: _TerminalStreamError | None = None
    line: str | None = None
    event: OpenAIEvent | None = None
    event_payload: dict[str, JsonValue] | None = None
    event_type: str | None = None
    transient_error: _TransientStreamError | None = None
    retryable_error: _RetryableStreamError | None = None
    history_replay: tuple[str, tuple[str | None, str | None, str | None]] | None = None


async def handle_stream_error(
    *,
    proxy: Any,
    account: Account,
    payload: ResponsesRequest,
    settlement: _StreamSettlement,
    event: OpenAIEvent | None,
    event_payload: dict[str, JsonValue] | None,
    event_type: str | None,
    line: str | None,
    preserve_raw_sse_line: bool,
    request_id: str,
    account_id: str | None,
    allow_retry: bool,
    allow_transient_retry: bool,
    downstream_visible: bool,
    upstream_model_output_seen: bool,
    preferred_account_id: str | None,
    replay_history: Callable[..., Awaitable[None]],
    saw_text_delta: bool = False,
    terminal_on_error: bool = False,
    eligible: bool = True,
    note_raw_error: bool = True,
) -> StreamErrorHandling:
    """Apply the shared pre-output response-protection and error contract."""
    result = StreamErrorHandling(
        response_id=request_id,
        line=line,
        event=event,
        event_payload=event_payload,
        event_type=event_type,
    )
    if event is not None and event.type in ("response.failed", "error"):
        if event.type == "response.failed":
            response = event.response
            error = response.error if response else None
            if response is not None and response.id:
                result.response_id = response.id
                settlement.response_id = response.id
        else:
            error = event.error
        if preserve_raw_sse_line and error is None:
            raw_error_type, raw_error_message, raw_error_param, raw_error_code = _raw_stream_error_fields(
                event_type,
                event_payload,
            )
            upstream_error = cast(UpstreamError, {"message": raw_error_message or "Upstream error"})
        else:
            raw_error_type = error.type if error else None
            raw_error_message = error.message if error else None
            raw_error_param = error.param if error else None
            raw_error_code = _normalize_error_code(error.code if error else None, raw_error_type)
            upstream_error = _upstream_error_from_openai(error)
        original_upstream_error = upstream_error
        raw_error_code = _raw_stream_error_code_or_upstream(event_type, event_payload, raw_error_code)
        rewritten_error = _facade()._rewrite_previous_response_stream_error(
            previous_response_id=payload.previous_response_id,
            preferred_account_id=preferred_account_id,
            error_code=raw_error_code,
            error_type=raw_error_type,
            error_message=raw_error_message,
            error_param=raw_error_param,
        )
        settlement.error = upstream_error
        upstream_error = settlement.error or cast(UpstreamError, {"message": "Upstream error"})
        settlement.record_success = False
        if note_raw_error:
            result.failure_metadata, retry_response_protection = _note_upstream_stream_error(
                code=raw_error_code,
                message=raw_error_message,
                error_type=raw_error_type,
                param=raw_error_param,
                request_id=request_id,
                account_id=account_id,
                allow_transient_retry=allow_transient_retry,
                downstream_visible=downstream_visible,
                upstream_model_output_seen=upstream_model_output_seen,
                eligible=eligible and rewritten_error is None,
            )
        else:
            retry_response_protection = False
        if retry_response_protection:
            result.error_code = raw_error_code
            result.error_message = raw_error_message
            settlement.account_health_error = False
            result.transient_error = _TransientStreamError(
                raw_error_code or "internal_error",
                upstream_error,
                preserve_on_selection_exhausted=True,
            )
        if rewritten_error is not None:
            rewritten_code, rewritten_message, upstream_error_code = rewritten_error
            if upstream_error_code is not None:
                await proxy._handle_stream_error(
                    account,
                    upstream_error if terminal_on_error else original_upstream_error,
                    upstream_error_code,
                )
            replay_error_fields = (
                (raw_error_code, raw_error_param, raw_error_message)
                if terminal_on_error
                else (
                    raw_error_code,
                    error.param if error else None,
                    error.message if error else None,
                )
            )
            result.history_replay = (rewritten_code, replay_error_fields)
            result.response_id = (
                event.response.id
                if event.type == "response.failed" and event.response and event.response.id
                else request_id
            )
            (
                result.line,
                result.event,
                result.event_payload,
                result.event_type,
            ) = _facade()._build_rewritten_stream_response_failed_event(
                response_id=result.response_id,
                error_code=rewritten_code,
                error_message=rewritten_message,
            )
            result.error_code = rewritten_code
            result.error_message = rewritten_message
            settlement.error = (
                cast(UpstreamError, {"message": rewritten_message, "type": "upstream_error", "code": rewritten_code})
                if terminal_on_error
                else original_upstream_error
            )
            settlement.account_health_error = False
        elif result.transient_error is None:
            result.error_code = raw_error_code
            result.error_message = raw_error_message
            if raw_error_code == "stream_incomplete":
                result.failure_metadata = _RequestLogFailureMetadata(
                    failure_phase="upstream",
                    failure_detail="upstream_eof_before_terminal_event",
                    upstream_error_code=raw_error_code,
                )
            settlement.account_health_error = (
                _facade()._should_penalize_stream_error(raw_error_code) if not saw_text_delta else False
            )
            if terminal_on_error:
                if allow_retry and raw_error_code == "stream_idle_timeout":
                    result.retryable_error = _RetryableStreamError(raw_error_code, upstream_error, exclude_account=True)
                if result.retryable_error is None and allow_retry:
                    security_work_error = _facade()._is_security_work_authorization_required_error(
                        raw_error_code,
                        raw_error_message,
                    )
                else:
                    security_work_error = False
                if security_work_error:
                    result.error_code = _facade()._SECURITY_WORK_AUTHORIZATION_REQUIRED_CODE
                    result.retryable_error = _RetryableStreamError(
                        _facade()._SECURITY_WORK_AUTHORIZATION_REQUIRED_CODE,
                        upstream_error,
                    )
                if (
                    result.retryable_error is None
                    and allow_retry
                    and _facade()._should_retry_stream_error(raw_error_code)
                ):
                    result.retryable_error = _RetryableStreamError(raw_error_code, upstream_error, exclude_account=True)
                if result.retryable_error is None:
                    result.terminal_error = _TerminalStreamError(result.error_code or raw_error_code, upstream_error)
        return result

    if preserve_raw_sse_line:
        raw_error_type, raw_error_message, raw_error_param, raw_error_code = _raw_stream_error_fields(
            event_type,
            event_payload,
        )
        raw_error_code = _raw_stream_error_code_or_upstream(event_type, event_payload, raw_error_code)
        result.error_code = raw_error_code
        result.error_message = raw_error_message
        upstream_error = cast(UpstreamError, {"message": raw_error_message or "Upstream error"})
        settlement.error = upstream_error
        settlement.record_success = False
        result.failure_metadata, retry_response_protection = _note_upstream_stream_error(
            code=raw_error_code,
            message=raw_error_message,
            error_type=raw_error_type,
            param=raw_error_param,
            request_id=request_id,
            account_id=account_id,
            allow_transient_retry=allow_transient_retry,
            downstream_visible=downstream_visible,
            upstream_model_output_seen=upstream_model_output_seen,
        )
        if retry_response_protection:
            settlement.account_health_error = False
            result.transient_error = _TransientStreamError(
                raw_error_code or "internal_error",
                upstream_error,
                preserve_on_selection_exhausted=True,
            )
        elif result.transient_error is None:
            # A preserved raw error line still carries a code the account
            # contract knows: invalid_request_error stays request-log only,
            # while an account-health code such as rate_limit_exceeded keeps
            # penalising the account once nothing has been visible yet.
            settlement.account_health_error = (
                _facade()._should_penalize_stream_error(raw_error_code) if not saw_text_delta else False
            )
    return result
