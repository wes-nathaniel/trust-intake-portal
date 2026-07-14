"""
Trust PDF → sections extractor.
Given a trust document (PDF), extracts every Article and generates a
plain-English explainer for each. Returns a list of section dicts ready to
drop into `case.trust_sections[]`, which unlocks the synchronized two-panel
Trust Viewer for the client.

Uses Claude Sonnet 4.5 via the Emergent LLM Key.

Public API:
  extract_trust_sections(pdf_bytes: bytes, filename: str) -> list[dict]

Returns a list of {id, article_number, article_title, article_text,
explainer_text, ...} dicts. Empty list on any failure.

Chunking strategy (per support recommendation):
  1. Extract raw PDF text.
  2. Split by Article headings into logical blocks.
  3. Send blocks in batches of ~3 to Claude per call (wrapped in
     asyncio.wait_for(timeout=85) so a single call can't hang forever).
  4. Aggregate results.

This keeps any single LLM call under ~90s and lets the whole extraction
progress incrementally in a background task.
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

MAX_PDF_TEXT_CHARS = 200_000            # extended — chunking handles context safely
LLM_CALL_TIMEOUT_SEC = 85               # single-call ceiling (support recommendation)
SECTIONS_PER_BATCH = 3                  # 3 sections per LLM call
MIN_BATCH_CHARS = 400                   # skip trivially small batches

# --- Article splitting ---
_ARTICLE_HEAD = re.compile(
    r"(?im)^\s*(?:ARTICLE|Article)\s+"
    r"(?P<num>[IVXLCDM]+|\d+)\s*[\.\-—:]?\s*(?P<title>.*)$"
)
_PREAMBLE_HEAD = re.compile(r"(?im)^\s*(preamble|recitals|introduction)\s*$")


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


def _split_into_articles(text: str) -> List[Dict[str, str]]:
    """Break PDF text into Preamble + Article blocks by heading regex.
    Falls back to a single block covering the whole doc when no headings match."""
    if not text:
        return []

    # Locate every article heading with its position
    matches = list(_ARTICLE_HEAD.finditer(text))
    if not matches:
        # No Article headings — return one giant block; the LLM will do its best.
        return [{
            "article_number": "N/A",
            "article_title": "",
            "raw_text": text.strip(),
        }]

    blocks: List[Dict[str, str]] = []

    # Everything before the first Article heading = Preamble/Recitals (if any).
    preamble_text = text[: matches[0].start()].strip()
    if len(preamble_text) >= MIN_BATCH_CHARS:
        blocks.append({
            "article_number": "Preamble",
            "article_title": "Introduction",
            "raw_text": preamble_text,
        })

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block_text = text[start:end].strip()
        num = (m.group("num") or "").strip().upper()
        title = (m.group("title") or "").strip()[:200]
        # Clean up the title line — many docs put it on the same line as the heading
        # but sometimes it's on the next line, so keep whatever regex captured.
        blocks.append({
            "article_number": num,
            "article_title": title,
            "raw_text": block_text,
        })

    return blocks


SYSTEM_PROMPT = (
    "You are a trust & estate paralegal parsing an uploaded trust document into "
    "structured, client-readable Articles. Never provide legal advice; explain "
    "existing text in plain English. Always return VALID JSON matching the schema "
    "exactly. Do NOT wrap the JSON in markdown or code fences."
)

BATCH_USER_TEMPLATE = """Below are {n} consecutive block(s) from a trust document (filename: {filename}). For EACH block, produce a section object with these fields:

1. `article_number` — the Roman/Arabic numeral or the literal word "Preamble" as it appears (never invent one).
2. `article_title` — the heading text WITHOUT the "Article X — " prefix (e.g. "Declaration of Trust").
3. `article_text` — the block's legal text VERBATIM. Preserve paragraphs and numbered/lettered lists. Use ONLY these HTML tags: <p>, <ol>, <ul>, <li>, <strong>, <em>. Do NOT paraphrase, shorten, or summarize.
4. `explainer_text` — a friendly plain-English walk-through of every meaningful sentence/clause in the same order. Define legal jargon inline (e.g. "'per stirpes' means each family branch shares equally"). Warm, non-condescending. Use <p> and <ul>/<li> as helpful.

Return ONLY this JSON (no wrapper, no code fences):
{{
  "sections": [
    {{"article_number": "...", "article_title": "...", "article_text": "...", "explainer_text": "..."}}
  ]
}}

