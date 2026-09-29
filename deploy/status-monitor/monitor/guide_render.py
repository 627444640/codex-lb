from __future__ import annotations

from html import escape
from zoneinfo import ZoneInfo

from .guides import GuideRecord


def render_guides(guides: list[GuideRecord]) -> str:
    if not guides:
        return '<p class="empty-copy">暂无已发布的排查指南。</p>'
    parts = []
    for guide in guides:
        e = escape
        steps = "".join(f"<li>{e(step)}</li>" for step in guide.solutions)
        endpoint = ""
        if guide.endpoint_url:
            target = f"guide-endpoint-{guide.id}"
            endpoint = (
                '<div class="endpoint-box"><div class="endpoint-value">'
                f'<span class="card-label">{e(guide.endpoint_label)}</span>'
                f'<code id="{target}">{e(guide.endpoint_url)}</code></div>'
                f'<button class="text-button copy-endpoint" type="button" data-copy-target="{target}" '
                f'aria-label="复制{e(guide.endpoint_label, quote=True)}">复制地址</button></div>'
                '<p class="copy-feedback" role="status" aria-live="polite"></p>'
                f'<p class="footnote">{e(guide.endpoint_help)}</p>'
            )
        note = f'<div class="troubleshooting-note">{e(guide.limitations)}</div>' if guide.limitations else ""
        date = guide.updated_at.astimezone(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d")
        parts.append(
            f'<details class="troubleshooting-item" id="{e(guide.slug, quote=True)}" open>'
            f'<summary><span class="error-code">{e(guide.code)}</span>'
            '<span class="troubleshooting-summary">'
            f'<span class="troubleshooting-name">{e(guide.title)}</span>'
            f'<span class="troubleshooting-signature">{e(guide.signature)}</span></span>'
            '<span class="troubleshooting-chevron" aria-hidden="true">⌄</span></summary>'
            f'<div class="troubleshooting-body"><p class="troubleshooting-scope">{e(guide.scope)}</p>'
            f'<div class="troubleshooting-block"><h3>原因</h3><p>{e(guide.cause)}</p></div>'
            f'<div class="troubleshooting-block"><h3>解决方法</h3><ol>{steps}</ol>{endpoint}</div>'
            f'{note}<p class="troubleshooting-updated">更新于 {date} · Asia/Taipei</p></div></details>'
        )
    return "\n".join(parts)
