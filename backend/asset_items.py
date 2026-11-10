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
OTHER_KINDS = ["Cryptocurrency", "Collectibles (coins, cards, antiques)", "Money Someone Owes You",
               "Royalties or Creative Work (books, music, patents)", "Equipment or Livestock",
               "Online Accounts or Digital Items", "Something Else"]
STATE_KINDS = {"house_land", "vehicle"}
REVIEW_KINDS = {"vehicle", "life_insurance"}
ANY_STATE = "ANY"
METHOD_OTHER = "__other__"
METHOD_UNSURE = "__unsure__"

GENERIC_METHODS = {
    "house_land": ["Deed recorded with the county where the property is located"],
    "bank": ["Bank form changing the name on the account to the trust"],
    "investment": ["Brokerage form retitling the account to the trust"],
    "vehicle": ["Vehicle title application filed with your state's motor vehicle office, naming the trust or the trustee as owner"],
    "business": ["Signed ownership transfer form (called an assignment)"],
    "belongings": ["Signed General Assignment of personal property"],
    "life_insurance": ["Change of owner form naming the trust"],
    "cash": ["Deposit into the trust bank account"],
    "other": ["Signed assignment form", "Account retitled in the trust name"],
}
RETIREMENT_RE = re.compile(r"\b(ira|roth|401\s*\(?k\)?|403\s*\(?b\)?|457|pension|retirement|sep\s*ira|simple\s*ira|tsp)\b", re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def seed_library(db):
    for kind, rows in GENERIC_METHODS.items():
        for wording in rows:
            await db.transfer_methods.update_one(
                {"kind": kind, "state": ANY_STATE, "wording": wording},
                {"$setOnInsert": {"id": uuid.uuid4().hex, "kind": kind, "state": ANY_STATE, "wording": wording,
                                  "status": "needs_check", "created_at": now_iso()}},
                upsert=True)


async def methods_for(db, kind: str, state: str) -> list:
    """Library rows for this kind + state; falls back to generic rows (always 'needs_check')."""
    lib_kind = kind if kind in GENERIC_METHODS else "other"
    rows = []
    if state:
        rows = await db.transfer_methods.find({"kind": lib_kind, "state": state}, {"_id": 0}).to_list(50)
    if not rows:
        rows = await db.transfer_methods.find({"kind": lib_kind, "state": ANY_STATE}, {"_id": 0}).to_list(50)
        rows = [{**r, "status": "needs_check"} for r in rows]
    return rows


def client_state(case: dict) -> str:
    g = (case.get("grantors") or [{}])[0] if case.get("grantors") else {}
    return ((g.get("address") or {}).get("state") or "").strip()


def flags(item: dict) -> dict:
    other = item.get("kind") == "other" or item.get("method") == METHOD_OTHER
    unsure = item.get("kind") == "unsure" or item.get("in_trust") == "unsure" or item.get("method") == METHOD_UNSURE
    review = (item.get("kind") in REVIEW_KINDS or item.get("source") == "ai"
              or item.get("method_status") == "needs_check")
    return {"other": other, "unsure": unsure, "review": review}


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


def effective(item: dict, admin: bool) -> dict:
    """Admins see pending internal edits merged in; clients see the released layer only."""
    base = {k: v for k, v in item.items() if k != "pending_admin"}
    if admin and item.get("pending_admin"):
        base = {**base, **item["pending_admin"], "has_unreleased_edits": True}
    return {**base, "flags": flags(base), "kind_label": KIND_LABELS.get(base.get("kind"), base.get("kind"))}


def schedule_a(items: list) -> dict:
    moved = [i for i in items if i.get("status") == "moved" and not i.get("deleted")]
    moved.sort(key=lambda i: (i.get("date_delivered") or "", i.get("created_at") or ""))
    part1 = [i for i in moved if (i.get("part") or "I") == "I"]
    part2 = [i for i in moved if i.get("part") == "II"]
    rows, n = {"part_i": [], "part_ii": []}, 0
    for key, group in (("part_i", part1), ("part_ii", part2)):
        for i in group:
            n += 1
            rows[key].append({"number": n, "description_of_property": description_text(i),
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
    }


ORGANIZE_PROMPT = (
    "You split a person's plain description of what they own into separate items for a living trust intake. "
    "Return VALID JSON only: {\"items\": [{\"description\": str, \"kind\": one of "
    + json.dumps([k for k in KINDS if k != "unsure"]) + ", \"other_kind\": str or null}], \"retirement_left_out\": [str]}. "
    "Keep each description short, in the person's own words, specific enough for a stranger to find it. "
    "Never include full account numbers; keep only last 4 digits if given. "
    "Retirement accounts (IRA, Roth, 401k, 403b, pension, and similar) must NOT be items; list them in retirement_left_out. "
    "Use kind 'other' with other_kind from " + json.dumps(OTHER_KINDS) + " when nothing else fits. "
    "Do not use dashes. Do not invent items."
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
        items.append({"description": desc.replace("—", ",").replace("–", ","), "kind": kind, "other_kind": ok,
                      "other_text": desc if ok == "Something Else" else ""})
    return {"items": items, "retirement_left_out": left_out}
