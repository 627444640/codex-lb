from __future__ import annotations

import json
import os
import secrets
import threading
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from .store import Store


class EmailSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    tls: Literal["ssl", "starttls"]
    sender: str = Field(max_length=254)
    username: str = Field(max_length=254)
    recipients: list[str] = Field(max_length=20)
    password: SecretStr | None = Field(default=None, max_length=1024)

    @field_validator("sender", "username")
    @classmethod
    def clean_address(cls, value):
        value = value.strip()
        if "\n" in value or "\r" in value:
            raise ValueError("Invalid email address")
        return value


class NoticeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=4000)
    level: Literal["info", "maintenance", "warning"] = "info"
    status: Literal["draft", "published", "withdrawn"] = "draft"
    starts_at: AwareDatetime
    ends_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def valid_content(self):
        self.title, self.body = self.title.strip(), self.body.strip()
        if not self.title or not self.body:
            raise ValueError("Empty content")
        if self.ends_at is not None and self.ends_at <= self.starts_at:
            raise ValueError("End must follow start")
        return self

    def stored(self):
        return {
            **self.model_dump(exclude={"starts_at", "ends_at"}),
            "starts_at": self.starts_at.timestamp(),
            "ends_at": self.ends_at.timestamp() if self.ends_at else None,
        }


def iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts is not None else None


def notice_response(row):
    return {**row, **{key: iso(row[key]) for key in ("starts_at", "ends_at", "created_at", "updated_at")}}


def atomic_private(path: Path, text: str):
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(6)}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def initialize_token(store: Store):
    path = store.settings.control_token_file
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as file:
            file.write(secrets.token_urlsafe(48))


class Control:
    def __init__(self, store: Store, config_path: Path | None):
        self.store, self.config_path = store, config_path
        self.lock = threading.Lock()

    def email(self):
        s = self.store.settings.smtp
        password_file = s.get("password_file")
        return {
            "enabled": bool(s.get("enabled")),
            "host": s.get("host", "smtp.163.com"),
            "port": s.get("port", 465),
            "tls": s.get("tls", "ssl"),
            "sender": s.get("sender", ""),
            "username": s.get("username", ""),
            "recipients": s.get("recipients", []),
            "password_configured": bool(password_file and Path(password_file).is_file()),
        }

    def overview(self):
        return {
            "available": True,
            "email": self.email(),
            "notices": [notice_response(n) for n in self.store.notices()],
            "events": [
                {
                    "id": e["id"],
                    "title": e["title"],
                    "created_at": iso(e["created_at"]),
                    "email_status": e["email_status"],
                    "attempts": e["attempts"],
                    "last_error": e["last_error"],
                }
                for e in self.store.events()
            ],
        }

    def update_email(self, request: EmailSettings):
        if self.config_path is None:
            raise ValueError("Configuration persistence unavailable")
        with self.lock:
            cfg = request.model_dump(exclude={"password"})
            existing = self.store.settings.smtp.get("password_file")
            password = request.password.get_secret_value() if request.password else None
            if password:
                # New secret first, then switch the config atomically. Existing credentials
                # remain usable if the configuration write fails.
                secret_path = self.store.settings.state_dir / f"smtp-secret-{secrets.token_hex(8)}.txt"
                atomic_private(secret_path, password)
                cfg["password_file"] = str(secret_path)
            elif existing:
                cfg["password_file"] = existing
            candidate = replace(self.store.settings, smtp=cfg).validate()
            if request.enabled and request.username and not self._secret_available(cfg.get("password_file")):
                raise ValueError("SMTP authorization code is required")
            data = asdict(candidate)
            data["source_db"], data["state_dir"] = str(candidate.source_db), str(candidate.state_dir)
            atomic_private(self.config_path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            self.store.settings = candidate
        return self.email()

    @staticmethod
    def _secret_available(path):
        return bool(
            path and Path(path).is_file() and not Path(path).stat().st_mode & 0o077 and Path(path).stat().st_size
        )
