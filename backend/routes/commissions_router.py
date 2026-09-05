"""Reps / Managers CRUD, public rep resolver, and the commission engine.

The commission split logic itself lives in `commissions.py` (a pure module).
This router file just exposes the HTTP surface + async DB access + WhatsApp
notifications on approve/deny.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

import commissions as commissions_mod
import whatsapp

from routes._neo_state import state

logger = logging.getLogger("neo.commissions")
router = APIRouter()


# ---------- Schemas ----------

class RepUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    rep_code: str = Field(min_length=2, max_length=32)
    phone: Optional[str] = Field(default="", max_length=30)
    manager_id: Optional[str] = None
    active: bool = True


class ManagerUpsert(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: Optional[str] = Field(default="", max_length=30)
    active: bool = True


class CommissionApproveReq(BaseModel):
    note: Optional[str] = None


# ---------- Helpers (module-level so other routers can import them) ----------

async def _notify_commission_released(c: dict):
    """WhatsApp/SMS the rep (and manager) that their commission is approved."""
    rep_amt = f"${(c.get('rep_cents') or 0)/100:,.2f}"
    try:
        if c.get("rep_phone"):
            whatsapp.send_whatsapp(
                c["rep_phone"],
                f"IGC: Your commission of {rep_amt} for {c.get('client_name')} ({c.get('product')}) is approved and being released."
            )
    except Exception as e:
        logger.error(f"rep commission whatsapp failed: {e}")
    if c.get("manager_id"):
        try:
            mgr_amt = f"${(c.get('manager_cents') or 0)/100:,.2f}"
            if c.get("manager_phone"):
                whatsapp.send_whatsapp(
                    c["manager_phone"],
                    f"IGC: Your override of {mgr_amt} for {c.get('client_name')} ({c.get('product')}) is approved and being released."
                )
        except Exception as e:
            logger.error(f"mgr commission whatsapp failed: {e}")


async def _create_commission_hold(case: dict, payment_record: dict):
    """Insert a pending-approval commission row + fire Stage-4 WhatsApp."""
    db = state.db
    notify = state.notify
    new_id = state.new_id
    now_iso = state.now_iso
    secrets_mod = state.secrets

    rep_code = case.get("rep_code")
    if not rep_code:
        return
    rep = await db.reps.find_one({"rep_code": rep_code}, {"_id": 0})
    if not rep:
        return
    manager = None
    if rep.get("manager_id"):
        manager = await db.managers.find_one({"id": rep["manager_id"]}, {"_id": 0})

    lookup_key = payment_record.get("lookup_key")
    split = commissions_mod.split_for(lookup_key, has_manager=bool(manager))
    if split["rep_cents"] <= 0:
        return

    existing = await db.commissions.find_one({"case_id": case["id"], "lookup_key": lookup_key})
    if existing:
        return

    approval_code = secrets_mod.token_urlsafe(6).upper().replace("_", "").replace("-", "")[:6]
    commission = {
        "id": new_id(),
        "case_id": case["id"],
        "case_short": case["id"][:8].upper(),
        "client_name": case.get("client_name") or case.get("client_email"),
        "product": commissions_mod.product_display_name(lookup_key or ""),
        "lookup_key": lookup_key,
        "rep_id": rep["id"],
        "rep_code": rep["rep_code"],
        "rep_name": rep.get("name"),
        "rep_email": rep.get("email"),
        "rep_phone": rep.get("phone"),
        "manager_id": (manager or {}).get("id"),
        "manager_name": (manager or {}).get("name"),
        "manager_phone": (manager or {}).get("phone"),
        "rep_cents": split["rep_cents"],
        "manager_cents": split["manager_cents"],
        "status": "pending_approval",
        "approval_code": approval_code,
        "created_at": now_iso(),
    }
    await db.commissions.insert_one(commission)

    try:
        rep_amt = f"${split['rep_cents']/100:,.2f}"
        mgr_amt = f"${split['manager_cents']/100:,.2f}" if split["manager_cents"] else None
        lines = [
            f"[IGC · Stage 4 · Commission Hold] {commission['product']} — {commission['client_name']} (case #{commission['case_short']}).",
            f"Rep: {rep.get('name')} ({rep['rep_code']}) → {rep_amt}",
        ]
        if manager:
            lines.append(f"Manager: {manager.get('name')} → {mgr_amt} override")
        lines.append(f"Reply APPROVE {approval_code} to release. Reply DENY {approval_code} to void.")
        notify.notify_admin("\n".join(lines))
    except Exception as e:
        logger.error(f"NEO stage-4 WhatsApp alert failed: {e}")


async def _wa_approve_commission(code: str, source: str) -> Optional[dict]:
    """Approve a commission by approval_code (called from whatsapp_commands)."""
    db = state.db
    now_iso = state.now_iso
    c = await db.commissions.find_one({"approval_code": code}, {"_id": 0})
    if not c:
        return None
    if c.get("status") != "pending_approval":
        return {"already": True, "status": c.get("status")}
    await db.commissions.update_one(
        {"id": c["id"]},
        {"$set": {"status": "approved", "approved_at": now_iso(), "approved_source": source}},
    )
    c = await db.commissions.find_one({"id": c["id"]}, {"_id": 0})
    try:
        await _notify_commission_released(c)
    except Exception as e:
        logger.error(f"commission released notify failed: {e}")
    return c


async def _wa_deny_commission(code: str, source: str) -> Optional[dict]:
    db = state.db
    now_iso = state.now_iso
    c = await db.commissions.find_one({"approval_code": code}, {"_id": 0})
    if not c:
        return None
    if c.get("status") != "pending_approval":
        return {"already": True, "status": c.get("status")}
    await db.commissions.update_one(
        {"id": c["id"]},
        {"$set": {"status": "denied", "denied_at": now_iso(), "denied_source": source}},
    )
    return await db.commissions.find_one({"id": c["id"]}, {"_id": 0})


# ---------- Route builder ----------

def build_routes():
    """Register the routes on `router`. Must be called after configure()."""
    db = state.db
    require_admin = state.require_admin
    new_id = state.new_id
    now_iso = state.now_iso

    # Reps
    @router.get("/admin/reps")
    async def list_reps(_: dict = Depends(require_admin)):
        reps = await db.reps.find({}, {"_id": 0}).to_list(500)
        return {"reps": reps}

    @router.post("/admin/reps")
    async def create_rep(body: RepUpsert, _: dict = Depends(require_admin)):
        code = body.rep_code.strip().upper()
        if await db.reps.find_one({"rep_code": code}):
            raise HTTPException(409, f"Rep code {code} already exists")
        if body.manager_id and not await db.managers.find_one({"id": body.manager_id}):
            raise HTTPException(400, "Manager not found")
        rep = {
            "id": new_id(),
            "name": body.name.strip(),
            "email": body.email.lower(),
            "rep_code": code,
            "phone": (body.phone or "").strip(),
            "manager_id": body.manager_id or None,
            "active": body.active,
            "created_at": now_iso(),
        }
        await db.reps.insert_one(rep)
        rep.pop("_id", None)
        return {"rep": rep}

    @router.put("/admin/reps/{rep_id}")
    async def update_rep(rep_id: str, body: RepUpsert, _: dict = Depends(require_admin)):
        code = body.rep_code.strip().upper()
        dup = await db.reps.find_one({"rep_code": code, "id": {"$ne": rep_id}})
        if dup:
            raise HTTPException(409, f"Rep code {code} already exists")
        if body.manager_id and not await db.managers.find_one({"id": body.manager_id}):
            raise HTTPException(400, "Manager not found")
        result = await db.reps.update_one({"id": rep_id}, {"$set": {
            "name": body.name.strip(),
            "email": body.email.lower(),
            "rep_code": code,
            "phone": (body.phone or "").strip(),
            "manager_id": body.manager_id or None,
            "active": body.active,
            "updated_at": now_iso(),
        }})
        if not result.matched_count:
            raise HTTPException(404, "Rep not found")
        rep = await db.reps.find_one({"id": rep_id}, {"_id": 0})
        return {"rep": rep}

    @router.delete("/admin/reps/{rep_id}")
    async def delete_rep(rep_id: str, _: dict = Depends(require_admin)):
        res = await db.reps.delete_one({"id": rep_id})
        if not res.deleted_count:
            raise HTTPException(404, "Rep not found")
        return {"ok": True}

    # Managers
    @router.get("/admin/managers")
    async def list_managers(_: dict = Depends(require_admin)):
        mgrs = await db.managers.find({}, {"_id": 0}).to_list(500)
        return {"managers": mgrs}

    @router.post("/admin/managers")
    async def create_manager(body: ManagerUpsert, _: dict = Depends(require_admin)):
        if await db.managers.find_one({"email": body.email.lower()}):
            raise HTTPException(409, "Manager email already exists")
        m = {
            "id": new_id(),
            "name": body.name.strip(),
            "email": body.email.lower(),
            "phone": (body.phone or "").strip(),
            "active": body.active,
            "created_at": now_iso(),
        }
        await db.managers.insert_one(m)
        m.pop("_id", None)
        return {"manager": m}

    @router.put("/admin/managers/{mgr_id}")
    async def update_manager(mgr_id: str, body: ManagerUpsert, _: dict = Depends(require_admin)):
        result = await db.managers.update_one({"id": mgr_id}, {"$set": {
            "name": body.name.strip(),
            "email": body.email.lower(),
            "phone": (body.phone or "").strip(),
            "active": body.active,
            "updated_at": now_iso(),
        }})
        if not result.matched_count:
            raise HTTPException(404, "Manager not found")
        m = await db.managers.find_one({"id": mgr_id}, {"_id": 0})
        return {"manager": m}

    @router.delete("/admin/managers/{mgr_id}")
    async def delete_manager(mgr_id: str, _: dict = Depends(require_admin)):
        res = await db.managers.delete_one({"id": mgr_id})
        if not res.deleted_count:
            raise HTTPException(404, "Manager not found")
        await db.reps.update_many({"manager_id": mgr_id}, {"$set": {"manager_id": None}})
        return {"ok": True}

    # Public rep resolver (unauth — StartNew displays the referred-by banner)
    @router.get("/reps/resolve/{rep_code}")
    async def resolve_rep_public(rep_code: str):
        code = (rep_code or "").strip().upper()
        if not code:
            raise HTTPException(404, "Not found")
        rep = await db.reps.find_one({"rep_code": code, "active": {"$ne": False}}, {"_id": 0})
        if not rep:
            raise HTTPException(404, "Not found")
        return {"rep_code": rep["rep_code"], "rep_name": rep.get("name")}

    # Commissions
    @router.get("/admin/commissions")
    async def list_commissions(
        status: Optional[str] = Query(None),
        _: dict = Depends(require_admin),
    ):
        q: dict = {}
        if status:
            q["status"] = status
        rows = await db.commissions.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
        return {"commissions": rows}

    @router.post("/admin/commissions/{commission_id}/approve")
    async def admin_approve_commission(commission_id: str, body: CommissionApproveReq, admin: dict = Depends(require_admin)):
        c = await db.commissions.find_one({"id": commission_id}, {"_id": 0})
        if not c:
            raise HTTPException(404, "Commission not found")
        if c.get("status") == "approved":
            return {"ok": True, "already_approved": True, "commission": c}
        await db.commissions.update_one({"id": commission_id}, {"$set": {
            "status": "approved",
            "approved_at": now_iso(),
            "approved_by": admin["id"],
            "approved_source": "admin_ui",
            "approve_note": (body.note or "")[:500],
        }})
        c = await db.commissions.find_one({"id": commission_id}, {"_id": 0})
        await _notify_commission_released(c)
        return {"ok": True, "commission": c}

    @router.post("/admin/commissions/{commission_id}/deny")
    async def admin_deny_commission(commission_id: str, body: CommissionApproveReq, admin: dict = Depends(require_admin)):
        c = await db.commissions.find_one({"id": commission_id}, {"_id": 0})
        if not c:
            raise HTTPException(404, "Commission not found")
        if c.get("status") == "denied":
            return {"ok": True, "already_denied": True, "commission": c}
        await db.commissions.update_one({"id": commission_id}, {"$set": {
            "status": "denied",
            "denied_at": now_iso(),
            "denied_by": admin["id"],
            "denied_source": "admin_ui",
            "deny_note": (body.note or "")[:500],
        }})
        c = await db.commissions.find_one({"id": commission_id}, {"_id": 0})
        return {"ok": True, "commission": c}
