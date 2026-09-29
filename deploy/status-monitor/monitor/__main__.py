from __future__ import annotations

import argparse
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ROOT, load_settings
from .control import initialize_token
from .store import Store


def private_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(content)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description="Codex LB 独立监控服务")
    parser.add_argument("command", choices=["init", "serve", "collect"])
    parser.add_argument("--config", type=Path, default=ROOT / "runtime/config.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=2466)
    args = parser.parse_args()
    if args.command == "init":
        if args.config.exists():
            parser.error("配置已存在；不会覆盖。")
        cfg = {
            "source_db": str(Path.home() / ".codex-lb/store.db"),
            "state_dir": ".",
            "origin": "http://127.0.0.1:2466",
            "title": "Codex LB",
            "poll_seconds": 60,
            "smtp": {
                "enabled": False,
                "host": "smtp.163.com",
                "port": 465,
                "tls": "ssl",
                "sender": "",
                "username": "",
                "recipients": [],
                "password_file": "smtp-password.txt",
            },
        }
        private_write(args.config, json.dumps(cfg, ensure_ascii=False, indent=2) + "\n")
        settings = load_settings(args.config)
        store = Store(settings)
        initialize_token(store)
        print("初始化完成；邮件提醒与公告通过 Codex LB 设置管理。")
        return
    settings = load_settings(args.config)
    if args.command == "serve":
        if args.host not in {"127.0.0.1", "::1", "localhost"}:
            parser.error("仅监听本机；公网通过 HTTPS 反向代理接入")
        import uvicorn

        from .server import create_app

        settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        logging.basicConfig(
            level=logging.INFO,
            handlers=[
                RotatingFileHandler(
                    settings.state_dir / "monitor.log", maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
                )
            ],
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        logging.getLogger("httpx").setLevel(logging.WARNING)
        uvicorn.run(
            create_app(settings, config_path=args.config.resolve()),
            host=args.host,
            port=args.port,
            proxy_headers=False,
            access_log=False,
            log_config=None,
        )
        return
    store = Store(settings)
    if args.command == "collect":
        from .collector import collect

        store.record(collect(settings))
        print("采集完成。")


if __name__ == "__main__":
    main()
