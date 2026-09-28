from contextlib import closing
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

BIN = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN))
import common


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("state", "config", "data"):
            (self.root / name).mkdir()
        (self.root / "config/deployment.json").write_text(json.dumps({"data_dir": str(self.root / "data")}))

    def tearDown(self):
        self.temp.cleanup()

    def database(self, password="hash", api=True, guest=False):
        with closing(sqlite3.connect(self.root / "data/store.db")) as db, db:
            db.execute(
                "CREATE TABLE dashboard_settings(id INTEGER, password_hash TEXT, api_key_auth_enabled INTEGER, guest_access_enabled INTEGER)"
            )
            db.execute("INSERT INTO dashboard_settings VALUES(1, ?, ?, ?)", (password, api, guest))

    def test_atomic_failure_preserves_original(self):
        path = self.root / "state/config"
        path.write_text("original")
        with patch("common.os.replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                common.atomic_write(path, "replacement")
        self.assertEqual(path.read_text(), "original")
        self.assertEqual(list(path.parent.iterdir()), [path])

    def test_lock_rejects_second_process_and_releases(self):
        code = "import sys; sys.path.insert(0, sys.argv[1]); from common import operation_lock\nwith operation_lock(sys.argv[2]): pass"
        args = [sys.executable, "-c", code, str(BIN), str(self.root)]
        with common.operation_lock(self.root):
            result = subprocess.run(args, capture_output=True, timeout=5)
            self.assertNotEqual(result.returncode, 0)
        self.assertEqual(subprocess.run(args, capture_output=True, timeout=5).returncode, 0)

    def test_marker_alone_cannot_expose_https(self):
        (self.root / "state/initialized.json").write_text("{}")
        self.database(password=None, api=False)
        with self.assertRaises(RuntimeError):
            common.assert_https_ready(self.root)

    def policy(self, allowed=True, guest=True):
        return {"schemaVersion": 1, "mode": "managed", "allowed": allowed,
                "requirements": {"mode": "managed", "adminPasswordRequired": True,
                                 "apiKeyAuthRequired": True, "guestPassword": "optional"},
                "state": {"password_configured": True, "api_key_auth_enabled": allowed,
                          "guest_access_enabled": guest, "guest_password_configured": False},
                "violations": [] if allowed else ["api_key_auth_required"]}

    def configure_probe(self):
        (self.root / "config/deployment.json").write_text(json.dumps({"backend": {
            "command": ["/test/codex-lb", "--port", "1234"],
            "environment": {"CODEX_LB_DEPLOYMENT_AUTH_POLICY": "managed"}}}))

    def test_guard_accepts_guests_and_uses_backend_environment(self):
        self.configure_probe()
        (self.root / "state/initialized.json").write_text("{}")
        with patch("common.subprocess.run", return_value=Mock(returncode=0, stdout=json.dumps(self.policy()))) as run:
            common.assert_https_ready(self.root)
        self.assertEqual(run.call_args.args[0], ["/test/codex-lb", "auth-policy", "check", "--json"])
        self.assertEqual(run.call_args.kwargs["env"]["CODEX_LB_DEPLOYMENT_AUTH_POLICY"], "managed")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)

    def test_guard_rejects_real_violation(self):
        self.configure_probe()
        (self.root / "state/initialized.json").write_text("{}")
        with patch("common.subprocess.run", return_value=Mock(returncode=1, stdout=json.dumps(self.policy(False)))):
            with self.assertRaisesRegex(RuntimeError, "api_key_auth_required"):
                common.assert_https_ready(self.root)

    def test_unknown_and_incompatible_probe_fail_closed(self):
        self.configure_probe()
        samples = [(2, "{}"), (0, "not json"), (0, "[]"), (0, json.dumps({**self.policy(), "schemaVersion": 2})),
                   (0, json.dumps({**self.policy(), "mode": "standard"})), (0, json.dumps({**self.policy(), "allowed": "true"})),
                   (1, json.dumps(self.policy()))]
        for code, output in samples:
            with self.subTest(code=code, output=output), patch("common.subprocess.run", return_value=Mock(returncode=code, stdout=output)):
                with self.assertRaisesRegex(RuntimeError, "Cannot establish"):
                    common.read_policy_state(self.root)
        with patch("common.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 5)):
            with self.assertRaises(RuntimeError):
                common.read_policy_state(self.root)

    def test_stubborn_child_has_bounded_shutdown(self):
        ready = self.root / "ready"
        child = (
            "import os,signal,time,pathlib; signal.signal(signal.SIGTERM,signal.SIG_IGN); pathlib.Path(%r).write_text(str(os.getpid())); time.sleep(60)"
            % str(ready)
        )
        worker = (
            "import sys,os,logging; sys.path.insert(0,%r); from supervise import run_service; sys.exit(run_service([sys.executable,'-c',%r],%r,os.environ.copy(),logging.getLogger('test'),grace=0.25))"
            % (str(BIN), child, str(self.root))
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", worker], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            started = time.monotonic()
            proc.terminate()
            self.assertEqual(proc.wait(timeout=3), 0)
            self.assertLess(time.monotonic() - started, 2)
            with self.assertRaises(ProcessLookupError):
                os.kill(int(ready.read_text()), 0)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=3)

    def run_supervisor_cli(self, child_code, *, drain_timeout=2):
        (self.root / "logs").mkdir(exist_ok=True)
        (self.root / "config/deployment.json").write_text(
            json.dumps({"backend": {"command": [sys.executable, "-c", child_code]}})
        )
        worker = (
            "import sys; from pathlib import Path; sys.path.insert(0, %r); import supervise; "
            "supervise.ROOT = Path(%r); supervise.LOG_DRAIN_TIMEOUT = %r; "
            "sys.argv = ['supervise.py', 'backend']; sys.exit(supervise.main())"
        ) % (str(BIN), str(self.root), drain_timeout)
        proc = subprocess.Popen(
            [sys.executable, "-c", worker],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=5)
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")
            return proc.returncode, (self.root / "logs/backend.log").read_text()
        finally:
            # Also reap the test descendant that deliberately holds the pipe open.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait(timeout=3)
            proc.stdout.close()
            proc.stderr.close()

    def test_supervisor_cli_retains_burst_tail_and_unterminated_diagnostic(self):
        code = (
            "import sys; "
            "sys.stdout.write(''.join(f'record-{i:04d} ' + 'a'*55 + '\\n' for i in range(1000))); "
            "sys.stdout.write('FATAL: last diagnostic without newline'); sys.stdout.flush(); sys.exit(17)"
        )
        returncode, log = self.run_supervisor_cli(code)
        self.assertEqual(returncode, 17)
        for index in range(1000):
            self.assertEqual(log.count(f"record-{index:04d} "), 1)
        self.assertIn("FATAL: last diagnostic without newline", log)
        self.assertLess(log.index("FATAL:"), log.index("Exited child code=17"))

    def test_supervisor_cli_preserves_redaction_and_oversized_line_limit_at_exit(self):
        code = (
            "import sys; sys.stdout.write('x'*70000 + '\\n'); "
            "sys.stdout.write('Authorization: Bearer private-value\\n'); sys.stdout.flush()"
        )
        returncode, log = self.run_supervisor_cli(code)
        self.assertEqual(returncode, 0)
        self.assertIn("Oversized log line omitted", log)
        self.assertNotIn("private-value", log)
        self.assertIn("Bearer [redacted]", log)

    def test_supervisor_cli_does_not_wait_forever_for_descendant_pipe(self):
        code = (
            "import subprocess, sys; "
            "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
            "print('parent finished', flush=True); sys.exit(17)"
        )
        started = time.monotonic()
        returncode, log = self.run_supervisor_cli(code, drain_timeout=0.25)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(returncode, 17)
        self.assertIn("parent finished", log)
        self.assertIn("Log drain deadline reached", log)


if __name__ == "__main__":
    unittest.main()
