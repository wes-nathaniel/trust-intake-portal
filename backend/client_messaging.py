"""Client text alerts via Signal House (SMS) + WhatsApp (opted-in clients only).

PREPARED BUT NOT ACTIVE: SIGNALHOUSE_ACTIVE stays False until the owner says to turn it on.
While inactive, notify_client_text() sends nothing and returns False so callers use email.
"""
import os
import re
import asyncio
import logging
import requests

import whatsapp

logger = logging.getLogger("trust-portal")

SIGNALHOUSE_ACTIVE = False
SIGNALHOUSE_BASE_URL = "https://v2.signalhouse.io"


def _digits(n: str) -> str:
    d = re.sub(r"\D", "", n or "")
    return f"1{d}" if len(d) == 10 else d


def signalhouse_configured() -> bool:
    return bool(os.environ.get("SIGNALHOUSE_API_KEY", "").strip() and os.environ.get("SIGNALHOUSE_FROM_NUMBER", "").strip())


def send_sms(to: str, body: str) -> bool:
    if not (SIGNALHOUSE_ACTIVE and signalhouse_configured() and _digits(to)):
        return False
    try:
        r = requests.post(
            f"{SIGNALHOUSE_BASE_URL}/message/sms",
            headers={"Authorization": f"Bearer {os.environ['SIGNALHOUSE_API_KEY'].strip()}"},
            json={"senderPhoneNumber": _digits(os.environ["SIGNALHOUSE_FROM_NUMBER"]),
                  "recipientPhoneNumber": _digits(to), "messageBody": body},
            timeout=15,
        )
        data = r.json() if r.content else {}
        payload = data.get("data", data) if isinstance(data, dict) else {}
        ok = r.ok and (payload.get("enqueuedCount") or 0) > 0
        if not ok:
            logger.error(f"Signal House SMS not accepted ({r.status_code}): {str(data)[:300]}")
        return ok
    except Exception as e:
        logger.error(f"Signal House SMS failed: {type(e).__name__}: {e}")
        return False


async def notify_client_text(phone: str, body: str, whatsapp_opt_in: bool = False) -> bool:
    """SMS to everyone with a phone; WhatsApp only if opted in. True if any channel accepted."""
    if not phone:
        return False
    sent = await asyncio.to_thread(send_sms, phone, body)
    if whatsapp_opt_in and SIGNALHOUSE_ACTIVE and whatsapp.CLIENT_WHATSAPP_ENABLED:
        sent = bool(await asyncio.to_thread(whatsapp.send_whatsapp, phone, body)) or sent
    return sent


def status() -> dict:
    return {"active": SIGNALHOUSE_ACTIVE, "configured": signalhouse_configured(),
            "client_whatsapp_enabled": whatsapp.CLIENT_WHATSAPP_ENABLED}
