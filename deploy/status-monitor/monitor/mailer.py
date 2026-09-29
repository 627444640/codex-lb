from __future__ import annotations

import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

from .store import Store


def send_email(settings, event):
    cfg = settings.smtp
    password = None
    if cfg.get("username"):
        path = Path(cfg["password_file"])
        if path.stat().st_mode & 0o077:
            raise ValueError("credential_permissions")
        password = path.read_text().strip()
        if not password:
            raise ValueError("credential_empty")
    message = EmailMessage()
    message["From"] = cfg["sender"]
    message["To"] = ", ".join(cfg["recipients"])
    message["Subject"] = f"{settings.title} {event['title']}"
    message["Date"] = formatdate(event["created_at"], usegmt=True)
    message["Message-ID"] = (
        f"<codex-lb-monitor-{event['id']}-{int(event['created_at'])}@{cfg['sender'].split('@')[-1]}>"
    )
    message.set_content(f"{event['body']}\n\n状态页：{settings.origin}/\n事件编号：{event['id']}\n")
    context = ssl.create_default_context()
    mode = cfg.get("tls", "ssl")
    port = int(cfg.get("port", 465 if mode == "ssl" else 587))
    if mode == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], port, timeout=10, context=context)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=10)
    try:
        if mode != "ssl":
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        if cfg.get("username"):
            server.login(cfg["username"], password)
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    finally:
        server.close()


def deliver_pending(store: Store, now=None, sender=send_email):
    if not store.settings.smtp_ready:
        return
    now = time.time() if now is None else now
    with store.db() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM events WHERE email_status IN ('pending','retry') "
                "AND next_attempt_at<=? ORDER BY id LIMIT 5",
                (now,),
            )
        ]
    for event in rows:
        attempt = event["attempts"] + 1
        try:
            sender(store.settings, event)
        except (OSError, smtplib.SMTPException, ValueError, KeyError):
            with store.db() as conn:
                conn.execute(
                    "UPDATE events SET email_status=?,attempts=?,next_attempt_at=?,last_error=? WHERE id=?",
                    (
                        "failed" if attempt >= 5 else "retry",
                        attempt,
                        now + min(3600, 60 * 2 ** (attempt - 1)),
                        "SMTP 投递失败，请检查发信设置或授权码",
                        event["id"],
                    ),
                )
        else:
            with store.db() as conn:
                conn.execute(
                    "UPDATE events SET email_status='sent',attempts=?,sent_at=?,last_error=NULL WHERE id=?",
                    (attempt, now, event["id"]),
                )
