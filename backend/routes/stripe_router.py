"""Stripe payments router — checkout session creation, status poll, webhook.

The `_stripe_apply_paid` helper is exposed at module level so unit tests
(and other server code) can force-run the "payment cleared → case Updated
→ commission hold created" pipeline without needing a real Stripe event.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import commissions as commissions_mod
import stripe_service

from routes._neo_state import state
from routes.commissions_router import _create_commission_hold

logger = logging.getLogger("neo.stripe")
router = APIRouter()


class StripeCheckoutReq(BaseModel):
    lookup_key: Literal["basic_living_trust", "private_trust"]
    origin_url: str  # e.g. https://trust.igcfirm.com


# ---------- Helpers (exposed for tests + other routers) ----------

async def _stripe_apply_paid(session_id: str):
    """Idempotent: when a Stripe session is paid, update the case, fire the
    payment-received WhatsApp alert, and create a commission hold if a rep
    is attached to the case."""
    db = state.db
    update_case = state.update_case
    notify = state.notify
    now_iso = state.now_iso

    record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
    if not record:
        return
    case_id = record.get("case_id")
    if not case_id:
        return
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        return
    p = dict(case.get("payment") or {})
    already_paid = p.get("status") in ("paid", "verified", "paid_manual")
    p["status"] = "paid"
    p["stripe_paid_at"] = now_iso()
    p["stripe_session_id"] = session_id
    p["amount_cents"] = record.get("amount") or p.get("amount_cents")
    p["lookup_key"] = record.get("lookup_key") or p.get("lookup_key")
    await update_case(case_id, {"payment": p, "status": "Payment Verified"})

    if already_paid:
        return

    # NEO Stage 3: Payment confirmed
    try:
        who = case.get("client_name") or case.get("client_email")
        amount_str = f"${(record.get('amount') or 0) / 100:,.2f}"
        product = commissions_mod.product_display_name(record.get("lookup_key") or "")
        notify.notify_admin(
            f"[IGC · Stage 3 · Payment Confirmed] {who} paid {amount_str} for {product}. "
            f"Case #{case_id[:8].upper()}."
        )
    except Exception as e:
        logger.error(f"NEO stage-3 WhatsApp alert failed: {e}")

    # NEO Stage 4: Commission hold (idempotent inside)
    try:
        await _create_commission_hold(case, record)
    except Exception as e:
        logger.error(f"commission hold create failed: {e}")


# ---------- Route builder ----------

def build_routes():
    db = state.db
    require_admin = state.require_admin
    get_current_user = state.get_current_user
    get_case = state.get_case
    update_case = state.update_case
    now_iso = state.now_iso

    @router.get("/admin/stripe/health")
    async def stripe_health(_: dict = Depends(require_admin)):
        return stripe_service.health()

    @router.post("/admin/stripe/setup-catalog")
    async def stripe_setup_catalog(_: dict = Depends(require_admin)):
        result = stripe_service.setup_catalog()
        if not result:
            raise HTTPException(502, "Stripe catalog setup returned no prices — see server logs.")
        return {"ok": True, "prices": result}

    @router.post("/trust-cases/{case_id}/stripe/checkout")
    async def stripe_create_checkout(case_id: str, body: StripeCheckoutReq, user: dict = Depends(get_current_user)):
        """Client kicks off a Stripe Checkout Session for their case."""
        case = await get_case(case_id, user)
        if not case:
            raise HTTPException(404, "Case not found")
        if user.get("role") == "admin":
            raise HTTPException(400, "Admins cannot start checkout on behalf of a client.")
        if not stripe_service.is_enabled():
            raise HTTPException(503, "Stripe is not configured.")

        try:
            session = stripe_service.create_checkout_session(
                lookup_key=body.lookup_key,
                origin_url=body.origin_url.rstrip("/"),
                metadata={
                    "case_id": case_id,
                    "user_id": user["id"],
                    "lookup_key": body.lookup_key,
                    "rep_code": case.get("rep_code") or "",
                },
                customer_email=case.get("client_email"),
            )
        except Exception as e:
            logger.error(f"Stripe checkout create failed: {e}")
            raise HTTPException(502, f"Stripe error: {e}")

        await db.payment_transactions.insert_one({
            "session_id": session["session_id"],
            "case_id": case_id,
            "user_id": user["id"],
            "lookup_key": body.lookup_key,
            "amount": session["amount_cents"],
            "currency": session["currency"],
            "status": "initiated",
            "payment_status": "pending",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        })

        p = dict(case.get("payment") or {})
        p["stripe_session_id"] = session["session_id"]
        p["amount_cents"] = session["amount_cents"]
        p["lookup_key"] = body.lookup_key
        p["product_name"] = commissions_mod.product_display_name(body.lookup_key)
        if not p.get("status") or p.get("status") in ("none", "amount_set"):
            p["status"] = "checkout_pending"
        await update_case(case_id, {"payment": p, "status": "Ready for Payment"})

        return {"checkout_url": session["checkout_url"], "session_id": session["session_id"]}

    @router.get("/payments/status/{session_id}")
    async def stripe_payment_status(session_id: str):
        """Unauthenticated status poll."""
        record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
        if not record:
            raise HTTPException(404, "Transaction not found")
        if record.get("payment_status") != "paid":
            try:
                s = stripe_service.retrieve_session(session_id)
                if s.payment_status == "paid" or s.status == "complete":
                    await db.payment_transactions.update_one(
                        {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                        {"$set": {
                            "status": "completed",
                            "payment_status": "paid",
                            "stripe_payment_intent_id": s.payment_intent,
                            "updated_at": now_iso(),
                        }},
                    )
                    await _stripe_apply_paid(session_id)
                    record = await db.payment_transactions.find_one({"session_id": session_id}, {"_id": 0})
            except Exception as e:
                logger.warning(f"stripe status live-fetch: {e}")
        return {
            "session_id": record["session_id"],
            "status": record.get("status"),
            "payment_status": record.get("payment_status"),
        }

    @router.post("/stripe/webhook")
    async def stripe_webhook(request: Request):
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event = stripe_service.construct_event(payload, sig)
        except Exception as e:
            logger.error(f"Stripe webhook signature verification failed: {e}")
            raise HTTPException(400, "Invalid signature")

        et = event["type"]
        obj = event["data"]["object"]
        # In stripe-python v15+, StripeObject no longer supports .get(); coerce
        # to a plain dict so we can use dict semantics safely below.
        try:
            obj_d = obj.to_dict_recursive() if hasattr(obj, "to_dict_recursive") else dict(obj)
        except Exception:
            obj_d = {}
        sid = obj_d.get("id")

        if et == "checkout.session.completed":
            await db.payment_transactions.update_one(
                {"session_id": sid, "payment_status": {"$ne": "paid"}},
                {"$set": {
                    "status": "completed",
                    "payment_status": obj_d.get("payment_status") or "paid",
                    "stripe_payment_intent_id": obj_d.get("payment_intent"),
                    "updated_at": now_iso(),
                }},
            )
            try:
                await _stripe_apply_paid(sid)
            except Exception as e:
                logger.error(f"Stripe apply_paid failed: {e}")

        elif et == "checkout.session.async_payment_succeeded":
            await db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"payment_status": "paid", "updated_at": now_iso()}},
            )
            try:
                await _stripe_apply_paid(sid)
            except Exception as e:
                logger.error(f"Stripe apply_paid failed: {e}")

        elif et == "checkout.session.async_payment_failed":
            await db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"status": "failed", "payment_status": "failed", "updated_at": now_iso()}},
            )
        elif et == "checkout.session.expired":
            await db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"status": "expired", "payment_status": "expired", "updated_at": now_iso()}},
            )
        return {"status": "ok"}
