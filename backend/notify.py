"""Multi-channel admin notification fan-out.

Sends the same short message to admin via SMS (Twilio), WhatsApp (Twilio),
and Email (Resend), so the firm never misses an event regardless of the
channel they prefer.
"""
import os
import logging

import resend
import sms
import whatsapp


logger = logging.getLogger("trust-portal")

WHATSAPP_NOTIFY_ADMIN = os.environ.get("WHATSAPP_NOTIFY_ADMIN", "true").strip().lower() in ("1", "true", "yes", "on")
EMAIL_NOTIFY_ADMIN = os.environ.get("EMAIL_NOTIFY_ADMIN", "true").strip().lower() in ("1", "true", "yes", "on")

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ADMIN_EMAIL = os.environ.get("ADMIN_NOTIFY_EMAIL", "wes@igchq.com")
NOTIFY_FROM_EMAIL = os.environ.get("NOTIFY_FROM_EMAIL", "notifications@igchq.com")

# Configure Resend
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY


def notify_admin(body: str, subject: str = "IGC Trust Portal — New Submission") -> dict:
    """Send body to the admin via SMS, WhatsApp (if enabled), and Email (if enabled).

    Returns a dict describing which channels succeeded — useful for logging
    but callers can safely ignore the return value.
    """
    result = {"sms": False, "whatsapp": False, "email": False}

    # SMS via Twilio
    try:
        result["sms"] = bool(sms.send_admin_sms(body))
    except Exception as e:
        logger.error(f"notify_admin SMS failed: {e}")

    # WhatsApp via Twilio
    if WHATSAPP_NOTIFY_ADMIN:
        try:
            result["whatsapp"] = bool(whatsapp.send_admin_whatsapp(body))
        except Exception as e:
            logger.error(f"notify_admin WhatsApp failed: {e}")

    # Email via Resend
    if EMAIL_NOTIFY_ADMIN and RESEND_API_KEY:
        try:
            email_body_html = f"""
<div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
  <h2 style="color: #1a1a2e; border-bottom: 2px solid #c9a84c; padding-bottom: 10px;">
    IGC Trust Portal — New Activity
  </h2>
  <div style="background: #f8f8f8; padding: 16px; border-radius: 6px; margin: 16px 0;">
    <p style="margin: 0; font-size: 15px; color: #333;">{body}</p>
  </div>
  <p style="color: #888; font-size: 12px;">
    Iron Gate Consulting · Trust Portal · <a href="https://trust.igchq.com/admin">View Admin Panel</a>
  </p>
</div>
"""
            params = {
                "from": f"IGC Trust Portal <{NOTIFY_FROM_EMAIL}>",
                "to": [ADMIN_EMAIL],
                "subject": subject,
                "html": email_body_html,
            }
            resp = resend.Emails.send(params)
            result["email"] = bool(resp and resp.get("id"))
            logger.info(f"notify_admin email sent: {resp}")
        except Exception as e:
            logger.error(f"notify_admin Email failed: {e}")
    elif EMAIL_NOTIFY_ADMIN and not RESEND_API_KEY:
        logger.warning("notify_admin: EMAIL_NOTIFY_ADMIN is true but RESEND_API_KEY is not set")

    return result
