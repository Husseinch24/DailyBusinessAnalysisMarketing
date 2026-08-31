#!/usr/bin/env python3
"""
Streamlit UI for MarketingProject — SendGrid-only version.

- Configure ingestion/scraping
- ASIN overrides
- Slack / Telegram / SendGrid email
- Select file attachments
- Save ui_config.json + notification_config.json
- Trigger pipeline
"""

import sys
import json
import re
import subprocess
from pathlib import Path

import streamlit as st

# -------------------------------------------------------
# Ensure project root is importable BEFORE importing settings
# -------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import PROJECT_ROOT as SETTINGS_PROJECT_ROOT

PROJECT_ROOT = SETTINGS_PROJECT_ROOT

UI_CONFIG_PATH = PROJECT_ROOT / "ui_config.json"
NOTIF_CONFIG_PATH = PROJECT_ROOT / "notification_config.json"


# -------------------------------------------------------
# Helpers
# -------------------------------------------------------

def parse_asin_input(raw: str) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,\n]", raw)
    seen = set()
    out = []
    for p in parts:
        p = p.strip()
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def build_ui_config(ingest_days, scrape_products, fetch_trends, asin_override):
    return {
        "ingest_days": ingest_days,
        "scrape_products": scrape_products,
        "fetch_trends": fetch_trends,
        "asin_override": asin_override,
    }


def build_notification_config(
    slack_enabled,
    slack_webhook,
    tg_enabled,
    tg_token,
    tg_chat_id,
    email_enabled,
    sendgrid_api_key,
    sendgrid_from,
    sendgrid_to,
    attach_dashboard,
    attach_txt_summary,
    attach_daily_md,
    attach_product_md,
    attach_plots,
):
    """
    SendGrid-only email configuration.
    """
    cfg = {
        "methods": [],
        "slack": {},
        "telegram": {},
        "email": {},
        "attachments": {
            "attach_dashboard": attach_dashboard,
            "attach_txt_summary": attach_txt_summary,
            "attach_daily_md": attach_daily_md,
            "attach_product_md": attach_product_md,
            "attach_plots": attach_plots,
        },
    }

    # Slack
    if slack_enabled and slack_webhook.strip():
        cfg["methods"].append("slack")
        cfg["slack"] = {"webhook_url": slack_webhook.strip()}

    # Telegram
    if tg_enabled and tg_token.strip() and tg_chat_id.strip():
        cfg["methods"].append("telegram")
        cfg["telegram"] = {
            "bot_token": tg_token.strip(),
            "chat_id": tg_chat_id.strip(),
        }

    # SendGrid email ONLY
    if email_enabled:
        cfg["methods"].append("email")

        email_cfg = {
            "provider": "sendgrid",
            "from_addr": sendgrid_from.strip(),
            "to_addr": sendgrid_to.strip(),
        }

        if sendgrid_api_key.strip():
            email_cfg["sendgrid_api_key"] = sendgrid_api_key.strip()
        else:
            st.info("No SendGrid API Key entered — notifier will look for SENDGRID_API_KEY env var.")

        cfg["email"] = email_cfg

    return cfg


# -------------------------------------------------------
# Streamlit UI
# -------------------------------------------------------

def main():
    st.set_page_config(page_title="MarketingProject Control Panel", layout="centered")
    st.title("MarketingProject Control Panel")

    with st.form("config_form"):

        # -------------------------
        # Ingestion / Scraping
        # -------------------------
        st.subheader("Ingestion & Scraping")

        ingest_days = st.number_input(
            "Ingest window (days)",
            min_value=1,
            max_value=365,
            value=100,
        )

        scrape_products = st.checkbox("Scrape product pages", value=True)
        fetch_trends = st.checkbox("Fetch Google Trends", value=True)

        # -------------------------
        # ASIN overrides
        # -------------------------
        st.subheader("ASIN Overrides (optional)")
        asin_raw = st.text_area("ASIN list (comma or newline)", height=120)

        # -------------------------
        # Notifications
        # -------------------------
        st.markdown("---")
        st.subheader("Notifications")

        # Slack
        slack_enabled = st.checkbox("Slack notifications", value=True)
        slack_webhook = st.text_input("Slack Webhook URL")

        # Telegram
        tg_enabled = st.checkbox("Telegram notifications", value=True)
        tg_token = st.text_input("Telegram Bot Token")
        tg_chat_id = st.text_input("Telegram Chat ID")

        # -------------------------
        # SendGrid Email (only)
        # -------------------------
        email_enabled = st.checkbox("Email notifications (SendGrid only)", value=True)

        st.markdown("### SendGrid Email Settings")
        sendgrid_api_key = st.text_input(
            "SendGrid API Key (optional — can use SENDGRID_API_KEY env var)",
            type="password",
        )
        sendgrid_from = st.text_input("From Email (SendGrid sender)")
        sendgrid_to = st.text_input("To Email (recipient)")

        # -------------------------
        # Attachments
        # -------------------------
        st.markdown("---")
        st.subheader("Email Attachments")

        attach_dashboard = st.checkbox("Attach Dashboard HTML", value=True)
        attach_txt_summary = st.checkbox("Attach TXT summary", value=True)
        attach_daily_md = st.checkbox("Attach daily Gemini Markdown", value=False)
        attach_product_md = st.checkbox("Attach Product Intelligence Markdown", value=False)
        attach_plots = st.checkbox("Attach PNG plots", value=False)

        submitted = st.form_submit_button("Save & Run Pipeline")

    # ------------------------------------------------------------------
    # Handle submission
    # ------------------------------------------------------------------
    if submitted:

        asin_override = parse_asin_input(asin_raw)

        ui_cfg = build_ui_config(
            ingest_days=ingest_days,
            scrape_products=scrape_products,
            fetch_trends=fetch_trends,
            asin_override=asin_override,
        )

        notif_cfg = build_notification_config(
            slack_enabled,
            slack_webhook,
            tg_enabled,
            tg_token,
            tg_chat_id,
            email_enabled,
            sendgrid_api_key,
            sendgrid_from,
            sendgrid_to,
            attach_dashboard,
            attach_txt_summary,
            attach_daily_md,
            attach_product_md,
            attach_plots,
        )

        # Save config files
        UI_CONFIG_PATH.write_text(json.dumps(ui_cfg, indent=2), encoding="utf-8")
        NOTIF_CONFIG_PATH.write_text(json.dumps(notif_cfg, indent=2), encoding="utf-8")

        st.success("Configuration saved successfully.")

        st.code(
            json.dumps(
                {
                    "ui_config": ui_cfg,
                    "notification_methods": notif_cfg["methods"],
                    "email_provider": notif_cfg["email"].get("provider", None),
                    "attachments": notif_cfg["attachments"],
                },
                indent=2,
            ),
            language="json",
        )

        st.info("Running pipeline… check terminal logs.")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pipeline.run_daily",
                "--config",
                str(UI_CONFIG_PATH),
            ],
            cwd=str(PROJECT_ROOT),
            check=False,
        )

        if result.returncode == 0:
            st.success("Pipeline completed successfully.")
        else:
            st.error(f"Pipeline exited with code {result.returncode}.")


if __name__ == "__main__":
    main()