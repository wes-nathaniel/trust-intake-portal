"""'Tell us what you own' asset items, Transfer Method Library, Schedule A table data.
No state names or state-specific wording live in this file; states come from intake data."""
import csv
import io
import json
import os
import re
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger("trust-portal")

KINDS = ["house_land", "bank", "investment", "vehicle", "business", "belongings", "life_insurance", "cash", "other", "unsure"]
KIND_LABELS = {
    "house_land": "House or Land", "bank": "Bank Account", "investment": "Investment Account", "vehicle": "Vehicle",
    "business": "Business Ownership", "belongings": "Personal Belongings", "life_insurance": "Life Insurance Policy",
    "cash": "Cash", "other": "Other", "unsure": "I am not sure",
}
# Kinds that carry a full account / policy number (encrypted at rest).
ACCT_KINDS = {"bank", "investment", "life_insurance"}
# Business items always get admin review; EIN is encrypted like account numbers.
BUSINESS_KINDS = {"business"}
OTHER_KINDS = ["Cryptocurrency", "Collectibles (coins, cards, antiques)", "Money Someone Owes You",
               "Royalties or Creative Work (books, music, patents)", "Equipment or Livestock",
               "Online Accounts or Digital Items", "Something Else"]
STATE_KINDS = {"house_land", "vehicle"}
REVIEW_KINDS = {"vehicle", "life_insurance"}
ANY_STATE = "ANY"
METHOD_OTHER = "__other__"
METHOD_UNSURE = "__unsure__"

VEHICLE_GENERIC_WORDING = (
    "Title application filed with your state's motor vehicle office, naming the trust or the trustee as owner. "
    "Bring the trust paperwork your state asks for."
)
LIFE_INSURANCE_GENERIC_WORDING = (
    "Change of owner form from your insurance company, signed and sent to them, naming the trust or the trustee as owner. "
    "Then ask them to confirm in writing who your beneficiary is."
)

# Rows in this dict have been reviewed and are marked confirmed.
# State-specific rows the admin adds remain needs_check until they confirm them.
GENERIC_CONFIRMED_METHODS = {
    "vehicle": VEHICLE_GENERIC_WORDING,
    "life_insurance": LIFE_INSURANCE_GENERIC_WORDING,
}

