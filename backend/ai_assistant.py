"""AI assistant for answering client intake questions.

Uses Claude Sonnet 4.5 via the Emergent LLM key and the emergentintegrations library.
Returns a dict: {text, confident}.
If confidence is low OR the question touches legal advice / specific case data, escalate.
"""
import os
import re
import logging
from emergentintegrations.llm.chat import LlmChat, UserMessage

logger = logging.getLogger("trust-portal")

EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "").strip()

SYSTEM_PROMPT = """You are a friendly assistant inside a trust & estate intake portal for a legal firm.
Your job is to help clients understand WHO to put in each role and explain estate planning concepts
at an elementary reading level. Keep answers short (2-4 sentences), warm, and jargon-free.

Plain-English role definitions you may use freely:
- GRANTOR / SETTLOR: the person creating the trust and putting their assets into it. Usually the client filling out this form.
- TRUSTEE: the person who manages the trust and follows the grantor's instructions. Someone the grantor trusts with money/property.
- SUCCESSOR TRUSTEE: the backup trustee who takes over if the main trustee can't serve. A reliable person who can step in later.
- BENEFICIARIES: the people who receive money, property, or benefits from the trust. Children, spouse, family, or anyone the grantor wants to receive something.

SCOPE RULES — you MUST escalate (say you're not sure and route to the team) when:
- the client asks for legal advice, tax advice, or anything that requires reviewing their documents
- the question is about THEIR specific documents, balances, or case
- the question is about fees, timelines, billing, or firm policies
- the question is unrelated to trust intake

CONFIDENCE RULES:
- If the question matches a definition/role concept you can answer from the definitions above, answer and mark CONFIDENT.
- Otherwise, respond with a brief "let me get that to our team" and mark NOT_CONFIDENT.

OUTPUT FORMAT (strict):
Respond with exactly these two lines:
Line 1: CONFIDENCE: CONFIDENT  (or)  CONFIDENCE: NOT_CONFIDENT
Line 2+: your answer, 2-4 short sentences. No markdown. No bullet points.
"""


async def answer_question(section: str, question: str, client_name: str = "") -> dict:
    """Return {"text": str, "confident": bool, "raw": str}."""
    if not EMERGENT_KEY:
        return {
            "text": "Thanks for your question — I'm passing this to our team and they'll reply shortly.",
            "confident": False,
            "raw": "",
        }
    try:
        chat = (
            LlmChat(api_key=EMERGENT_KEY, session_id="trust-portal", system_message=SYSTEM_PROMPT)
            .with_model("anthropic", "claude-sonnet-4-5-20250929")
        )
        prompt = (
            f"Section in the intake: {section}\n"
            f"Client name: {client_name or 'client'}\n"
            f"Question: {question}"
        )
        raw = await chat.send_message(UserMessage(text=prompt))
        text = (raw or "").strip()
        confident = False
        answer = text
        m = re.match(r"^\s*CONFIDENCE:\s*(CONFIDENT|NOT_CONFIDENT)\s*\n?", text, re.IGNORECASE)
        if m:
            confident = m.group(1).upper() == "CONFIDENT"
            answer = text[m.end():].strip()
        if not answer:
            answer = "Let me get that to our team — they'll reply in this same box shortly."
            confident = False
        return {"text": answer, "confident": confident, "raw": raw}
    except Exception as e:
        logger.error(f"AI assistant failed: {e}")
        return {
            "text": "Our team will get back to you on this one shortly.",
            "confident": False,
            "raw": "",
        }
