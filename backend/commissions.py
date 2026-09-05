"""Fixed-dollar commission engine for rep referrals.

Two product tiers, fixed commission amounts (NOT percentages):

    Basic Living Trust ($1,497)
        rep only           -> rep $500
        rep + manager      -> rep $450  + manager $50 override

    Private Trust ($2,497)
        rep only           -> rep $800
        rep + manager      -> rep $720  + manager $80 override

All commissions require Wes to approve via WhatsApp before release.
"""
from __future__ import annotations
from typing import Optional, Dict, Any


PRODUCT_TIERS = {
    "basic_living_trust": {
        "price_cents": 149700,
        "name": "Basic Living Trust",
        "rep_only": 50000,           # $500
        "rep_with_manager": 45000,   # $450
        "manager_override": 5000,    # $50
    },
    "private_trust": {
        "price_cents": 249700,
        "name": "Private Trust",
        "rep_only": 80000,           # $800
        "rep_with_manager": 72000,   # $720
        "manager_override": 8000,    # $80
    },
}


def split_for(product_lookup_key: str, has_manager: bool) -> Dict[str, int]:
    """Return the commission split in cents for the given product.

    Returns dict:
      {rep_cents: int, manager_cents: int}
    """
    tier = PRODUCT_TIERS.get(product_lookup_key)
    if not tier:
        return {"rep_cents": 0, "manager_cents": 0}
    if has_manager:
        return {
            "rep_cents": tier["rep_with_manager"],
            "manager_cents": tier["manager_override"],
        }
    return {"rep_cents": tier["rep_only"], "manager_cents": 0}


def product_display_name(product_lookup_key: str) -> str:
    tier = PRODUCT_TIERS.get(product_lookup_key)
    return tier["name"] if tier else product_lookup_key
