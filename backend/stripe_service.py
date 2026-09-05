"""Stripe payments for the Trust Portal.

Uses the Emergent claimable Stripe sandbox. Keys are read from env vars
provisioned into `/app/backend/.env`:

    STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY, STRIPE_ACCOUNT_ID,
    STRIPE_WEBHOOK_SECRET, STRIPE_MODE, STRIPE_ONBOARDING_URL

Two products are exposed by lookup key:

    - basic_living_trust  ($1,497)
    - private_trust       ($2,497)

The setup_catalog() helper below is idempotent — safe to call at every
FastAPI startup. It will create the Product/Price rows on first run and
be a no-op afterwards.
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict, Any

import stripe

logger = logging.getLogger("stripe-service")

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"

STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_MODE = os.environ.get("STRIPE_MODE", "test")
STRIPE_ONBOARDING_URL = os.environ.get("STRIPE_ONBOARDING_URL", "")


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
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def _get_or_create_product(entry: Dict[str, Any]):
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
    """Create a Stripe Checkout Session for the given catalog item.

    origin_url is the frontend origin (e.g. https://app.example.com) that
    the client will be redirected back to. Success + cancel URLs are
    built from it so this same code works in preview and production.
    """
    price = price_for_lookup(lookup_key)
    md = {k: (v or "") for k, v in (metadata or {}).items()}
    kwargs = dict(
        line_items=[{"price": price.id, "quantity": 1}],
        mode="subscription" if price.recurring else "payment",
        success_url=f"{origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{origin_url}/payment/cancel?session_id={{CHECKOUT_SESSION_ID}}",
        metadata=md,
    )
    if customer_email:
        kwargs["customer_email"] = customer_email
    session = stripe.checkout.Session.create(**kwargs)
    return {
        "session_id": session.id,
        "checkout_url": session.url,
        "amount_cents": (price.unit_amount or 0),
        "currency": price.currency,
    }


def retrieve_session(session_id: str):
    return stripe.checkout.Session.retrieve(session_id)


def construct_event(payload: bytes, sig_header: str):
    return stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)


def health() -> Dict[str, Any]:
    return {
        "enabled": is_enabled(),
        "mode": STRIPE_MODE,
        "account_id": os.environ.get("STRIPE_ACCOUNT_ID"),
        "publishable_key": STRIPE_PUBLISHABLE_KEY[:20] + "..." if STRIPE_PUBLISHABLE_KEY else None,
        "webhook_configured": bool(STRIPE_WEBHOOK_SECRET),
        "onboarding_url": STRIPE_ONBOARDING_URL,
    }
