from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator

from app.modules.shared.schemas import DashboardModel


class AssistantConfiguration(DashboardModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool = False
    base_url: str = "http://127.0.0.1:2455/v1"
    model: str = Field(
        default="mercury-2.5",
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@-]*$",
        strict=True,
    )
    requests_per_minute: int = Field(default=6, ge=1, le=60, strict=True)
    daily_request_limit: int = Field(default=200, ge=1, le=10000, strict=True)

    @field_validator("base_url")
    @classmethod
    def validate_destination(cls, value: str) -> str:
        value = value.rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path != "/v1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(ch.isspace() or ord(ch) < 32 for ch in value)
            or "\\" in value
        ):
            raise ValueError("Use an HTTP(S) /v1 base URL without credentials or parameters")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("Plain HTTP is allowed only for a local Codex LB")
        _ = parsed.port
        return value


class AssistantConfigurationUpdate(AssistantConfiguration):
    api_key: SecretStr | None = Field(default=None, max_length=2048)
    clear_key: bool = False


class AssistantConfigurationResponse(AssistantConfiguration):
    available: bool = True
    key_configured: bool = False
    daily_requests_used: int = 0


class AssistantConnectionTest(DashboardModel):
    ok: bool
    message: str
