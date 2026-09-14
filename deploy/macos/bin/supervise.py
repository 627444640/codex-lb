#!/usr/bin/env python3
"""Foreground service runner with bounded shutdown and redacted rotating logs."""

import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time

from common import assert_https_ready, redact

ROOT = Path(__file__).resolve().parents[1]
LOG_DRAIN_TIMEOUT = 2


def run_service(command, cwd, env, logger, guard=None, grace=30):
    child = None
    stopping_at = None
    guard_failed = False
    exited_at = None
    previous_handlers = {}

    def stop(signum=None, frame=None):
        nonlocal stopping_at
        if stopping_at is None:
            stopping_at = time.monotonic()
        if child is not None and child.poll() is None:
            try:
                child.terminate()
            except ProcessLookupError:
                pass

    for sig in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[sig] = signal.signal(sig, stop)
    selector = selectors.DefaultSelector()
    pending = b""
    discarding = False
    try:
        if guard:
            guard()
        # Stay in launchd's job process group. launchd can reap descendants even
        # if the supervisor itself dies; do not detach the child into a session.
        child = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=False
        )
        logger.info("Started child pid=%s", child.pid)
        os.set_blocking(child.stdout.fileno(), False)
        selector.register(child.stdout, selectors.EVENT_READ)
        next_guard = time.monotonic() + 5
        while True:
            now = time.monotonic()
            if stopping_at is not None:
                if child.poll() is None and now - stopping_at >= grace:
                    logger.warning("Shutdown deadline reached; killing child")
                    child.kill()
                    child.wait(timeout=5)
            elif guard and child.poll() is None and now >= next_guard:
                next_guard = now + 5
                try:
                    guard()
                except Exception as exc:
                    logger.error("HTTPS authentication guard: %s", redact(str(exc)))
                    guard_failed = True
                    stop()
            select_timeout = 0.2 if exited_at is None else max(0, min(0.2, exited_at + LOG_DRAIN_TIMEOUT - now))
            for key, _ in selector.select(timeout=select_timeout):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                for fragment in chunk.splitlines(keepends=True):
                    ended = fragment.endswith(b"\n")
                    if not discarding:
                        pending += fragment
                        if len(pending) > 65536:
                            logger.warning("Oversized log line omitted")
                            pending = b""
                            discarding = True
                    if ended:
                        if not discarding:
                            logger.info("%s", redact(pending.decode(errors="replace").rstrip()))
                        pending = b""
                        discarding = False
            if child.poll() is not None:
                if exited_at is None:
                    exited_at = time.monotonic()
                if selector.get_map():
                    if time.monotonic() - exited_at < LOG_DRAIN_TIMEOUT:
                        continue
                    logger.warning("Log drain deadline reached; remaining child output may be incomplete")
                if pending:
                    logger.info("%s", redact(pending.decode(errors="replace").rstrip()))
                logger.info("Exited child code=%s", child.returncode)
                return 1 if guard_failed else (0 if stopping_at is not None else child.returncode)
    finally:
        selector.close()
        if child is not None:
            if child.poll() is None:
                stop()
                try:
                    child.wait(timeout=grace)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
            child.stdout.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def main():
    os.umask(0o077)
    if len(sys.argv) != 2 or sys.argv[1] not in ("backend", "https"):
        raise SystemExit("Expected backend or https")
    service = sys.argv[1]
    cfg = json.loads((ROOT / "config/deployment.json").read_text())
    logger = logging.getLogger(service)
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(ROOT / f"logs/{service}.log", maxBytes=10 * 1024 * 1024, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    logger.addHandler(handler)
    os.chmod(ROOT / f"logs/{service}.log", 0o600)
    env = os.environ.copy()
    env.update(cfg[service].get("environment", {}))
    try:
        return run_service(
            cfg[service]["command"],
            ROOT,
            env,
            logger,
            guard=(lambda: assert_https_ready(ROOT)) if service == "https" else None,
        )
    except Exception as exc:
        logger.error("%s: %s", type(exc).__name__, redact(str(exc)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
