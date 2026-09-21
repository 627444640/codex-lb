from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

spec = importlib.util.spec_from_file_location(
    "sqlite_recovery_rehearsal", Path(__file__).resolve().parents[2] / "tools/sqlite_recovery_rehearsal.py"
)
assert spec is not None and spec.loader is not None
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


def create_source(tmp_path: Path) -> tuple[Path, Path]:
    db = tmp_path / "source.db"
    key = tmp_path / "key"
    key.write_bytes(Fernet.generate_key())
    encryptor = Fernet(key.read_bytes())
    with sqlite3.connect(db) as connection:
        connection.executescript(
            "CREATE TABLE accounts(access_token_encrypted BLOB,refresh_token_encrypted BLOB,id_token_encrypted BLOB);"
            "CREATE TABLE api_keys(id INTEGER); CREATE TABLE request_logs(id INTEGER);"
            "CREATE TABLE alembic_version(version_num TEXT); INSERT INTO alembic_version VALUES('fixture_revision');"
            "INSERT INTO api_keys VALUES(1); INSERT INTO request_logs VALUES(1);"
        )
        connection.execute("INSERT INTO accounts VALUES(?,?,?)", [encryptor.encrypt(b"fixture-only") for _ in range(3)])
    return db, key


def test_snapshot_restores_credentials_privately_without_modifying_source(tmp_path):
    db, key = create_source(tmp_path)
    before = (hashlib.sha256(db.read_bytes()).digest(), key.read_bytes())
    result = recovery.rehearse(db, key, tmp_path / "run")
    assert result["verified"] is True
    assert result["credential_fields_verified"] == 3
    assert result["upstream_requests"] == 0
    assert result["application_started"] is False
    assert before == (hashlib.sha256(db.read_bytes()).digest(), key.read_bytes())
    assert (tmp_path / "run").stat().st_mode & 0o777 == 0o700
    assert Path(result["archive"]).stat().st_mode & 0o777 == 0o600
    assert (tmp_path / "run/restored/encryption.key").stat().st_mode & 0o777 == 0o600
    assert "fixture-only" not in json.dumps(result)
    assert key.read_text() not in json.dumps(result)


def test_wrong_key_cannot_be_reported_as_verified(tmp_path):
    db, key = create_source(tmp_path)
    key.write_bytes(Fernet.generate_key())
    with pytest.raises(RuntimeError, match="credential verification failed"):
        recovery.rehearse(db, key, tmp_path / "run")
    assert not (tmp_path / "run/result.json").exists()


def test_existing_output_and_archive_traversal_are_rejected(tmp_path):
    db, key = create_source(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        recovery.rehearse(db, key, output)
    archive = tmp_path / "invalid.tar.gz"
    with tarfile.open(archive, "w:gz") as stream:
        stream.add(key, arcname="../escape.key")
    with pytest.raises(RuntimeError, match="Unexpected archive members"):
        recovery.restore_and_verify(archive, tmp_path / "restored")
    assert not (tmp_path / "escape.key").exists()
