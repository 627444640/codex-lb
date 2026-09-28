"""Small shared primitives; no credentials are read or printed here."""

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
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


def read_policy_state(root):
    try:
        cfg = json.loads((Path(root) / "config/deployment.json").read_text())
        env = os.environ.copy()
        env.update(cfg["backend"].get("environment", {}))
        result = subprocess.run(
            [cfg["backend"]["command"][0], "auth-policy", "check", "--json"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if len(result.stdout) > 16384 or result.returncode not in (0, 1):
            raise ValueError("Policy probe unavailable")
        policy = json.loads(result.stdout)
        if (
            type(policy.get("schemaVersion")) is not int
            or policy["schemaVersion"] != 1
            or policy.get("mode") != "managed"
            or type(policy.get("allowed")) is not bool
            or policy["allowed"] != (result.returncode == 0)
        ):
            raise ValueError("Incompatible policy protocol")
        state = policy["state"]
        if not isinstance(state, dict) or any(
            type(state.get(key)) is not bool
            for key in (
                "password_configured",
                "api_key_auth_enabled",
                "guest_access_enabled",
                "guest_password_configured",
            )
        ):
            raise ValueError("Invalid policy state")
        violations = policy["violations"]
        if (
            not isinstance(violations, list)
            or any(not isinstance(item, str) for item in violations)
            or policy["allowed"] != (not violations)
        ):
            raise ValueError("Invalid policy verdict")
        requirements = policy["requirements"]
        if (
            not isinstance(requirements, dict)
            or requirements.get("mode") != "managed"
            or type(requirements.get("adminPasswordRequired")) is not bool
            or type(requirements.get("apiKeyAuthRequired")) is not bool
            or requirements.get("guestPassword") != "optional"
        ):
            raise ValueError("Invalid policy requirements")
        return policy
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        raise RuntimeError("Cannot establish installed deployment authentication policy") from None


def read_auth_state(root):
    return read_policy_state(root)["state"]


def assert_https_ready(root):
    if not (Path(root) / "state/initialized.json").is_file():
        raise RuntimeError("Initialize dashboard password and API key authentication before exposing HTTPS")
    policy = read_policy_state(root)
    if not policy["allowed"]:
        raise RuntimeError("HTTPS authentication policy: " + ", ".join(policy["violations"]))


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
