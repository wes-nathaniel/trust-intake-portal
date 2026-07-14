"""Trust explainer enrichment.

After `trust_extractor.extract_trust_sections()` returns the article-by-article
sections, this module makes ONE additional Claude Sonnet 4.5 call to produce
9 educational "overview" sections that flow directly after the article
explanations. They are appended to the same sections list (with
`kind="educational"`) so the frontend renders them as part of a single,
continuous scroll — no second page, no separate scroll area.

Sections generated (in order):
  1. Grantor Overview
  2. Trustee Overview
  3. Successor Trustee Overview
  4. Incapacity Procedures
  5. Death Procedures
  6. Asset Protection Basics
  7. Distribution Logic
  8. Trust Fundamentals
  9. "What happens if…" scenarios

Same voice, same HTML formatting (<p>, <ul>, <li>, <strong>, <em>) as the
per-article explainers so the client experiences one seamless narrative.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

LLM_CALL_TIMEOUT_SEC = 85

SECTION_SPECS = [
    ("Grantor Overview",
     "Who the Grantor is, what powers they retain while alive and competent, "
     "their day-to-day responsibilities, what happens if they become incapacitated, "
     "and what happens at their death. Refer to grantor names from the articles when known."),
    ("Trustee Overview",
     "Who the Trustee is (initially the Grantor in most revocable trusts), their fiduciary duties "
     "(loyalty, prudence, impartiality, duty to account), day-to-day powers, and the "
     "standard of care they must meet."),
    ("Successor Trustee Overview",
     "Who the named Successor Trustee is, exactly when they step in (incapacity or death of prior trustee), "
     "what authority they hold, and what safeguards exist to prevent abuse. Refer to successor names when known."),
    ("Incapacity Procedures",
     "How incapacity is proven (usually two physicians' letters or a certified capacity certificate), "
     "how the Successor Trustee takes over without going to court, what bills and needs the trustee must handle, "
     "and how the client's health and finances are protected during that period."),
    ("Death Procedures",
     "What happens the moment the Grantor dies: the trust becomes irrevocable, the Successor Trustee's "
     "immediate duties (notify beneficiaries, gather assets, pay final debts and taxes, then distribute), "
     "and typical timing (weeks to a few months, avoiding probate)."),
    ("Asset Protection Basics",
     "How this trust protects the client's estate from probate, from public court records, and — for "
     "beneficiaries — how spendthrift clauses shield inherited assets from creditors, lawsuits, and divorce claims. "
     "Be honest about what a revocable trust does NOT protect (Grantor's own creditors during life)."),
    ("Distribution Logic",
     "How assets actually move from the trust to beneficiaries: outright vs. staged distributions, per stirpes vs. "
     "per capita, discretionary distributions by the Trustee, and how the Trustee decides in gray-area situations. "
     "Refer to beneficiary structures mentioned in the articles."),
    ("Trust Fundamentals",
     "The big-picture 'why': probate avoidance, privacy, incapacity planning, tax neutrality (for a revocable trust), "
     "and the difference between revocable and irrevocable. Written for a client who has never had a trust before."),
    ("\"What happens if…\" scenarios",
     "Concrete answers to the questions clients almost always ask: what if the Grantor becomes incapacitated? "
     "what if the Successor Trustee dies or refuses? what if a beneficiary is a minor / has creditor problems / has "
     "special needs? what if a beneficiary contests the trust? what if the family disagrees? Give 5-8 short scenarios "
     "as an unordered list, each 1-3 sentences."),
]

SYSTEM_PROMPT = (
    "You are a warm, knowledgeable trust & estate paralegal writing client-facing "
    "educational content in plain English. Match the voice, formatting, and HTML "
    "conventions of the per-article explainers already produced for this trust: "
    "use <p>, <ul>, <li>, <strong>, <em> only. Define legal jargon inline. Never "
    "provide new legal advice — explain the law and the trust as they exist. "
    "Return VALID JSON only, no code fences."
)


def _build_context_summary(articles: List[Dict]) -> str:
    """Assemble a concise brief of the extracted articles so Claude can
    personalize the educational sections (names, structure, unusual clauses)."""
    lines = []
    for a in articles:
        num = (a.get("article_number") or "").strip()
        title = (a.get("article_title") or "").strip()
        # Strip HTML for the summary — we only need signal, not legal text.
        body = re.sub(r"<[^>]+>", " ", a.get("article_text") or "")
        body = re.sub(r"\s+", " ", body).strip()
        excerpt = body[:500]
        prefix = num if num.lower() == "preamble" else f"Article {num}"
        lines.append(f"{prefix} — {title}: {excerpt}")
    return "\n".join(lines)


def _spec_json(articles: List[Dict]) -> str:
    ctx = _build_context_summary(articles)
    spec_lines = []
    for i, (name, brief) in enumerate(SECTION_SPECS, start=1):
        spec_lines.append(f'{i}. "{name}" — {brief}')
    return (
        "TRUST CONTEXT (the articles already extracted for this trust):\n"
        f"{ctx or '(no article context provided)'}\n\n"
        "TASK: Produce the following 9 educational sections, in order, tailored to the "
        "trust above (use the actual grantor / trustee / beneficiary names where they "
        "appear in the context). Keep each section focused; 200-450 words each is a "
        "good target. Use <p> paragraphs, and <ul><li> lists where helpful.\n\n"
        + "\n".join(spec_lines)
        + "\n\nReturn ONLY this JSON (no markdown fences):\n"
        + '{"sections":[{"article_title":"Grantor Overview","explainer_text":"<p>…</p>"}, ...]}'
    )


def _parse_json_lenient(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except Exception:
        pass
    m = re.search(r"\{.*\}", s, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


async def enrich_sections(articles: List[Dict], filename: str = "trust.pdf") -> List[Dict]:
    """Given the article sections produced by `trust_extractor`, generate the
    9 educational overview sections and return them as ready-to-append section
    dicts. Returns a hardcoded-template fallback on any LLM failure so the
    client always gets a complete explainer."""
    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()

    llm_sections: List[Dict] = []
    if api_key and articles:
        try:
            from emergentintegrations.llm.chat import LlmChat, UserMessage
            chat = LlmChat(
                api_key=api_key,
                session_id=f"trust-enrich-{uuid.uuid4().hex[:8]}",
                system_message=SYSTEM_PROMPT,
            ).with_model("anthropic", "claude-sonnet-4-5-20250929")
            raw = await asyncio.wait_for(
                chat.send_message(UserMessage(text=_spec_json(articles))),
                timeout=LLM_CALL_TIMEOUT_SEC,
            )
            parsed = _parse_json_lenient(raw if isinstance(raw, str) else str(raw))
            if parsed and isinstance(parsed.get("sections"), list):
                llm_sections = parsed["sections"]
        except asyncio.TimeoutError:
            logger.error("enrich_sections: LLM call timed out")
        except Exception as e:
            logger.error(f"enrich_sections: LLM call failed: {e}")

    # Normalize into the canonical section schema.
    out: List[Dict] = []
    for i, (canonical_title, _brief) in enumerate(SECTION_SPECS):
        llm_entry = llm_sections[i] if i < len(llm_sections) else None
        explainer = ""
        title = canonical_title
        if llm_entry and isinstance(llm_entry, dict):
            explainer = str(llm_entry.get("explainer_text") or llm_entry.get("explainer_html") or "").strip()
            # If LLM used a slightly different title, keep the canonical one so
            # ordering + navigation feel consistent.
        if not explainer:
            explainer = _fallback_body(canonical_title)
        out.append({
            "id": str(uuid.uuid4()),
            "kind": "educational",
            "article_number": f"Overview {i + 1}",
            "article_title": title,
            "article_text": "",  # No legal text — educational content sits in the right pane only
            "explainer_text": explainer,
            # Legacy aliases (kept for older consumers)
            "title": title,
            "trust_html": "",
            "explainer_html": explainer,
        })
    return out


# --- Fallback content (used only if the LLM call fails entirely so the ----
# client never sees a broken explainer). Kept intentionally short.
_FALLBACK = {
    "Grantor Overview": "<p>The <strong>Grantor</strong> is the person who creates and funds the trust. While alive and mentally competent, the Grantor typically keeps full control — you can add or remove property, change beneficiaries, or dissolve the trust at any time. If the Grantor becomes incapacitated, the Successor Trustee takes over management. At the Grantor's death, the trust becomes irrevocable and the assets pass to the beneficiaries according to its terms — usually without probate.</p>",
    "Trustee Overview": "<p>The <strong>Trustee</strong> is the person or entity managing the trust's assets. In a typical revocable trust, the Grantor is the initial Trustee. The Trustee owes <em>fiduciary duties</em> to the beneficiaries: <strong>loyalty</strong> (act in their interest, not the Trustee's), <strong>prudence</strong> (invest and manage carefully), <strong>impartiality</strong> (treat all beneficiaries fairly), and <strong>duty to account</strong> (keep records and report to beneficiaries). The Trustee has broad powers to invest, sell, distribute, and defend trust property.</p>",
    "Successor Trustee Overview": "<p>The <strong>Successor Trustee</strong> is the person you name to take over if you can no longer serve — because of incapacity, death, or resignation. They step in <em>automatically</em> under the trust's terms; no court order is needed. Once serving, they hold the same fiduciary duties and powers as the original Trustee.</p>",
    "Incapacity Procedures": "<p>The trust typically defines incapacity as two independent physicians certifying in writing that the current Trustee can no longer manage financial affairs. Once documented, the Successor Trustee immediately assumes control. They can then pay bills, manage investments, handle housing decisions, and coordinate with health-care agents under a separate durable power of attorney. Because the trust already owns the assets, there is no court intervention and no delay.</p>",
    "Death Procedures": "<p>At the Grantor's death, the trust becomes <strong>irrevocable</strong> — its terms lock in. The Successor Trustee has several duties: (1) notify beneficiaries and required parties in writing, (2) marshal the trust's assets and inventory them, (3) pay final debts, funeral expenses, and any taxes owed, and (4) distribute the remaining assets to the beneficiaries as the trust directs. Because the trust already holds title to the assets, this happens outside of probate — typically in weeks or a few months rather than the year-plus a probate court takes.</p>",
    "Asset Protection Basics": "<p>This trust provides several forms of protection:</p><ul><li><strong>Probate avoidance</strong> — assets titled in the trust bypass court supervision, saving time, cost, and public exposure.</li><li><strong>Privacy</strong> — probate is public; a trust is not.</li><li><strong>Spendthrift protection for beneficiaries</strong> — once an inheritance is held in a beneficiary's sub-trust, it is generally shielded from that beneficiary's creditors, lawsuits, and divorce claims.</li></ul><p>Important honesty: while you are alive and control the trust as Grantor, your own creditors can generally still reach these assets. Full creditor protection kicks in only after death, once the trust is irrevocable.</p>",
    "Distribution Logic": "<p>How assets move to beneficiaries depends on what the trust says. Common patterns include:</p><ul><li><strong>Outright</strong> — the beneficiary receives their share free and clear.</li><li><strong>Staged</strong> — distributed at ages (e.g., 1/3 at 25, 1/3 at 30, balance at 35).</li><li><strong>Discretionary</strong> — the Trustee decides amount and timing based on standards like health, education, maintenance, and support.</li></ul><p><em>Per stirpes</em> means each family branch shares equally: if a child predeceases you, their share is split among their own descendants. <em>Per capita</em> means every living beneficiary at the same level shares equally regardless of branch.</p>",
    "Trust Fundamentals": "<p>A <strong>revocable living trust</strong> is a legal container you create during life to hold your property. Because the trust — not you personally — holds title to the assets, they pass at death without going through probate court. During life, you keep full control: you can amend, revoke, or ignore the trust at any time. A revocable trust is tax-neutral (income is reported on your personal return using your SSN) and does not protect assets from your creditors while you live. It becomes irrevocable at your death, at which point it locks in and delivers your instructions to your beneficiaries.</p>",
    "\"What happens if…\" scenarios": "<ul><li><strong>If the Grantor becomes incapacitated:</strong> two physicians' letters trigger the Successor Trustee to take over without court involvement.</li><li><strong>If the Successor Trustee dies, resigns, or refuses:</strong> the next-named alternate serves; if none is named, beneficiaries can petition to appoint one.</li><li><strong>If a beneficiary is a minor:</strong> their share is held in a sub-trust until the trust's specified age.</li><li><strong>If a beneficiary has creditor or lawsuit issues:</strong> spendthrift language keeps their share protected inside the trust; the Trustee can pay expenses for them directly.</li><li><strong>If a beneficiary has special needs:</strong> a supplemental-needs sub-trust keeps public benefits eligibility intact.</li><li><strong>If a beneficiary contests the trust:</strong> a no-contest (<em>in terrorem</em>) clause can forfeit their share if the challenge fails.</li><li><strong>If the family disagrees:</strong> the Trustee follows the written terms — the trust is designed to prevent family conflict, not require consensus.</li></ul>",
}


def _fallback_body(title: str) -> str:
    return _FALLBACK.get(title, f"<p>Educational content for {title} is being prepared.</p>")
