from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, ConfigDict, Field, SecretStr, model_validator

from app.modules.shared.schemas import DashboardModel


class EmailConfiguration(DashboardModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    tls: Literal["ssl", "starttls"]
    sender: str = Field(max_length=254)
    username: str = Field(max_length=254)
    recipients: list[str] = Field(max_length=20)


class EmailConfigurationResponse(EmailConfiguration):
    password_configured: bool


class EmailConfigurationUpdate(EmailConfiguration):
    password: SecretStr | None = Field(default=None, max_length=1024)


class AnnouncementUpdate(DashboardModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=4000)
    level: Literal["info", "maintenance", "warning"] = "info"
    status: Literal["draft", "published", "withdrawn"] = "draft"
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> AnnouncementUpdate:
        self.title, self.body = self.title.strip(), self.body.strip()
        if not self.title or not self.body:
            raise ValueError("Title and body cannot be blank")
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("End must follow start")
        return self


class AnnouncementResponse(AnnouncementUpdate):
    id: int
    created_at: AwareDatetime
    updated_at: AwareDatetime


class AnnouncementSaved(DashboardModel):
    id: int


class NotificationEvent(DashboardModel):
    id: int
    title: str
    created_at: AwareDatetime
    email_status: Literal["disabled", "pending", "retry", "failed", "sent", "superseded"]
    attempts: int
    last_error: str | None


class StatusPageSettingsResponse(DashboardModel):
    available: bool
    email: EmailConfigurationResponse | None = None
    notices: list[AnnouncementResponse] = Field(default_factory=list)
    events: list[NotificationEvent] = Field(default_factory=list)
