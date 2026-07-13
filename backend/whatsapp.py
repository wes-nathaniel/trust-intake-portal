"""Twilio WhatsApp helper — reuses the same Twilio credentials as sms.py.

Twilio WhatsApp uses the standard Messages API with a `whatsapp:` prefix on
both the `from_` and `to` numbers. During development you can use the Twilio
Sandbox for WhatsApp (from = whatsapp:+14155238886). For production, provision
a WhatsApp-enabled sender in the Twilio Console and set TWILIO_WHATSAPP_FROM
to the E.164 form prefixed with `whatsapp:`.
"""
import os
import logging

logger = logging.getLogger("trust-portal")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "").strip()
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "").strip()


def _wa(number: str) -> str:
    """Ensure a phone number is in the `whatsapp:+E164` format Twilio requires."""
    n = (number or "").strip()
    if not n:
        return ""
    if n.startswith("whatsapp:"):
        return n
    if not n.startswith("+"):
        # Assume US if raw digits provided
        digits = "".join(ch for ch in n if ch.isdigit())
        if len(digits) == 10:
            n = "+1" + digits
        else:
            n = "+" + digits
    return "whatsapp:" + n


def is_enabled() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_WHATSAPP_FROM)


def send_whatsapp(to: str, body: str) -> bool:
    """Send a WhatsApp message. Returns True if actually sent, False if mocked/failed."""
    if not is_enabled():
        logger.info(f"[whatsapp-mock] to={to} body={body[:120]}")
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(
            body=body,
            from_=_wa(TWILIO_WHATSAPP_FROM),
            to=_wa(to),
        )
        return True
    except Exception as e:
        logger.error(f"Twilio WhatsApp send failed: {e}")
        return False


def send_admin_whatsapp(body: str) -> bool:
    if not ADMIN_WHATSAPP_NUMBER:
        logger.info(f"[whatsapp-mock:no-admin-whatsapp] body={body[:120]}")
        return False
    return send_whatsapp(ADMIN_WHATSAPP_NUMBER, body)
