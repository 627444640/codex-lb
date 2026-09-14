#!/usr/bin/env python3
"""Local lifecycle, status and consistent backups. Never prints credentials."""

import argparse
from contextlib import closing, nullcontext
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request

from common import atomic_write, operation_lock, assert_https_ready, read_auth_state

ROOT = Path(__file__).resolve().parents[1]
CFG_PATH = ROOT / "config/deployment.json"
# Load runtime configuration only when executing a command; --help works from
# a source checkout without creating or reading private deployment files.
CFG = {}
DATA = ROOT / "data"
LABELS = {"backend": "com.local.codex-lb", "https": "com.local.codex-lb.caddy"}
DOMAIN = f"gui/{os.getuid()}"
AGENTS = Path.home() / "Library/LaunchAgents"
REQUIRED_TABLES = {"accounts", "api_keys", "dashboard_settings", "alembic_version"}
REQUIRED_FILES = (
    "data/store.db",
    "data/encryption.key",
    "config/deployment.json",
    "config/Caddyfile",
    "bin/manage.py",
    "bin/supervise.py",
    "bin/codex-lbctl",
    "versions.json",
    "runtime/caddy",
    "caddy/pki/authorities/local/root.crt",
    "caddy/pki/authorities/local/root.key",
    "caddy/pki/authorities/local/intermediate.crt",
    "caddy/pki/authorities/local/intermediate.key",
)


def reload_config():
    global CFG, DATA
    CFG = json.loads(CFG_PATH.read_text())
    DATA = Path(CFG["data_dir"])


def command(args, check=True, **kwargs):
    return subprocess.run(args, check=check, capture_output=True, text=True, **kwargs)


def service_details(service, timeout=None):
    raw = command(["/bin/launchctl", "print", f"{DOMAIN}/{LABELS[service]}"], check=False, timeout=timeout)
    if raw.returncode:
        # Other failures (including unavailable GUI domain or EPERM) are unknown.
        if "Could not find service" in (raw.stderr + raw.stdout):
            return {"loaded": False}
        raise RuntimeError(f"Cannot determine {service} LaunchAgent state (exit {raw.returncode})")
    result = {"loaded": True}
    for line in raw.stdout.splitlines():
        stripped = line.strip()
        if (
            line.startswith("\t")
            and not line.startswith("\t\t")
            and stripped.startswith(("state =", "pid =", "last exit code ="))
        ):
            k, v = stripped.split(" = ", 1)
            result[k] = v
    return result


def loaded(service):
    return service_details(service)["loaded"]


def install_agents():
    AGENTS.mkdir(parents=True, exist_ok=True)
    for service, label in LABELS.items():
        content = {
            "Label": label,
            "ProgramArguments": [CFG["manager_python"], str(ROOT / "bin/supervise.py"), service],
            "WorkingDirectory": str(ROOT),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "ExitTimeOut": 45,
            "Umask": 0o077,
            "StandardOutPath": "/dev/null",
            "StandardErrorPath": "/dev/null",
            "EnvironmentVariables": {
                "PATH": os.pathsep.join(
                    (
                        str(Path(CFG["manager_python"]).parent),
                        str(Path.home() / ".local/bin"),
                        "/opt/homebrew/bin",
                        "/usr/local/bin",
                        "/usr/bin",
                        "/bin",
                        "/usr/sbin",
                        "/sbin",
                    )
                ),
                "PYTHONUNBUFFERED": "1",
            },
        }
        target = AGENTS / f"{label}.plist"
        target.write_bytes(plistlib.dumps(content))
        target.chmod(0o600)
    print("User LaunchAgents installed.")


def probe(url, ca=None):
    try:
        context = (
            ssl.create_default_context(cafile=str(ca)) if ca and Path(ca).is_file() else ssl.create_default_context()
        )
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context)
        )
        with opener.open(url, timeout=5) as res:
            # Health output is intentionally not echoed: service bodies may contain details.
            return res.status, "HTTP response"
    except urllib.error.HTTPError as exc:
        return exc.code, "HTTP error"
    except urllib.error.URLError as exc:
        return None, type(exc.reason).__name__
    except Exception as exc:
        return None, type(exc).__name__