Rules:
- Preserve document order.
- Every explainer must define any legal terms it uses (trustee, grantor, per stirpes, spendthrift, corpus, in terrorem, etc.).
- Do NOT invent sections that aren't in the block text.

BLOCKS:
{blocks}
"""


def _parse_json_lenient(raw: str) -> Optional[dict]:
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


async def _run_batch(api_key: str, filename: str, batch: List[Dict[str, str]]) -> List[Dict]:
    """Send one batch of 1-N blocks to Claude with a hard timeout. Returns
    a list of parsed section dicts (may be shorter than batch on partial failure)."""
    formatted = []
    for idx, b in enumerate(batch, start=1):
        formatted.append(
            f"---\nBLOCK {idx} (article_number hint: {b['article_number']}, title hint: {b['article_title'] or 'n/a'}):\n{b['raw_text']}\n"
        )
    user_prompt = BATCH_USER_TEMPLATE.format(
        n=len(batch),
        filename=filename or "trust.pdf",
        blocks="\n".join(formatted),
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"trust-extract-{uuid.uuid4().hex[:8]}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await asyncio.wait_for(
            chat.send_message(UserMessage(text=user_prompt)),
            timeout=LLM_CALL_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.error(f"Trust extraction batch timed out after {LLM_CALL_TIMEOUT_SEC}s (blocks {[b['article_number'] for b in batch]})")
        return []
    except Exception as e:
        logger.error(f"Trust extraction batch LLM call failed: {e}")
        return []

    raw_str = raw if isinstance(raw, str) else str(raw)
    parsed = _parse_json_lenient(raw_str)
    if not parsed or not isinstance(parsed.get("sections"), list):
        logger.error(f"Trust extraction: unparsable batch output ({raw_str[:400]})")
        return []
    return parsed["sections"]


def _finalize(sections_raw: List[Dict]) -> List[Dict]:
    """Normalize model output into the canonical schema and drop empties."""
    out = []
    for i, s in enumerate(sections_raw):
        if not isinstance(s, dict):
            continue
        article_number = str(s.get("article_number") or "").strip()[:20] or str(i + 1)
        article_title = str(s.get("article_title") or s.get("title") or f"Article {article_number}").strip()[:200]
        article_text = str(s.get("article_text") or s.get("trust_html") or "").strip()
        explainer_text = str(s.get("explainer_text") or s.get("explainer_html") or s.get("explain_html") or "").strip()
        if not article_text and not explainer_text:
            continue
        prefix = "" if article_number.lower() in {"", "preamble"} else f"Article {article_number} — "
        composite_title = f"{prefix}{article_title}".strip(" —")
        out.append({
            "id": str(uuid.uuid4()),
            "article_number": article_number,
            "article_title": article_title,
            "article_text": article_text,
            "explainer_text": explainer_text,
            # Legacy aliases (kept for older consumers)
            "title": composite_title,
            "trust_html": article_text,
            "explainer_html": explainer_text,
        })
    return out


async def extract_trust_sections(pdf_bytes: bytes, filename: str,
                                 progress_cb=None) -> List[Dict]:
    """Main entry point. Returns a list of section dicts.

    `progress_cb`, if provided, is called as `progress_cb(done_batches,
    total_batches, aggregated_count)` after every batch so callers can stream
    progress into a job status doc."""
    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key:
        logger.warning("extract_trust_sections: EMERGENT_LLM_KEY missing")
        return []

    text = await asyncio.to_thread(_extract_pdf_text, pdf_bytes)
    if not text or len(text) < 200:
        logger.info(f"extract_trust_sections: PDF text too short ({len(text)} chars)")
        return []
    text = text[:MAX_PDF_TEXT_CHARS]

    blocks = _split_into_articles(text)
    if not blocks:
        return []

    # Group blocks into batches of SECTIONS_PER_BATCH
    batches: List[List[Dict]] = [
        blocks[i:i + SECTIONS_PER_BATCH]
        for i in range(0, len(blocks), SECTIONS_PER_BATCH)
    ]
    logger.info(
        f"extract_trust_sections: {len(blocks)} block(s) → {len(batches)} batch(es) of up to {SECTIONS_PER_BATCH}"
    )

    aggregated_raw: List[Dict] = []
    for i, batch in enumerate(batches, start=1):
        result = await _run_batch(api_key, filename or "trust.pdf", batch)
        aggregated_raw.extend(result)
        if progress_cb:
            try:
                await progress_cb(i, len(batches), len(aggregated_raw))
            except Exception as e:
                logger.warning(f"progress_cb failed: {e}")

    return _finalize(aggregated_raw)
