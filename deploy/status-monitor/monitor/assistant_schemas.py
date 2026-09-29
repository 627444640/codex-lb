from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

DEFAULT_ASSISTANT_MODEL = "mercury-2.5"


class AssistantConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool = False
    base_url: str = "http://127.0.0.1:2455/v1"
    model: str = Field(
        default=DEFAULT_ASSISTANT_MODEL,
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


class AssistantConnectionTest(BaseModel):
    ok: bool
    message: str


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=6000)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=4)
    stream: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def bounded_history(self):
        if sum(len(message.content) for message in self.history) > 12000:
            raise ValueError("Conversation history is too long")
        return self


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=6000)
    source_ids: list[Annotated[int, Field(strict=True, ge=1)]] = Field(max_length=3)


class ChatSource(BaseModel):
    title: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource] = Field(default_factory=list)
    model_used: bool
