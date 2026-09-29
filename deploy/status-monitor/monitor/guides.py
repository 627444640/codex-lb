from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from .store import Store


class GuideContent(BaseModel):
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


class GuideRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1, strict=True)


class GuideRecord(GuideContent):
    id: int
    slug: str
    revision: int
    created_at: AwareDatetime
    updated_at: AwareDatetime
    deleted_at: AwareDatetime | None


class GuideNotFound(Exception):
    pass


class GuideConflict(Exception):
    pass


class GuideRepository:
    def __init__(self, store: Store):
        self.store = store

    def initialize(self, seed_file: Path) -> None:
        with self.store.db() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS troubleshooting_guides (
                id INTEGER PRIMARY KEY, slug TEXT NOT NULL UNIQUE, content TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('draft','published','withdrawn')),
                sort_order INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL, updated_at REAL NOT NULL, deleted_at REAL)""")
            conn.execute("BEGIN IMMEDIATE")
            if conn.execute("SELECT 1 FROM monitor_meta WHERE key='troubleshooting-seed-v1'").fetchone():
                return
            now = time.time()
            for seed in json.loads(seed_file.read_text()):
                slug = seed.pop("slug")
                content = GuideContent.model_validate(seed)
                conn.execute(
                    "INSERT OR IGNORE INTO troubleshooting_guides "
                    "(slug,content,status,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (slug, self._json(content), content.status, content.sort_order, now, now),
                )
            conn.execute("INSERT INTO monitor_meta VALUES ('troubleshooting-seed-v1','done')")

    @staticmethod
    def _json(content: GuideContent) -> str:
        return content.model_dump_json(exclude={"status", "sort_order", "revision"})

    @staticmethod
    def _record(row: sqlite3.Row) -> GuideRecord:
        data = dict(row)
        content = json.loads(data.pop("content"))
        for key in ("created_at", "updated_at", "deleted_at"):
            data[key] = datetime.fromtimestamp(data[key], timezone.utc) if data[key] is not None else None
        return GuideRecord.model_validate({**content, **data})

    def list(self, *, public: bool = False) -> list[GuideRecord]:
        where = "WHERE status='published' AND deleted_at IS NULL" if public else ""
        with self.store.db() as conn:
            rows = conn.execute(f"SELECT * FROM troubleshooting_guides {where} ORDER BY sort_order,id").fetchall()
        return [self._record(row) for row in rows]

    def get(self, guide_id: int) -> GuideRecord:
        with self.store.db() as conn:
            row = conn.execute("SELECT * FROM troubleshooting_guides WHERE id=?", (guide_id,)).fetchone()
        if row is None:
            raise GuideNotFound()
        return self._record(row)

    @staticmethod
    def _missing_or_conflict(conn: sqlite3.Connection, guide_id: int) -> None:
        if conn.execute("SELECT 1 FROM troubleshooting_guides WHERE id=?", (guide_id,)).fetchone() is None:
            raise GuideNotFound()
        raise GuideConflict()

    def save(self, data: GuideWrite, guide_id: int | None = None) -> GuideRecord:
        now = time.time()
        with self.store.db() as conn:
            if guide_id is None:
                if data.revision is not None:
                    raise GuideConflict()
                cursor = conn.execute(
                    "INSERT INTO troubleshooting_guides "
                    "(slug,content,status,sort_order,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                    (f"error-{uuid4().hex[:16]}", self._json(data), data.status, data.sort_order, now, now),
                )
                guide_id = cursor.lastrowid
            else:
                changed = conn.execute(
                    "UPDATE troubleshooting_guides SET content=?,status=?,sort_order=?,"
                    "updated_at=?,revision=revision+1 WHERE id=? AND revision=? AND deleted_at IS NULL",
                    (self._json(data), data.status, data.sort_order, now, guide_id, data.revision),
                ).rowcount
                if not changed:
                    self._missing_or_conflict(conn, guide_id)
            row = conn.execute("SELECT * FROM troubleshooting_guides WHERE id=?", (guide_id,)).fetchone()
            return self._record(row)

    def set_deleted(self, guide_id: int, revision: int, *, restore: bool = False) -> GuideRecord:
        now = time.time()
        condition = "IS NOT NULL" if restore else "IS NULL"
        with self.store.db() as conn:
            changed = conn.execute(
                "UPDATE troubleshooting_guides SET deleted_at=?,status='draft',"
                "updated_at=?,revision=revision+1 WHERE id=? AND revision=? "
                f"AND deleted_at {condition}",
                (None if restore else now, now, guide_id, revision),
            ).rowcount
            if not changed:
                self._missing_or_conflict(conn, guide_id)
            row = conn.execute("SELECT * FROM troubleshooting_guides WHERE id=?", (guide_id,)).fetchone()
            return self._record(row)
