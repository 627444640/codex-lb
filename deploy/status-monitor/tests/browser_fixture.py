"""Disposable monitor for integrated Settings browser acceptance; synthetic source only."""

import json
import os
from dataclasses import asdict, replace
from pathlib import Path

import uvicorn
from test_monitor import Fixture

from monitor.server import create_app

os.umask(0o077)
fixture = Fixture()
fixture.setUp()
fixture.request()
root = Path(__file__).resolve().parent.parent / "07_Working/status-settings-preview"
root.mkdir(parents=True, exist_ok=True)
settings = replace(
    fixture.settings,
    state_dir=root / "monitor",
    origin="http://127.0.0.1:2467",
    title="Settings preview",
    poll_seconds=10,
    smtp={
        "enabled": False,
        "host": "smtp.163.com",
        "port": 465,
        "tls": "ssl",
        "sender": "demo@example.invalid",
        "username": "demo@example.invalid",
        "recipients": ["demo@example.invalid"],
    },
)
settings.state_dir.mkdir(exist_ok=True)
config_path = settings.state_dir / "config.json"
cfg = asdict(settings)
cfg["source_db"] = str(settings.source_db)
cfg["state_dir"] = str(settings.state_dir)
config_path.write_text(json.dumps(cfg))
config_path.chmod(0o600)
app = create_app(settings, config_path=config_path)
lb = root / "lb"
lb.mkdir(exist_ok=True)
bridge = lb / "status-monitor.json"
bridge.write_text(json.dumps({"url": "http://127.0.0.1:2467", "token_file": str(settings.control_token_file)}))
bridge.chmod(0o600)
try:
    uvicorn.run(app, host="127.0.0.1", port=2467, proxy_headers=False, access_log=False)
finally:
    fixture.doCleanups()
