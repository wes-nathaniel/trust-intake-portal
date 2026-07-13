"""
Trust PDF → sections extractor.
Given a trust document (PDF), extracts every Article and generates a
plain-English explainer for each. Returns a list of section dicts ready to
drop into `case.trust_sections[]`, which unlocks the synchronized two-panel
Trust Viewer for the client.

Uses Claude Sonnet 4.5 via the Emergent LLM Key.

Public API:
  extract_trust_sections(pdf_bytes: bytes, filename: str) -> list[dict]

Returns a list of {id, title, trust_html, explainer_html} dicts. Empty list on
any failure (never raises — the caller should fall back to the PDF viewer).
"""
from __future__ import annotations
import io
import json
import logging
import os
import re
import uuid
from typing import List, Dict

logger = logging.getLogger(__name__)

MAX_PDF_TEXT_CHARS = 120_000  # ~30 pages of dense legal text; fits Sonnet context.


def _extract_pdf_text(data: bytes) -> str:
    try:
        import pypdfium2 as pdfium
    except Exception as e:
        logger.warning(f"pypdfium2 unavailable: {e}")
        return ""
    try:
        pdf = pdfium.PdfDocument(data)
        out = []
        for i in range(len(pdf)):
            try:
                page = pdf[i]
                tp = page.get_textpage()
                out.append(tp.get_text_range() or "")
                tp.close()
                page.close()
            except Exception:
                continue
        pdf.close()
        return "\n".join(out).strip()
    except Exception as e:
        logger.warning(f"PDF text extraction failed: {e}")
        return ""


SYSTEM_PROMPT = (
    "You are a trust & estate paralegal parsing an uploaded trust document into "
    "structured, client-readable Articles. Never provide legal advice; explain "
    "existing text in plain English. Always return VALID JSON matching the schema "
    "exactly. Do NOT wrap the JSON in markdown or code fences."
)

USER_TEMPLATE = """Parse the following trust document into ordered Articles. For EACH Article:

1. Copy the legal text VERBATIM into `trust_html` — preserve paragraphs, numbered/lettered lists, and defined-term formatting (use <p>, <ol>, <ul>, <li>, <strong>, <em>).
2. Write a 2–4 sentence plain-English explanation in `explainer_html` — warm, non-legalese tone. Use <p> and <ul>/<li> when helpful. Never quote the legal text; paraphrase it.
3. `title` should mirror the document's exact heading (e.g. "Article I — Declaration of Trust"). If the document uses "SECTION 1" or similar, use that. If untitled, invent a short human title.

Return ONLY this JSON (no wrapper, no code fences):
{{
  "sections": [
    {{"title": "...", "trust_html": "...", "explainer_html": "..."}},
    ...
  ]
}}

Rules:
- Include EVERY article, in document order. Do not skip, merge, or renumber.
- If a "recitals" or preamble block appears before Article I, include it as the first section with title "Preamble".
- If the document has no clear articles, split by top-level headings or major numbered sections instead.
- Do not add sections that aren't in the document.

Trust document text (filename: {filename}, may be truncated):
---
{text}
---
"""


def _parse_json_lenient(raw: str) -> dict | None:
    if not raw:
        return None
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except Exception:
        pass
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


async def extract_trust_sections(pdf_bytes: bytes, filename: str) -> List[Dict]:
    """Return a list of {id, title, trust_html, explainer_html} sections
    extracted from the PDF. Empty list on any failure."""
    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key:
        logger.warning("extract_trust_sections: EMERGENT_LLM_KEY missing")
        return []
    text = _extract_pdf_text(pdf_bytes)
    if not text or len(text) < 200:
        logger.info(f"extract_trust_sections: PDF text too short ({len(text)} chars)")
        return []
    text = text[:MAX_PDF_TEXT_CHARS]

    user_prompt = USER_TEMPLATE.format(filename=filename or "trust.pdf", text=text)

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"trust-extract-{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_prompt))
    except Exception as e:
        logger.error(f"Trust extraction LLM call failed: {e}")
        return []

    raw_str = raw if isinstance(raw, str) else str(raw)
    parsed = _parse_json_lenient(raw_str)
    if not parsed or not isinstance(parsed.get("sections"), list):
        logger.error(f"Trust extraction: unparsable output ({raw_str[:400]})")
        return []

    out = []
    for i, s in enumerate(parsed["sections"]):
        if not isinstance(s, dict):
            continue
        title = str(s.get("title") or f"Article {i+1}").strip()[:200]
        trust_html = str(s.get("trust_html") or "").strip()
        explainer_html = str(s.get("explainer_html") or "").strip()
        if not trust_html and not explainer_html:
            continue
        out.append({
            "id": str(uuid.uuid4()),
            "title": title,
            "trust_html": trust_html,
            "explainer_html": explainer_html,
        })
    return out
