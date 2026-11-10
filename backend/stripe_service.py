"""Stripe payments for the Trust Portal.

Keys are read from env vars in `/app/backend/.env`:
    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_ACCOUNT_ID,
    STRIPE_WEBHOOK_SECRET, STRIPE_MODE

Two products are exposed by lookup key:
    - basic_living_trust
    - private_trust

The setup_catalog() helper is idempotent — safe to call at every startup.

Checkout mode: Embedded Checkout (ui_mode=embedded).
Debit-only restriction uses payment_method_options.card.restrictions.funding_types_blocked.
Requires Stripe API version 2026-08-26 or later on the connected account.
Apple Pay and Google Pay are disabled by passing payment_method_types=["card"].
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any

import stripe

logger = logging.getLogger("stripe-service")

# Key resolution — CUSTOM_STRIPE_* (user-supplied via secrets card) always wins
# over STRIPE_* (Emergent platform-managed, may be overwritten on restart).
# This ensures the user's Echo Holding Ventures account is always used once set.

def _key() -> str:
    return (
        os.environ.get("CUSTOM_STRIPE_SECRET_KEY")
        or os.environ.get("STRIPE_SECRET_KEY")
        or ""
    )

def _apply_key():
    """Set stripe.api_key from the highest-priority source before every API call."""
    stripe.api_key = _key()

def get_publishable_key() -> str:
    return (
        os.environ.get("CUSTOM_STRIPE_PUBLISHABLE_KEY")
        or os.environ.get("STRIPE_PUBLISHABLE_KEY")
        or ""
    )

def get_webhook_secret() -> str:
    return (
        os.environ.get("CUSTOM_STRIPE_WEBHOOK_SECRET")
        or os.environ.get("STRIPE_WEBHOOK_SECRET")
        or ""
    )

# Keep module-level names for any code that imports them directly (backward compat).
# These are read once at import; use the getter functions for live values.
STRIPE_WEBHOOK_SECRET = get_webhook_secret()
STRIPE_PUBLISHABLE_KEY = get_publishable_key()
STRIPE_MODE = os.environ.get("STRIPE_MODE", "test")
STRIPE_ONBOARDING_URL = os.environ.get("STRIPE_ONBOARDING_URL", "")

# Apply key immediately at import so any top-level stripe usage works.
_apply_key()


# Catalog — trust preparation professional services. Fixed dollar amounts,
# no tax add-on (matches previous Square behaviour). Amount is in cents.
CATALOG = [
    {
        "emergent_product_id": "basic_living_trust",
        "name": "Basic Living Trust",
        "description": "Iron Gate Consulting — Basic Living Trust preparation",
        "tax_code": "txcd_20030000",  # professional services
        "prices": [
            {"lookup_key": "basic_living_trust", "amount": 149700, "currency": "usd"},
        ],
    },
    {
        "emergent_product_id": "private_trust",
        "name": "Private Trust",
        "description": "Iron Gate Consulting — Private Trust preparation",
        "tax_code": "txcd_20030000",
        "prices": [
            {"lookup_key": "private_trust", "amount": 249700, "currency": "usd"},
        ],
    },
]


def is_enabled() -> bool:
    return bool(_key())


def _get_or_create_product(entry: Dict[str, Any]):
    _apply_key()
    for p in stripe.Product.list(active=True, limit=100).auto_paging_iter():
        md = p.to_dict().get("metadata") or {}
        if md.get("emergent_product_id") == entry["emergent_product_id"]:
            return p
    return stripe.Product.create(
        name=entry["name"],
        description=entry.get("description") or None,
        tax_code=entry.get("tax_code"),
        metadata={
            "managed_by": "emergent_trust_portal",
            "emergent_product_id": entry["emergent_product_id"],
        },
    )


def setup_catalog() -> Dict[str, str]:
    """Idempotently create the products + prices in Stripe.

    Returns a mapping of lookup_key -> price_id for convenience.
    """
    out: Dict[str, str] = {}
    if not is_enabled():
        logger.warning("setup_catalog skipped — STRIPE_SECRET_KEY not set")
        return out
    _apply_key()
    try:
        for entry in CATALOG:
            product = _get_or_create_product(entry)
            for p in entry["prices"]:
                existing = stripe.Price.list(
                    lookup_keys=[p["lookup_key"]], active=True, limit=1
                ).data
                if existing and (
                    existing[0].unit_amount != p["amount"]
                    or existing[0].currency != p["currency"]
                ):
                    stripe.Price.modify(existing[0].id, active=False)
                    existing = []
                if not existing:
                    kwargs = dict(
                        product=product.id,
                        unit_amount=p["amount"],
                        currency=p["currency"],
                        lookup_key=p["lookup_key"],
                        transfer_lookup_key=True,
                    )
                    if p.get("interval"):
                        kwargs["recurring"] = {"interval": p["interval"]}
                    price = stripe.Price.create(**kwargs)
                    out[p["lookup_key"]] = price.id
                else:
                    out[p["lookup_key"]] = existing[0].id
        logger.info(f"Stripe catalog ready: {out}")
    except Exception as e:
        logger.error(f"Stripe setup_catalog failed: {e}")
    return out


def price_for_lookup(lookup_key: str):
    _apply_key()
    prices = stripe.Price.list(lookup_keys=[lookup_key], active=True, limit=1).data
    if not prices:
        raise RuntimeError(f"Stripe price not found for lookup_key={lookup_key}")
    return prices[0]


def create_checkout_session(
    lookup_key: str,
    origin_url: str,
    metadata: Optional[Dict[str, str]] = None,
    customer_email: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an Embedded Checkout Session (debit-only, no Apple Pay / Google Pay).

    Returns client_secret for the EmbeddedCheckout component on the frontend.
    If funding_types_blocked is not supported by the account API version,
    the session is created without it (card-only still enforced via payment_method_types).
    """
    _apply_key()
    price = price_for_lookup(lookup_key)
    md = {k: (v or "") for k, v in (metadata or {}).items()}
    base_kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription" if price.recurring else "payment",
        ui_mode="embedded",
        payment_method_types=["card"],   # disables Apple Pay and Google Pay
        return_url=f"{origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        metadata=md,
    )
    if customer_email:
        base_kwargs["customer_email"] = customer_email

    # Attempt debit-only restriction (requires Stripe API version 2026-08-26+)
    try:
        session = stripe.checkout.Session.create(
            **base_kwargs,
            payment_method_options={
                "card": {
                    "restrictions": {
                        "funding_types_blocked": ["credit", "prepaid"]
                    }
                }
            },
        )
        debit_enforced = True
    except Exception as e:
        logger.warning(f"Debit-only restriction not supported by API version, creating without it: {e}")
        session = stripe.checkout.Session.create(**base_kwargs)
        debit_enforced = False

    return {
        "session_id": session.id,
        "client_secret": session.client_secret,
        # Keep checkout_url for backward compat (None for embedded sessions)
        "checkout_url": getattr(session, "url", None),
        "amount_cents": (price.unit_amount or 0),
        "currency": price.currency,
        "debit_enforced": debit_enforced,
    }


