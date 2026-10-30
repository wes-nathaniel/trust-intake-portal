"""WhatsApp Cloud API (Meta) sender — same IGC number/credentials as the main IGC portal. No Twilio."""
import os
import re
import logging
import requests

logger = logging.getLogger("trust-portal")

GRAPH_API_VERSION = "v21.0"


def is_configured() -> bool:
    return bool(os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip() and os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip())


def normalize_phone(phone: str) -> str:
    d = re.sub(r"\D", "", phone or "")
    return f"1{d}" if len(d) == 10 else d


def send_template(to: str, name: str, params: list, lang: str = "en_US") -> dict:
    """Send an approved template (delivers outside WhatsApp's 24-hour window)."""
    if not is_configured():
        return {"ok": False, "error": "WhatsApp Cloud API not configured"}
    to_n = normalize_phone(to)
    if not to_n:
        return {"ok": False, "error": "No recipient phone"}
    comps = [{"type": "body", "parameters": [{"type": "text", "text": (str(p) or "-")[:500]} for p in params]}]
    try:
        r = requests.post(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{os.environ['WHATSAPP_PHONE_NUMBER_ID'].strip()}/messages",
            headers={"Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN'].strip()}"},
            json={"messaging_product": "whatsapp", "to": to_n, "type": "template",
                  "template": {"name": name, "language": {"code": lang}, "components": comps}},
            timeout=15,
        )
        data = r.json() if r.content else {}
        if r.ok and data.get("messages"):
            return {"ok": True, "message_id": data["messages"][0].get("id", "")}
        err = (data.get("error") or {}).get("message") or r.text[:300]
        logger.error(f"WhatsApp template send failed ({r.status_code}): {err}")
        return {"ok": False, "error": err}
    except Exception as e:
        logger.error(f"WhatsApp template send error: {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)[:300]}


def send_text(to: str, body: str) -> dict:
    """Send a plain-text WhatsApp message. Returns {"ok", "message_id"|"error"}."""
    if not is_configured():
        return {"ok": False, "error": "WhatsApp Cloud API not configured"}
    to_n = normalize_phone(to)
    if not to_n:
        return {"ok": False, "error": "No recipient phone"}
    try:
        r = requests.post(
            f"https://graph.facebook.com/{GRAPH_API_VERSION}/{os.environ['WHATSAPP_PHONE_NUMBER_ID'].strip()}/messages",
            headers={"Authorization": f"Bearer {os.environ['WHATSAPP_ACCESS_TOKEN'].strip()}"},
            json={"messaging_product": "whatsapp", "to": to_n, "type": "text",
                  "text": {"preview_url": False, "body": body[:4096]}},
            timeout=15,
        )
        data = r.json() if r.content else {}
        if r.ok and data.get("messages"):
            return {"ok": True, "message_id": data["messages"][0].get("id", "")}
        err = (data.get("error") or {}).get("message") or r.text[:300]
        logger.error(f"WhatsApp Cloud API send failed ({r.status_code}): {err}")
        return {"ok": False, "error": err}
    except Exception as e:
        logger.error(f"WhatsApp Cloud API send error: {type(e).__name__}: {e}")
        return {"ok": False, "error": str(e)[:300]}
