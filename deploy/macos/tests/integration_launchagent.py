"""Opt-in real launchd smoke test using only a temporary, uniquely named job.

Run directly with Python 3.12+ on macOS. Production labels, plists, and data
are never used. The temporary job is unloaded and its group reaped on exit.
"""

import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid


def run() -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("This opt-in integration requires macOS launchd")
    source = Path(__file__).resolve().parents[1] / "bin"
    label = "com.local.codex-lb-review-" + uuid.uuid4().hex
    target = f"gui/{os.getuid()}/{label}"
    group = None
    result = {}
    with tempfile.TemporaryDirectory(prefix="codex-lb-launchagent-") as name:
        root = Path(name)
        for directory in ("bin", "config", "state", "logs", "data"):
            (root / directory).mkdir()
        for script in ("manage.py", "supervise.py", "common.py"):
            shutil.copy2(source / script, root / "bin" / script)
        worker = root / "worker.py"
        worker.write_text("""import json, os, pathlib, signal, socket, sys, time
root = pathlib.Path(sys.argv[1])
s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()
ending = False
def stop(*args):
    global ending
    s.close(); ending = True
signal.signal(signal.SIGTERM, stop)
(root / 'ready.json').write_text(json.dumps({'port': s.getsockname()[1]}))
while not ending: time.sleep(0.01)
time.sleep(0.4)
(root / 'final-write').write_text('committed after listener closed')
print('FINAL temporary service diagnostic', flush=True)
""")
        (root / "config/deployment.json").write_text(
            json.dumps(
                {
                    "data_dir": str(root / "data"),
                    "manager_python": sys.executable,
                    "backend": {"command": [sys.executable, str(worker), str(root)]},
                }
            )
        )
        plist = root / "temporary.plist"
        plist.write_bytes(
            plistlib.dumps(
                {
                    "Label": label,
                    "ProgramArguments": [sys.executable, str(root / "bin/supervise.py"), "backend"],
                    "RunAtLoad": True,
                    "KeepAlive": True,
                    "ExitTimeOut": 10,
                    "StandardOutPath": "/dev/null",
                    "StandardErrorPath": "/dev/null",
                }
            )
        )
        sys.path.insert(0, str(root / "bin"))
        try:
            spec = importlib.util.spec_from_file_location("temporary_manage", root / "bin/manage.py")
            manage = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(manage)
            manage.LABELS = {"backend": label}
            subprocess.run(
                ["/bin/launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)],
                check=True,
                capture_output=True,
                timeout=10,
            )
            deadline = time.monotonic() + 10
            while not (root / "ready.json").exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Temporary LaunchAgent did not become ready")
                time.sleep(0.05)
            details = manage.service_details("backend", timeout=2)
            group = os.getpgid(int(details["pid"]))
            port = json.loads((root / "ready.json").read_text())["port"]
            probe = manage.port_state
            manage.port_state = lambda _, **kwargs: probe(port, **kwargs)
            started = time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()):
                manage.stop("backend", timeout=10)
            result = {
                "complete_stop_seconds": round(time.monotonic() - started, 3),
                "final_write_before_stop_return": (root / "final-write").exists(),
                "process_group_absent": manage.process_group_absent(group),
                "job_unloaded": not manage.service_details("backend", timeout=2)["loaded"],
                "final_log_retained": "FINAL temporary service diagnostic" in (root / "logs/backend.log").read_text(),
                "pending_stop_record_cleared": not (root / "state/stopping-backend.json").exists(),
            }
            assert all(value is True for key, value in result.items() if key != "complete_stop_seconds"), result
            group = None
        finally:
            try:
                subprocess.run(
                    ["/bin/launchctl", "bootout", "--wait", target], check=False, capture_output=True, timeout=10
                )
            finally:
                if group is not None:
                    try:
                        os.killpg(group, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                sys.path.remove(str(root / "bin"))
    result["temporary_directory_removed"] = not root.exists()
    result["scope"] = "One randomly named temporary LaunchAgent; no production labels, plists, or data touched"
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
