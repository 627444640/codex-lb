from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal, TypeVar
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.core.exceptions import AppError
from app.modules.status_page.schemas import (
    AnnouncementSaved,
    AnnouncementUpdate,
    EmailConfigurationResponse,
    EmailConfigurationUpdate,
    StatusPageSettingsResponse,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class StatusPageUnavailable(AppError):
    status_code = 503
    code = "status_page_unavailable"
    message = "The status service is not connected or could not complete the request."


class StatusPageControlRejected(AppError):
    status_code = 400
    code = "status_page_configuration_rejected"
    message = "Check the email configuration, authorization code and announcement schedule."


class MonitorConnection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    token_file: Path

    @field_validator("url")
    @classmethod
    def loopback_only(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Control URL must be a literal loopback HTTP origin")
        return value.rstrip("/")

    @field_validator("token_file")
    @classmethod
    def absolute_token_path(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Token path must be absolute")
        return value


class StatusPageService:
    def __init__(self, connection_file: Path) -> None:
        self._connection_file = connection_file

    def _connection(self) -> tuple[MonitorConnection, str]:
        connection = MonitorConnection.model_validate_json(self._connection_file.read_text())
        if self._connection_file.stat().st_mode & 0o077 or connection.token_file.stat().st_mode & 0o077:
            raise ValueError("Connector credentials must be private")
        token = connection.token_file.read_text().strip()
        if len(token) < 32:
            raise ValueError("Invalid service credential")
        return connection, token

    async def _request(
        self,
        method: Literal["GET", "POST", "PUT"],
        path: str,
        response_type: type[ResponseT],
        content: str | None = None,
    ) -> ResponseT:
        try:
            connection, token = await asyncio.to_thread(self._connection)
            async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
                response = await client.request(
                    method,
                    f"{connection.url}{path}",
                    content=content,
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                )
            if response.status_code in {400, 404, 422}:
                raise StatusPageControlRejected()
            response.raise_for_status()
            return response_type.model_validate_json(response.content)
        except (OSError, ValueError, ValidationError, httpx.HTTPError):
            raise StatusPageUnavailable() from None

    async def get_settings(self) -> StatusPageSettingsResponse:
        if not self._connection_file.exists():
            return StatusPageSettingsResponse(available=False)
        return await self._request("GET", "/internal/settings", StatusPageSettingsResponse)

    async def update_email(self, payload: EmailConfigurationUpdate) -> EmailConfigurationResponse:
        wire = payload.model_dump(mode="json", by_alias=False, exclude={"password"})
        wire["password"] = payload.password.get_secret_value() if payload.password else None
        return await self._request("PUT", "/internal/email", EmailConfigurationResponse, json.dumps(wire))

    async def save_announcement(self, payload: AnnouncementUpdate, notice_id: int | None = None) -> AnnouncementSaved:
        return await self._request(
            "POST" if notice_id is None else "PUT",
            "/internal/notices" if notice_id is None else f"/internal/notices/{notice_id}",
            AnnouncementSaved,
            payload.model_dump_json(by_alias=False),
        )
