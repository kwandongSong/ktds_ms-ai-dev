
# teams.py – Simple Teams Incoming Webhook notifier
import requests
from config import CONFIG

def send_teams_message(title: str, text: str) -> dict:
    url = CONFIG.get("TEAMS_WEBHOOK_URL","")
    if not url or "YOUR_WEBHOOK_URL" in url:
        raise RuntimeError("TEAMS_WEBHOOK_URL not configured.")
    payload = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": "0076D7",
        "summary": title,
        "title": title,
        "text": text
    }
    r = requests.post(url, json=payload, timeout=30)
    r.raise_for_status()
    return {"status": "ok"}
