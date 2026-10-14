"""Public-safe summaries of recorded request outcomes, not root-cause verdicts."""

from __future__ import annotations

from dataclasses import asdict, dataclass

WINDOW_SECONDS = 86400


@dataclass(frozen=True)
class ErrorCategory:
    key: str
    label: str
    guide_slug: str


CATEGORIES = {
    "upstream_processing": ErrorCategory("upstream_processing", "上游通用错误", "error-upstream-processing"),
    "upstream_overload": ErrorCategory("upstream_overload", "上游过载", "error-upstream-overload"),
    "stream_incomplete": ErrorCategory("stream_incomplete", "流式响应中断", "error-stream-incomplete"),
    "continuation": ErrorCategory("continuation", "会话连续性失败", "error-continuation"),
    "upstream_timeout": ErrorCategory("upstream_timeout", "上游请求超时", "error-upstream-timeout"),
    "upstream_transport": ErrorCategory("upstream_transport", "上游连接错误", "error-stream-incomplete"),
    "context_limit": ErrorCategory("context_limit", "上下文超限", "error-context-limit"),
    "client_request": ErrorCategory("client_request", "请求或访问条件不满足", "error-client-request"),
    "interrupted": ErrorCategory("interrupted", "请求中断", "error-stream-incomplete"),
    "other": ErrorCategory("other", "其他错误（待核对）", ""),
}
CODE_CATEGORIES = {
    "server_error": "upstream_processing",
    "server_is_overloaded": "upstream_overload",
    "overloaded_error": "upstream_overload",
    "stream_incomplete": "stream_incomplete",
    "upstream_websocket_liveness_timeout": "stream_incomplete",
    "previous_response_owner_unavailable": "continuation",
    "previous_response_not_found": "continuation",
    "upstream_request_timeout": "upstream_timeout",
    "upstream_error": "upstream_transport",
    "upstream_unavailable": "upstream_transport",
    "context_length_exceeded": "context_limit",
    "invalid_request_error": "client_request",
    "unsupported_value": "client_request",
    "interrupted": "interrupted",
}


@dataclass(frozen=True)
class OutcomeGroup:
    status: str
    error_code: str | None
    model: str
    count: int
    last_at: float | None


@dataclass(frozen=True)
class CategorySummary:
    key: str
    label: str
    guide_slug: str
    guidance: str
    count: int
    failure_share_percent: float
    last_error_at: float | None
    models: tuple[str, ...]


@dataclass(frozen=True)
class RequestQuality:
    window_seconds: int
    window_started_at: float
    window_ended_at: float
    total: int
    successes: int
    cancelled: int
    errors: int
    error_percent: float | None
    last_sample_at: float | None
    last_error_at: float | None
    attention: bool
    categories: tuple[CategorySummary, ...]


def latest_time(values: list[float | None]) -> float | None:
    return max((value for value in values if value is not None), default=None)


def summarize_request_quality(
    groups: list[OutcomeGroup], now: float, min_requests: int, high_error_percent: float
) -> RequestQuality:
    total = sum(group.count for group in groups)
    successes = sum(group.count for group in groups if group.status == "success")
    cancelled = sum(group.count for group in groups if group.status == "cancelled")
    failed = [group for group in groups if group.status not in {"success", "cancelled"}]
    errors = sum(group.count for group in failed)
    error_percent = round(errors / total * 100, 2) if total else None
    categories = []
    for key, category in CATEGORIES.items():
        members = [group for group in failed if CODE_CATEGORIES.get(group.error_code or "", "other") == key]
        if not members:
            continue
        count = sum(group.count for group in members)
        categories.append(
            CategorySummary(
                key=key,
                label=category.label,
                guide_slug=category.guide_slug,
                guidance={
                    "upstream_processing": "短时重试；持续出现时查看上游处理错误说明。",
                    "upstream_overload": "降低并发或稍后重试，观察是否集中在单一模型。",
                    "stream_incomplete": "检查长请求和代理连接稳定性，避免重复提交已产生输出的请求。",
                    "continuation": "开启新会话或携带完整上下文重试，避免跨账号复用旧 response。",
                    "upstream_timeout": "缩短请求上下文并检查上游和代理超时。",
                    "upstream_transport": "检查上游连接和代理链路，确认是否只影响单一路径。",
                    "context_limit": "压缩历史内容或开启新任务，减少携带的上下文。",
                    "client_request": "检查客户端模型、参数和推理级别配置。",
                    "interrupted": "确认客户端是否主动取消，避免把取消误判为上游故障。",
                    "other": "查看独立常见问题页面，确认是否是新的错误类型。",
                }[key],
                count=count,
                failure_share_percent=round(count / errors * 100, 2),
                last_error_at=latest_time([group.last_at for group in members]),
                models=tuple(sorted({group.model for group in members})),
            )
        )
    categories.sort(key=lambda category: (-category.count, category.key))
    return RequestQuality(
        window_seconds=WINDOW_SECONDS,
        window_started_at=now - WINDOW_SECONDS,
        window_ended_at=now,
        total=total,
        successes=successes,
        cancelled=cancelled,
        errors=errors,
        error_percent=error_percent,
        last_sample_at=latest_time([group.last_at for group in groups]),
        last_error_at=latest_time([group.last_at for group in failed]),
        attention=bool(total >= min_requests and error_percent is not None and error_percent >= high_error_percent),
        categories=tuple(categories),
    )


def public_request_quality(quality: RequestQuality) -> dict:
    return asdict(quality)
