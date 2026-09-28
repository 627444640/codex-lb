from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "password,api,guest,guest_password,code",
    [
        ("dummy", 1, 0, None, 0),
        ("dummy", 1, 1, None, 0),
        ("dummy", 1, 1, "dummy-guest", 0),
        (None, 1, 1, None, 1),
        ("dummy", 0, 0, None, 1),
    ],
)
def test_cli_reads_policy_without_leaking_credentials(tmp_path, password, api, guest, guest_password, code):
    path = tmp_path / "state.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE dashboard_settings(id INTEGER, password_hash TEXT, api_key_auth_enabled INTEGER, "
            "guest_access_enabled INTEGER, guest_password_hash TEXT)"
        )
        db.execute("INSERT INTO dashboard_settings VALUES (1,?,?,?,?)", (password, api, guest, guest_password))
    before = path.read_bytes()
    env = {
        **os.environ,
        "CODEX_LB_DATABASE_URL": f"sqlite+aiosqlite:///{path}",
        "CODEX_LB_DEPLOYMENT_AUTH_POLICY": "managed",
    }
    process = subprocess.run(
        [sys.executable, "-c", "from app.cli import main; main()", "auth-policy", "check", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == code, process.stderr
    result = json.loads(process.stdout)
    assert result["schemaVersion"] == 1
    assert result["allowed"] is (code == 0)
    assert result["state"]["guest_access_enabled"] is bool(guest)
    assert "dummy" not in process.stdout + process.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("case", ["missing", "corrupt", "postgres", "invalid-mode", "bypass-mode"])
def test_cli_unknown_is_bounded_and_never_creates_or_repairs_database(tmp_path, case):
    path = tmp_path / "state.db"
    if case == "corrupt":
        path.write_bytes(b"not a sqlite database")
    env = {
        **os.environ,
        "CODEX_LB_DATABASE_URL": f"sqlite+aiosqlite:///{path}",
        "CODEX_LB_DEPLOYMENT_AUTH_POLICY": "managed",
    }
    if case == "postgres":
        env["CODEX_LB_DATABASE_URL"] = "postgresql+asyncpg://private:secret@example.invalid/db"
    if case == "invalid-mode":
        env["CODEX_LB_DEPLOYMENT_AUTH_POLICY"] = "private-invalid-setting"
    if case == "bypass-mode":
        env["CODEX_LB_DASHBOARD_AUTH_MODE"] = "disabled"
    process = subprocess.run(
        [sys.executable, "-c", "from app.cli import main; main()", "auth-policy", "check", "--json"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 2
    assert json.loads(process.stdout)["allowed"] is None
    assert "secret" not in process.stdout + process.stderr
    assert "private-invalid-setting" not in process.stdout + process.stderr
    assert list(tmp_path.iterdir()) == ([path] if case == "corrupt" else [])
