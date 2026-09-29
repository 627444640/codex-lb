from __future__ import annotations

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, ConfigDict, Field, field_validator

from app.modules.shared.schemas import DashboardModel


class GuideContent(DashboardModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    code: str = Field(min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=100)
    signature: str = Field(default="", max_length=160)
    scope: str = Field(min_length=1, max_length=1000)
    cause: str = Field(min_length=1, max_length=3000)
    solutions: list[Annotated[str, Field(min_length=1, max_length=1000)]] = Field(min_length=1, max_length=12)
    limitations: str = Field(default="", max_length=2000)
    endpoint_url: str = Field(default="", max_length=2048)
    endpoint_label: str = Field(default="API 基地址", max_length=80)
    endpoint_help: str = Field(default="", max_length=1000)
    status: Literal["draft", "published", "withdrawn"] = "draft"
    sort_order: int = Field(default=100, ge=0, le=1000000, strict=True)

    @field_validator("endpoint_url")
    @classmethod
    def safe_address(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or any(ch.isspace() or ord(ch) < 32 for ch in value)
            or "\\" in value
        ):
            raise ValueError("Use an HTTP(S) address without embedded credentials")
        _ = parsed.port
        return value


class GuideWrite(GuideContent):
    revision: int | None = Field(default=None, ge=1, strict=True)


class GuideRevision(DashboardModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)


class GuideRecord(GuideContent):
    id: int
    slug: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None


class GuideListResponse(DashboardModel):
    available: bool
    guides: list[GuideRecord] = Field(default_factory=list)
