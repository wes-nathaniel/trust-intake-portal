"""Stripe payments router — checkout session creation, status poll, webhook,
admin send-payment-link, and admin payment-link email.

The `_stripe_apply_paid` helper is exposed at module level so unit tests
(and other server code) can force-run the "payment cleared → case Updated
→ commission hold created" pipeline without needing a real Stripe event.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

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
    origin_url: str


class SendPaymentLinkReq(BaseModel):
    lookup_key: Literal["basic_living_trust", "private_trust"]
    origin_url: str
    email_subject: Optional[str] = None
    email_message: Optional[str] = None


# ---------- Helpers (exposed for tests + other routers) ----------

async def _stripe_apply_paid(session_id: str):
    """Idempotent: when a Stripe session is paid, update the case, send admin alert
    email with one-tap link to the case, and create a commission hold if a rep
    is attached to the case. Does NOT change client_visible status."""
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
    already_paid = p.get("status") in ("paid", "verified", "paid_manual", "received_zelle")
    p["status"] = "paid"
    p["stripe_paid_at"] = now_iso()
    p["stripe_session_id"] = session_id
    p["amount_cents"] = record.get("amount") or p.get("amount_cents")
    p["lookup_key"] = record.get("lookup_key") or p.get("lookup_key")
    # Update internal status only — client_status stays unchanged until admin presses Release
    await update_case(case_id, {"payment": p, "status": "Payment Verified"})

    if already_paid:
        return

    # Send admin alert email with one-tap link to case
    try:
        from routes._neo_state import state as _st
        send_email = _st.send_email_notification
        email_shell = _st.email_shell
        cta = _st.cta
        ADMIN_EMAIL = _st.ADMIN_NOTIFY_EMAIL
        FRONTEND_URL = _st.FRONTEND_URL
        branding_doc = _st.branding_doc

        branding = await branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        who = case.get("client_name") or case.get("client_email")
        amount_cents = record.get("amount") or p.get("amount_cents") or 0
        amount_str = f"${amount_cents / 100:,.2f}"
        product = commissions_mod.product_display_name(record.get("lookup_key") or "")
        case_link = f"{FRONTEND_URL}/admin/cases/{case_id}"
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Payment received</p>
<p><b>{who}</b> paid <b>{amount_str}</b> for <b>{product}</b>.</p>
<p style="color:#64748B;font-size:13px;">Case #{case_id[:8].upper()} · {case.get('trust_name') or ''}</p>
<p>The client's visible status has not changed. Press Release when you are ready.</p>
{cta(case_link, "Open case now", accent)}
"""
        html = email_shell(biz, primary, accent, inner)
        await send_email(ADMIN_EMAIL, f"Payment received — {who} — Case #{case_id[:8].upper()}", html)
    except Exception as e:
        logger.error(f"Admin payment alert email failed: {e}")

    # NEO Stage 3: Payment confirmed WhatsApp alert
    try:
        who = case.get("client_name") or case.get("client_email")
        amount_str = f"${(record.get('amount') or 0) / 100:,.2f}"
        product = commissions_mod.product_display_name(record.get("lookup_key") or "")
        notify.notify_admin(
            f"[IGC Stage 3 Payment] {who} paid {amount_str} for {product}. "
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

    @router.get("/payments/stripe-config")
    async def stripe_public_config():
        """Public endpoint — returns publishable key for the EmbeddedCheckout frontend."""
        return {
            "publishable_key": stripe_service.get_publishable_key(),
            "mode": stripe_service.STRIPE_MODE,
        }

    @router.post("/admin/trust-cases/{case_id}/send-payment-link")
    async def admin_send_payment_link(
        case_id: str, body: SendPaymentLinkReq, admin: dict = Depends(require_admin)
    ):
        """Admin creates a Stripe Embedded Checkout session and emails the client a link."""
        from routes._neo_state import state as _st
        send_email = _st.send_email_notification
        email_shell = _st.email_shell
        cta = _st.cta
        FRONTEND_URL = _st.FRONTEND_URL
        branding_doc = _st.branding_doc
        now_iso_fn = now_iso
        client_auto_off = _st.client_auto_email_off

        case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
        if not case:
            raise HTTPException(404, "Case not found")
        if not stripe_service.is_enabled():
            raise HTTPException(503, "Stripe is not configured.")

        origin = body.origin_url.rstrip("/")
        try:
            session = stripe_service.create_checkout_session(
                lookup_key=body.lookup_key,
                origin_url=origin,
                metadata={
                    "case_id": case_id,
                    "admin_sent": "true",
                    "lookup_key": body.lookup_key,
                    "rep_code": case.get("rep_code") or "",
                },
                customer_email=case.get("client_email"),
            )
        except Exception as e:
            logger.error(f"Stripe checkout create (admin) failed: {e}")
            raise HTTPException(502, f"Stripe error: {e}")

        await db.payment_transactions.insert_one({
            "session_id": session["session_id"],
            "case_id": case_id,
            "admin_sent_by": admin["id"],
            "lookup_key": body.lookup_key,
            "amount": session["amount_cents"],
            "currency": session["currency"],
            "status": "initiated",
            "payment_status": "pending",
            "created_at": now_iso_fn(),
        })

        p = dict(case.get("payment") or {})
        p["stripe_session_id"] = session["session_id"]
        p["stripe_client_secret"] = session.get("client_secret") or ""
        p["amount_cents"] = session["amount_cents"]
        p["lookup_key"] = body.lookup_key
        p["product_name"] = commissions_mod.product_display_name(body.lookup_key)
        p["link_sent_at"] = now_iso_fn()
        p["link_sent_by"] = admin["id"]
        if not p.get("status") or p.get("status") in ("none", "amount_set"):
            p["status"] = "link_sent"
        await update_case(case_id, {"payment": p})

        # Email to client
        try:
            branding = await branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            amount_str = f"${session['amount_cents']/100:,.2f}"
            portal_link = f"{FRONTEND_URL}/portal"
            custom_msg = body.email_message or (
                f"Your trust preparation fee of {amount_str} is now ready. "
                f"You can pay securely by debit card right from your portal. "
                f"Debit cards only. No credit cards."
            )
            subject = body.email_subject or f"Your trust payment is ready — {biz}"
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Your payment is ready</p>
<p>{custom_msg}</p>
<p style="color:#64748B;font-size:13px;">Case #{case_id[:8].upper()}</p>
{cta(portal_link, "Open your portal to pay", accent)}
"""
            html = email_shell(biz, primary, accent, inner)
            await send_email(case.get("client_email"), subject, html)
        except Exception as e:
            logger.error(f"Payment link email failed: {e}")

        return {
            "ok": True,
            "session_id": session["session_id"],
            "amount_cents": session["amount_cents"],
            "debit_enforced": session.get("debit_enforced", False),
        }

    @router.post("/trust-cases/{case_id}/stripe/checkout")
    async def stripe_create_checkout(case_id: str, body: StripeCheckoutReq, user: dict = Depends(get_current_user)):
        """Client kicks off a Stripe Embedded Checkout Session for their case."""
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
        p["stripe_client_secret"] = session.get("client_secret") or ""
        p["amount_cents"] = session["amount_cents"]
        p["lookup_key"] = body.lookup_key
        p["product_name"] = commissions_mod.product_display_name(body.lookup_key)
        if not p.get("status") or p.get("status") in ("none", "amount_set"):
            p["status"] = "checkout_pending"
        await update_case(case_id, {"payment": p})

        return {
            "session_id": session["session_id"],
            "client_secret": session.get("client_secret"),
            "amount_cents": session["amount_cents"],
        }

    @router.get("/trust-cases/{case_id}/stripe/session")
    async def stripe_get_session(case_id: str, user: dict = Depends(get_current_user)):
        """Return stored client_secret for the EmbeddedCheckout component."""
        case = await get_case(case_id, user)
        p = case.get("payment") or {}
        if not p.get("stripe_client_secret"):
            return {"has_session": False}
        already_paid = p.get("status") in ("paid", "verified", "paid_manual", "received_zelle")
        return {
            "has_session": True,
            "client_secret": p["stripe_client_secret"],
            "amount_cents": p.get("amount_cents"),
            "already_paid": already_paid,
            "status": p.get("status"),
        }

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