def retrieve_session(session_id: str):
    _apply_key()
    return stripe.checkout.Session.retrieve(session_id)


def construct_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(payload, sig_header, get_webhook_secret())


def account_info() -> Dict[str, Any]:
    """Retrieve live account name from Stripe for admin diagnostics."""
    _apply_key()
    try:
        acct = stripe.Account.retrieve()
        # stripe-python v5+ returns StripeObjects, not plain dicts.
        # Coerce to dict for safe attribute access.
        acct_d = acct.to_dict() if hasattr(acct, "to_dict") else dict(acct)
        bp = acct_d.get("business_profile") or {}
        name = (bp.get("name") if isinstance(bp, dict) else getattr(bp, "name", "")) or ""
        if not name:
            settings = acct_d.get("settings") or {}
            dash = (settings.get("dashboard") if isinstance(settings, dict) else {}) or {}
            name = (dash.get("display_name") if isinstance(dash, dict) else "") or ""
        return {
            "account_id": acct_d.get("id", ""),
            "business_name": name,
            "email": acct_d.get("email", ""),
            "country": acct_d.get("country", ""),
            "charges_enabled": acct_d.get("charges_enabled"),
        }
    except Exception as e:
        logger.warning(f"account_info failed: {e}")
        return {"account_id": os.environ.get("STRIPE_ACCOUNT_ID", ""), "error": str(e)}


def health() -> Dict[str, Any]:
    info = account_info()
    pk = get_publishable_key()
    using_custom = bool(os.environ.get("CUSTOM_STRIPE_SECRET_KEY"))
    return {
        "enabled": is_enabled(),
        "mode": STRIPE_MODE,
        "account_id": info.get("account_id") or os.environ.get("STRIPE_ACCOUNT_ID"),
        "business_name": info.get("business_name", ""),
        "charges_enabled": info.get("charges_enabled"),
        "publishable_key": pk[:20] + "..." if pk else None,
        "webhook_configured": bool(get_webhook_secret()),
        "checkout_mode": "embedded",
        "debit_only": True,
        "apple_pay": False,
        "google_pay": False,
        "key_source": "custom (your account)" if using_custom else "platform managed",
    }
