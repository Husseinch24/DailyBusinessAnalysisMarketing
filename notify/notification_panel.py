"""
Interactive notification setup panel.

Asks the user:
- which channels to use (Slack, Telegram, Email)
- required settings (webhook URL, bot token, SMTP data, email)

Saves configuration to notification_config.json
"""

import json
from pathlib import Path

# Config stays at project root
CONFIG_PATH = Path("notification_config.json")


def ask_yes_no(prompt: str) -> bool:
    while True:
        ans = input(f"{prompt} [y/n]: ").strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer with 'y' or 'n'.")


def main():
    print("=== Notification Setup Panel ===")
    print("Configure how you want to be notified when the daily report is generated.\n")

    config = {
        "methods": [],
        "slack": {},
        "telegram": {},
        "email": {},
    }

    # Slack
    if ask_yes_no("Do you want Slack notifications?"):
        webhook = input("Enter Slack Incoming Webhook URL: ").strip()
        if webhook:
            config["methods"].append("slack")
            config["slack"]["webhook_url"] = webhook

    # Telegram
    if ask_yes_no("Do you want Telegram notifications?"):
        token = input("Enter Telegram Bot Token: ").strip()
        chat_id = input("Enter Telegram Chat ID (your chat or group id): ").strip()
        if token and chat_id:
            config["methods"].append("telegram")
            config["telegram"]["bot_token"] = token
            config["telegram"]["chat_id"] = chat_id

    # Email
    if ask_yes_no("Do you want Email notifications?"):
        smtp_host = input("SMTP host (e.g. smtp.gmail.com): ").strip()
        smtp_port = input("SMTP port (e.g. 587): ").strip()
        username = input("SMTP username (email address): ").strip()
        password = input("SMTP password or app password: ").strip()
        from_addr = input("From email address: ").strip()
        to_addr = input("To email address for reports: ").strip()

        if smtp_host and smtp_port and username and password and from_addr and to_addr:
            config["methods"].append("email")
            config["email"] = {
                "smtp_host": smtp_host,
                "smtp_port": int(smtp_port),
                "username": username,
                "password": password,
                "from_addr": from_addr,
                "to_addr": to_addr,
                "use_tls": True,
            }

    CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    print(f"\n[panel] Notification configuration saved to {CONFIG_PATH}")
    print(f"[panel] Enabled methods: {config['methods']}")


if __name__ == "__main__":
    main()