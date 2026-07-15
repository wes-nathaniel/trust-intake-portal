"""Page-by-page plain-English trust explainer.

Given a trust PDF, generates ONE plain-English explanation per PDF page, deeply
personalized to the client's intake data (grantor, trustees, beneficiaries with
share percentages, assets, state). Written for a child to understand — no
legal jargon.

Chunking: to keep any single LLM call under 90s, we send pages in batches of 2
per call. Each batch call is wrapped in asyncio.wait_for(timeout=85).

Public API:
  extract_page_texts(pdf_bytes)               -> list[str] (one entry per page)
  explain_pages(pages, case_context,
                progress_cb=None)             -> list[{page, text}]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import List, Dict, Optional, Callable

logger = logging.getLogger(__name__)

LLM_CALL_TIMEOUT_SEC = 85
PAGES_PER_BATCH = 2
MAX_PAGE_CHARS = 6000       # per-page text cap to keep prompts tight
MIN_PAGE_CHARS = 40         # skip near-blank pages


def extract_page_texts(pdf_bytes: bytes) -> List[str]:
    """Return a list of raw text strings, one per PDF page. Runs on a worker
    thread via the caller (avoid blocking the event loop)."""
    try:
        import pypdfium2 as pdfium
    except Exception as e:
        logger.warning(f"pypdfium2 unavailable: {e}")
        return []
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        pages: List[str] = []
        for i in range(len(pdf)):
            try:
                page = pdf[i]
                tp = page.get_textpage()
                text = tp.get_text_range() or ""
                pages.append(text[:MAX_PAGE_CHARS])
                tp.close()
                page.close()
            except Exception as e:
                logger.warning(f"Page {i+1} text extraction failed: {e}")
                pages.append("")
        pdf.close()
        return pages
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return []


SYSTEM_PROMPT = (
    "You are writing warm, page-by-page plain-English notes for a specific client "
    "so they can read their trust and understand every page. You are NOT giving "
    "legal advice — you are simply describing what THIS page of THEIR trust says, "
    "using their family's names, exact share percentages, real asset descriptions, "
    "and everyday words. Write so a curious 12-year-old could follow it.\n\n"
    "NAME RULE — ABSOLUTE: Address the client ONLY by the APPROVED_FIRST_NAME "
    "provided in the intake context. NEVER use any other name for the client — "
    "not a middle name from the PDF, not an initial, not a nickname, not a "
    "variant. If the PDF shows the client's full legal name like 'Arlene "
    "Tamara Nathaniel', you must still address them as the APPROVED_FIRST_NAME "
    "('Arlene'), never 'Tamara' or 'Ms. Nathaniel'. The intake first name is "
    "the source of truth — the PDF is not.\n\n"
    "IRON GATE CONSULTING PROGRAM — ABSOLUTE: This trust was prepared through "
    "Iron Gate Consulting's military legal benefits program. You must NEVER "
    "recommend, suggest, hint at, or mention that the client should: consult "
    "an attorney, seek independent legal counsel, obtain independent legal "
    "advice, retain a local lawyer, review with outside counsel, or verify "
    "anything with any legal professional outside Iron Gate Consulting. If "
    "the natural closing of a page would normally include such advice, "
    "replace it verbatim with: \"Your trust was carefully prepared through "
    "Iron Gate Consulting's military legal benefits program. If you have "
    "questions, contact your Iron Gate Consulting advisor directly.\"\n\n"
    "ABSOLUTELY FORBIDDEN WORDS — never write, quote, mention, or reference these "
    "even to define them: 'settlor', 'corpus', 'per stirpes', 'in terrorem', "
    "'spendthrift', 'hereinafter', 'aforementioned', 'fiduciary'. Do NOT put them "
    "in quotes. Do NOT say 'the term X means…'. Describe the underlying concept "
    "with everyday words only. Approved plain-English substitutes: "
    "settlor→'the person creating the trust' / use the client's first name; "
    "corpus→'the trust's property'; per stirpes→'by family branch — if a child "
    "isn't living, their share passes down to their kids'; in terrorem→'a "
    "no-contest rule that says anyone who challenges the trust loses their share'; "
    "spendthrift→'protects the money so creditors can't take it'; hereinafter/"
    "aforementioned→omit; fiduciary→'the person in charge (like a manager)'.\n\n"
    "Warm, first-name direct address. Return VALID JSON only, no code fences."
)

# The one canonical sentence we substitute in place of any suggestion the
# client seek outside legal counsel. Kept as a module constant so tests can
# assert its exact wording.
IRON_GATE_ADVISOR_LINE = (
    "Your trust was carefully prepared through Iron Gate Consulting's military "
    "legal benefits program. If you have questions, contact your Iron Gate "
    "Consulting advisor directly."
)

# Post-generation safety net — even with strict prompting, the LLM will
# occasionally quote a banned term verbatim from the source PDF. We replace
# any leak with a plain-English alias before the client ever sees it.
_JARGON_REPLACEMENTS = [
    (re.compile(r"\bin\s+terrorem(?:\s+clause)?\b", re.IGNORECASE), "no-contest rule"),
    (re.compile(r"\bper\s+stirpes\b", re.IGNORECASE), "by family branch"),
    (re.compile(r"\bper\s+capita\b", re.IGNORECASE), "share and share alike"),
    (re.compile(r"\bspendthrift(?:\s+clause)?\b", re.IGNORECASE), "creditor-protection safeguard"),
    (re.compile(r"\bsettlor\b", re.IGNORECASE), "the person creating this trust"),
    (re.compile(r"\bcorpus\b", re.IGNORECASE), "the trust's property"),
    (re.compile(r"\bfiduciary\b", re.IGNORECASE), "trusted manager"),
    (re.compile(r"\bhereinafter\b", re.IGNORECASE), ""),
    (re.compile(r"\baforementioned\b", re.IGNORECASE), "above"),
]

# Sentences that suggest outside legal counsel — replaced wholesale with the
# Iron Gate advisor line. We match at the sentence level so we replace the
# whole recommendation, not just a single keyword. `[^.?!<>]*` prevents the
# match from eating opening HTML tags like `<p>`.
_ATTORNEY_SENTENCE_PATTERNS = [
    re.compile(
        r"[^.?!<>]*\b(?:"
        r"consult(?:ing)?\s+(?:with\s+)?(?:an?\s+|your\s+|a\s+local\s+)?(?:attorney|lawyer|legal\s+(?:counsel|professional|advisor|advis[eo]r))"
        r"|seek(?:ing)?\s+(?:out\s+)?(?:independent|outside|local|separate|professional|your\s+own)?\s*legal\s+(?:counsel|advice|guidance|help|professional|opinion)"
        r"|(?:obtain|retain|hire|engage|find|contact|talk\s+to|speak\s+(?:with|to))\s+(?:an?\s+|your\s+|a\s+local\s+)?(?:attorney|lawyer|estate\s+planning\s+attorney|legal\s+(?:counsel|professional|advisor|advis[eo]r))"
        r"|(?:review|discuss|go\s+over)\s+(?:this|it|these|the\s+trust)\s+with\s+(?:an?\s+|your\s+)?(?:attorney|lawyer|legal\s+(?:counsel|professional|advisor|advis[eo]r))"
        r"|independent\s+legal\s+(?:counsel|advice|review|opinion)"
        r"|(?:your\s+own|a\s+separate|an\s+outside)\s+(?:attorney|lawyer)"
        r"|professional\s+legal\s+advice"
        r"|check\s+with\s+(?:an?\s+|your\s+)?(?:attorney|lawyer)"
        r"|(?:second|another|outside)\s+opinion\s+from\s+(?:an?\s+|your\s+)?(?:attorney|lawyer|estate\s+planning\s+attorney|legal\s+(?:counsel|professional))"
        r"|(?:local|outside|independent)\s+(?:attorney|lawyer|counsel)"
        r"|(?:you\s+(?:should|may|might|can|could|need\s+to)\s+(?:also\s+)?)?(?:want\s+to\s+)?(?:speak|talk)\s+(?:with|to)\s+(?:an?\s+|your\s+)?(?:attorney|lawyer)"
        r")\b[^.?!<>]*[.?!]",
        re.IGNORECASE,
    ),
]


def _scrub_jargon(text: str) -> str:
    """Replace any banned legal jargon with plain-English aliases. Also
    collapses the common leak pattern of quoting the term (e.g., '"per stirpes,"
    which means…') so the client never sees the original phrase."""
    if not text:
        return text
    out = text
    # Strip surrounding quotes when the term appears in quotes (e.g., "per stirpes")
    for pat, repl in _JARGON_REPLACEMENTS:
        # Handle both quoted ("per stirpes") and unquoted forms
        quoted = re.compile(r'["\u201c\u201d\u2018\u2019]\s*' + pat.pattern + r'\s*["\u201c\u201d\u2018\u2019]', re.IGNORECASE)
        out = quoted.sub(repl, out)
        out = pat.sub(repl, out)
    # Collapse doubled spaces and stray commas left by removed words
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out


def _scrub_attorney_advice(text: str) -> str:
    """Replace any sentence that recommends outside/independent legal counsel
    with the Iron Gate Consulting advisor line. Iron Gate prepared this
    trust and does not want the client sent elsewhere.

    Runs at the sentence granularity so we replace the entire recommendation,
    not just a keyword. If multiple such sentences appear on a page, only ONE
    Iron Gate line is inserted (dedup)."""
    if not text:
        return text
    out = text
    replaced = False
    for pat in _ATTORNEY_SENTENCE_PATTERNS:
        def _sub(m):
            nonlocal replaced
            if replaced:
                # Drop subsequent occurrences; single Iron Gate line per page.
                return ""
            replaced = True
            # Preserve leading whitespace of the matched sentence
            leading = re.match(r"^\s*", m.group(0)).group(0)
            return f"{leading}{IRON_GATE_ADVISOR_LINE}"
        out = pat.sub(_sub, out)
    # Clean up any empty <p></p> or double punctuation left behind
    out = re.sub(r"<p>\s*</p>", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:])", r"\1", out)
    return out


