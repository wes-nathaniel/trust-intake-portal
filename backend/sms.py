"""Twilio SMS helper — graceful no-op when keys are missing."""
import os
import logging

logger = logging.getLogger("trust-portal")

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
ADMIN_PHONE_NUMBER = os.environ.get("ADMIN_PHONE_NUMBER", "").strip()


def is_enabled() -> bool:
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER)


def send_sms(to: str, body: str) -> bool:
    """Returns True if actually sent, False if mocked/failed."""
    if not is_enabled():
        logger.info(f"[sms-mock] to={to} body={body[:120]}")
        return False
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=body, from_=TWILIO_FROM_NUMBER, to=to)
        return True
    except Exception as e:
        logger.error(f"Twilio send failed: {e}")
        return False


def send_admin_sms(body: str) -> bool:
    if not ADMIN_PHONE_NUMBER:
        logger.info(f"[sms-mock:no-admin-phone] body={body[:120]}")
        return False
    return send_sms(ADMIN_PHONE_NUMBER, body)
