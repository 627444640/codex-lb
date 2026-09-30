from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    source_db: Path
    state_dir: Path
    origin: str = "http://127.0.0.1:2466"
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)
    title: str = "Codex LB"
    poll_seconds: int = 60
    stale_seconds: int = 900
    request_window_seconds: int = 900
    alert_failures: int = 3
    alert_recoveries: int = 2
    low_quota_percent: float = 20
    high_error_percent: float = 10
    min_requests: int = 10
    retention_days: int = 90
    checks: tuple[dict, ...] = field(
        default_factory=lambda: (
            {"id": "gateway", "name": "负载均衡服务", "url": "http://127.0.0.1:2455/health/ready"},
        )
    )
    smtp: dict = field(default_factory=dict)

    @property
    def control_token_file(self):
        return self.state_dir / "control-token.txt"

    @property
    def secure_cookie(self):
        return self.origin.startswith("https://")

    @property
    def state_db(self):
        return self.state_dir / "monitor.db"

    @property
    def smtp_ready(self):
        s = self.smtp
        return bool(
            s.get("enabled")
            and s.get("host")
            and s.get("sender")
            and s.get("recipients")
            and (not s.get("username") or s.get("password_file"))
        )

    def validate(self):
        if self.source_db.resolve() == self.state_db.resolve():
            raise ValueError("Source and monitor databases must be separate")
        if self.source_db.resolve().parent == self.state_dir.resolve():
            raise ValueError("Monitor state must be outside the source data directory")
        u = urlsplit(self.origin)
        if u.scheme not in {"http", "https"} or not u.hostname or u.path not in {"", "/"}:
            raise ValueError("Origin must be an HTTP(S) origin without a path")
        if u.username or u.password or u.query or u.fragment:
            raise ValueError("Origin must not contain credentials or parameters")
        if u.scheme == "http" and u.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Non-local deployment requires HTTPS")
        if not isinstance(self.allowed_hosts, (tuple, list)):
            raise ValueError("Allowed hosts must be a list")
        for host in self.allowed_hosts:
            if not isinstance(host, str) or not host or host != host.strip():
                raise ValueError("Allowed hosts must contain trimmed host names")
            try:
                ip_address(host)
            except ValueError:
                if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host):
                    raise ValueError("Invalid allowed host") from None
        if not 10 <= self.poll_seconds <= 3600 or not 60 <= self.stale_seconds <= 86400:
            raise ValueError("Invalid monitoring interval")
        if not 60 <= self.request_window_seconds <= 3600 or not 1 <= self.retention_days <= 365:
            raise ValueError("Invalid monitoring window or retention")
        if not 1 <= self.alert_failures <= 20 or not 1 <= self.alert_recoveries <= 20:
            raise ValueError("Invalid alert debounce")
        if not 0 < self.low_quota_percent < 100 or not 0 < self.high_error_percent < 100:
            raise ValueError("Invalid alert threshold")
        if self.min_requests < 1:
            raise ValueError("Invalid minimum requests")
        ids = set()
        for check in self.checks:
            cu = urlsplit(check["url"])
            if cu.scheme not in {"http", "https"} or not cu.hostname or cu.username or cu.password:
                raise ValueError("Invalid health check URL")
            if check["id"] in ids or check["id"] in {"source", "quota", "requests"}:
                raise ValueError("Duplicate or reserved health check ID")
            ids.add(check["id"])
        if self.smtp.get("enabled"):
            if not self.smtp_ready or self.smtp.get("tls", "starttls") not in {"starttls", "ssl"}:
                raise ValueError("SMTP requires recipients, sender, host and TLS")
            for address in [self.smtp["sender"], *self.smtp["recipients"]]:
                if not isinstance(address, str) or "@" not in address or "\n" in address or "\r" in address:
                    raise ValueError("Invalid email address")
        return self


def load_settings(path: Path):
    data = json.loads(path.read_text())
    base = path.resolve().parent
    for key in ("source_db", "state_dir"):
        p = Path(data[key]).expanduser()
        data[key] = p if p.is_absolute() else base / p
    if "checks" in data:
        data["checks"] = tuple(data["checks"])
    if "allowed_hosts" in data:
        data["allowed_hosts"] = tuple(data["allowed_hosts"])
    if data.get("smtp", {}).get("password_file"):
        p = Path(data["smtp"]["password_file"]).expanduser()
        data["smtp"]["password_file"] = str(p if p.is_absolute() else base / p)
    return Settings(**data).validate()