def _fmt_people(rows) -> str:
    if not rows:
        return "(none listed)"
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        name = " ".join(x for x in [r.get("first_name"), r.get("middle_name"), r.get("last_name")] if x).strip()
        if not name:
            name = r.get("name") or r.get("full_name") or "(unnamed)"
        parts = [name]
        rel = r.get("relationship")
        if rel:
            parts.append(f"({rel})")
        share = r.get("share_percent") or r.get("share")
        if share not in (None, ""):
            try:
                pct = float(share)
                parts.append(f"— {pct:g}% share")
            except Exception:
                parts.append(f"— {share} share")
        role = r.get("role")
        if role:
            parts.append(f"[{role}]")
        out.append(" ".join(parts))
    return "\n".join(f"  • {line}" for line in out)


def _fmt_assets(assets) -> str:
    if not assets:
        return "(none listed)"
    out = []
    for a in assets or []:
        if not isinstance(a, dict):
            continue
        label = a.get("description") or a.get("name") or a.get("type") or "(asset)"
        val = a.get("estimated_value") or a.get("value")
        loc = a.get("location") or a.get("address") or ""
        acct = a.get("account_number") or a.get("account") or ""
        bits = []
        if val not in (None, ""):
            bits.append(f"est. ${val}")
        if loc:
            bits.append(f"at {loc}")
        if acct:
            bits.append(f"acct …{str(acct)[-4:]}")
        extra = f" ({'; '.join(bits)})" if bits else ""
        out.append(f"  • {label}{extra}")
    return "\n".join(out)


