"""End-to-end check for iteration 21: after regeneration completes for the
seeded Michael Thompson case, verify:
  (a) Every page mentions 'Michael' at least once.
  (b) 0 attorney-recommendation phrases anywhere.
  (c) 0 banned jargon anywhere.
  (d) At least one page contains the exact Iron Gate advisor line.
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"
SEEDED_CASE_ID = "8eb42bd3-5d43-43f2-b765-b98a144bd931"

ATTORNEY_PHRASES = [
    "consult an attorney", "consult a lawyer", "consult with an attorney",
    "independent legal counsel", "local attorney", "seek legal counsel",
    "professional legal advice", "your own attorney", "estate planning attorney",
    "review this trust with", "contact a lawyer", "contact an attorney",
    "talk to a lawyer", "talk to an attorney",
]
BANNED_JARGON = ["settlor", "per stirpes", "corpus", "in terrorem",
                 "spendthrift", "hereinafter", "aforementioned", "fiduciary"]

IRON_GATE_LINE = (
    "Your trust was carefully prepared through Iron Gate Consulting's military "
    "legal benefits program. If you have questions, contact your Iron Gate "
    "Consulting advisor directly."
)


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


def _wait_for_completion(admin_session, timeout=360):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = admin_session.get(
            f"{BASE_URL}/api/trust-cases/{SEEDED_CASE_ID}/trust-page-explanations",
            timeout=30,
        )
        assert r.status_code == 200
        last = r.json()
        if last.get("status") == "completed" and last.get("explanations"):
            return last
        if last.get("status") == "failed":
            pytest.fail(f"job failed: {last.get('error')}")
        time.sleep(6)
    pytest.fail(f"timed out — last={last}")


def test_regenerate_and_verify_iteration21_rules(admin_session):
    # Trigger regenerate
    r = admin_session.post(
        f"{BASE_URL}/api/admin/trust-cases/{SEEDED_CASE_ID}/trust-page-explanations/regenerate",
        timeout=30,
    )
    # Some setups may 200 or 202 — both are acceptable startups
    assert r.status_code in (200, 202), f"regen unexpected: {r.status_code} {r.text[:300]}"

    result = _wait_for_completion(admin_session)
    explanations = result["explanations"]
    assert len(explanations) >= 1

    iron_gate_page_count = 0
    for entry in explanations:
        page = entry["page"]
        text = entry["text"]
        lower = text.lower()

        # (a) Michael must appear on every page
        assert "michael" in lower, f"page {page} missing 'Michael': {text[:200]}"

        # (b) 0 attorney-recommendation phrases
        for phrase in ATTORNEY_PHRASES:
            assert phrase not in lower, \
                f"page {page} still contains attorney phrase '{phrase}': {text[:300]}"

        # (c) 0 banned jargon
        for term in BANNED_JARGON:
            assert term not in lower, \
                f"page {page} still contains banned jargon '{term}': {text[:300]}"

        if IRON_GATE_LINE in text:
            iron_gate_page_count += 1

    # (d) At least ONE page must include the exact Iron Gate line
    assert iron_gate_page_count >= 1, (
        f"expected at least one page to contain the exact Iron Gate advisor "
        f"line; found {iron_gate_page_count}"
    )
