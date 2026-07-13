"""Multi-channel admin notification fan-out.

Sends the same short message to admin via SMS (Twilio) and WhatsApp (Twilio),
so the firm never misses an event regardless of the channel they prefer.
"""
import os
import logging

import sms
import whatsapp

logger = logging.getLogger("trust-portal")

WHATSAPP_NOTIFY_ADMIN = os.environ.get("WHATSAPP_NOTIFY_ADMIN", "true").strip().lower() in ("1", "true", "yes", "on")


def notify_admin(body: str) -> dict:
    """Send `body` to the admin via SMS and (if enabled) WhatsApp.

    Returns a dict describing which channels succeeded — useful for logging
    but callers can safely ignore the return value.
    """
    result = {"sms": False, "whatsapp": False}
    try:
        result["sms"] = bool(sms.send_admin_sms(body))
    except Exception as e:
        logger.error(f"notify_admin SMS failed: {e}")
    if WHATSAPP_NOTIFY_ADMIN:
        try:
            result["whatsapp"] = bool(whatsapp.send_admin_whatsapp(body))
        except Exception as e:
            logger.error(f"notify_admin WhatsApp failed: {e}")
    return result
