"""Small shared primitives; no credentials are read or printed here."""

from contextlib import closing, contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile


def atomic_write(path, content, mode=0o600):
    path = Path(path)
    data = content.encode() if isinstance(content, str) else content
    fd, name = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def operation_lock(root):
    """Never unlink the lock inode: other processes may already be waiting on it."""
    path = Path(root) / "state/operation.lock"
    with path.open("a+b") as stream:
        os.fchmod(stream.fileno(), 0o600)
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another management operation is running; retry when it finishes") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_auth_state(root):
    cfg = json.loads((Path(root) / "config/deployment.json").read_text())
    db_path = Path(cfg["data_dir"]) / "store.db"
    if not db_path.is_file():
        raise RuntimeError("Backend database is missing")
    try:
        with closing(sqlite3.connect(db_path.as_uri() + "?mode=ro", uri=True, timeout=2)) as db:
            row = db.execute(
                "SELECT password_hash IS NOT NULL AND length(password_hash) > 0, "
                "api_key_auth_enabled, guest_access_enabled "
                "FROM dashboard_settings WHERE id = 1"
            ).fetchone()
    except sqlite3.Error as exc:
        raise RuntimeError("Cannot establish database authentication state: " + type(exc).__name__) from None
    if row is None:
        raise RuntimeError("Dashboard settings are not initialized")
    return dict(zip(("password_configured", "api_key_auth_enabled", "guest_access_enabled"), map(bool, row)))


def assert_https_ready(root):
    if not (Path(root) / "state/initialized.json").is_file():
        raise RuntimeError("Initialize dashboard password and API key authentication before exposing HTTPS")
    state = read_auth_state(root)
    if not state["password_configured"] or not state["api_key_auth_enabled"] or state["guest_access_enabled"]:
        raise RuntimeError(
            "HTTPS requires an actual dashboard password, API key auth enabled and guest access disabled"
        )


def redact(line):
    if re.fullmatch(r"\s*[A-Za-z0-9_-]{32,}\s*", line):
        return "[redacted secret]"
    line = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted-key]", line)
    line = re.sub(r"eyJ[A-Za-z0-9_.-]{25,}", "[redacted-token]", line)
    line = re.sub(r"(?i)([?&](?:code|state|access_token|refresh_token|api_key|key)=)[^&\s\"]+", r"\1[redacted]", line)
    line = re.sub(r"(?i)(Bearer\s+)\S+", r"\1[redacted]", line)
    if "bootstrap token" in line.lower():
        return "Dashboard bootstrap token generated; initialize from localhost."
    return line
