"""Nia AI Assistant router — trust-focused client chat.

The heavy lifting (system prompt, urgent-flag regex, LLM call) lives in
`nia_assistant.py`. This file just exposes the HTTP surface, applies a
per-IP + per-session rate limit, and persists turn history in Mongo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import jwt as _jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import nia_assistant

from routes._neo_state import state

logger = logging.getLogger("neo.nia")
router = APIRouter()


class NiaChatReq(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str = Field(min_length=6, max_length=120)
    case_id: Optional[str] = None
    client_first_name: Optional[str] = Field(default=None, max_length=80)


def build_routes():
    db = state.db
    now_iso = state.now_iso
    notify = state.notify
    get_jwt_secret = state.get_jwt_secret
    JWT_ALGORITHM = state.JWT_ALGORITHM

    @router.post("/nia/chat")
    async def nia_chat(body: NiaChatReq, request: Request):
        """Client-facing chat with Nia. Auth optional — Nia works pre-login too.
        Simple per-IP + per-session rate limit (20 messages / 5 min) to protect the LLM budget."""
        ip = (request.client.host if request.client else "unknown")
        now_ts = int(datetime.now(timezone.utc).timestamp())
        window_start = now_ts - 300
        await db.nia_rate.delete_many({"ts": {"$lt": window_start}})
        recent = await db.nia_rate.count_documents({
            "$or": [{"ip": ip}, {"session_id": body.session_id}],
            "ts": {"$gte": window_start},
        })
        if recent >= 20:
            raise HTTPException(429, "Slow down — please wait a moment before sending more messages.")
        await db.nia_rate.insert_one({"ip": ip, "session_id": body.session_id, "ts": now_ts})

        # Best-effort caller identification (not required).
        user = None
        try:
            token = request.cookies.get("access_token")
            if token:
                payload = _jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
                user = await db.users.find_one({"id": payload.get("sub")}, {"_id": 0, "password_hash": 0})
        except Exception:
            user = None

        doc = await db.nia_sessions.find_one({"session_id": body.session_id}, {"_id": 0})
        history = (doc or {}).get("turns", []) if doc else []

        first_name = body.client_first_name
        if not first_name and user:
            name = user.get("name") or ""
            first_name = (name.split(" ") or [""])[0]
        if not first_name and body.case_id:
            case = await db.trust_cases.find_one({"id": body.case_id}, {"_id": 0})
            if case:
                grantors = case.get("grantors") or []
                if grantors:
                    first_name = (grantors[0].get("first_name")
                                  or (grantors[0].get("full_legal_name") or "").split(" ")[0])

        urgent = nia_assistant.detect_urgent(body.message)

        try:
            reply = await nia_assistant.chat(
                history=history,
                message=body.message,
                session_id=body.session_id,
                client_first_name=first_name,
            )
        except Exception as e:
            logger.error(f"Nia chat failed: {e}")
            reply = ("I'm having a hard time reaching my brain right now — a member of the Iron Gate team "
                     "has been notified and will follow up shortly. In the meantime, please try again in a minute.")
            urgent = True

        new_turns = list(history) + [
            {"role": "user", "content": body.message, "at": now_iso()},
            {"role": "assistant", "content": reply, "at": now_iso()},
        ]
        trimmed = new_turns[-30:]

        await db.nia_sessions.update_one(
            {"session_id": body.session_id},
            {"$set": {
                "session_id": body.session_id,
                "turns": trimmed,
                "case_id": body.case_id,
                "user_id": (user or {}).get("id"),
                "updated_at": now_iso(),
            }},
            upsert=True,
        )

        if urgent:
            try:
                case_note = f" (case #{body.case_id[:8].upper()})" if body.case_id else ""
                who = ((user or {}).get("name")
                       or (user or {}).get("email")
                       or first_name or "A client")
                notify.notify_admin(
                    f"[IGC · Nia flagged URGENT] {who}{case_note}: \"{body.message[:180]}\""
                )
            except Exception as e:
                logger.error(f"Nia urgent whatsapp failed: {e}")

        return {"reply": reply, "urgent": urgent, "session_id": body.session_id}

    @router.get("/nia/history/{session_id}")
    async def nia_history(session_id: str):
        doc = await db.nia_sessions.find_one({"session_id": session_id}, {"_id": 0})
        return {"turns": (doc or {}).get("turns", [])}
