from contextlib import closing

"""Targeted lifecycle/backup regressions; all files and service calls are isolated."""

import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import types
import unittest
import threading
from unittest.mock import Mock, patch


MANAGE = Path(__file__).with_name("manage.py")
if not MANAGE.exists():
    MANAGE = Path(__file__).resolve().parents[1] / "bin/manage.py"
stub_common = types.ModuleType("common")
stub_common.atomic_write = lambda path, content: path.write_text(content)
stub_common.operation_lock = Mock()
stub_common.assert_https_ready = Mock()
stub_common.read_auth_state = Mock()
spec = importlib.util.spec_from_file_location("isolated_manage", MANAGE)
manage = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"common": stub_common}):
    spec.loader.exec_module(manage)


class ManageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="manage-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "service"
        self.root.mkdir()
        self.data = Path(self.tmp.name) / "data"
        self.cfg = {
            "data_dir": str(self.data),
            "manager_python": "/usr/bin/python3",
            "public_url": "https://localhost:8443",
        }
        for name in ("state", "backups", "certs", "agents", "config"):
            (self.root / name).mkdir()
        (self.root / "config/deployment.json").write_text(json.dumps(self.cfg))
        patches = patch.multiple(
            manage,
            ROOT=self.root,
            CFG_PATH=self.root / "config/deployment.json",
            DATA=self.data,
            CFG=self.cfg.copy(),
            AGENTS=self.root / "agents",
        )
        patches.start()
        self.addCleanup(patches.stop)
        self.output = patch("sys.stdout", new_callable=io.StringIO)
        self.output.start()
        self.addCleanup(self.output.stop)

    def payload(self, directory, *, version="1.24.0", text="original"):
        for name in manage.REQUIRED_FILES:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name != "data/store.db":
                target.write_text(text)
        (directory / "config/deployment.json").write_text(json.dumps(self.cfg))
        (directory / "versions.json").write_text(
            json.dumps({"codex_lb": version, "python": "3.13.15", "caddy": "2.11.4"})
        )
        with closing(sqlite3.connect(directory / "data/store.db")) as db, db:
            for table in ("accounts", "api_keys", "dashboard_settings"):
                db.execute(f"CREATE TABLE {table} (id INTEGER)")
            db.execute("CREATE TABLE alembic_version (version_num TEXT)")
            db.execute("INSERT INTO alembic_version VALUES ('migration1')")
        (directory / "initialized.json").write_text("{}")
        (directory / "bin/common.py").write_text(text)

    def make_archive(self, payload, name="test.tar.gz"):
        archive = self.root / "backups" / name
        with tarfile.open(archive, "w:gz") as tar:
            for path in payload.iterdir():
                tar.add(path, arcname=path.name)
        manage.checksum_path(archive).write_text(manage.archive_digest(archive) + "\n")
        return archive

    def install_live(self, payload):
        import shutil

        for source, dest in (
            ("data", self.data),
            ("bin", self.root / "bin"),
            ("config", self.root / "config"),
            ("runtime", self.root / "state/runtime"),
            ("caddy", self.root / "state/caddy"),
        ):
            shutil.copytree(payload / source, dest, dirs_exist_ok=True)
        for name in ("versions.json", "initialized.json"):
            shutil.copy2(payload / name, self.root / "state" / name)

    def test_readiness_failure_reports_safe_http_or_transport_detail(self):
        for response, message in (
            ((403, "HTTP error"), "HTTP 403.*::1/128"),
            ((None, "SSLCertVerificationError"), "SSLCertVerificationError"),
        ):
            with (
                self.subTest(response=response),
                patch.object(manage, "probe", return_value=response),
                patch.object(manage.time, "monotonic", side_effect=[0, 0, 2]),
                patch.object(manage.time, "sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, message):
                    manage.wait_ready("https", timeout=1)

    def test_readiness_retries_temporary_unavailability(self):
        with (
            patch.object(manage, "probe", side_effect=[(503, "HTTP error"), (200, "HTTP response")]),
            patch.object(manage.time, "monotonic", side_effect=[0, 0, 0.5]),
            patch.object(manage.time, "sleep"),
        ):
            manage.wait_ready("backend", timeout=1)

    def test_zero_readiness_timeout_has_defined_diagnostic(self):
        with patch.object(manage.time, "monotonic", return_value=0):
            with self.assertRaisesRegex(RuntimeError, "No probe completed"):
                manage.wait_ready("https", timeout=0)

    def test_port_states_refused_is_only_closed(self):
        sock = Mock()
        sock.__enter__ = Mock(return_value=sock)
        sock.__exit__ = Mock(return_value=False)
        with patch.object(manage.socket, "socket", return_value=sock):
            for code, state in (
                (0, "open"),
                (errno.ECONNREFUSED, "closed"),
                (errno.EPERM, "unknown"),
                (errno.ETIMEDOUT, "unknown"),
            ):
                sock.connect_ex.return_value = code
                self.assertEqual(manage.port_state(2455)["state"], state)
            sock.connect_ex.side_effect = TimeoutError()
            self.assertEqual(manage.port_state(2455)["state"], "unknown")

    def test_stop_fails_closed_and_attempts_both_services(self):
        with (
            patch.object(manage, "service_details", return_value={"loaded": False}),
            patch.object(manage, "port_state", return_value={"state": "unknown", "error": "EPERM"}) as ports,
        ):
            with self.assertRaisesRegex(RuntimeError, "Cannot confirm"):
                manage.stop(timeout=0)
        self.assertEqual([call.args[0] for call in ports.call_args_list], [8443, 2455])

    def test_stop_cli_waits_for_final_write_after_listener_closes(self):
        marker = self.root / "late-write"
        worker = """import pathlib, signal, socket, sys, time
s = socket.socket(); s.bind(('127.0.0.1', 0)); s.listen()
ending = False
def stop(*args):
    global ending
    s.close(); ending = True
signal.signal(signal.SIGTERM, stop)
print(s.getsockname()[1], flush=True)
while not ending: time.sleep(0.01)
time.sleep(0.3)
pathlib.Path(sys.argv[1]).write_text('final commit')
"""
        child = subprocess.Popen(
            [sys.executable, "-c", worker, str(marker)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        reaper = threading.Thread(target=child.wait)
        try:
            line = child.stdout.readline()
            self.assertTrue(line, child.stderr.read() if not line else "")
            port = int(line)
            reaper.start()
            probe = manage.port_state

            def bootout(args, **kwargs):
                self.assertIn("--wait", args)
                self.assertGreater(kwargs["timeout"], 0)
                child.terminate()

            with (
                patch.object(manage, "service_details", return_value={"loaded": True, "pid": str(child.pid)}),
                patch.object(manage, "command", side_effect=bootout),
                patch.object(manage, "port_state", side_effect=lambda _, **kwargs: probe(port, **kwargs)),
                patch.object(sys, "argv", ["manage.py", "stop", "backend"]),
                patch.object(manage, "operation_lock", return_value=manage.nullcontext()),
            ):
                manage.main()
            self.assertEqual(marker.read_text(), "final commit")
            self.assertIsNotNone(child.returncode)
            self.assertFalse((self.root / "state/stopping-backend.json").exists())
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
            if reaper.is_alive():
                reaper.join(timeout=3)
            child.stdout.close()
            child.stderr.close()

    def test_closed_port_cannot_bypass_pending_process_group(self):
        pending = self.root / "state/stopping-backend.json"
        pending.write_text(json.dumps({"groups": [12345], "removal_confirmed": True}))
        for group_check in (False, PermissionError("denied")):
            with (
                self.subTest(group_check=group_check),
                patch.object(manage, "service_details", return_value={"loaded": False}),
                patch.object(manage, "port_state", return_value={"state": "closed"}),
                patch.object(
                    manage,
                    "process_group_absent",
                    **(
                        {"side_effect": group_check}
                        if isinstance(group_check, Exception)
                        else {"return_value": group_check}
                    ),
                ),
            ):
                with self.assertRaises(RuntimeError):
                    manage.stop("backend", timeout=0)
            self.assertTrue(pending.exists())

    def test_bootout_timeout_is_bounded_and_retry_fails_closed(self):
        with (
            patch.object(manage, "service_details", return_value={"loaded": True, "pid": "12345"}),
            patch.object(manage.os, "getpgid", return_value=12345),
            patch.object(manage, "command", side_effect=subprocess.TimeoutExpired("launchctl", 0.01)) as command,
        ):
            with self.assertRaises(RuntimeError):
                manage.stop("backend", timeout=0.01)
        self.assertLessEqual(command.call_args.kwargs["timeout"], 0.01)
        with (
            patch.object(manage, "service_details", return_value={"loaded": False}),
            patch.object(manage, "port_state", return_value={"state": "closed"}),
        ):
            with self.assertRaisesRegex(RuntimeError, "Prior LaunchAgent removal"):
                manage.stop("backend", timeout=0)

    def test_process_group_permission_error_is_unknown(self):
        with patch.object(manage.os, "killpg", side_effect=PermissionError()):
            with self.assertRaisesRegex(RuntimeError, "Cannot determine process group"):
                manage.process_group_absent(12345)

    def test_backup_recovers_prior_services_after_partial_stop(self):
        with (
            patch.object(manage, "loaded", return_value=True),
            patch.object(manage, "stop", side_effect=RuntimeError("partial stop")),
            patch.object(manage, "start") as start,
        ):
            with self.assertRaisesRegex(RuntimeError, "partial stop"):
                manage.backup()
        self.assertEqual([call.args[0] for call in start.call_args_list], ["backend", "https"])
        self.assertEqual(list((self.root / "backups").iterdir()), [])

    def test_legacy_backup_validates_and_missing_db_never_created(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        archive = self.make_archive(source)
        destination = Path(self.tmp.name) / "extracted"
        manage.extract_verified(archive, destination)
        self.assertTrue((destination / "data/store.db").is_file())
        (source / "data/store.db").unlink()
        archive = self.make_archive(source)
        destination = Path(self.tmp.name) / "missing"
        with self.assertRaisesRegex(RuntimeError, "store.db"):
            manage.extract_verified(archive, destination)
        self.assertFalse((destination / "data/store.db").exists())

    def test_database_requires_codex_tables_and_migration(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        db_path = source / "data/store.db"
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("DROP TABLE accounts")
        with self.assertRaisesRegex(RuntimeError, "tables"):
            manage.validate_staged(source)
        with closing(sqlite3.connect(db_path)) as db, db:
            db.execute("CREATE TABLE accounts (id INTEGER)")
            db.execute("DELETE FROM alembic_version")
        with self.assertRaisesRegex(RuntimeError, "migration"):
            manage.validate_staged(source)

    def test_backup_requires_complete_ca_and_format2_common(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        for name in ("root.crt", "root.key", "intermediate.crt", "intermediate.key"):
            path = source / "caddy/pki/authorities/local" / name
            original = path.read_bytes()
            path.unlink()
            with self.assertRaisesRegex(RuntimeError, name.replace(".", r"\.")):
                manage.validate_staged(source)
            path.write_bytes(original)
        (source / "bin/common.py").unlink()
        manage.validate_staged(source)  # Existing legacy backups have no common.py.
        (source / "backup-format.json").write_text(
            json.dumps({"format": 2, "root": str(self.root.resolve()), "data_dir": str(self.data.resolve())})
        )
        with self.assertRaisesRegex(RuntimeError, r"format 2 requires bin/common.py"):
            manage.validate_staged(source)

    def test_python_version_requires_exact_safe_313_release(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        versions = json.loads((source / "versions.json").read_text())
        for python in ("3.13", "3.14.1", "3.13.15;echo bad"):
            (source / "versions.json").write_text(json.dumps({**versions, "python": python}))
            with self.assertRaisesRegex(RuntimeError, "Python version"):
                manage.validate_staged(source)
        with (
            patch.object(manage, "command") as command,
            patch.object(manage.shutil, "which", return_value="/synthetic/bin/uv"),
        ):
            manage.install_version("1.24.0", "3.13.15")
        self.assertEqual(command.call_args.args[0][0], "/synthetic/bin/uv")
        self.assertEqual(command.call_args.args[0][-2:], ["3.13.15", "codex-lb==1.24.0"])

    def test_version_install_fails_before_mutation_without_uv(self):
        with patch.object(manage, "command") as command, patch.object(manage.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "uv must be installed and available on PATH"):
                manage.install_version("1.24.0", "3.13.15")
        command.assert_not_called()

    def test_help_runs_without_private_runtime_config(self):
        destination = self.root / "bin"
        destination.mkdir()
        for script in ("manage.py", "common.py", "codex-lbctl"):
            shutil.copy2(MANAGE.parent / script, destination / script)
        (self.root / "config/deployment.json").unlink()
        for script in ("manage.py", "codex-lbctl"):
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, str(destination / script), "--help"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=self.tmp.name,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("verify-backup", result.stdout)
        self.assertFalse((self.root / "config/deployment.json").exists())

    def test_launchagent_uses_configured_python_and_current_home(self):
        home = self.root / "synthetic-home"
        with patch.object(manage.Path, "home", return_value=home):
            manage.install_agents()
        for service, label in manage.LABELS.items():
            content = plistlib.loads((self.root / "agents" / f"{label}.plist").read_bytes())
            self.assertEqual(
                content["ProgramArguments"], [self.cfg["manager_python"], str(self.root / "bin/supervise.py"), service]
            )
            search = content["EnvironmentVariables"]["PATH"].split(os.pathsep)
            self.assertEqual(search[0], str(Path(self.cfg["manager_python"]).parent))
            self.assertIn(str(home / ".local/bin"), search)

    def test_optional_ancillary_tools_are_accepted_but_not_required(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        for name in ("admin.py", "clients.py"):
            self.assertFalse((source / "bin" / name).exists())
        manage.validate_staged(source)
        for name in ("admin.py", "clients.py"):
            (source / "bin" / name).write_text("# synthetic optional ancillary tool\n")
        manage.validate_staged(source)

    def test_https_ready_refreshes_changed_ca_export(self):
        source = self.root / "state/caddy/pki/authorities/local/root.crt"
        source.parent.mkdir(parents=True)
        source.write_text("current CA")
        exported = self.root / "certs/root.crt"
        exported.write_text("stale CA")
        with patch.object(manage, "probe", return_value=(200, "HTTP response")):
            manage.wait_ready("https")
        self.assertEqual(exported.read_text(), "current CA")

    def test_archive_rejects_traversal_links_and_duplicate_members(self):
        for names, typecode in (
            (["../escape"], tarfile.REGTYPE),
            (["data/link"], tarfile.SYMTYPE),
            (["data/file", "data/file"], tarfile.REGTYPE),
        ):
            archive = self.root / "backups/malicious.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name in names:
                    info = tarfile.TarInfo(name)
                    info.type = typecode
                    if typecode == tarfile.SYMTYPE:
                        info.linkname = "/etc/passwd"
                    tar.addfile(info)
            manage.checksum_path(archive).write_text(manage.archive_digest(archive))
            with self.assertRaises(RuntimeError):
                manage.extract_verified(archive, self.root / "extract")
        self.assertFalse((self.root / "escape").exists())

    def test_restore_rejects_different_data_directory_before_stop(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        self.install_live(source)
        (source / "config/deployment.json").write_text(json.dumps({**self.cfg, "data_dir": "/another/location"}))
        archive = self.make_archive(source)
        with (
            patch.object(manage, "loaded", return_value=False),
            patch.object(manage, "stop") as stop,
            patch.object(manage, "recovery_snapshot") as backup,
        ):
            with self.assertRaisesRegex(RuntimeError, "different data"):
                manage.restore(archive)
        stop.assert_not_called()
        backup.assert_not_called()

    def test_restore_rolls_back_files_version_config_and_service_state(self):
        source = Path(self.tmp.name) / "original"
        self.payload(source)
        self.install_live(source)
        (self.root / "agents/com.local.codex-lb.plist").write_text("original plist")
        replacement = Path(self.tmp.name) / "replacement"
        self.payload(replacement, version="1.25.0", text="replacement")
        (replacement / "config/deployment.json").write_text(
            json.dumps({**self.cfg, "public_url": "https://changed:8443"})
        )
        archive = self.make_archive(replacement)
        resume = Mock(side_effect=[RuntimeError("HTTPS startup failed"), None])
        with (
            patch.object(manage, "loaded", return_value=True),
            patch.object(manage, "recovery_snapshot", return_value=Path("recovery.tar.gz")),
            patch.object(manage, "stop"),
            patch.object(manage, "install_agents"),
            patch.object(manage, "resume_services", resume),
            patch.object(manage, "install_version") as install,
        ):
            with self.assertRaisesRegex(RuntimeError, "original files, version and prior service state recovered"):
                manage.restore(archive)
        self.assertEqual((self.root / "bin/manage.py").read_text(), "original")
        self.assertEqual((self.data / "encryption.key").read_text(), "original")
        self.assertEqual((self.root / "agents/com.local.codex-lb.plist").read_text(), "original plist")
        self.assertEqual(manage.CFG["public_url"], self.cfg["public_url"])
        self.assertEqual(manage.DATA, self.data)
        self.assertEqual([call.args for call in install.call_args_list], [("1.25.0", "3.13.15"), ("1.24.0", "3.13.15")])
        self.assertEqual(resume.call_args_list[-1].args[0], ["backend", "https"])

    def test_restore_stop_failure_recovers_prior_service_set(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        self.install_live(source)
        archive = self.make_archive(source)
        with (
            patch.object(manage, "loaded", side_effect=lambda service: service == "backend"),
            patch.object(manage, "recovery_snapshot", return_value=Path("recovery.tar.gz")),
            patch.object(manage, "stop", side_effect=RuntimeError("partial shutdown")),
            patch.object(manage, "resume_services") as resume,
        ):
            with self.assertRaisesRegex(RuntimeError, "prior service state recovered"):
                manage.restore(archive)
        resume.assert_called_once_with(["backend"])

    def test_restore_cli_recovers_damaged_or_missing_database_and_keeps_raw_snapshot(self):
        source = Path(self.tmp.name) / "healthy"
        self.payload(source)
        archive = self.make_archive(source)
        self.install_live(source)
        for damaged in (b"corrupted SQLite data", None):
            with self.subTest(damaged=damaged):
                if damaged is None:
                    (self.data / "store.db").unlink()
                else:
                    (self.data / "store.db").write_bytes(damaged)
                with (
                    patch.object(manage, "loaded", return_value=False),
                    patch.object(manage, "stop"),
                    patch.object(manage, "install_agents"),
                    patch.object(manage, "operation_lock", return_value=manage.nullcontext()),
                    patch.object(sys, "argv", ["manage.py", "restore", str(archive)]),
                ):
                    manage.main()
                self.assertEqual(manage.check_database(self.data / "store.db")["integrity_check"], "ok")
                raw = sorted((self.root / "backups/recovery").glob("pre-restore-*.tar.gz"))[-1]
                self.assertEqual(manage.checksum_path(raw).read_text().strip(), manage.archive_digest(raw))
                with tarfile.open(raw) as tar:
                    if damaged is None:
                        self.assertNotIn("data/store.db", tar.getnames())
                    else:
                        with tar.extractfile("data/store.db") as saved:
                            self.assertEqual(saved.read(), damaged)
                with self.assertRaisesRegex(RuntimeError, "Raw recovery snapshot"):
                    manage.verify_backup(raw)
                self.assertNotIn(raw, manage.completed_archives())

    def test_raw_snapshot_publication_failure_preserves_files_and_recovers_services(self):
        source = Path(self.tmp.name) / "original"
        self.payload(source)
        self.install_live(source)
        archive = self.make_archive(source)
        original_database = (self.data / "store.db").read_bytes()
        replace = manage.os.replace

        def fail_raw_archive(source, destination):
            if Path(destination).name.startswith("pre-restore-") and str(destination).endswith(".tar.gz"):
                raise OSError("simulated snapshot publication failure")
            return replace(source, destination)

        with (
            patch.object(manage, "loaded", return_value=True),
            patch.object(manage, "stop"),
            patch.object(manage.os, "replace", side_effect=fail_raw_archive),
            patch.object(manage, "resume_services") as resume,
            patch.object(manage, "install_version") as install,
        ):
            with self.assertRaisesRegex(RuntimeError, "original files, version and prior service state recovered"):
                manage.restore(archive)
        self.assertEqual((self.data / "store.db").read_bytes(), original_database)
        self.assertEqual(list((self.root / "backups/recovery").iterdir()), [])
        install.assert_not_called()
        resume.assert_called_once_with(["backend", "https"])

    def test_restore_does_not_snapshot_or_replace_after_failed_shutdown(self):
        source = Path(self.tmp.name) / "original"
        self.payload(source)
        self.install_live(source)
        archive = self.make_archive(source)
        with (
            patch.object(manage, "loaded", return_value=False),
            patch.object(manage, "stop", side_effect=RuntimeError("still writing")),
            patch.object(manage, "recovery_snapshot") as snapshot,
            patch.object(manage, "apply_replacements") as replace,
        ):
            with self.assertRaises(RuntimeError):
                manage.restore(archive)
        snapshot.assert_not_called()
        replace.assert_not_called()

    def test_restore_partial_directory_swap_is_rolled_back(self):
        source = Path(self.tmp.name) / "original"
        self.payload(source)
        self.install_live(source)
        replacement = Path(self.tmp.name) / "replacement"
        self.payload(replacement, text="replacement")
        archive = self.make_archive(replacement)
        original_replace = manage.os.replace

        def fail_config(source, destination):
            if Path(source).name == "new" and Path(destination) == self.root / "config":
                raise OSError("simulated directory swap failure")
            return original_replace(source, destination)

        with (
            patch.object(manage, "loaded", return_value=False),
            patch.object(manage, "recovery_snapshot", return_value=Path("recovery.tar.gz")),
            patch.object(manage, "stop"),
            patch.object(manage, "resume_services"),
            patch.object(manage.os, "replace", side_effect=fail_config),
        ):
            with self.assertRaisesRegex(RuntimeError, "original files, version and prior service state recovered"):
                manage.restore(archive)
        self.assertEqual((self.data / "encryption.key").read_text(), "original")
        self.assertEqual((self.root / "state/runtime/caddy").read_text(), "original")
        self.assertEqual(json.loads((self.root / "config/deployment.json").read_text()), self.cfg)
        self.assertEqual((self.root / "bin/manage.py").read_text(), "original")

    def test_failed_rollback_shutdown_preserves_original_directories(self):
        source = Path(self.tmp.name) / "original"
        self.payload(source)
        self.install_live(source)
        replacement = Path(self.tmp.name) / "replacement"
        self.payload(replacement, text="replacement")
        archive = self.make_archive(replacement)
        with (
            patch.object(manage, "loaded", return_value=False),
            patch.object(manage, "recovery_snapshot", return_value=Path("recovery.tar.gz")),
            patch.object(manage, "stop", side_effect=[None, RuntimeError("unknown port")]),
            patch.object(manage, "install_agents", side_effect=RuntimeError("plist failure")),
        ):
            with self.assertRaisesRegex(
                RuntimeError, "automatic recovery is incomplete.*Preserved restore directories"
            ):
                manage.restore(archive)
        saved = list(self.data.parent.glob(".data.restore-*/original/encryption.key"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), "original")
        self.assertEqual((self.data / "encryption.key").read_text(), "replacement")

    def test_backup_publish_failure_has_no_final_pair_and_recovers(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        self.install_live(source)
        original_replace = manage.os.replace

        def fail_archive(source, destination):
            if str(destination).endswith(".tar.gz"):
                raise OSError("simulated commit failure")
            return original_replace(source, destination)

        with (
            patch.object(manage, "loaded", return_value=True),
            patch.object(manage, "stop"),
            patch.object(manage, "start") as start,
            patch.object(manage.os, "replace", side_effect=fail_archive),
        ):
            with self.assertRaisesRegex(OSError, "commit failure"):
                manage.backup()
        self.assertEqual(list((self.root / "backups").iterdir()), [])
        self.assertEqual(start.call_count, 2)

    def test_retention_only_counts_valid_completed_pairs(self):
        source = Path(self.tmp.name) / "payload"
        self.payload(source)
        self.install_live(source)
        (self.root / "README.md").write_text("management instructions")
        (self.root / "setup.command").write_text("echo setup")
        valid = [self.make_archive(source, f"codex-lb-2000010{number}.tar.gz") for number in range(1, 7)]
        invalid = self.root / "backups/codex-lb-00000000.tar.gz"
        invalid.write_text("incomplete")
        with (
            patch.object(manage, "loaded", return_value=False),
            patch.object(manage, "stop"),
            patch.object(manage, "resume_services"),
        ):
            archive = manage.backup()
        self.assertFalse(valid[0].exists())
        self.assertFalse(valid[1].exists())
        self.assertTrue(invalid.exists())
        self.assertEqual(len(manage.completed_archives()), 5)
        with tarfile.open(archive) as tar:
            self.assertIn("README.md", tar.getnames())
            self.assertIn("setup.command", tar.getnames())
            self.assertIn("backup-format.json", tar.getnames())

    def test_status_reports_actual_auth_and_unknown_without_secret(self):
        with (
            patch.object(manage, "service_details", side_effect=RuntimeError("private detail")),
            patch.object(manage, "port_state", return_value={"state": "unknown", "error": "EPERM"}),
            patch.object(manage, "probe", return_value=(None, "PermissionError")),
            patch.object(
                manage,
                "read_auth_state",
                return_value={
                    "password_configured": True,
                    "api_key_auth_enabled": False,
                    "guest_access_enabled": False,
                },
            ),
        ):
            result = manage.status()
        self.assertFalse(result["authentication"]["api_key_auth_enabled"])
        self.assertFalse(result["readiness"]["https_auth_ready"])
        self.assertIsNone(result["readiness"]["backend_ready"])
        self.assertIsNone(result["services"]["backend"]["loaded"])
        self.assertNotIn("private detail", json.dumps(result))

    def test_mutation_lock_wraps_restart_once(self):
        context = Mock()
        context.__enter__ = Mock(return_value=None)
        context.__exit__ = Mock(return_value=False)
        with (
            patch.object(manage, "operation_lock", return_value=context) as lock,
            patch.object(manage, "reload_config"),
            patch.object(manage, "stop") as stop,
            patch.object(manage, "start") as start,
            patch.object(sys, "argv", ["manage.py", "restart", "backend"]),
        ):
            manage.main()
        lock.assert_called_once_with(self.root)
        context.__enter__.assert_called_once()
        context.__exit__.assert_called_once()
        stop.assert_called_once_with("backend")
        start.assert_called_once_with("backend")


if __name__ == "__main__":
    unittest.main()
