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
    first = client_name.split(" ")[0]
    return (
        f"CLIENT: {client_name} (address as: {first})\n"
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

TASK: Write ONE plain-English walk-through per page for the pages below. Reference the client by first name, cite exact beneficiary shares by name where relevant, describe assets in plain words, and NEVER use legal jargon. If a page is blank, contains only headers/footers/signature blocks, or is a notary certificate, say so briefly and warmly (2-3 sentences).

CRITICAL: Do NOT write, quote, or mention any of these Latin/legal terms — not even to define them: settlor, corpus, per stirpes, per capita, in terrorem, spendthrift, hereinafter, aforementioned, fiduciary. If the source PDF uses one of these words, describe the concept without ever naming it. Example: instead of 'the term "per stirpes" means by branch', write 'if a beneficiary passes away before receiving their share, that share flows down to their own children'. Instead of 'an "in terrorem" clause', write 'a no-contest rule that says anyone who tries to fight the trust loses their share'.

Return ONLY this JSON (no markdown fences):
{{"pages":[{{"page":1,"text":"<p>...</p>"}}, ...]}}

Format rules for the "text" field: HTML only using <p>, <ul>, <li>, <strong>, <em>. 120-350 words per page is a healthy target for content pages, 30-80 words for blank/signature pages. Warm, direct, first-name address.

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
        out.append({"page": n, "text": txt})
    return out


async def explain_pages(pages: List[str], case_context: dict,
                        progress_cb: Optional[Callable] = None) -> List[Dict]:
    """Generate a plain-English explanation for each page in `pages` (list of
    strings, index 0 = page 1). Returns [{page:int, text:str}] in ascending
    page order. Returns [] on missing API key or complete failure."""
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
    logger.info(f"trust_page_explainer: {len(entries)} page(s) → {len(batches)} batch(es) of up to {PAGES_PER_BATCH}")

    aggregated: List[Dict] = []
    for i, batch in enumerate(batches, start=1):
        result = await _run_batch(api_key, ctx_brief, batch)
        aggregated.extend(result)
        if progress_cb:
            try:
                await progress_cb(i, len(batches), len(aggregated))
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
