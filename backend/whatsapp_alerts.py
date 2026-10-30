"""Admin WhatsApp alerts (Intake Started, ID / Proof of Address uploaded, client login/logout,
Waiting on Documents, In Review). Recipient comes from settings.admin_notification_phone."""
import asyncio
import logging
from datetime import datetime, timezone

import whatsapp_utils

logger = logging.getLogger("trust-portal")

SETTINGS_ID = "notifications"
DEFAULT_ADMIN_PHONE = "+19545983681"
DEFAULT_TEMPLATE = "igc_admin_alert"
_bg = set()


async def ensure_settings(db):
    await db.settings.update_one(
        {"id": SETTINGS_ID},
        {"$setOnInsert": {"id": SETTINGS_ID, "admin_notification_phone": DEFAULT_ADMIN_PHONE,
                          "admin_email_alerts_enabled": True}},
        upsert=True,
    )


async def get_settings(db) -> dict:
    return await db.settings.find_one({"id": SETTINGS_ID}, {"_id": 0}) or {}


async def admin_email_enabled(db) -> bool:
    return (await get_settings(db)).get("admin_email_alerts_enabled", True) is not False


async def send_admin_alert(db, title: str, client_name: str, case_name: str, extra: str = "") -> dict:
    s = await get_settings(db)
    phone = s.get("admin_notification_phone") or ""
    template = s.get("admin_alert_template") or DEFAULT_TEMPLATE
    res = await asyncio.to_thread(
        whatsapp_utils.send_template, phone, template,
        [("status", title), ("client_name", client_name or "-"), ("case_name", case_name or "-")],
        s.get("admin_alert_template_language") or "en_US")
    res["via"] = "template"
    if not res.get("ok"):
        # Fallback: plain text (delivers only inside WhatsApp's 24-hour window)
        tmpl_err = res.get("error", "")
        body = f"IGC Alert: {title}\nClient: {client_name or '—'}\nCase: {case_name or '—'}" + (f"\n{extra}" if extra else "")
        res = await asyncio.to_thread(whatsapp_utils.send_text, phone, body)
        res.update({"via": "text", "template_error": tmpl_err})
    await db.admin_whatsapp_log.insert_one({
        "title": title, "client_name": client_name, "case_name": case_name, "ok": res.get("ok"),
        "via": res.get("via", ""), "template_error": res.get("template_error", ""),
        "message_id": res.get("message_id", ""), "error": res.get("error", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return res


def fire(db, title: str, client_name: str, case_name: str, extra: str = ""):
    """Fire-and-forget so alerts never slow down or break the client's request."""
    async def _run():
        try:
            await send_admin_alert(db, title, client_name, case_name, extra)
        except Exception as e:
            logger.error(f"admin WhatsApp alert failed ({title}): {e}")
    t = asyncio.create_task(_run())
    _bg.add(t)
    t.add_done_callback(_bg.discard)