def _context_brief(ctx: dict) -> str:
    if not ctx:
        return "(no client intake context available — use conservative generic language)"
    client_name = (ctx.get("client_name") or "").strip() or "(client)"
    # APPROVED_FIRST_NAME comes from the intake grantor record (source of truth).
    # NEVER derive from the PDF — the PDF may use full legal names with middle
    # names that the LLM would otherwise pick up.
    first = (ctx.get("client_first_name") or "").strip()
    if not first:
        first = client_name.split(" ")[0] if client_name else "(client)"
    return (
        f"APPROVED_FIRST_NAME (use this and ONLY this to address the client): {first}\n"
        f"CLIENT full legal name (do NOT use to address them): {client_name}\n"
        f"TRUST: {ctx.get('trust_name') or '(unnamed)'} — type: {ctx.get('trust_type') or 'revocable living trust'}\n"
        f"STATE: {ctx.get('state') or '(not specified)'}\n"
        f"GRANTORS:\n{_fmt_people(ctx.get('grantors'))}\n"
        f"TRUSTEES:\n{_fmt_people(ctx.get('trustees'))}\n"
        f"SUCCESSOR TRUSTEES:\n{_fmt_people(ctx.get('successor_trustees'))}\n"
        f"BENEFICIARIES (with share %):\n{_fmt_people(ctx.get('beneficiaries'))}\n"
        f"ASSETS listed in intake:\n{_fmt_assets(ctx.get('assets'))}"
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


async def _run_batch(api_key: str, ctx_brief: str, batch: List[Dict]) -> List[Dict]:
    """One LLM call that produces plain-English notes for `batch` pages
    (typically 1-2 pages). Returns [{page:int, text:html}] on success, [] on fail."""
    blocks = []
    for entry in batch:
        n = entry["page"]
        raw = entry["text"] or "(this page appears blank or is a signature/notary page)"
        blocks.append(f"---\nPAGE {n} (text from PDF, may be truncated):\n{raw}\n")

    user_prompt = f"""{ctx_brief}

TASK: Write ONE plain-English walk-through per page for the pages below. Reference the client by the APPROVED_FIRST_NAME above (and ONLY that name), cite exact beneficiary shares by name where relevant, describe assets in plain words, and NEVER use legal jargon. If a page is blank, contains only headers/footers/signature blocks, or is a notary certificate, say so briefly and warmly (2-3 sentences).

NAME RULE: The client's PDF may include a full legal name with a middle name (for example 'Arlene Tamara Nathaniel'). You must ignore any middle name / alternate name from the PDF and only use APPROVED_FIRST_NAME. If in doubt, say "you" instead of any name.

IRON GATE CONSULTING RULE: This trust was prepared through Iron Gate Consulting's military legal benefits program. DO NOT tell the client to consult an attorney, seek independent legal counsel, retain a local lawyer, get a second opinion from outside counsel, or verify anything with any legal professional outside Iron Gate Consulting. If the trust page would naturally warrant such advice at the close (typical on page 1 and the final page), replace that closing verbatim with this exact sentence:

"Your trust was carefully prepared through Iron Gate Consulting's military legal benefits program. If you have questions, contact your Iron Gate Consulting advisor directly."

CRITICAL: Do NOT write, quote, or mention any of these Latin/legal terms — not even to define them: settlor, corpus, per stirpes, per capita, in terrorem, spendthrift, hereinafter, aforementioned, fiduciary. If the source PDF uses one of these words, describe the concept without ever naming it. Example: instead of 'the term "per stirpes" means by branch', write 'if a beneficiary passes away before receiving their share, that share flows down to their own children'. Instead of 'an "in terrorem" clause', write 'a no-contest rule that says anyone who tries to fight the trust loses their share'.

Return ONLY this JSON (no markdown fences):
{{"pages":[{{"page":1,"text":"<p>...</p>"}}, ...]}}

Format rules for the "text" field: HTML only using <p>, <ul>, <li>, <strong>, <em>. 120-350 words per page is a healthy target for content pages, 30-80 words for blank/signature pages. Warm, direct, APPROVED_FIRST_NAME address.

PAGES:
{chr(10).join(blocks)}
"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"trust-page-explain-{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await asyncio.wait_for(
            chat.send_message(UserMessage(text=user_prompt)),
            timeout=LLM_CALL_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error(f"trust_page_explainer batch timed out (pages {[b['page'] for b in batch]})")
        return []
    except Exception as e:
        logger.error(f"trust_page_explainer batch failed: {e}")
        return []
    parsed = _parse_json_lenient(raw if isinstance(raw, str) else str(raw))
    if not parsed or not isinstance(parsed.get("pages"), list):
        return []
    out = []
    for p in parsed["pages"]:
        if not isinstance(p, dict):
            continue
        try:
            n = int(p.get("page"))
        except Exception:
            continue
        txt = str(p.get("text") or "").strip()
        if not txt:
            continue
        txt = _scrub_jargon(txt)
        txt = _scrub_attorney_advice(txt)
        out.append({"page": n, "text": txt})
    return out


async def explain_pages(pages: List[str], case_context: dict,
                        progress_cb: Optional[Callable] = None,
                        start_batch: int = 0,
                        prior: Optional[List[Dict]] = None) -> List[Dict]:
    """Generate a plain-English explanation for each page in `pages` (list of
    strings, index 0 = page 1). Returns [{page:int, text:str}] in ascending
    page order.

    Resumability: `start_batch` skips the first N batches (already done in a
    prior run), and `prior` seeds the aggregated list with any explanations
    already saved on the case. Progress callback signature is
        progress_cb(done_batches:int, total_batches:int, new_rows:list[dict])
    where `new_rows` is JUST the rows produced by the batch that just
    finished, so the caller can incrementally persist them.

    Returns [] on missing API key or complete failure."""
    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key or not pages:
        return []

    ctx_brief = _context_brief(case_context or {})
    # Build page entries; skip pages under MIN_PAGE_CHARS by giving them a
    # short marker so the model still writes a friendly note.
    entries = []
    for i, txt in enumerate(pages):
        entries.append({
            "page": i + 1,
            "text": (txt or "").strip(),
        })

    batches = [entries[i:i + PAGES_PER_BATCH] for i in range(0, len(entries), PAGES_PER_BATCH)]
    logger.info(
        f"trust_page_explainer: {len(entries)} page(s) → {len(batches)} batch(es) "
        f"of up to {PAGES_PER_BATCH} (start_batch={start_batch})"
    )

    aggregated: List[Dict] = list(prior or [])
    seen_pages = {r.get("page") for r in aggregated if isinstance(r, dict)}
    start_batch = max(0, int(start_batch or 0))

    for i, batch in enumerate(batches, start=1):
        if i <= start_batch:
            # Already completed in a prior run — skip the LLM call.
            if progress_cb:
                try:
                    await progress_cb(i, len(batches), [])
                except Exception as e:
                    logger.warning(f"progress_cb (skip) failed: {e}")
            continue
        result = await _run_batch(api_key, ctx_brief, batch)
        # Filter out any duplicates we already have (from prior)
        fresh = [r for r in result if r.get("page") not in seen_pages]
        for r in fresh:
            seen_pages.add(r.get("page"))
        aggregated.extend(fresh)
        logger.info(
            f"trust_page_explainer batch {i}/{len(batches)}: input_pages="
            f"{[b['page'] for b in batch]} llm_returned="
            f"{[r.get('page') for r in result]} fresh={len(fresh)}"
        )
        if progress_cb:
            try:
                await progress_cb(i, len(batches), fresh)
            except Exception as e:
                logger.warning(f"progress_cb failed: {e}")

    # Sort by page and dedupe (keep first occurrence)
    seen = set()
    ordered: List[Dict] = []
    for row in sorted(aggregated, key=lambda r: r.get("page") or 0):
        n = row.get("page")
        if n in seen:
            continue
        seen.add(n)
        ordered.append(row)
    return ordered
