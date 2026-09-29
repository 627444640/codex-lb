"""Manage only the independent monitor's per-user LaunchAgent."""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABEL = "com.local.codex-lb-monitor"
PLIST = Path.home() / "Library/LaunchAgents" / f"{LABEL}.plist"
TARGET = f"gui/{os.getuid()}/{LABEL}"


def main():
    parser = argparse.ArgumentParser(description="独立监控服务管理；不操作原 Codex LB")
    parser.add_argument("command", choices=["install", "start", "stop", "restart", "status"])
    args = parser.parse_args()
    if args.command == "install":
        config = ROOT / "runtime/config.json"
        if not config.exists():
            parser.error("请先初始化 runtime/config.json")
        spec = {
            "Label": LABEL,
            "ProgramArguments": [str(ROOT / ".venv/bin/python"), "-m", "monitor", "serve", "--config", str(config)],
            "WorkingDirectory": str(ROOT),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "ProcessType": "Background",
            "ExitTimeOut": 30,
            "Umask": 0o077,
            "StandardOutPath": str(ROOT / "runtime/launchd.stdout.log"),
            "StandardErrorPath": str(ROOT / "runtime/launchd.stderr.log"),
            "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "PYTHONUNBUFFERED": "1"},
        }
        if PLIST.exists():
            if plistlib.loads(PLIST.read_bytes()) != spec:
                parser.error("同名 LaunchAgent 已存在且内容不同；保留原文件，停止覆盖")
        else:
            PLIST.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(PLIST, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "wb") as f:
                plistlib.dump(spec, f)
        print(f"独立 LaunchAgent 已准备：{PLIST}")
        return
    commands = {
        "start": ["bootstrap", f"gui/{os.getuid()}", str(PLIST)],
        "stop": ["bootout", TARGET],
        "restart": ["kickstart", "-k", TARGET],
        "status": ["print", TARGET],
    }
    result = subprocess.run(["/bin/launchctl", *commands[args.command]], check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
