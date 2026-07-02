"""
AI Document Explainer — extracts text from an uploaded document (PDF/DOCX/TXT/image)
and asks Claude Sonnet 4.5 (via Emergent LLM Key) to produce a short structured
explanation the client can read directly under the document in the portal.

Public API:
  * extract_text(data: bytes, filename: str, mime: str) -> str
  * generate_explanation(label: str, filename: str, text: str) -> dict
      returns {"what_is", "what_it_does", "why_it_matters", "notarization",
               "client_action", "generated_at"}

Failures never raise — they return a structured error dict so the upload flow
does not break if the LLM is down.
"""
from __future__ import annotations
import io
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

MAX_TEXT_CHARS = 45000  # Fits comfortably within Claude Sonnet 4.5 context budget.


# --------- text extraction ---------
def _extract_pdf(data: bytes) -> str:
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


def _extract_docx(data: bytes) -> str:
    try:
        import docx  # python-docx
    except Exception as e:
        logger.warning(f"python-docx unavailable: {e}")
        return ""
    try:
        d = docx.Document(io.BytesIO(data))
        parts = [p.text for p in d.paragraphs if p.text]
        # Tables
        for t in d.tables:
            for row in t.rows:
                for cell in row.cells:
                    if cell.text:
                        parts.append(cell.text)
        return "\n".join(parts).strip()
    except Exception as e:
        logger.warning(f"DOCX text extraction failed: {e}")
        return ""


def _extract_txt(data: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return data.decode(enc, errors="ignore")
        except Exception:
            continue
    return ""


def extract_text(data: bytes, filename: str, mime: str) -> str:
    fn = (filename or "").lower()
    mt = (mime or "").lower()
    if fn.endswith(".pdf") or "pdf" in mt:
        return _extract_pdf(data)[:MAX_TEXT_CHARS]
    if fn.endswith(".docx") or "wordprocessingml" in mt:
        return _extract_docx(data)[:MAX_TEXT_CHARS]
    if fn.endswith(".txt") or mt.startswith("text/"):
        return _extract_txt(data)[:MAX_TEXT_CHARS]
    # .doc (legacy) and image formats: no reliable text — return empty so the
    # LLM prompt falls back to using only the label + filename.
    return ""


# --------- LLM explainer ---------
SYSTEM_PROMPT = (
    "You are a trust & estate paralegal explaining legal documents to a lay client. "
    "You write short, warm, plain-English explanations — NEVER legal advice. Assume the "
    "client is a U.S. adult unfamiliar with legal jargon. Keep every field concise: 1–3 "
    "sentences each. When you are unsure whether a document requires notarization, say "
    "so honestly (do not invent). Always return VALID JSON matching the schema exactly."
)

USER_TEMPLATE = """The admin has uploaded a document titled "{label}" (filename: {filename}) to a client's trust portal. Explain it to the client.

Return ONLY a JSON object with these exact keys (no markdown, no code fences):
{{
  "what_is": "1-2 sentence definition of the document.",
  "what_it_does": "1-2 sentences on its practical function.",
  "why_it_matters": "1-2 sentences on why the client should care.",
  "notarization": "Say clearly: 'Yes — requires notarization', 'No — no notary needed', or 'Depends — ...' with a short reason. Never guess if unsure.",
  "client_action": "One short line telling the client what (if anything) they must do next. If nothing, say 'No action needed — this is for your records.'"
}}

Document content (may be truncated):
---
{text}
---
"""


def _empty_explanation(error: str = "") -> dict:
    return {
        "what_is": "",
        "what_it_does": "",
        "why_it_matters": "",
        "notarization": "",
        "client_action": "",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "error": error or "",
    }


def _parse_json_lenient(raw: str) -> dict | None:
    if not raw:
        return None
    # Strip common code-fence wrappers Claude sometimes emits despite instructions.
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except Exception:
        pass
    # Last-resort: grab first {...} block
    m = re.search(r"\{.*\}", stripped, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


async def generate_explanation(label: str, filename: str, text: str) -> dict:
    """Call Claude Sonnet 4.5 and return a structured explanation dict.
    Never raises — logs and returns an error-tagged dict on failure."""
    api_key = os.environ.get("EMERGENT_LLM_KEY", "").strip()
    if not api_key:
        return _empty_explanation("EMERGENT_LLM_KEY not configured")

    text_for_prompt = (text or "").strip()
    if not text_for_prompt:
        text_for_prompt = (
            "(No machine-readable text could be extracted from this file. Base your "
            "explanation on the document label and filename only, and clearly note that "
            "the actual contents were not analyzed.)"
        )

    user_prompt = USER_TEMPLATE.format(
        label=(label or "(unlabeled)").strip(),
        filename=filename or "unknown",
        text=text_for_prompt,
    )

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        chat = LlmChat(
            api_key=api_key,
            session_id=f"doc-explainer-{datetime.now(timezone.utc).timestamp()}",
            system_message=SYSTEM_PROMPT,
        ).with_model("anthropic", "claude-sonnet-4-5-20250929")
        raw = await chat.send_message(UserMessage(text=user_prompt))
    except Exception as e:
        logger.error(f"AI explainer call failed: {e}")
        return _empty_explanation(f"LLM call failed: {e}")

    raw_str = raw if isinstance(raw, str) else str(raw)
    parsed = _parse_json_lenient(raw_str)
    if not parsed:
        logger.error(f"AI explainer returned unparsable output: {raw_str[:400]}")
        return _empty_explanation("Model returned non-JSON output")

    return {
        "what_is":       str(parsed.get("what_is") or "").strip(),
        "what_it_does":  str(parsed.get("what_it_does") or "").strip(),
        "why_it_matters": str(parsed.get("why_it_matters") or "").strip(),
        "notarization":  str(parsed.get("notarization") or "").strip(),
        "client_action": str(parsed.get("client_action") or "").strip(),
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "error":         "",
    }
