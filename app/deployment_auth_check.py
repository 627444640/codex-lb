"""Read a policy snapshot without starting the app or any background work."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config.settings import get_settings
from app.core.deployment_auth_policy import AuthState, DeploymentAuthPolicy


def check_auth_policy() -> int:
    try:
        config = get_settings()
        url = make_url(config.database_url)
        if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:" or url.query:
            raise ValueError("unsupported database")
        path = Path(url.database).resolve(strict=True)
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            db.execute("PRAGMA query_only=ON")
            row = db.execute(
                "SELECT password_hash IS NOT NULL AND length(password_hash)>0, "
                "api_key_auth_enabled, guest_access_enabled, guest_password_hash IS NOT NULL "
                "FROM dashboard_settings WHERE id=1"
            ).fetchone()
        if row is None or any(value not in (0, 1) for value in row):
            raise ValueError("invalid authentication state")
        result = DeploymentAuthPolicy(config.deployment_auth_policy).snapshot(AuthState(*map(bool, row)))
    except Exception:
        # Never print configuration validation errors, database paths or credential values.
        print(json.dumps({"schemaVersion": 1, "allowed": None, "violations": ["policy_state_unknown"]}))
        return 2
    print(json.dumps(result))
    return 0 if result["allowed"] else 1
