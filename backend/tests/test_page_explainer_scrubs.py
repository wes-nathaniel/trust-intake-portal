"""Unit tests for iteration 21 fixes:
(1) Attorney/legal-counsel scrubber in trust_page_explainer.
(2) client_first_name derivation from intake grantor in _build_case_context.
"""
import os
import sys

import pytest

# Make backend importable when running pytest from repo root
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from trust_page_explainer import (  # noqa: E402
    IRON_GATE_ADVISOR_LINE,
    _scrub_attorney_advice,
)


# ---------- _scrub_attorney_advice ----------

class TestScrubAttorneyAdvice:
    def test_consult_an_attorney(self):
        text = "<p>You should consult an attorney about details.</p>"
        out = _scrub_attorney_advice(text)
        assert IRON_GATE_ADVISOR_LINE in out
        # HTML tags preserved
        assert out.startswith("<p>") and out.endswith("</p>")
        assert "consult an attorney" not in out.lower()

    def test_independent_legal_counsel_and_local_attorney(self):
        text = "<p>Seek independent legal counsel and consult your local attorney.</p>"
        out = _scrub_attorney_advice(text)
        assert IRON_GATE_ADVISOR_LINE in out
        assert "independent legal counsel" not in out.lower()
        assert "local attorney" not in out.lower()

    def test_review_with_your_own_attorney(self):
        text = "<p>Review this trust with your own attorney.</p>"
        out = _scrub_attorney_advice(text)
        assert IRON_GATE_ADVISOR_LINE in out
        assert "your own attorney" not in out.lower()

    def test_talk_to_a_lawyer(self):
        text = "<p>Talk to a lawyer if needed.</p>"
        out = _scrub_attorney_advice(text)
        assert IRON_GATE_ADVISOR_LINE in out
        assert "talk to a lawyer" not in out.lower()

    def test_second_opinion_estate_planning_attorney(self):
        text = "<p>You may want a second opinion from an estate planning attorney.</p>"
        out = _scrub_attorney_advice(text)
        assert IRON_GATE_ADVISOR_LINE in out
        assert "estate planning attorney" not in out.lower()

    def test_no_attorney_language_unchanged(self):
        text = "<p>This page has no attorney language.</p>"
        out = _scrub_attorney_advice(text)
        # Should not inject Iron Gate line if nothing matched
        assert IRON_GATE_ADVISOR_LINE not in out
        # The word "attorney" appears in the input but no advice sentence — 
        # scrubber may or may not replace; assert Iron Gate NOT inserted.
        assert out == text or "attorney" in out

    def test_multiple_attorney_sentences_single_replacement(self):
        text = (
            "<p>You should consult an attorney about details. "
            "You may also want to talk to a lawyer. "
            "Consider retaining a local attorney too.</p>"
        )
        out = _scrub_attorney_advice(text)
        # Exactly ONE Iron Gate line inserted
        assert out.count(IRON_GATE_ADVISOR_LINE) == 1
        assert "consult an attorney" not in out.lower()
        assert "talk to a lawyer" not in out.lower()
        assert "local attorney" not in out.lower()

    def test_empty_input(self):
        assert _scrub_attorney_advice("") == ""
        assert _scrub_attorney_advice(None) is None


# ---------- _build_case_context ----------

class TestBuildCaseContextFirstName:
    def test_arlene_grantor_first_name_wins_over_pdf_shape(self):
        from server import _build_case_context

        case = {
            "client_name": "Arlene Tamara Nathaniel",
            "grantors": [
                {"first_name": "Arlene", "middle_name": "Tamara", "last_name": "Nathaniel"}
            ],
        }
        ctx = _build_case_context(case)
        assert ctx["client_first_name"] == "Arlene"
        # Must NOT return the middle name regardless of client_name shape
        assert ctx["client_first_name"] != "Tamara"

    def test_fallback_to_client_name_first_token(self):
        from server import _build_case_context

        case = {
            "client_name": "Michael Thompson",
            "grantors": [],
        }
        ctx = _build_case_context(case)
        assert ctx["client_first_name"] == "Michael"

    def test_empty_grantor_first_name_falls_back(self):
        from server import _build_case_context

        case = {
            "client_name": "Jane Doe",
            "grantors": [{"first_name": "  ", "last_name": "Doe"}],
        }
        ctx = _build_case_context(case)
        assert ctx["client_first_name"] == "Jane"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
