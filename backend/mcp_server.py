"""MCP (Model Context Protocol) server for IGC Trust Portal.

HTTP transport: POST /api/mcp/{key}
JSON-RPC 2.0 protocol.

ALL write tools create proposals for admin approval.
Claude cannot release, delete, approve, or touch payments.
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("mcp-server")

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "IGC Trust Portal"
SERVER_VERSION = "1.0.0"

# Dot-notation prefixes that Claude is never allowed to propose changing
BLOCKED_FIELD_PREFIXES = [
    "status", "internal_status", "client_status", "payment", "release",
    "release_history", "esign", "client_email", "trust_unlocked",
    "admin_created", "created_at", "updated_at", "id", "case_id", "user_id",
]

TOOLS = [
    {
        "name": "list_cases",
        "description": (
            "List all trust cases. Returns case IDs, client names, emails, "
            "current status, trust name. Use this to find a case_id before reading details."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "description": "Optional status filter, e.g. 'In Review' or 'Drafting Trust'",
                }
            },
        },
    },
    {
        "name": "read_case",
        "description": (
            "Read all data for a trust case by case_id. Returns grantors, trustees, "
            "beneficiaries, assets, documents, payment status, admin notes. "
            "SSNs are never returned."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "description": "Full UUID case_id"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "read_schedule_a",
        "description": "Read Schedule A (assets moved into trust) for a case in column order.",
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "read_intake_summary",
        "description": (
            "Read the intake asset summary for trust design. Includes asset breakdown by kind "
            "and state, original typed text, states with property, and unsure items."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "read_asset_account_numbers",
        "description": (
            "Read the full account numbers for all bank, investment, and life insurance "
            "items on a trust case. Required to draft Schedule A with the exact identifier "
            "for each account. Every call is written to the audit log."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "description": "Full UUID case_id"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "read_business_eins",
        "description": (
            "Read the full EIN (Employer Identification Number) for all business ownership "
            "items on a trust case. Required to draft Schedule A with the exact EIN for each business. "
            "Every call is written to the audit log."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"case_id": {"type": "string", "description": "Full UUID case_id"}},
            "required": ["case_id"],
        },
    },
    {
        "name": "read_client_activity",
        "description": (
            "Return client login and activity status for one case or all active cases. "
            "Fields: last_login_at, last_active_at, online_now (true if active within 5 min), active_case_id. "
            "Useful for knowing when it is safe to publish or when to call a client. "
            "Every call is written to the audit log."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string", "description": "Full UUID case_id — omit to get all cases"},
            },
            "required": [],
        },
    },
    {
        "name": "propose_field_change",
        "description": (
            "Use dot notation for nested fields (e.g. 'trust_name', 'grantors.0.full_legal_name'). "
            "Blocked fields: status, payment, release, client_email, trust_unlocked, and IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "field_path": {
                    "type": "string",
                    "description": "Dot-notation field path, e.g. 'trust_name'",
                },
                "new_value": {"description": "Proposed new value (any type)"},
                "reason": {"type": "string", "description": "Why this change is needed (shown to admin)"},
            },
            "required": ["case_id", "field_path", "new_value", "reason"],
        },
    },
    {
        "name": "propose_client_message",
        "description": (
            "Propose a message to send to the client via email. "
            "Admin must approve AND choose to send it. "
            "5th grade reading level. No dashes of any kind."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "subject": {"type": "string", "description": "Email subject line"},
                "message": {
                    "type": "string",
                    "description": "Full message text. Plain sentences. No dashes. 5th grade level.",
                },
                "reason": {"type": "string", "description": "Why this message should be sent (shown to admin)"},
            },
            "required": ["case_id", "subject", "message"],
        },
    },
    {
        "name": "propose_admin_note",
        "description": (
            "Propose an admin note to add to a case. Admin must approve it before it appears. "
            "Use this to flag follow-ups, summarize findings, or document recommendations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "case_id": {"type": "string"},
                "note": {"type": "string", "description": "Note text (shown to admin for review)"},
            },
            "required": ["case_id", "note"],
        },
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ok(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _text(content: str) -> dict:
    return {"content": [{"type": "text", "text": content}]}


def _is_blocked_field(field_path: str) -> bool:
    lower = field_path.lower().strip()
    return any(lower == p or lower.startswith(p + ".") for p in BLOCKED_FIELD_PREFIXES)


async def handle_request(body: dict, db, audit_key_id: str) -> dict:
    method = body.get("method", "")
    params = body.get("params") or {}
    req_id = body.get("id")

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method in ("notifications/initialized", "ping"):
        return _ok(req_id, {})

    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = await _call_tool(tool_name, args, db, audit_key_id)
        except Exception as e:
            logger.exception("tool error in %s", tool_name)
            return _error(req_id, -32603, str(e))
        return _ok(req_id, result)

    return _error(req_id, -32601, f"Method not found: {method}")


async def _call_tool(name: str, args: dict, db, audit_key_id: str) -> dict:
    if name == "list_cases":
        return await _list_cases(args, db)
    if name == "read_case":
        return await _read_case(args, db)
    if name == "read_schedule_a":
        return await _read_schedule_a(args, db)
    if name == "read_intake_summary":
        return await _read_intake_summary(args, db)
    if name == "read_asset_account_numbers":
        return await _read_asset_account_numbers(args, db, audit_key_id)
    if name == "read_business_eins":
        return await _read_business_eins(args, db, audit_key_id)
    if name == "read_client_activity":
        return await _read_client_activity(args, db, audit_key_id)
    if name == "propose_field_change":
        return await _propose_field_change(args, db, audit_key_id)
    if name == "propose_client_message":
        return await _propose_client_message(args, db, audit_key_id)
    if name == "propose_admin_note":
        return await _propose_admin_note(args, db, audit_key_id)
    raise ValueError(f"Unknown tool: {name}")


async def _list_cases(args: dict, db) -> dict:
    query = {}
    if args.get("status_filter"):
        query["status"] = args["status_filter"]
    cases = await db.trust_cases.find(query, {
        "_id": 0, "id": 1, "client_name": 1, "client_email": 1,
        "status": 1, "trust_name": 1, "intake_path": 1, "created_at": 1,
    }).sort("created_at", -1).to_list(100)
    lines = [
        f"- {c.get('id','')[:8]} | {c.get('client_name','?')} <{c.get('client_email','')}> "
        f"| {c.get('status','?')} | Trust: {c.get('trust_name','unnamed')}"
        for c in cases
    ]
    return _text(f"Found {len(cases)} case(s):\n" + "\n".join(lines) if lines else "No cases found.")


async def _read_case(args: dict, db) -> dict:
    cid = args.get("case_id", "")
    case = await db.trust_cases.find_one(
        {"$or": [{"id": cid}, {"id": {"$regex": f"^{cid}", "$options": "i"}}]},
        {"_id": 0, "password_hash": 0},
    )
    if not case:
        return _text(f"Case not found: {cid}")
    for g in (case.get("grantors") or []):
        g.pop("ssn", None)
        g.pop("ssn_encrypted", None)
    # Strip encrypted account numbers — use read_asset_account_numbers tool for those
    for it in (case.get("asset_items") or []):
        it.pop("account_number", None)
    pay = case.get("payment") or {}
    pay.pop("stripe_client_secret", None)
    return _text(json.dumps(case, default=str, indent=2))


async def _read_schedule_a(args: dict, db) -> dict:
    from asset_items import schedule_a, description_text, method_text
    cid = args.get("case_id", "")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "asset_items": 1})
    if not case:
        return _text(f"Case not found: {cid}")
    sa = schedule_a(case.get("asset_items") or [])
    rows = []
    for key, label in (("part_i", "Part I"), ("part_ii", "Part II")):
        for r in sa[key]:
            rows.append(
                f"{label} #{r['number']}: {r['description_of_property']} | "
                f"Date: {r['date_delivered'] or 'not filled'} | "
                f"Method: {r['instrument_or_method_of_transfer'] or 'not filled'}"
            )
    if not rows:
        return _text("No items marked 'Moved into trust' on this case.")
    return _text(f"Schedule A ({len(rows)} item(s)):\n" + "\n".join(rows))


async def _read_intake_summary(args: dict, db) -> dict:
    from asset_items import intake_summary
    cid = args.get("case_id", "")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0})
    if not case:
        return _text(f"Case not found: {cid}")
    return _text(json.dumps(intake_summary(case), default=str, indent=2))


async def _read_asset_account_numbers(args: dict, db, actor_key_id: str = "") -> dict:
    """Return full decrypted account numbers for ACCT_KINDS items. Writes audit log every call."""
    import sys, os, uuid as _uuid, datetime as _dt
    sys.path.insert(0, os.path.dirname(__file__))
    import crypto as _crypto
    from asset_items import ACCT_KINDS
    cid = args.get("case_id", "")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "asset_items": 1, "client_name": 1})
    if not case:
        return _text(f"Case not found: {cid}")
    items = [
        i for i in (case.get("asset_items") or [])
        if not i.get("deleted") and i.get("kind") in ACCT_KINDS
    ]
    if not items:
        return _text("No bank, investment, or life insurance items found on this case.")
    lines = []
    for it in items:
        raw = it.get("account_number", "")
        plain = _crypto.decrypt_account_number(raw) if raw else "(not provided)"
        lines.append(f"- {it.get('description','?')} [{it.get('kind','?')}]: account number {plain}")
    try:
        await db.account_number_audit_log.insert_one({
            "id": str(_uuid.uuid4()), "action": "mcp_read",
            "case_id": cid, "mcp_key_id": actor_key_id,
            "client_name": case.get("client_name", ""),
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat()
        })
    except Exception:
        pass
    result = f"Full account numbers for {case.get('client_name','?')} ({cid[:8]}):\n" + "\n".join(lines)
    return _text(result)


async def _read_business_eins(args: dict, db, actor_key_id: str = "") -> dict:
    """Return full decrypted EINs for business ownership items. Writes audit log every call."""
    import sys, os, uuid as _uuid, datetime as _dt
    sys.path.insert(0, os.path.dirname(__file__))
    import crypto as _crypto
    cid = args.get("case_id", "")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "asset_items": 1, "client_name": 1})
    if not case:
        return _text(f"Case not found: {cid}")
    items = [
        i for i in (case.get("asset_items") or [])
        if not i.get("deleted") and i.get("kind") == "business"
    ]
    if not items:
        return _text("No business ownership items found on this case.")
    lines = []
    for it in items:
        bi = it.get("business_info") or {}
        raw = bi.get("ein", "")
        plain = _crypto.decrypt_account_number(raw) if raw else "(not provided)"
        legal_name = (bi.get("legal_name") or "").strip() or it.get("description", "?")
        lines.append(f"- {legal_name}: EIN {plain}")
    try:
        await db.account_number_audit_log.insert_one({
            "id": str(_uuid.uuid4()), "action": "mcp_read_business_ein",
            "case_id": cid, "mcp_key_id": actor_key_id,
            "client_name": case.get("client_name", ""),
            "at": _dt.datetime.now(_dt.timezone.utc).isoformat()
        })
    except Exception:
        pass
    result = f"Full EINs for {case.get('client_name','?')} ({cid[:8]}):\n" + "\n".join(lines)
    return _text(result)


async def _read_client_activity(args: dict, db, actor_key_id: str = "") -> dict:
    """Return last_login_at, last_active_at, online_now for one case or all cases.
    Every call is written to the audit log."""
    import sys, os, uuid as _uuid, datetime as _dt
    sys.path.insert(0, os.path.dirname(__file__))

    cid = (args.get("case_id") or "").strip()
    _now = _dt.datetime.now(_dt.timezone.utc)
    _five_ago = (_now - _dt.timedelta(minutes=5)).isoformat()

    # Fetch case(s) and join with users
    if cid:
        case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "id": 1, "client_id": 1, "client_name": 1, "client_email": 1})
        if not case:
            return _text(f"Case not found: {cid}")
        cases_to_check = [case]
    else:
        cases_to_check = await db.trust_cases.find(
            {"deleted": {"$ne": True}},
            {"_id": 0, "id": 1, "client_id": 1, "client_name": 1, "client_email": 1}
        ).sort("created_at", -1).to_list(100)

    # Collect user IDs
    user_ids = list({c.get("client_id") for c in cases_to_check if c.get("client_id")})
    users_map = {}
    if user_ids:
        async for u in db.users.find(
            {"id": {"$in": user_ids}},
            {"_id": 0, "id": 1, "last_login_at": 1, "last_active_at": 1, "active_case_id": 1}
        ):
            users_map[u["id"]] = u

    lines = []
    for c in cases_to_check:
        u = users_map.get(c.get("client_id") or "", {})
        last_active = u.get("last_active_at", "")
        online = False
        if last_active:
            try:
                _last_dt = _dt.datetime.fromisoformat(last_active.replace("Z", "+00:00"))
                online = (_now - _last_dt).total_seconds() < 300
            except Exception:
                pass
        name = (c.get("client_name") or c.get("client_email") or "?").strip()
        lines.append(
            f"- {name} (case {c['id'][:8]}):\n"
            f"  last_login_at: {u.get('last_login_at') or 'never'}\n"
            f"  last_active_at: {last_active or 'never'}\n"
            f"  online_now: {online}"
        )

    # Audit log
    try:
        await db.account_number_audit_log.insert_one({
            "id": str(_uuid.uuid4()), "action": "mcp_read_client_activity",
            "case_id": cid or "all", "mcp_key_id": actor_key_id,
            "at": _now.isoformat()
        })
    except Exception:
        pass

    header = f"Client activity ({len(lines)} case{'s' if len(lines) != 1 else ''}):"
    return _text(header + "\n" + "\n".join(lines))


async def _propose_field_change(args: dict, db, audit_key_id: str) -> dict:
    cid = args.get("case_id", "")
    field_path = args.get("field_path", "")
    new_value = args.get("new_value")
    reason = args.get("reason", "")
    if _is_blocked_field(field_path):
        return _text(f"Field '{field_path}' cannot be changed via this tool.")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "id": 1, "client_name": 1})
    if not case:
        return _text(f"Case not found: {cid}")
    proposal = {
        "id": uuid.uuid4().hex, "type": "field_change",
        "case_id": cid, "case_name": case.get("client_name", "?"),
        "field_path": field_path, "new_value": new_value, "reason": reason,
        "status": "pending", "created_at": _now(), "created_by_key": audit_key_id,
    }
    await db.mcp_proposals.insert_one(proposal)
    return _text(
        f"Proposal created (ID: {proposal['id'][:8]}). Admin will review this change "
        f"to '{field_path}' on case {cid[:8]}."
    )


async def _propose_client_message(args: dict, db, audit_key_id: str) -> dict:
    cid = args.get("case_id", "")
    subject = args.get("subject", "")
    message = args.get("message", "")
    reason = args.get("reason", "")
    case = await db.trust_cases.find_one(
        {"id": cid}, {"_id": 0, "id": 1, "client_name": 1, "client_email": 1}
    )
    if not case:
        return _text(f"Case not found: {cid}")
    proposal = {
        "id": uuid.uuid4().hex, "type": "client_message",
        "case_id": cid, "case_name": case.get("client_name", "?"),
        "to_email": case.get("client_email", ""), "subject": subject,
        "message": message, "reason": reason,
        "status": "pending", "sent": False,
        "created_at": _now(), "created_by_key": audit_key_id,
    }
    await db.mcp_proposals.insert_one(proposal)
    return _text(
        f"Message proposal created (ID: {proposal['id'][:8]}). Subject: '{subject}'. "
        f"Admin must approve and send it to {case.get('client_email','')}."
    )


async def _propose_admin_note(args: dict, db, audit_key_id: str) -> dict:
    cid = args.get("case_id", "")
    note = args.get("note", "")
    case = await db.trust_cases.find_one({"id": cid}, {"_id": 0, "id": 1, "client_name": 1})
    if not case:
        return _text(f"Case not found: {cid}")
    proposal = {
        "id": uuid.uuid4().hex, "type": "admin_note",
        "case_id": cid, "case_name": case.get("client_name", "?"),
        "note": note, "status": "pending",
        "created_at": _now(), "created_by_key": audit_key_id,
    }
    await db.mcp_proposals.insert_one(proposal)
    return _text(
        f"Note proposal created (ID: {proposal['id'][:8]}). Admin will review before it's added."
    )
