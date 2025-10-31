# notifier.py
import requests
from typing import Sequence, Dict
from config import CONFIG
from teams import send_teams_message
import base64, json, requests

def _decode_jwt(token: str) -> dict:
    try:
        payload = token.split(".")[1] + "=="
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
    except Exception:
        return {}
    
# ── Email via Microsoft Graph ─────────────────────────────────
def send_email_graph(access_token: str, to_email: str, subject: str, body_md: str):
    """
    Delegated 토큰(scp 포함) → /me/sendMail
    App 토큰(roles 포함) → /users/{MAIL_SENDER_USER_ID}/sendMail
    """
    if not access_token:
        raise RuntimeError("Graph access token is missing")

    claims = _decode_jwt(access_token)
    is_delegated = bool(claims.get("scp"))          # delegated: 'scp' claim 존재
    is_app = bool(claims.get("roles"))              # app: 'roles' claim 존재

    if is_delegated:
        url = "https://graph.microsoft.com/v1.0/me/sendMail"
    elif is_app:
        user = CONFIG.get("MAIL_SENDER_USER_ID")
        if not user:
            raise RuntimeError("App token 사용 시 MAIL_SENDER_USER_ID 필요")
        url = f"https://graph.microsoft.com/v1.0/users/{user}/sendMail"
    else:
        # 알 수 없으면 안전하게 /me 시도
        url = "https://graph.microsoft.com/v1.0/me/sendMail"

    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    html = f"<html><body>{body_md.replace(chr(10), '<br/>')}</body></html>"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to_email}}],
        },
        "saveToSentItems": "true"
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    if r.status_code == 401:
        # 토큰 만료/스코프 미부여/다른 계정 문제
        raise requests.HTTPError(f"401 Unauthorized: 토큰 만료 또는 권한(메일 전송) 미동의 가능성. endpoint={url}", response=r)
    r.raise_for_status()
    return {"ok": True}
# def send_email_graph(access_token: str, to_email: str, subject: str, body_md: str):
#     """
#     Graph /sendMail (me/sendMail) – 위임 권한 (User.Read / Mail.Send) 필요
#     """
#     url = "https://graph.microsoft.com/v1.0/me/sendMail"
#     headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
#     html = f"<html><body>{body_md.replace(chr(10), '<br/>')}</body></html>"
#     payload = {
#         "message": {
#             "subject": subject,
#             "body": {"contentType": "HTML", "content": html},
#             "toRecipients": [{"emailAddress": {"address": to_email}}],
#         },
#         "saveToSentItems": "true"
#     }
#     r = requests.post(url, headers=headers, json=payload, timeout=30)
#     r.raise_for_status()
#     return {"ok": True}

# ── SMS via Azure Communication Services ──────────────────────
def send_sms_acs(to_phone: str, body: str):
    """
    Azure Communication Services SMS
    pip install azure-communication-sms
    """
    from azure.communication.sms import SmsClient
    conn = CONFIG["ACS_SMS_CONNECTION_STRING"]
    sender = CONFIG["ACS_SMS_FROM"]
    client = SmsClient.from_connection_string(conn)
    resp = client.send(from_=sender, to=[to_phone], message=body)
    # resp is a list of SendSmsResponse
    return {"ok": True, "messageId": resp[0].message_id if resp else None}

# ── Teams (Webhook) – 공용 채널 ──────────────────────────────
def send_teams(title: str, body_md: str, webhook_url: str | None = None):
    return send_teams_message(title, body_md, webhook_url=webhook_url)

# ── 상위 레벨: 채널 라우팅 ───────────────────────────────────
def notify_owner(owner: Dict[str, str], channels: Sequence[str], title: str, body_md: str, graph_access_token: str | None):
    """
    channels: ["email","sms","teams"] 중 택1~3
    owner: {"email": "...", "phone": "..."}
    """
    results = {}
    if "email" in channels and owner.get("email") and graph_access_token:
        results["email"] = send_email_graph(graph_access_token, owner["email"], title, body_md)
    if "sms" in channels and owner.get("phone"):
        # 문자 본문은 짧게 요약해서 보낼 것을 권장
        text = body_md
        if len(text) > 300:  # SMS 길이 절단 (PoC)
            text = text[:297] + "..."
        results["sms"] = send_sms_acs(owner["phone"], text)
    if "teams" in channels:
        results["teams"] = send_teams(title, body_md, webhook_url=CONFIG.get("TEAMS_WEBHOOK_URL"))
    return results
