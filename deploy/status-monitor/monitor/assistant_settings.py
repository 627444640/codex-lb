from __future__ import annotations

import json
import threading
from pathlib import Path

from pydantic import SecretStr, field_validator

from .assistant_schemas import (
    DEFAULT_ASSISTANT_MODEL,
    AssistantConfiguration,
    AssistantConfigurationResponse,
    AssistantConfigurationUpdate,
)
from .control import atomic_private


class AssistantStored(AssistantConfiguration):
    api_key: SecretStr | None = None

    @field_validator("model", mode="before")
    @classmethod
    def migrate_unconfigured_model(cls, value):
        # Older disabled configurations used an empty string before a model was chosen.
        if isinstance(value, str) and not value.strip():
            return DEFAULT_ASSISTANT_MODEL
        return value


class AssistantSettings:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "troubleshooting-assistant.json"
        self.lock = threading.Lock()

    def read(self) -> AssistantStored:
        if not self.path.exists():
            return AssistantStored()
        if self.path.is_symlink() or self.path.stat().st_mode & 0o077:
            raise ValueError("Assistant configuration must be private")
        return AssistantStored.model_validate_json(self.path.read_text())

    def public_admin(self, daily_used: int) -> AssistantConfigurationResponse:
        stored = self.read()
        return AssistantConfigurationResponse(
            **stored.model_dump(exclude={"api_key"}),
            key_configured=bool(stored.api_key and stored.api_key.get_secret_value()),
            daily_requests_used=daily_used,
        )

    def update(self, request: AssistantConfigurationUpdate) -> None:
        with self.lock:
            old = self.read()
            replacement = request.api_key.get_secret_value().strip() if request.api_key else ""
            if request.clear_key and replacement:
                raise ValueError("Do not clear and replace the key together")
            if replacement and (any(ch.isspace() or ord(ch) < 32 for ch in replacement) or len(replacement) < 16):
                raise ValueError("Invalid API key")
            if old.api_key and request.base_url != old.base_url and not replacement and not request.clear_key:
                raise ValueError("A changed destination requires an explicitly supplied key")
            key = (
                None if request.clear_key else replacement or (old.api_key.get_secret_value() if old.api_key else None)
            )
            if request.enabled and (not key or not request.model):
                raise ValueError("An enabled assistant requires a model and API key")
            payload = request.model_dump(exclude={"api_key", "clear_key"})
            payload["api_key"] = key
            AssistantStored.model_validate(payload)
            atomic_private(self.path, json.dumps(payload, ensure_ascii=False) + "\n")