def port_state(port, timeout=1):
    """Only an explicit ECONNREFUSED establishes that a TCP listener is absent."""
    try:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            code = sock.connect_ex(("127.0.0.1", port))
    except OSError as exc:
        return {"state": "unknown", "error": type(exc).__name__}
    if code == 0:
        return {"state": "open"}
    if code == errno.ECONNREFUSED:
        return {"state": "closed"}
    return {"state": "unknown", "error": errno.errorcode.get(code, f"errno {code}")}


def wait_ready(service, timeout=45):
    end = time.monotonic() + timeout
    ca = ROOT / "certs/root.crt"
    code, detail = None, "No probe completed"
    while time.monotonic() < end:
        if service == "backend":
            code, detail = probe("http://127.0.0.1:2455/health/ready")
        else:
            source = ROOT / "state/caddy/pki/authorities/local/root.crt"
            if source.is_file() and (not ca.is_file() or source.read_bytes() != ca.read_bytes()):
                ca.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, ca)
                ca.chmod(0o644)
            code, detail = probe("https://localhost:8443/health/ready", ca)
        if code == 200:
            return
        time.sleep(1)
    last = f"HTTP {code}" if code is not None else detail
    hint = "; check Caddy remote_ip allows 127.0.0.1/32 and ::1/128" if service == "https" and code == 403 else ""
    raise RuntimeError(f"{service} did not become ready; last probe: {last}{hint}; inspect bounded logs")


def start(service="all"):
    for item in ["backend", "https"] if service == "all" else [service]:
        if item == "https":
            assert_https_ready(ROOT)
        target = AGENTS / f"{LABELS[item]}.plist"
        if not target.exists():
            install_agents()
        if not loaded(item):
            command(["/bin/launchctl", "bootstrap", DOMAIN, str(target)])
        wait_ready(item)
        print(f"{item}: ready")


def process_group_absent(group: int) -> bool:
    try:
        os.killpg(group, 0)
    except ProcessLookupError:
        return True
    except OSError as exc:
        raise RuntimeError(f"Cannot determine process group {group} state: {type(exc).__name__}") from None
    return False


def stop(service="all", timeout=45):
    errors = []
    for item in ["https", "backend"] if service == "all" else [service]:
        try:
            deadline = time.monotonic() + timeout
            pending = ROOT / f"state/stopping-{item}.json"
            shutdown = (
                json.loads(pending.read_text()) if pending.exists() else {"groups": [], "removal_confirmed": True}
            )
            if (
                not isinstance(shutdown, dict)
                or not isinstance(shutdown.get("groups"), list)
                or any(type(group) is not int or group <= 1 for group in shutdown["groups"])
                or type(shutdown.get("removal_confirmed")) is not bool
            ):
                raise RuntimeError("Invalid pending shutdown record; inspect service processes")
            if not shutdown["removal_confirmed"]:
                raise RuntimeError(
                    f"Prior LaunchAgent removal was not confirmed; inspect job/process state and reconcile {pending}"
                )
            details = service_details(item, timeout=max(0.001, deadline - time.monotonic()))
            if details["loaded"]:
                if "pid" in details:
                    pid = int(details["pid"])
                    if pid <= 1:
                        raise RuntimeError("Invalid LaunchAgent PID")
                    try:
                        group = os.getpgid(pid)
                    except ProcessLookupError:
                        # launchd starts this supervisor as its job's group leader.
                        group = pid
                    if group != pid:
                        raise RuntimeError("LaunchAgent is not in its expected independent process group")
                    if group not in shutdown["groups"]:
                        shutdown["groups"].append(group)
                shutdown["removal_confirmed"] = False
                atomic_write(pending, json.dumps(shutdown) + "\n")
                command(
                    ["/bin/launchctl", "bootout", "--wait", f"{DOMAIN}/{LABELS[item]}"],
                    timeout=max(0.001, deadline - time.monotonic()),
                )
                shutdown["removal_confirmed"] = True
                atomic_write(pending, json.dumps(shutdown) + "\n")
            port = 2455 if item == "backend" else 8443
            while True:
                groups_absent = all(process_group_absent(group) for group in shutdown["groups"])
                state = port_state(port, timeout=max(0.001, min(1, deadline - time.monotonic())))
                if groups_absent and state["state"] == "closed":
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        f"Cannot confirm {item} shutdown: process groups absent={groups_absent}; port {port} is {state['state']} ({state.get('error', 'listener present')})"
                    )
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
            pending.unlink(missing_ok=True)
            print(f"{item}: stopped")
        except Exception as exc:
            errors.append(f"{item}: {exc}")
    if errors:
        raise RuntimeError("; ".join(errors))


