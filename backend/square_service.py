"""Square API integration for trust payment invoices.

Workflow:
1. Admin creates a Square invoice for a trust case.
2. We create an Order (with a single line item) + an Invoice.
3. Publish the invoice so Square emails the client with a hosted payment page.
4. Webhooks update payment state (created / paid / ACH pending vs completed / failed).
"""
from __future__ import annotations
import os
import uuid
import hmac
import hashlib
import base64
import logging
from typing import Optional

logger = logging.getLogger("square")

try:
    from square import Square
    from square.environment import SquareEnvironment
    _SQUARE_OK = True
except Exception as e:  # pragma: no cover
    Square = None  # type: ignore
    SquareEnvironment = None  # type: ignore
    logger.warning("Square SDK import failed: %s", e)
    _SQUARE_OK = False


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default) or default


def is_enabled() -> bool:
    return _SQUARE_OK and bool(_env("SQUARE_ACCESS_TOKEN"))


# Cache for auto-discovered location id
_DISCOVERED_LOCATION_ID: Optional[str] = None


def _resolve_location_id() -> str:
    """Return a usable location_id. Falls back to auto-discovery from Square
    if the configured SQUARE_LOCATION_ID is missing or doesn't belong to this token.
    This makes the integration resilient to stale/typo env vars."""
    global _DISCOVERED_LOCATION_ID
    configured = _env("SQUARE_LOCATION_ID")

    if _DISCOVERED_LOCATION_ID:
        return _DISCOVERED_LOCATION_ID

    sq = _client_raw()
    if configured:
        try:
            resp = sq.locations.get(location_id=configured)
            loc = getattr(resp, "location", None) or (resp.get("location") if isinstance(resp, dict) else None)
            lid = getattr(loc, "id", None) if loc is not None and not isinstance(loc, dict) else (loc or {}).get("id")
            if lid:
                _DISCOVERED_LOCATION_ID = lid
                return lid
        except Exception as e:
            logger.warning("Configured SQUARE_LOCATION_ID '%s' is invalid — auto-discovering from Square API: %s",
                           configured, e)

    # Fallback: list active locations on this token and pick the first active one
    try:
        resp = sq.locations.list()
        locs = getattr(resp, "locations", None) or (resp.get("locations") if isinstance(resp, dict) else [])
        for loc in (locs or []):
            lid = getattr(loc, "id", None) if not isinstance(loc, dict) else loc.get("id")
            status = getattr(loc, "status", None) if not isinstance(loc, dict) else loc.get("status")
            if lid and status == "ACTIVE":
                _DISCOVERED_LOCATION_ID = lid
                logger.info("Square auto-discovered location_id=%s", lid)
                return lid
    except Exception as e:
        logger.error("Square locations.list failed: %s", e)

    raise RuntimeError("No usable Square location found for this access token")


def _client_raw() -> "Square":
    if not _SQUARE_OK or not _env("SQUARE_ACCESS_TOKEN"):
        raise RuntimeError("Square is not configured")
    env_name = (_env("SQUARE_ENVIRONMENT", "production") or "production").lower()
    env = SquareEnvironment.PRODUCTION if env_name == "production" else SquareEnvironment.SANDBOX
    return Square(token=_env("SQUARE_ACCESS_TOKEN"), environment=env)


def _client() -> "Square":
    if not is_enabled():
        raise RuntimeError("Square is not configured")
    return _client_raw()


def _money(cents: int) -> dict:
    return {"amount": int(cents), "currency": "USD"}


def _idem() -> str:
    return str(uuid.uuid4())


