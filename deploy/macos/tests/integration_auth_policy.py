"""Real candidate backend/Caddy policy regression using only temporary state.

No production keys, model requests, LaunchAgents, or system trust modifications.
The isolated runner adds one API-key-protected synthetic stream to test continuity.
"""

import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request


def port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        value = sock.getsockname()[1]
    if value in (1455, 2019, 2455, 8443):
        return port()
    return value


def wait_until(check, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if check():
                return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.15)
    raise AssertionError("Isolated check timed out")


class Client:
    def __init__(self, base, ca=None):
        self.base = base
        handlers = [urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())]
        if ca:
            handlers.append(urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(ca))))
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, path, body=None, method=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Authorization"] = "Bearer " + key
        query = urllib.request.Request(
            self.base + path,
            headers=headers,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            with self.opener.open(query, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)


RUNNER = """import asyncio, os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from fastapi.responses import StreamingResponse
from app.main import app as backend
from app.core.auth.dependencies import validate_proxy_api_key
import uvicorn
@asynccontextmanager
async def lifespan(app):
    async with backend.router.lifespan_context(backend):
        yield
app=FastAPI(lifespan=lifespan)
@app.get('/__policy_test_stream', dependencies=[Depends(validate_proxy_api_key)])
async def stream():
    async def ticks():
        for i in range(600):
            yield f'data: {i}\\n\\n'
            await asyncio.sleep(0.1)
    return StreamingResponse(ticks(), media_type='text/event-stream')
app.mount('/', backend)
uvicorn.run(app, host='127.0.0.1', port=int(os.environ['ISOLATED_BACKEND_PORT']), proxy_headers=False, log_level='error')
"""


def run(backend, caddy):
    processes = []
    report = {}
    with tempfile.TemporaryDirectory(prefix="managed-auth-https-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        for folder in ("data", "state", "logs", "bin", "config"):
            (root / folder).mkdir()
        for script in ("common.py", "supervise.py"):
            shutil.copy2(Path(__file__).resolve().parents[1] / "bin" / script, root / "bin" / script)
        backend_port, https_port = port(), port()
        env = {
            key: value for key, value in os.environ.items() if not key.startswith("CODEX_LB_") and key != "PYTHONPATH"
        }
        env.update(
            {
                "CODEX_LB_DATA_DIR": str(root / "data"),
                "CODEX_LB_DATABASE_URL": "sqlite+aiosqlite:///" + str(root / "data/store.db"),
                "CODEX_LB_ENCRYPTION_KEY_FILE": str(root / "data/encryption.key"),
                "CODEX_LB_DEPLOYMENT_AUTH_POLICY": "managed",
                "CODEX_LB_DASHBOARD_AUTH_MODE": "standard",
                "CODEX_LB_UPSTREAM_BASE_URL": "http://127.0.0.1:9/disabled-upstream",
                "ISOLATED_BACKEND_PORT": str(backend_port),
            }
        )
        for name in (
            "OTEL",
            "MODEL_REGISTRY",
            "USAGE_REFRESH",
            "AUTH_GUARDIAN",
            "RATE_LIMIT_RESET_CREDITS_REFRESH",
            "QUOTA_PLANNER_SCHEDULER",
            "AUTOMATIONS_SCHEDULER",
            "LIVE_USAGE_INGESTION",
            "IMAGE_INLINE_FETCH",
            "LEADER_ELECTION",
            "STICKY_SESSION_CLEANUP",
        ):
            env[f"CODEX_LB_{name}_ENABLED"] = "false"
        runner = root / "runner.py"
        runner.write_text(RUNNER)
        config = root / "config/Caddyfile"
        config.write_text(
            "{\n admin off\n auto_https disable_redirects\n skip_install_trust\n"
            f" storage file_system {{\n root {root / 'caddy'}\n }}\n}}\n"
            f"https://127.0.0.1:{https_port} {{\n bind 127.0.0.1\n tls internal\n"
            f" reverse_proxy 127.0.0.1:{backend_port}\n}}\n"
        )
        deployment = {
            "data_dir": str(root / "data"),
            "backend": {"command": [str(backend)], "environment": env},
            "https": {"command": [str(caddy), "run", "--config", str(config)], "environment": {}},
        }
        (root / "config/deployment.json").write_text(json.dumps(deployment))
        output = (root / "server.log").open("wb")
        try:
            server = subprocess.Popen(
                [str(backend.parent / "python"), str(runner)],
                cwd=root,
                env=env,
                stdout=output,
                stderr=output,
                start_new_session=True,
            )
            processes.append(server)
            admin = Client(f"http://127.0.0.1:{backend_port}")
            wait_until(lambda: admin.request("/health/ready")[0] == 200)
            password = "isolated-https-admin-password"
            assert admin.request("/api/dashboard-auth/password/setup", {"password": password})[0] == 200
            assert admin.request("/api/settings", {"apiKeyAuthEnabled": True}, "PUT")[0] == 200
            code, created = admin.request("/api/api-keys/", {"name": "isolated-stream-test"})
            assert code == 200
            key = created["key"]
            (root / "state/initialized.json").write_text("{}")

            def start_https():
                process = subprocess.Popen(
                    [sys.executable, str(root / "bin/supervise.py"), "https"],
                    cwd=root,
                    env=env,
                    stdout=output,
                    stderr=output,
                    start_new_session=True,
                )
                processes.append(process)
                return process

            supervisor = start_https()
            ca = root / "caddy/pki/authorities/local/root.crt"
            wait_until(ca.exists)
            https = Client(f"https://127.0.0.1:{https_port}", ca)
            wait_until(lambda: https.request("/health/ready")[0] == 200)
            assert https.request("/api/dashboard-auth/password/login", {"password": password})[0] == 200
            stream_response = https.opener.open(
                urllib.request.Request(
                    https.base + "/__policy_test_stream", headers={"Authorization": "Bearer " + key}
                ),
                timeout=30,
            )
            samples, errors = [], []
            stop = threading.Event()

            def read_stream():
                try:
                    while not stop.is_set():
                        line = stream_response.readline()
                        if not line:
                            raise AssertionError("Stream ended during guest changes")
                        if line.startswith(b"data:"):
                            samples.append(time.monotonic())
                except Exception as exc:
                    if not stop.is_set():
                        errors.append(type(exc).__name__)

            reader = threading.Thread(target=read_stream, daemon=True)
            reader.start()
            started = time.monotonic()
            for guest_password in (None, "isolated-guest-one", "isolated-guest-two", None):
                assert https.request("/api/settings", {"guestAccessEnabled": True}, "PUT")[0] == 200
                if guest_password:
                    assert https.request("/api/dashboard-auth/guest/password", {"password": guest_password})[0] == 200
                else:
                    assert https.request("/api/dashboard-auth/guest/password", method="DELETE")[0] == 200
                guest = Client(https.base, ca)
                assert guest.request("/api/dashboard-auth/guest/login", {"password": guest_password})[0] == 200
                assert guest.request("/api/settings")[0] == 200
                assert guest.request("/api/settings", {"guestAccessEnabled": False}, "PUT")[0] == 403
                assert guest.request("/v1/models")[0] == 401
                assert guest.request("/v1/usage", key=key)[0] == 200
                time.sleep(3)
                assert supervisor.poll() is None
            assert https.request("/api/settings", {"guestAccessEnabled": False}, "PUT")[0] == 200
            assert (
                https.request("/api/settings", {"guestAccessEnabled": True, "apiKeyAuthEnabled": False}, "PUT")[0]
                == 409
            )
            assert https.request("/api/dashboard-auth/password", {"password": password}, "DELETE")[0] == 409
            assert len(re.findall("Started child pid=", (root / "logs/https.log").read_text())) == 1
            assert not errors and len(samples) > 50 and samples[-1] - samples[0] >= 10
            report["guest_continuity"] = {
                "seconds": round(time.monotonic() - started, 2),
                "stream_samples": len(samples),
                "proxy_restarts": 0,
            }
            stop.set()
            reader.join(timeout=2)
            stream_response.close()

            for field in ("api_key_auth_enabled", "password_hash"):
                with sqlite3.connect(root / "data/store.db") as db:
                    original = db.execute(f"SELECT {field} FROM dashboard_settings WHERE id=1").fetchone()[0]
                    db.execute(
                        f"UPDATE dashboard_settings SET {field}=? WHERE id=1", (0 if field.startswith("api") else None,)
                    )
                supervisor.wait(timeout=40)
                assert supervisor.returncode == 1
                report[field + "_emergency"] = "passed"
                with sqlite3.connect(root / "data/store.db") as db:
                    db.execute(f"UPDATE dashboard_settings SET {field}=? WHERE id=1", (original,))
                supervisor = start_https()
                wait_until(lambda: https.request("/health/ready")[0] == 200)
            deployment["backend"]["environment"]["CODEX_LB_DATABASE_URL"] = "sqlite+aiosqlite:///" + str(
                root / "missing.db"
            )
            (root / "config/deployment.json").write_text(json.dumps(deployment))
            supervisor.wait(timeout=40)
            assert supervisor.returncode == 1 and not (root / "missing.db").exists()
            report["unreadable_state_emergency"] = "passed"
            return report
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
            output.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", type=Path, required=True)
    parser.add_argument("--caddy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.backend.resolve(), args.caddy.resolve())
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