def resume_services(active, allow_uninitialized=False):
    errors = []
    for service in LABELS:
        if service not in active:
            continue
        if service == "https" and allow_uninitialized and not (ROOT / "state/initialized.json").is_file():
            print("HTTPS remains stopped: restored backup predates authentication setup.")
            continue
        try:
            start(service)
        except Exception as exc:
            errors.append(f"{service}: {type(exc).__name__}: {exc}")
    if errors:
        raise RuntimeError("Service recovery incomplete: " + "; ".join(errors))


def check_database(db_path):
    if not db_path.is_file() or db_path.is_symlink() or db_path.stat().st_size == 0:
        raise RuntimeError("Required nonempty SQLite database is missing")
    # Read-only mode must never turn a missing database into a new empty database.
    with closing(sqlite3.connect(db_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
        checks = [row[0] for row in db.execute("PRAGMA integrity_check")]
        if checks != ["ok"]:
            raise RuntimeError("Database integrity check failed")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES.issubset(tables):
            raise RuntimeError("Required codex-lb database tables are missing")
        versions = db.execute("SELECT version_num FROM alembic_version").fetchall()
        if not versions or any(not isinstance(row[0], str) or not row[0].strip() for row in versions):
            raise RuntimeError("Database migration version is missing")
    return {"integrity_check": "ok", "bytes": db_path.stat().st_size, "schema": "codex-lb"}


def status():
    result = {"services": {}, "ports": {}, "health": {}, "database": {}, "dashboard": CFG["public_url"]}
    for service in LABELS:
        try:
            result["services"][service] = service_details(service)
        except Exception as exc:
            result["services"][service] = {"loaded": None, "state": "unknown", "error": type(exc).__name__}
    for port in (2455, 8443, 1455, 2019):
        result["ports"][str(port)] = port_state(port)
    for label, url in (
        ("backend_live", "http://127.0.0.1:2455/health/live"),
        ("backend_ready", "http://127.0.0.1:2455/health/ready"),
        ("https_ready", "https://localhost:8443/health/ready"),
    ):
        code, detail = probe(url, ROOT / "certs/root.crt")
        result["health"][label] = {"http": code, "detail": detail}
    try:
        result["database"] = check_database(DATA / "store.db")
    except Exception as exc:
        result["database"] = {"state": "unknown", "error": type(exc).__name__}
    marker = (ROOT / "state/initialized.json").is_file()
    try:
        auth = read_auth_state(ROOT)
        auth = {key: bool(auth[key]) for key in ("password_configured", "api_key_auth_enabled", "guest_access_enabled")}
        result["authentication"] = {"state": "known", **auth}
        allowed = (
            marker and auth["password_configured"] and auth["api_key_auth_enabled"] and not auth["guest_access_enabled"]
        )
    except Exception as exc:
        result["authentication"] = {"state": "unknown", "error": type(exc).__name__}
        allowed = None
    result["readiness"] = {
        "initialized_marker": marker,
        "backend_ready": result["health"]["backend_ready"]["http"] == 200
        if result["health"]["backend_ready"]["http"] is not None
        else None,
        "https_auth_ready": allowed,
        "https_ready": result["health"]["https_ready"]["http"] == 200
        if result["health"]["https_ready"]["http"] is not None
        else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def archive_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def checksum_path(archive):
    return archive.with_suffix(archive.suffix + ".sha256")


def validate_staged(destination):
    manifest = destination / "backup-format.json"
    if manifest.exists():
        metadata = json.loads(manifest.read_text())
        if isinstance(metadata, dict) and metadata.get("format") == "raw-recovery":
            raise RuntimeError("Raw recovery snapshot is unverified material, not a restorable backup")
    for name in REQUIRED_FILES:
        path = destination / name
        if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
            raise RuntimeError(f"Backup required file is missing or empty: {name}")
    check_database(destination / "data/store.db")
    config = json.loads((destination / "config/deployment.json").read_text())
    if not isinstance(config, dict) or not isinstance(config.get("data_dir"), str):
        raise RuntimeError("Backup deployment config is invalid")
    if not Path(config["data_dir"]).is_absolute() or Path(config["data_dir"]).resolve() != DATA.resolve():
        raise RuntimeError("Backup targets a different data directory")
    for key in ("root", "root_dir", "deployment_root"):
        if key in config and (
            not isinstance(config[key], str)
            or not Path(config[key]).is_absolute()
            or Path(config[key]).resolve() != ROOT.resolve()
        ):
            raise RuntimeError("Backup targets a different deployment root")
    if (
        not isinstance(config.get("manager_python"), str)
        or not Path(config["manager_python"]).is_absolute()
        or not isinstance(config.get("public_url"), str)
    ):
        raise RuntimeError("Backup deployment config lacks required runtime settings")
    versions = json.loads((destination / "versions.json").read_text())
    if not isinstance(versions, dict) or not all(
        isinstance(versions.get(key), str) and versions[key].strip() for key in ("codex_lb", "python", "caddy")
    ):
        raise RuntimeError("Backup version manifest is incomplete")
    if not re.fullmatch(r"[0-9][A-Za-z0-9.+_-]{0,127}", versions["codex_lb"]):
        raise RuntimeError("Backup codex-lb version is invalid")
    if not re.fullmatch(r"3\.13\.[0-9]{1,6}", versions["python"]):
        raise RuntimeError("Backup Python version must be an explicit 3.13.x release")
    if manifest.exists():
        if (
            not isinstance(metadata, dict)
            or metadata.get("format") != 2
            or metadata.get("root") != str(ROOT.resolve())
            or metadata.get("data_dir") != str(DATA.resolve())
        ):
            raise RuntimeError("Backup format or deployment location does not match")
        common = destination / "bin/common.py"
        if not common.is_file() or common.is_symlink() or common.stat().st_size == 0:
            raise RuntimeError("Backup format 2 requires bin/common.py")
    return versions


def extract_verified(archive, destination):
    archive = Path(archive)
    checksum = checksum_path(archive)
    if archive.is_symlink() or checksum.is_symlink() or not archive.is_file() or not checksum.is_file():
        raise RuntimeError("Backup archive or checksum is missing or linked")
    expected = checksum.read_text().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or expected != archive_digest(archive):
        raise RuntimeError("Backup checksum missing or mismatched")
    with tarfile.open(archive, "r:gz") as tar:
        seen = set()
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if not member.name or path.is_absolute() or ".." in path.parts or "\\" in member.name or str(path) == ".":
                raise RuntimeError("Unsafe path in backup")
            if not (member.isdir() or member.isfile()) or member.issym() or member.islnk():
                raise RuntimeError("Unexpected links or special files in backup")
            normalized = str(path)
            if normalized in seen:
                raise RuntimeError("Duplicate path in backup")
            seen.add(normalized)
            top = path.parts[0]
            if top not in {
                "data",
                "caddy",
                "runtime",
                "config",
                "bin",
                "versions.json",
                "initialized.json",
                "backup-format.json",
            } and not (len(path.parts) == 1 and path.suffix in {".md", ".command"}):
                raise RuntimeError("Unexpected top-level entry in backup")
        tar.extractall(destination, filter="data")
    return validate_staged(destination)


def verify_backup(archive):
    with tempfile.TemporaryDirectory(prefix="verify-", dir=ROOT / "state") as tmp:
        extract_verified(archive, Path(tmp))
    print("Backup checksum, safe extraction, required files, database schema and integrity: passed")


def completed_archives():
    valid = []
    for path in sorted((ROOT / "backups").glob("codex-lb-*.tar.gz")):
        try:
            with tempfile.TemporaryDirectory(prefix="retention-", dir=ROOT / "state") as tmp:
                extract_verified(path, Path(tmp))
            valid.append(path)
        except (OSError, ValueError, RuntimeError, tarfile.TarError, sqlite3.Error):
            continue
    return valid


def write_snapshot(archive: Path, *, raw_recovery: bool = False) -> Path:
    """Publish a snapshot after the caller has established complete shutdown."""
    archive.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".backup-", dir=archive.parent) as tmp:
        pending = Path(tmp) / archive.name
        with tarfile.open(pending, "w:gz", dereference=False) as tar:
            for path, name in (
                (DATA, "data"),
                (ROOT / "state/caddy", "caddy"),
                (ROOT / "state/runtime", "runtime"),
                (ROOT / "config", "config"),
                (ROOT / "bin", "bin"),
                (ROOT / "state/versions.json", "versions.json"),
                (ROOT / "state/initialized.json", "initialized.json"),
            ):
                if path.exists():
                    tar.add(path, arcname=name)
            for path in sorted(ROOT.iterdir()):
                if path.suffix in {".md", ".command"}:
                    tar.add(path, arcname=path.name)
            metadata = Path(tmp) / "backup-format.json"
            metadata.write_text(
                json.dumps(
                    {
                        "format": "raw-recovery" if raw_recovery else 2,
                        "root": str(ROOT.resolve()),
                        "data_dir": str(DATA.resolve()),
                    }
                )
                + "\n"
            )
            tar.add(metadata, arcname=metadata.name)
        pending.chmod(0o600)
        checksum_path(pending).write_text(archive_digest(pending) + "\n")
        checksum_path(pending).chmod(0o600)
        for path in (pending, checksum_path(pending)):
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        if not raw_recovery:
            with tempfile.TemporaryDirectory(prefix="backup-check-", dir=ROOT / "state") as checked:
                extract_verified(pending, Path(checked))
        # Publish the archive last: a final archive with its checksum is complete.
        os.replace(checksum_path(pending), checksum_path(archive))
        try:
            os.replace(pending, archive)
        except BaseException:
            checksum_path(archive).unlink(missing_ok=True)
            raise
    return archive


def recovery_snapshot() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return write_snapshot(ROOT / "backups/recovery" / f"pre-restore-{stamp}.tar.gz", raw_recovery=True)


def backup():
    active = [service for service in LABELS if loaded(service)]
    backups = ROOT / "backups"
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = backups / f"codex-lb-{stamp}.tar.gz"
    # Stop belongs inside recovery: bootout may stop one service and then fail.
    try:
        stop()
        write_snapshot(archive)
        for old in completed_archives()[:-5]:
            old.unlink()
            checksum_path(old).unlink(missing_ok=True)
    finally:
        resume_services(active)
    print(str(archive))
    return archive


def install_version(version, python_version):
    if not re.fullmatch(r"3\.13\.[0-9]{1,6}", python_version):
        raise RuntimeError("Python version must be an explicit 3.13.x release")
    uv = shutil.which("uv")
    if uv is None:
        raise RuntimeError("uv must be installed and available on PATH before changing application versions")
    command([uv, "tool", "install", "--force", "--python", python_version, f"codex-lb=={version}"])


def prepare_replacements(staged):
    pairs = [
        (staged / source, destination)
        for source, destination in (
            ("data", DATA),
            ("caddy", ROOT / "state/caddy"),
            ("runtime", ROOT / "state/runtime"),
            ("config", ROOT / "config"),
            ("bin", ROOT / "bin"),
            ("versions.json", ROOT / "state/versions.json"),
            ("initialized.json", ROOT / "state/initialized.json"),
        )
    ]
    pairs.append((staged / "caddy/pki/authorities/local/root.crt", ROOT / "certs/root.crt"))
    pairs.extend((path, ROOT / path.name) for path in staged.iterdir() if path.suffix in {".md", ".command"})
    pairs.extend((None, AGENTS / f"{label}.plist") for label in LABELS.values())
    records = []
    try:
        for source, destination in pairs:
            if destination.is_symlink():
                raise RuntimeError(f"Refusing linked restore destination: {destination}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            slot = Path(tempfile.mkdtemp(prefix=f".{destination.name}.restore-", dir=destination.parent))
            record = {"destination": destination, "slot": slot, "saved": False, "installed": False}
            records.append(record)
            if source is not None and source.exists():
                if source.is_dir():
                    shutil.copytree(source, slot / "new")
                else:
                    shutil.copy2(source, slot / "new")
            elif source is None and destination.exists():
                # Preserve original LaunchAgent bytes before install_agents rewrites them.
                shutil.copy2(destination, slot / "new")
        return records
    except BaseException:
        for record in records:
            shutil.rmtree(record["slot"], ignore_errors=True)
        raise


def apply_replacements(records):
    for record in records:
        destination, slot = record["destination"], record["slot"]
        if destination.exists():
            os.replace(destination, slot / "original")
            record["saved"] = True
        # Track absence too: install_agents may create an originally missing plist.
        record["installed"] = True
        if (slot / "new").exists():
            os.replace(slot / "new", destination)


def rollback_replacements(records):
    errors = []
    for record in reversed(records):
        destination, slot = record["destination"], record["slot"]
        try:
            if record["installed"] and destination.exists():
                os.replace(destination, slot / "failed")
            if record["saved"]:
                os.replace(slot / "original", destination)
        except OSError as exc:
            errors.append(f"{destination}: {type(exc).__name__}")
    if errors:
        raise RuntimeError("Rollback file recovery incomplete: " + "; ".join(errors))


def restore(archive):
    active = [service for service in LABELS if loaded(service)]
    current = json.loads((ROOT / "state/versions.json").read_text())
    # Extract before recovery backup/retention so the selected input cannot disappear.
    with tempfile.TemporaryDirectory(prefix="restore-", dir=ROOT / "state") as tmp:
        staged = Path(tmp)
        versions = extract_verified(archive, staged)
        records = prepare_replacements(staged)
        version_attempted = False
        recovery = None
        preserve_slots = False
        try:
            try:
                stop()
                recovery = recovery_snapshot()
                if (current["codex_lb"], current["python"]) != (versions["codex_lb"], versions["python"]):
                    version_attempted = True
                    install_version(versions["codex_lb"], versions["python"])
                apply_replacements(records)
                reload_config()
                install_agents()
                resume_services(active, allow_uninitialized=True)
            except BaseException as original_error:
                modified = version_attempted or any(record["saved"] or record["installed"] for record in records)
                try:
                    if modified:
                        # Startup might partially succeed. Never replace a live database.
                        stop()
                        rollback_replacements(records)
                        if version_attempted:
                            install_version(current["codex_lb"], current["python"])
                        reload_config()
                    resume_services(active)
                except BaseException as recovery_error:
                    preserve_slots = True
                    locations = ", ".join(str(record["slot"]) for record in records)
                    raise RuntimeError(
                        f"Restore failed and automatic recovery is incomplete ({type(recovery_error).__name__}: {recovery_error}). Unverified recovery snapshot: {recovery}. Preserved restore directories: {locations}. Service state must be checked with status."
                    ) from original_error
                raise RuntimeError(
                    f"Restore failed ({type(original_error).__name__}); original files, version and prior service state recovered. Unverified recovery snapshot: {recovery}"
                ) from original_error
        finally:
            if not preserve_slots:
                for record in records:
                    shutil.rmtree(record["slot"], ignore_errors=True)
    print(f"Restore completed. Unverified recovery snapshot: {recovery}. Run status and authenticated smoke tests.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("start", "stop", "restart"):
        sub.add_parser(name).add_argument("service", nargs="?", choices=["all", "backend", "https"], default="all")
    for name in ("status", "backup", "install-agents"):
        sub.add_parser(name)
    for name in ("restore", "verify-backup"):
        sub.add_parser(name).add_argument("archive", type=Path)
    logs = sub.add_parser("logs")
    logs.add_argument("service", nargs="?", choices=["backend", "https"], default="backend")
    logs.add_argument("--lines", type=int, default=60)
    sub.add_parser("uninstall")
    args = parser.parse_args()
    if sys.version_info < (3, 12):
        raise RuntimeError("The maintenance CLI requires Python 3.12 or later")
    mutating = args.action in {"start", "stop", "restart", "backup", "restore", "install-agents", "uninstall"}
    with operation_lock(ROOT) if mutating else nullcontext():
        # Another locked restore may have changed config while this process waited.
        reload_config()
        if args.action in ("start", "stop"):
            globals()[args.action](args.service)
        elif args.action == "restart":
            stop(args.service)
            start(args.service)
        elif args.action == "install-agents":
            install_agents()
        elif args.action == "verify-backup":
            verify_backup(args.archive)
        elif args.action == "restore":
            restore(args.archive)
        elif args.action == "logs":
            log = ROOT / f"logs/{args.service}.log"
            if log.exists():
                print("\n".join(log.read_text(errors="replace").splitlines()[-args.lines :]))
        elif args.action == "uninstall":
            stop()
            for label in LABELS.values():
                (AGENTS / f"{label}.plist").unlink(missing_ok=True)
            print("LaunchAgents removed; application, certificates and data retained.")
        else:
            globals()[args.action]()


if __name__ == "__main__":
    os.umask(0o077)
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"Command failed (exit {exc.returncode}); inspect bounded logs", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
