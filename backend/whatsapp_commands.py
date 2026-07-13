"""WhatsApp admin command parser.

Handles messages sent from the ADMIN_WHATSAPP_NUMBER to the Twilio WhatsApp
sender, letting the firm operate the portal from their phone. Commands are
case-insensitive and use a slash prefix.

Recognized commands:
  /help                                    → list of commands
  /whoami                                  → sanity check ("Recognized as admin support@…")
  /cases <status?>                         → list up to 10 cases in given status (default: all active)
  /case <short-id> status <new-status>     → update case status
  /case <short-id> note <text>             → append internal admin note
  /case <short-id> info                    → basic case info + last 3 events

Short-id is the first 8 chars of the case UUID (uppercase in UI). Match is
case-insensitive and prefix-based against the full id.

`register_status_updater(fn)` and `register_note_appender(fn)` are called from
server.py at import time so we avoid a circular import.
"""
from __future__ import annotations

import logging
from typing import Optional, Callable, List, Awaitable

logger = logging.getLogger("trust-portal")

# --- state injected from server.py (avoids circular import) ---
_db = None
_statuses: List[str] = []
_now_iso: Optional[Callable[[], str]] = None
_update_status: Optional[Callable[[str, str], Awaitable[None]]] = None
_append_note: Optional[Callable[[str, str], Awaitable[dict]]] = None


def configure(*, db, statuses, now_iso, update_status, append_note):
    """Wire up dependencies at server startup."""
    global _db, _statuses, _now_iso, _update_status, _append_note
    _db = db
    _statuses = list(statuses)
    _now_iso = now_iso
    _update_status = update_status
    _append_note = append_note


HELP_TEXT = (
    "IGC Portal WhatsApp commands:\n"
    "  /whoami\n"
    "  /cases [status]\n"
    "  /case <id> info\n"
    "  /case <id> status <new-status>\n"
    "  /case <id> note <text>\n"
    "\nStatuses: " + ", ".join([
        "Intake Started", "Intake In Progress", "Waiting on Documents",
        "In Review", "Drafting Trust", "Ready for Client Review",
        "Ready for Payment", "Pending Payment Verification",
        "Payment Verified", "Completed",
    ])
)


def _match_status(text: str) -> Optional[str]:
    """Fuzzy-match a status name (case/space-insensitive)."""
    t = "".join(ch for ch in text.lower() if ch.isalnum())
    for s in _statuses:
        if "".join(ch for ch in s.lower() if ch.isalnum()) == t:
            return s
    # Prefix fallback
    for s in _statuses:
        if s.lower().startswith(text.lower()):
            return s
    return None


async def _find_case_by_short_id(short_id: str) -> Optional[dict]:
    """Match a case by the first 8 chars of its UUID (case-insensitive)."""
    sid = short_id.strip().lower()
    if not sid:
        return None
    # Regex-anchored prefix match on `id`
    import re
    pattern = "^" + re.escape(sid)
    doc = await _db.trust_cases.find_one(
        {"id": {"$regex": pattern, "$options": "i"}},
        {"_id": 0},
    )
    return doc


async def handle_admin_command(body: str, admin_number: str, admin_email: Optional[str] = None) -> str:
    """Parse and execute an admin command. Always returns a reply string
    (which the webhook will send back via WhatsApp)."""
    text = (body or "").strip()
    if not text.startswith("/"):
        return (
            "Hi — this is the IGC admin WhatsApp channel. "
            "Send /help for the command list."
        )

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd in ("/help", "/?"):
        return HELP_TEXT

    if cmd == "/whoami":
        who = admin_email or "unknown"
        return f"Recognized as admin ({who}) from {admin_number}."

    if cmd == "/cases":
        return await _cmd_cases(rest)

    if cmd == "/case":
        return await _cmd_case(rest)

    return f"Unknown command: {cmd}. Send /help."


async def _cmd_cases(rest: str) -> str:
    q: dict = {"archived": {"$ne": True}}
    label = "active"
    if rest.strip():
        matched = _match_status(rest.strip())
        if not matched:
            return f"Unknown status '{rest.strip()}'. Send /help."
        q["status"] = matched
        label = matched
    docs = await _db.trust_cases.find(
        q,
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "status": 1},
    ).sort("updated_at", -1).to_list(10)
    if not docs:
        return f"No {label} cases."
    lines = [f"{label.upper()} — showing {len(docs)}:"]
    for d in docs:
        short = d["id"][:8].upper()
        name = d.get("client_name") or d.get("client_email") or "—"
        lines.append(f"• #{short} · {name} · {d.get('status') or '—'}")
    return "\n".join(lines)


async def _cmd_case(rest: str) -> str:
    parts = rest.split(maxsplit=2)
    if not parts:
        return "Usage: /case <id> <info|status|note> [value]"
    short_id = parts[0]
    sub = (parts[1].lower() if len(parts) > 1 else "info")
    value = parts[2] if len(parts) > 2 else ""

    case = await _find_case_by_short_id(short_id)
    if not case:
        return f"No case matches #{short_id.upper()}."

    case_id = case["id"]
    short = case_id[:8].upper()
    name = case.get("client_name") or case.get("client_email") or "—"

    if sub == "info":
        notes = case.get("admin_notes") or []
        recent = notes[-3:] if notes else []
        out = [
            f"#{short} · {name}",
            f"Status: {case.get('status') or '—'}",
            f"Email: {case.get('client_email') or '—'}",
            f"Trust type: {case.get('trust_type') or '—'}",
        ]
        if recent:
            out.append("Recent notes:")
            for n in recent:
                body = n.get("note") or n.get("body") or ""
                out.append(f" · {body[:80]}")
        return "\n".join(out)

    if sub == "status":
        if not value.strip():
            return "Usage: /case <id> status <new-status>. Send /help for the list."
        matched = _match_status(value.strip())
        if not matched:
            return f"Unknown status '{value}'. Send /help."
        try:
            await _update_status(case_id, matched)
            return f"✓ Case #{short} ({name}) → {matched}"
        except Exception as e:
            logger.error(f"WhatsApp /case status failed: {e}")
            return f"Failed to update status: {e}"

    if sub == "note":
        if not value.strip():
            return "Usage: /case <id> note <text>"
        try:
            note = await _append_note(case_id, value.strip())
            body = note.get("note") or note.get("body") or ""
            return f"✓ Note added to #{short} ({name}): \"{body[:80]}\""
        except Exception as e:
            logger.error(f"WhatsApp /case note failed: {e}")
            return f"Failed to add note: {e}"

    return f"Unknown case sub-command '{sub}'. Try info | status | note."