GENERIC_METHODS = {
    "house_land": ["Deed recorded with the county where the property is located"],
    "bank": ["Bank form changing the name on the account to the trust"],
    "investment": ["Brokerage form retitling the account to the trust"],
    "vehicle": [VEHICLE_GENERIC_WORDING],
    "business": [
        "Signed assignment of ownership interest (called an assignment)",
        "Stock or membership certificates reissued in the name of the trust",
    ],
    "belongings": ["Signed General Assignment of personal property"],
    "life_insurance": [LIFE_INSURANCE_GENERIC_WORDING],
    "cash": ["Deposit into the trust bank account"],
    "other": ["Signed assignment form", "Account retitled in the trust name"],
}
RETIREMENT_RE = re.compile(
    r"\b(ira|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?\s*(plan|account)?|roth\s+(ira|401|account)|sep\s+ira|simple\s+ira|"
    r"pension(\s+(plan|account))?|retirement\s+(account|plan|savings|fund)|tsp\s+account|thrift\s+savings)\b", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def seed_library(db):
    """Upsert generic transfer-method rows.

    * Confirmed rows (vehicle, life_insurance generic defaults): delete any old
      wording for the same kind/state=ANY so stale rows don't appear to clients,
      then upsert the new wording with status='confirmed'.
    * All other generic rows: insert-only (needs_check), never overwritten.
    * State-specific rows added by the admin are untouched.
    """
    # 1. Migrate confirmed generic rows
    for kind, new_wording in GENERIC_CONFIRMED_METHODS.items():
        # Remove old generic rows for this kind (preserves state-specific rows)
        await db.transfer_methods.delete_many(
            {"kind": kind, "state": ANY_STATE, "wording": {"$ne": new_wording}}
        )
        # Upsert new confirmed row — $set runs on both insert and update so an
        # existing confirmed row that already has the right wording still gets
        # status=confirmed in case someone manually downgraded it.
        await db.transfer_methods.update_one(
            {"kind": kind, "state": ANY_STATE, "wording": new_wording},
            {
                "$setOnInsert": {"id": uuid.uuid4().hex, "kind": kind, "state": ANY_STATE,
                                 "wording": new_wording, "created_at": now_iso()},
                "$set": {"status": "confirmed"},
            },
            upsert=True,
        )

    # 2. Seed remaining generic rows (needs_check, insert-only)
    for kind, rows in GENERIC_METHODS.items():
        if kind in GENERIC_CONFIRMED_METHODS:
            continue  # already handled above
        for wording in rows:
            await db.transfer_methods.update_one(
                {"kind": kind, "state": ANY_STATE, "wording": wording},
                {"$setOnInsert": {"id": uuid.uuid4().hex, "kind": kind, "state": ANY_STATE, "wording": wording,
                                  "status": "needs_check", "created_at": now_iso()}},
                upsert=True,
            )


async def methods_for(db, kind: str, state: str) -> list:
    """Library rows for this kind + state; falls back to generic rows.

    State-specific rows are returned as-is (admin controls their status).
    Generic fallback rows preserve their stored status so confirmed rows
    (vehicle, life_insurance) don't get incorrectly downgraded to needs_check.
    """
    lib_kind = kind if kind in GENERIC_METHODS else "other"
    rows = []
    if state:
        rows = await db.transfer_methods.find({"kind": lib_kind, "state": state}, {"_id": 0}).to_list(50)
    if not rows:
        rows = await db.transfer_methods.find({"kind": lib_kind, "state": ANY_STATE}, {"_id": 0}).to_list(50)
        # Preserve stored status; only default to needs_check when not set
        rows = [{**r, "status": r.get("status") or "needs_check"} for r in rows]
    return rows


def client_state(case: dict) -> str:
    g = (case.get("grantors") or [{}])[0] if case.get("grantors") else {}
    return ((g.get("address") or {}).get("state") or "").strip()


def flags(item: dict) -> dict:
    bi = item.get("business_info") or {}
    biz_unsure = (bi.get("biz_type") == "unsure"
                  or bi.get("has_operating_agreement") == "unsure"
                  or bi.get("has_certs") == "unsure"
                  or bi.get("owned_by_trust") == "unsure"
                  or bi.get("has_biz_bank") == "unsure")
    other = item.get("kind") == "other" or item.get("method") == METHOD_OTHER
    unsure = (item.get("kind") == "unsure" or item.get("in_trust") == "unsure"
              or item.get("method") == METHOD_UNSURE or biz_unsure)
    review = (item.get("kind") in REVIEW_KINDS
              or item.get("kind") in BUSINESS_KINDS  # every business item goes to Wes
              or item.get("source") == "ai"
              or item.get("method_status") == "needs_check")
    return {"other": other, "unsure": unsure, "review": review}


def _business_description_line(bi: dict) -> str:
    """Build Schedule A description from business_info dict.
    No crypto imports needed: server.py injects ein_plain for full-EIN exports;
    _mask_item_acct injects ein_last4 for display-only paths.
    """
    type_map = {
        "llc": "LLC", "corp": "corporation", "s_corp": "S corporation",
        "partnership": "partnership", "sole_prop": "sole proprietorship",
        "nonprofit": "nonprofit",
    }
    parts = []
    pct   = (bi.get("ownership_pct") or "").strip()
    name  = (bi.get("legal_name") or "").strip()
    btype = (bi.get("biz_type") or "").strip()
    state = (bi.get("state_formed") or "").strip()
    ein_plain = (bi.get("ein_plain") or "").strip()   # injected by server.py for full export
    ein_last4 = (bi.get("ein_last4") or "").strip()   # from _mask_item_acct
    street     = (bi.get("biz_address_street") or "").strip()
    city       = (bi.get("biz_address_city") or "").strip()
    state_addr = (bi.get("biz_address_state") or "").strip()

    if pct:
        parts.append(f"{pct} percent ownership interest in")
    elif name:
        parts.append("Ownership interest in")
    if name:
        parts.append(name)
    type_str = type_map.get(btype, "")
    if type_str and state:
        parts.append(f"a {state} {type_str}")
    elif type_str:
        parts.append(f"a {type_str}")
    elif state:
        parts.append(f"formed in {state}")
    if ein_plain and len(ein_plain) == 9:
        parts.append(f"EIN {ein_plain[:2]}-{ein_plain[2:]}")
    elif ein_last4:
        parts.append(f"EIN ending in {ein_last4}")
    if street:
        addr = f"located at {street}"
        if city:
            addr += f", {city}"
        if state_addr:
            addr += f", {state_addr}"
        parts.append(addr)
    return re.sub(r",\s*,", ",", ", ".join(parts)).rstrip(",").strip()


def method_text(item: dict) -> str:
    m = item.get("method") or ""
    if m == METHOD_OTHER:
        return item.get("method_other") or ""
    if m == METHOD_UNSURE:
        return ""
    return m


def description_text(item: dict) -> str:
    d = (item.get("description") or "").strip()
    if item.get("kind") == "other":
        pre = item.get("other_text") if item.get("other_kind") == "Something Else" else item.get("other_kind")
        if pre:
            return f"{pre}: {d}"
    return d


def description_text_with_acct(item: dict) -> str:
    """Like description_text but appends decrypted account number for Schedule A exports."""
    base = description_text(item)
    plain = (item.get("account_number_plain") or "").strip()
    if plain and item.get("kind") in ACCT_KINDS:
        return f"{base}, account number {plain}"
    return base


def effective(item: dict, admin: bool) -> dict:
    """Admins see pending internal edits merged in; clients see the released layer only."""
    base = {k: v for k, v in item.items() if k != "pending_admin"}
    if admin and item.get("pending_admin"):
        base = {**base, **item["pending_admin"], "has_unreleased_edits": True}
    return {**base, "flags": flags(base), "kind_label": KIND_LABELS.get(base.get("kind"), base.get("kind"))}


def schedule_a(items: list, include_account_numbers: bool = False) -> dict:
    # Defense-in-depth: exclude retirement accounts even if one somehow
    # slipped past the backend guard (e.g. older data, admin override).
    moved = [
        i for i in items
        if i.get("status") == "moved"
        and not i.get("deleted")
        and not RETIREMENT_RE.search(i.get("description") or "")
    ]
    moved.sort(key=lambda i: (i.get("date_delivered") or "", i.get("created_at") or ""))
    part1 = [i for i in moved if (i.get("part") or "I") == "I"]
    part2 = [i for i in moved if i.get("part") == "II"]
    rows, n = {"part_i": [], "part_ii": []}, 0
    desc_fn = description_text_with_acct if include_account_numbers else description_text
    for key, group in (("part_i", part1), ("part_ii", part2)):
        for i in group:
            n += 1
            bi = i.get("business_info") or {}
            if i.get("kind") == "business" and (bi.get("legal_name") or bi.get("ownership_pct")):
                desc = _business_description_line(bi)
            else:
                desc = desc_fn(i)
            rows[key].append({"number": n, "description_of_property": desc,
                              "date_delivered": i.get("date_delivered") or "",
                              "instrument_or_method_of_transfer": method_text(i), "trustee_initials": ""})
    return rows


def schedule_a_csv(sa: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Part", "No.", "Description of Property", "Date Delivered", "Instrument or Method of Transfer", "Trustee Initials"])
    for part, key in (("I", "part_i"), ("II", "part_ii")):
        for r in sa[key]:
            w.writerow([part, r["number"], r["description_of_property"], r["date_delivered"],
                        r["instrument_or_method_of_transfer"], r["trustee_initials"]])
    return buf.getvalue()


def intake_summary(case: dict) -> dict:
    items = [effective(i, True) for i in (case.get("asset_items") or []) if not i.get("deleted")]
    # Retirement accounts are blocked from being saved, but surface any that
    # slipped past (older data) so the admin can review.
    retirement_items = [i["description"] for i in items if RETIREMENT_RE.search(i.get("description") or "")]
    items = [i for i in items if not RETIREMENT_RE.search(i.get("description") or "")]
    by_kind, by_state = {}, {}
    for i in items:
        by_kind.setdefault(i["kind_label"], []).append(i)
        by_state.setdefault(i.get("state") or "(no state given)", []).append(i)
    return {
        "client_state": client_state(case),
        "original_text": case.get("asset_raw_texts") or [],
        "total_items": len(items),
        "by_kind": {k: {"count": len(v), "items": [x["description"] for x in v]} for k, v in by_kind.items()},
        "by_state": {k: len(v) for k, v in by_state.items()},
        "states_with_property": sorted({i.get("state") for i in items if i.get("kind") in STATE_KINDS and i.get("state")}),
        "has_business": any(i.get("kind") == "business" for i in items),
        "unsure_items": [i["description"] for i in items if i["flags"]["unsure"]],
        "other_items": [description_text(i) for i in items if i["flags"]["other"]],
        "review_items": [i["description"] for i in items if i["flags"]["review"]],
        "legacy_assets": case.get("assets") or [],
        "retirement_items_in_list": retirement_items,  # should always be empty; non-empty = admin follow-up needed
    }


ORGANIZE_PROMPT = (
    "You split a person's plain description of what they own into separate items for a living trust intake.\n"
    "Return VALID JSON only:\n"
    "{\"items\": [{\"description\": str, \"kind\": one of "
    + json.dumps([k for k in KINDS if k != "unsure"])
    + ", \"other_kind\": str or null, \"business_info\": null or object}], "
    "\"retirement_left_out\": [str]}\n"
    "Rules:\n"
    "- Each description: short, in the person's words, specific. Never include full account numbers.\n"
    "- Retirement accounts (IRA, Roth, 401k, 403b, pension, similar) go in retirement_left_out only.\n"
    "- Use kind 'other' with other_kind from " + json.dumps(OTHER_KINDS) + " when nothing fits.\n"
    "- Do not use dashes. Do not invent items.\n\n"
    "For Business Ownership items (kind='business'), set business_info to:\n"
    "{\"legal_name\": str, \"biz_type\": one of ['llc','corp','s_corp','partnership','sole_prop','nonprofit','other','unsure'] or empty, "
    "\"state_formed\": full US state name or empty, \"ownership_pct\": percent as a number string or empty, "
    "\"biz_address_street\": street address or empty, "
    "\"ein\": nine digits if EIN XX-XXXXXXX pattern found else empty, "
    "\"ein_detected_in_text\": true if EIN was in the text}\n"
    "If you see an EIN (like '12-3456789'), put the nine digits in ein, set ein_detected_in_text=true, "
    "and do NOT include the EIN anywhere in the description field.\n"
    "For non-business items set business_info to null."
)


async def organize(text: str) -> dict:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=f"assets-organize-{uuid.uuid4().hex[:8]}",
                   system_message=ORGANIZE_PROMPT).with_model("anthropic", "claude-sonnet-4-5-20250929")
    raw = await chat.send_message(UserMessage(text=text[:6000]))
    raw = raw if isinstance(raw, str) else str(raw)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0)) if m else {"items": []}
    items, left_out = [], list(data.get("retirement_left_out") or [])
    for it in data.get("items") or []:
        desc = str(it.get("description") or "").strip()
        if not desc:
            continue
        if RETIREMENT_RE.search(desc):
            left_out.append(desc)
            continue
        kind = it.get("kind") if it.get("kind") in KINDS else "other"
        ok = it.get("other_kind") if it.get("other_kind") in OTHER_KINDS else ("Something Else" if kind == "other" else None)
        item_data = {"description": desc.replace("—", ",").replace("–", ","), "kind": kind, "other_kind": ok,
                     "other_text": desc if ok == "Something Else" else ""}
        # Extract business_info for business items
        if kind == "business" and it.get("business_info"):
            raw_bi = it["business_info"]
            ein_raw = re.sub(r"[^0-9]", "", str(raw_bi.get("ein") or ""))
            valid_biz_types = {"llc", "corp", "s_corp", "partnership", "sole_prop", "nonprofit", "other", "unsure", ""}
            btype = raw_bi.get("biz_type") or ""
            if btype not in valid_biz_types:
                btype = ""
            item_data["business_info"] = {
                "legal_name": str(raw_bi.get("legal_name") or "").strip()[:200],
                "biz_type": btype,
                "state_formed": str(raw_bi.get("state_formed") or "").strip()[:40],
                "ownership_pct": str(raw_bi.get("ownership_pct") or "").strip()[:10],
                "biz_address_street": str(raw_bi.get("biz_address_street") or "").strip()[:200],
                "ein": ein_raw if len(ein_raw) == 9 else "",
                "ein_detected": bool(raw_bi.get("ein_detected_in_text")) and len(ein_raw) == 9,
            }
        items.append(item_data)
    return {"items": items, "retirement_left_out": left_out}
