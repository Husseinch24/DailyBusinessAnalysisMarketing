"""
Notifier module for MarketingProject (SendGrid-only version).

Supports:
- Slack
- Telegram
- SendGrid Email (with attachments)
"""

import json
import mimetypes
import os
import base64
from pathlib import Path

import requests
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Mail,
    Attachment,
    FileContent,
    FileName,
    FileType,
    Disposition
)

from config.settings import METRICS_PATH, REPORTS_DIR

CONFIG_PATH = Path("notification_config.json")


# --------------------------------------------------------
# Load config & metrics
# --------------------------------------------------------

def _load_config():
    if not CONFIG_PATH.exists():
        print("[notify] No notification_config.json found.")
        return None

    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    methods = cfg.get("methods", [])

    if not methods:
        print("[notify] No methods enabled.")
        return None

    return cfg


def _load_metrics():
    if not METRICS_PATH.exists():
        return {}
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------
# Summary text
# --------------------------------------------------------

def _short_summary_text():
    metrics = _load_metrics()

    rows = metrics.get("metrics", {}).get("rows", "unknown")
    unique_asins = metrics.get("metrics", {}).get("unique_asins", "unknown")
    avg_rating = metrics.get("metrics", {}).get("overall_avg_rating", "unknown")

    return (
        "Daily marketing report generated.\n"
        f"- Rows analyzed: {rows}\n"
        f"- Unique products: {unique_asins}\n"
        f"- Overall avg rating: {avg_rating}\n"
    )


# --------------------------------------------------------
# Collect attachments based on config flags
# --------------------------------------------------------

def _collect_attachments(cfg) -> list[Path]:
    out = []
    attach_cfg = cfg.get("attachments", {}) or {}

    def append_if_exists(path: Path):
        if path.exists():
            out.append(path)
        else:
            print(f"[notify] File not found, skipping: {path}")

    # Dashboard
    if attach_cfg.get("attach_dashboard"):
        append_if_exists(REPORTS_DIR / "dashboard.html")

    # Summary TXT
    if attach_cfg.get("attach_txt_summary"):
        append_if_exists(REPORTS_DIR / "daily_summary.txt")

    # Daily MD summary
    if attach_cfg.get("attach_daily_md"):
        md_files = sorted(REPORTS_DIR.glob("daily_business_summary_*.md"))
        if md_files:
            out.append(md_files[-1])

    # Product Intelligence MD
    if attach_cfg.get("attach_product_md"):
        md_files = sorted(REPORTS_DIR.glob("product_intel_*.md"))
        if md_files:
            out.append(md_files[-1])

    # PNG Plots
    if attach_cfg.get("attach_plots"):
        plots_dir = REPORTS_DIR / "plots"
        for p in plots_dir.glob("*.png"):
            out.append(p)

    return out


# --------------------------------------------------------
# Slack / Telegram
# --------------------------------------------------------

def _send_slack(cfg, message: str):
    webhook = cfg.get("slack", {}).get("webhook_url")
    if not webhook:
        print("[notify] Slack webhook not configured.")
        return

    try:
        r = requests.post(webhook, json={"text": message}, timeout=10)
        print("[notify] Slack sent." if r.status_code == 200 else f"[notify] Slack error: {r.text}")
    except Exception as e:
        print(f"[notify] Slack exception: {e}")


def _send_telegram(cfg, message: str):
    tg = cfg.get("telegram", {})
    token = tg.get("bot_token")
    chat_id = tg.get("chat_id")

    if not token or not chat_id:
        print("[notify] Telegram not configured.")
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, data={"chat_id": chat_id, "text": message}, timeout=10)
        print("[notify] Telegram sent." if r.status_code == 200 else f"[notify] Telegram error: {r.text}")
    except Exception as e:
        print(f"[notify] Telegram exception: {e}")


# --------------------------------------------------------
# SendGrid Email with Attachments (FIXED)
# --------------------------------------------------------

def _send_email_sendgrid(cfg, message: str):
    email_cfg = cfg.get("email", {})

    api_key = email_cfg.get("sendgrid_api_key") or os.getenv("SENDGRID_API_KEY")
    from_addr = email_cfg.get("from_addr")
    to_addr = email_cfg.get("to_addr")

    if not api_key or not from_addr or not to_addr:
        print("[notify] Missing SendGrid API key or from/to address.")
        return

    attachment_paths = _collect_attachments(cfg)

    try:
        mail = Mail(
            from_email=from_addr,
            to_emails=to_addr,
            subject="Daily Marketing Report",
            plain_text_content=message,
        )

        # FIX: Correct SendGrid API → use mail.add_attachment()
        for path in attachment_paths:
            try:
                file_bytes = path.read_bytes()
                encoded = base64.b64encode(file_bytes).decode()

                mime = mimetypes.guess_type(path)[0] or "application/octet-stream"

                attachment = Attachment(
                    FileContent(encoded),
                    FileName(path.name),
                    FileType(mime),
                    Disposition("attachment"),
                )

                mail.add_attachment(attachment)
                print(f"[notify] Attached: {path}")

            except Exception as e:
                print(f"[notify] ERROR attaching {path}: {e}")

        sg = SendGridAPIClient(api_key)
        response = sg.send(mail)
        print(f"[notify] SendGrid email sent. Status={response.status_code}")

    except Exception as e:
        print(f"[notify] SendGrid email exception: {e}")


# --------------------------------------------------------
# Dispatcher
# --------------------------------------------------------

def notify_all():
    cfg = _load_config()
    if not cfg:
        return

    message = _short_summary_text()
    methods = cfg.get("methods", [])

    print(f"[notify] Methods: {methods}")

    if "slack" in methods:
        _send_slack(cfg, message)

    if "telegram" in methods:
        _send_telegram(cfg, message)

    if "email" in methods:
        _send_email_sendgrid(cfg, message)


if __name__ == "__main__":
    notify_all()
