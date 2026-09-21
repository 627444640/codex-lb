#!/usr/bin/env python3
"""Private SQLite/key snapshot and offline restore; no application imports or network."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MEMBERS = frozenset({"store.db", "encryption.key", "manifest.json"})


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    connection.execute("PRAGMA query_only=ON")
    return connection


def inspect_snapshot(database: Path, key_path: Path) -> dict:
    key = key_path.read_bytes()
    encryptor = Fernet(key)
    with closing(readonly(database)) as connection:
        integrity = [row[0] for row in connection.execute("PRAGMA integrity_check")]
        if integrity != ["ok"]:
            raise RuntimeError("Snapshot database integrity check failed")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"accounts", "api_keys", "request_logs", "alembic_version"}.issubset(tables):
            raise RuntimeError("Snapshot is missing required tables")
        checked = 0
        accounts = 0
        for row in connection.execute(
            "SELECT access_token_encrypted,refresh_token_encrypted,id_token_encrypted FROM accounts"
        ):
            accounts += 1
            for encrypted in row:
                try:
                    plaintext = encryptor.decrypt(bytes(encrypted))
                    if not plaintext:
                        raise RuntimeError("Snapshot contains an empty credential")
                    del plaintext
                except (InvalidToken, TypeError, ValueError):
                    raise RuntimeError("Snapshot credential verification failed") from None
                checked += 1
        return {
            "integrity_check": "ok",
            "schema_heads": [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")],
            "accounts": accounts,
            "api_keys": connection.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0],
            "request_logs": connection.execute("SELECT COUNT(*) FROM request_logs").fetchone()[0],
            "credential_fields_verified": checked,
        }


def restore_and_verify(archive_path: Path, destination: Path) -> dict:
    destination.mkdir(mode=0o700)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != len(MEMBERS) or {member.name for member in members} != MEMBERS:
            raise RuntimeError("Unexpected archive members")
        if any(not member.isfile() for member in members):
            raise RuntimeError("Archive contains a non-regular file")
        for member in members:
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError("Archive member cannot be read")
            target = destination / member.name
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with extracted, os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(extracted, output)
    manifest = json.loads((destination / "manifest.json").read_text())
    for name in ["store.db", "encryption.key"]:
        if digest(destination / name) != manifest["sha256"][name]:
            raise RuntimeError("Restored file checksum mismatch")
    result = inspect_snapshot(destination / "store.db", destination / "encryption.key")
    if result != manifest["snapshot"]:
        raise RuntimeError("Restored snapshot metadata mismatch")
    return result


def rehearse(source_database: Path, source_key: Path, output: Path) -> dict:
    if not source_database.is_file() or not source_key.is_file():
        raise RuntimeError("Existing database and key files are required")
    if source_database.is_symlink() or source_key.is_symlink():
        raise RuntimeError("Source files must not be symlinks")
    if output.exists():
        raise RuntimeError("Output run already exists; refusing to overwrite")
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    stage = output / "snapshot"
    stage.mkdir(mode=0o700)
    key_before = digest(source_key)
    descriptor = os.open(stage / "encryption.key", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(source_key.read_bytes())
    database = stage / "store.db"
    descriptor = os.open(database, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    source = readonly(source_database)
    target = sqlite3.connect(database)
    try:
        source.backup(target, pages=1024, sleep=0.01)
    finally:
        target.close()
        source.close()
    if key_before != digest(source_key) or key_before != digest(stage / "encryption.key"):
        raise RuntimeError("Encryption key changed while snapshot was captured")
    snapshot = inspect_snapshot(database, stage / "encryption.key")
    manifest = {
        "format": "codex-lb-sqlite-key-snapshot-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sha256": {name: digest(stage / name) for name in ["store.db", "encryption.key"]},
        "snapshot": snapshot,
        "scope": "database and encryption key only; not a whole-service restore archive",
    }
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    os.chmod(stage / "manifest.json", 0o600)
    archive_path = output / "sqlite-key-snapshot.tar.gz"
    descriptor = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as raw, tarfile.open(fileobj=raw, mode="w:gz") as archive:
        for name in sorted(MEMBERS):
            archive.add(stage / name, arcname=name, recursive=False)
    restored = restore_and_verify(archive_path, output / "restored")
    result = {
        "verified": True,
        "scope": "offline SQLite and encryption-key restoration",
        "created_at": manifest["created_at"],
        "archive": str(archive_path),
        "restored_directory": str(output / "restored"),
        "archive_sha256": digest(archive_path),
        "source_key_unchanged": digest(source_key) == key_before,
        "upstream_requests": 0,
        "application_started": False,
        **restored,
    }
    if not result["source_key_unchanged"]:
        raise RuntimeError("Source encryption key changed before rehearsal completed")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    os.chmod(output / "result.json", 0o600)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-database", type=Path, required=True)
    parser.add_argument("--source-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    previous_umask = os.umask(0o077)
    try:
        result = rehearse(args.source_database, args.source_key, args.output)
    except Exception as error:
        # Exception types are enough for private-file failures; do not render
        # arbitrary library exception values that might include credentials.
        print(json.dumps({"verified": False, "error_type": type(error).__name__}))
        raise SystemExit(1) from None
    finally:
        os.umask(previous_umask)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