def create_invoice(
    *,
    client_email: str,
    client_name: str,
    amount_cents: int,
    description: str,
    case_id: str,
    trust_name: str,
    due_in_days: int = 14,
) -> dict:
    """Create + publish an invoice. Returns dict with invoice_id, public_url, status."""
    from datetime import datetime, timedelta, timezone
    sq = _client()
    location_id = _resolve_location_id()

    # --- Step 1: Create an order with a single line item so the invoice has content ---
    order_req = {
        "idempotency_key": _idem(),
        "order": {
            "location_id": location_id,
            "line_items": [{
                "name": description or f"Trust fee ({trust_name})",
                "quantity": "1",
                "base_price_money": _money(amount_cents),
                "note": f"Case #{case_id[:8].upper()}",
            }],
            "metadata": {"case_id": case_id, "trust_name": trust_name[:250]},
        },
    }
    order_resp = sq.orders.create(**order_req)
    order_id = getattr(order_resp, "order", None)
    if order_id is None and isinstance(order_resp, dict):
        order_id = order_resp.get("order", {}).get("id")
    else:
        # SDK returns an object with .order.id
        try:
            order_id = order_resp.order.id  # type: ignore[attr-defined]
        except Exception:
            order_id = None
    if not order_id:
        raise RuntimeError(f"Square: could not create order (response: {order_resp!r})")

    # --- Step 2: Create invoice tied to that order ---
    due_date = (datetime.now(timezone.utc) + timedelta(days=due_in_days)).date().isoformat()
    invoice_req = {
        "idempotency_key": _idem(),
        "invoice": {
            "location_id": location_id,
            "order_id": order_id,
            "primary_recipient": {
                "email_address": client_email,
                "given_name": (client_name or client_email).split(" ")[0][:50],
                "family_name": " ".join((client_name or "").split(" ")[1:])[:50] or None,
            },
            "payment_requests": [{
                "request_type": "BALANCE",
                "due_date": due_date,
                "automatic_payment_source": "NONE",
                "reminders": [
                    {"relative_scheduled_days": -3, "message": "Friendly reminder: your trust fee is due soon."},
                    {"relative_scheduled_days": 1, "message": "Your trust fee is past due."},
                ],
            }],
            "delivery_method": "EMAIL",
            "invoice_number": f"IGC-{case_id[:8].upper()}-{int(datetime.now(timezone.utc).timestamp())}",
            "title": f"Trust fee — {trust_name[:120]}",
            "description": description or "Trust preparation and filing fee.",
            "accepted_payment_methods": {
                "card": True,
                "bank_account": True,
                "square_gift_card": False,
                "buy_now_pay_later": False,
            },
            "custom_fields": [
                {"label": "Case ID", "value": case_id[:8].upper(), "placement": "ABOVE_LINE_ITEMS"},
                {"label": "Trust Name", "value": trust_name[:120], "placement": "ABOVE_LINE_ITEMS"},
            ],
            "sale_or_service_date": datetime.now(timezone.utc).date().isoformat(),
        },
    }
    inv_resp = sq.invoices.create(**invoice_req)
    inv_obj = getattr(inv_resp, "invoice", None) or (inv_resp.get("invoice") if isinstance(inv_resp, dict) else None)
    if inv_obj is None:
        raise RuntimeError(f"Square: could not create invoice (response: {inv_resp!r})")
    invoice_id = getattr(inv_obj, "id", None) or (inv_obj.get("id") if isinstance(inv_obj, dict) else None)
    version = getattr(inv_obj, "version", None) or (inv_obj.get("version") if isinstance(inv_obj, dict) else 0)

    # --- Step 3: Publish & send invoice (triggers email) ---
    pub_resp = sq.invoices.publish(
        invoice_id=invoice_id,
        version=int(version or 0),
        idempotency_key=_idem(),
    )
    pub_obj = getattr(pub_resp, "invoice", None) or (pub_resp.get("invoice") if isinstance(pub_resp, dict) else None)
    public_url = None
    status = "SENT"
    if pub_obj is not None:
        public_url = getattr(pub_obj, "public_url", None) or (pub_obj.get("public_url") if isinstance(pub_obj, dict) else None)
        status = getattr(pub_obj, "status", None) or (pub_obj.get("status") if isinstance(pub_obj, dict) else status)

    return {
        "invoice_id": invoice_id,
        "order_id": order_id,
        "public_url": public_url,
        "status": status,
        "amount_cents": amount_cents,
        "due_date": due_date,
    }


def get_invoice(invoice_id: str) -> dict:
    sq = _client()
    resp = sq.invoices.get(invoice_id=invoice_id)
    inv = getattr(resp, "invoice", None) or (resp.get("invoice") if isinstance(resp, dict) else None)
    if inv is None:
        raise RuntimeError(f"Square: invoice not found (response: {resp!r})")
    def _g(o, k):
        return getattr(o, k, None) if not isinstance(o, dict) else o.get(k)
    return {
        "invoice_id": _g(inv, "id"),
        "status": _g(inv, "status"),
        "public_url": _g(inv, "public_url"),
        "next_payment_amount_money": _g(inv, "next_payment_amount_money"),
        "version": _g(inv, "version"),
        "updated_at": _g(inv, "updated_at"),
        "payment_requests": _g(inv, "payment_requests"),
    }


def cancel_invoice(invoice_id: str, version: int) -> dict:
    sq = _client()
    resp = sq.invoices.cancel(invoice_id=invoice_id, version=int(version or 0))
    inv = getattr(resp, "invoice", None) or (resp.get("invoice") if isinstance(resp, dict) else None)
    def _g(o, k):
        return getattr(o, k, None) if not isinstance(o, dict) else o.get(k)
    return {"invoice_id": _g(inv, "id"), "status": _g(inv, "status")}


def get_payment(payment_id: str) -> dict:
    sq = _client()
    resp = sq.payments.get(payment_id=payment_id)
    p = getattr(resp, "payment", None) or (resp.get("payment") if isinstance(resp, dict) else None)
    if p is None:
        return {}
    def _g(o, k):
        return getattr(o, k, None) if not isinstance(o, dict) else o.get(k)
    bt = _g(p, "bank_account_details") or _g(p, "external_details") or {}
    risk = _g(p, "risk_evaluation") or {}
    return {
        "payment_id": _g(p, "id"),
        "status": _g(p, "status"),  # APPROVED, PENDING, COMPLETED, CANCELED, FAILED
        "amount_money": _g(p, "amount_money"),
        "approved_money": _g(p, "approved_money"),
        "processing_fee": _g(p, "processing_fee"),
        "source_type": _g(p, "source_type"),  # CARD, BANK_ACCOUNT, EXTERNAL, etc.
        "bank_status": (_g(bt, "status") if bt else None),  # ACH PENDING / COMPLETED / FAILED
        "failure_reason": _g(p, "statement_description_identifier"),
        "risk_level": (_g(risk, "risk_level") if risk else None),
        "risk_reason": (_g(risk, "reason") if risk else None),
    }


# ---------- Webhook signature verification ----------
def verify_webhook_signature(*, body_bytes: bytes, signature_header: str,
                             url: str, signature_key: Optional[str] = None) -> bool:
    """
    Verify Square's v2 webhook signature.

    Square computes HMAC-SHA256(notification_url + raw_body, signature_key) and base64-encodes.
    Header: `x-square-hmacsha256-signature`.
    """
    key = signature_key or _env("SQUARE_WEBHOOK_SIGNATURE_KEY")
    if not key:
        return False
    try:
        payload = (url or "").encode("utf-8") + (body_bytes or b"")
        digest = hmac.new(key.encode("utf-8"), payload, hashlib.sha256).digest()
        expected = base64.b64encode(digest).decode("utf-8")
        # Constant-time compare
        return hmac.compare_digest(expected.strip(), (signature_header or "").strip())
    except Exception as e:
        logger.error("Webhook signature verify failed: %s", e)
        return False
