from __future__ import annotations

# Individual usage fields are persisted as SQL Integer columns, including on
# PostgreSQL. Invalid or out-of-range evidence is unavailable, never measured 0.
MAX_TOKEN_COUNT = 2_147_483_647


def parse_token_count(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_TOKEN_COUNT:
        return value
    return None


def require_token_count(value: object, *, field_name: str) -> int:
    count = parse_token_count(value)
    if count is None:
        # Do not include upstream values or payloads in an accounting error.
        raise ValueError(f"{field_name} must be a non-negative integer within the supported token range")
    return count
