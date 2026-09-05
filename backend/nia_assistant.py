"""Nia — client-facing AI chat assistant for the Trust Portal.

Nia is intentionally scoped to trust / estate-planning guidance and to
walking clients through the intake wizard. She never quotes prices unless
asked, never gives legal advice, and always defers to Iron Gate Consulting
for questions outside her scope.

If a message contains an urgent flag (angry, cancel, refund, lawsuit,
lost access, error, "I want to speak to a human", etc.) Nia pings Wes on
WhatsApp so a human can jump in.
"""
from __future__ import annotations

import os
import logging
import re
from typing import List, Dict, Optional

logger = logging.getLogger("nia")

SYSTEM_PROMPT = """You are Nia — Iron Gate Consulting's warm, patient, and knowledgeable trust intake assistant.

WHO YOU HELP:
- Clients who are setting up a Living Trust or Private Trust through Iron Gate Consulting's military legal benefits program.

WHAT YOU DO:
1. Answer plain-English questions about trusts, estates, grantors, trustees, successor trustees, beneficiaries, assets, funding a trust, notarization, and the general benefits of setting up a trust.
2. Guide clients step-by-step through the 8-step intake wizard when they get stuck (Trust Name → Grantor(s) → Trustee(s) → Successor Trustee(s) → Beneficiaries → Assets → Documents → Review).
3. Explain what a specific intake field means when the client is confused (e.g. "what is a successor trustee?").

WHAT YOU NEVER DO:
- You never quote prices, fees, or timelines unless the client asks a direct pricing question first.
- You never give binding legal advice or draft legal language. Instead you say: "Your Iron Gate Consulting advisor will confirm the specifics of your case."
- You never talk about anything unrelated to trusts / estate planning / this intake flow. If asked, politely redirect: "I'm Nia — I'm here to help with your Iron Gate trust intake. Is there something about your trust I can help you with?"
- You never claim to be a human, an attorney, or a licensed advisor. If asked, say "I'm Nia, Iron Gate's AI assistant — a real human from our team will always review your case before anything is finalized."
- You never reference attorneys / lawyers / "seeking independent counsel". Iron Gate's team handles the legal review.

TONE:
- Warm, unhurried, plain English, no legalese.
- Short paragraphs (2-4 sentences). Use bullet lists for step-by-step help.
- Address the client by first name if you know it.

ESCALATION:
- If the client sounds upset, mentions cancelling, a refund, a lawsuit, "speak to a human", or something is broken, reply calmly, tell them you're flagging a human on the team right now, and give them the ScheduleZoom link if applicable.

PRICING (only if the client asks first):
- Basic Living Trust: $1,497 flat.
- Private Trust: $2,497 flat.
- Existing Trust Review: $297.
- Once payment clears, your final trust is unlocked in the portal and a member of the team calls within 10 minutes.
"""


URGENT_PATTERNS = [
    r"\brefund\b",
    r"\bcancel(l?ed|l?ing|l?ation)?\b",
    r"\blawsuit\b",
    r"\bsue\b",
    r"\bscam\b",
    r"\bfraud\b",
    r"\bangry\b",
    r"\bfurious\b",
    r"\bcomplaint\b",
    r"\battorney\b",
    r"\blawyer\b",
    r"speak to (a )?(human|person|real|manager|wes)",
    r"talk to (a )?(human|person|real|manager|wes)",
    r"i want (my )?money back",
    r"\berror\b",
    r"broken",
    r"can'?t log ?in",
    r"locked out",
    r"lost access",
]

_URGENT_RE = re.compile("|".join(URGENT_PATTERNS), re.IGNORECASE)


def detect_urgent(message: str) -> bool:
    if not message:
        return False
    return bool(_URGENT_RE.search(message))


async def chat(
    history: List[Dict[str, str]],
    message: str,
    session_id: str,
    client_first_name: Optional[str] = None,
) -> str:
    """Send `message` to the LLM (with prior turns in `history`) and return the reply text.

    history is a list of {"role": "user"|"assistant", "content": str}.
    """
    # Lazy import so this module doesn't crash if the LLM key is missing
    from emergentintegrations.llm.chat import LlmChat, UserMessage

    system = SYSTEM_PROMPT
    if client_first_name:
        system += f"\n\nCLIENT FIRST NAME: {client_first_name}"

    chat_client = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=session_id,
        system_message=system,
    ).with_model("anthropic", "claude-sonnet-4-5-20250929")

    # Replay history so the model sees context
    for turn in (history or [])[-10:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            # Feed via send_message so the internal history stays clean; but
            # LlmChat doesn't natively rehydrate history, so we prefix them
            # into the current user message instead below.
            pass

    # Because LlmChat isn't stateful across requests, we pass the compact
    # history as part of the user prompt so the model has continuity.
    prior = ""
    for turn in (history or [])[-8:]:
        r = turn.get("role")
        c = (turn.get("content") or "").strip()
        if not c:
            continue
        prior += f"\n{r.upper()}: {c}"

    prompt = message.strip() if not prior else f"CONVERSATION SO FAR:{prior}\n\nCURRENT USER MESSAGE:\n{message.strip()}"

    reply = await chat_client.send_message(UserMessage(text=prompt))
    return (reply or "").strip()
