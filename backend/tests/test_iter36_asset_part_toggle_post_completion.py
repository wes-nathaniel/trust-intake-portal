"""
Iteration 36 — Asset Part I/II toggle, post_completion flag, retirement filter, client portal button.
Tests:
- Admin PATCH /admin/trust-cases/{caseId}/asset-items/{itemId}/part
- POST /trust-cases/{caseId}/asset-items on completed case sets post_completion=True
- Schedule A does NOT include retirement keyword items
- Asset adds/edits do NOT change case status
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASS = "Wllorenzo03!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def completed_case_id(admin_session):
    """Get or find a completed trust case for testing."""
    r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases", params={"limit": 50})
    assert r.status_code == 200
    data = r.json()
    cases = data if isinstance(data, list) else data.get("cases", [])
    # Find a completed case
    for c in cases:
        if c.get("status") == "Completed":
            return c["id"]
    pytest.skip("No completed case found — skipping post_completion tests")


@pytest.fixture(scope="module")
def any_case_id(admin_session):
    """Get any case for basic asset item tests."""
    r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases", params={"limit": 50})
    assert r.status_code == 200
    data = r.json()
    cases = data if isinstance(data, list) else data.get("cases", [])
    if not cases:
        pytest.skip("No cases available")
    return cases[0]["id"]


class TestPartToggle:
    """Part I/II toggle — admin can move item between parts."""

    created_item_ids = []

    def _add_item_as_admin(self, admin_session, case_id):
        payload = {
            "description": "TEST_ Savings account at Main Street Bank",
            "kind": "bank",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": False,
            "date_delivered": "2025-01-15",
            "method": "Bank form changing the name on the account to the trust",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items", json=payload)
        return r

    def test_toggle_part_i_to_ii(self, admin_session, any_case_id):
        """Add item then toggle it from Part I to Part II."""
        # First add an item
        r = self._add_item_as_admin(admin_session, any_case_id)
        assert r.status_code == 200, f"Add item failed: {r.text}"
        item = r.json()
        item_id = item.get("id")
        assert item_id, "No item id returned"
        self.created_item_ids.append((any_case_id, item_id))

        # Toggle to Part II
        patch_r = admin_session.patch(
            f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/asset-items/{item_id}/part",
            json={"part": "II"}
        )
        assert patch_r.status_code == 200, f"PATCH part failed: {patch_r.text}"
        data = patch_r.json()
        assert data.get("ok") is True
        assert data.get("part") == "II"

        # Verify persistence
        get_r = admin_session.get(f"{BASE_URL}/api/trust-cases/{any_case_id}/asset-items")
        items = get_r.json().get("items", [])
        toggled = next((i for i in items if i.get("id") == item_id), None)
        assert toggled is not None, "Item not found after toggle"
        assert toggled.get("part") == "II", f"Expected Part II, got {toggled.get('part')}"
        print(f"PASS: Toggled item {item_id} to Part II")

    def test_toggle_part_ii_to_i(self, admin_session, any_case_id):
        """Toggle an item from Part II back to Part I."""
        # Add item
        r = self._add_item_as_admin(admin_session, any_case_id)
        assert r.status_code == 200
        item_id = r.json().get("id")
        self.created_item_ids.append((any_case_id, item_id))

        # Set to Part II first
        admin_session.patch(
            f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/asset-items/{item_id}/part",
            json={"part": "II"}
        )

        # Toggle back to Part I
        patch_r = admin_session.patch(
            f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/asset-items/{item_id}/part",
            json={"part": "I"}
        )
        assert patch_r.status_code == 200
        assert patch_r.json().get("part") == "I"
        print(f"PASS: Toggled item {item_id} back to Part I")

    def test_toggle_invalid_part_rejected(self, admin_session, any_case_id):
        """Invalid part value is rejected with 422."""
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/asset-items/fakeid/part",
            json={"part": "III"}
        )
        assert r.status_code in (422, 400), f"Expected validation error, got {r.status_code}"
        print("PASS: Invalid part value rejected")

    def test_toggle_requires_admin(self, any_case_id):
        """Non-admin cannot toggle part."""
        client_session = requests.Session()
        # Unauthenticated
        r = client_session.patch(
            f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/asset-items/fakeid/part",
            json={"part": "II"}
        )
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print("PASS: Toggle requires admin auth")

    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, admin_session, any_case_id):
        yield
        for cid, iid in self.created_item_ids:
            admin_session.delete(f"{BASE_URL}/api/trust-cases/{cid}/asset-items/{iid}")


class TestPostCompletion:
    """Items added to completed cases get post_completion=True."""

    created_item_ids = []

    def test_add_item_to_completed_case_sets_post_completion(self, admin_session, completed_case_id):
        """POST asset item on completed case — post_completion must be True."""
        payload = {
            "description": "TEST_ Checking account at First National Bank",
            "kind": "bank",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": True,
            "date_delivered": "",
            "method": "",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{completed_case_id}/asset-items", json=payload)
        assert r.status_code == 200, f"Add item failed: {r.text}"
        item = r.json()
        item_id = item.get("id")
        self.created_item_ids.append((completed_case_id, item_id))

        # Verify post_completion via GET
        get_r = admin_session.get(f"{BASE_URL}/api/trust-cases/{completed_case_id}/asset-items")
        items = get_r.json().get("items", [])
        new_item = next((i for i in items if i.get("id") == item_id), None)
        assert new_item is not None
        assert new_item.get("post_completion") is True, f"Expected post_completion=True, got {new_item.get('post_completion')}"
        print(f"PASS: post_completion=True for item on completed case")

    def test_add_item_to_completed_case_defaults_to_part_ii(self, admin_session, completed_case_id):
        """POST asset item on completed case — part should default to Part II."""
        payload = {
            "description": "TEST_ Investment account post-completion test",
            "kind": "investment",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": True,
            "date_delivered": "",
            "method": "",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{completed_case_id}/asset-items", json=payload)
        assert r.status_code == 200
        item_id = r.json().get("id")
        self.created_item_ids.append((completed_case_id, item_id))

        get_r = admin_session.get(f"{BASE_URL}/api/trust-cases/{completed_case_id}/asset-items")
        items = get_r.json().get("items", [])
        new_item = next((i for i in items if i.get("id") == item_id), None)
        assert new_item is not None
        assert new_item.get("part") == "II", f"Expected Part II, got {new_item.get('part')}"
        print("PASS: New item on completed case defaults to Part II")

    def test_case_status_unchanged_after_asset_add(self, admin_session, completed_case_id):
        """Adding an asset must NOT change case status."""
        # Get current status
        cases_r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{completed_case_id}")
        before_status = cases_r.json().get("status")

        payload = {
            "description": "TEST_ Cash in home safe",
            "kind": "cash",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": True,
            "date_delivered": "",
            "method": "",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{completed_case_id}/asset-items", json=payload)
        assert r.status_code == 200
        item_id = r.json().get("id")
        self.created_item_ids.append((completed_case_id, item_id))

        cases_r2 = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{completed_case_id}")
        after_status = cases_r2.json().get("status")
        assert before_status == after_status, f"Status changed from {before_status} to {after_status}"
        print(f"PASS: Case status unchanged ({before_status}) after asset add")

    @pytest.fixture(autouse=True, scope="class")
    def cleanup(self, admin_session, completed_case_id):
        yield
        for cid, iid in self.created_item_ids:
            admin_session.delete(f"{BASE_URL}/api/trust-cases/{cid}/asset-items/{iid}")


class TestRetirementFilter:
    """Retirement accounts are blocked and excluded from Schedule A."""

    def test_retirement_item_rejected_on_save(self, admin_session, any_case_id):
        """POST with retirement keyword in description returns 400."""
        payload = {
            "description": "My IRA account at Fidelity",
            "kind": "investment",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": True,
            "date_delivered": "",
            "method": "",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{any_case_id}/asset-items", json=payload)
        assert r.status_code == 400, f"Expected 400 for retirement account, got {r.status_code}: {r.text}"
        print("PASS: IRA rejected with 400")

    def test_401k_rejected(self, admin_session, any_case_id):
        """401k description is rejected."""
        payload = {
            "description": "401k account at Vanguard",
            "kind": "investment",
            "other_kind": "",
            "other_text": "",
            "state": "",
            "in_trust": "yes",
            "not_done": True,
            "date_delivered": "",
            "method": "",
            "method_other": "",
            "attachment_doc_id": "",
        }
        r = admin_session.post(f"{BASE_URL}/api/trust-cases/{any_case_id}/asset-items", json=payload)
        assert r.status_code == 400, f"Expected 400 for 401k, got {r.status_code}"
        print("PASS: 401k rejected with 400")

    def test_schedule_a_excludes_retirement(self, admin_session, any_case_id):
        """Schedule A GET should not include retirement keywords even if status=moved."""
        # Just check that the schedule_a endpoint is accessible and returns expected structure
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/schedule-a")
        assert r.status_code == 200
        data = r.json()
        assert "part_i" in data
        assert "part_ii" in data
        # Check no retirement items in either part
        all_items = data["part_i"] + data["part_ii"]
        import re
        RETIREMENT_RE = re.compile(
            r"\b(ira|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?|roth\s+(ira|401|account)|sep\s+ira|"
            r"simple\s+ira|pension|retirement\s+(account|plan)|tsp\s+account|thrift\s+savings)\b", re.I)
        for item in all_items:
            desc = item.get("description_of_property", "")
            assert not RETIREMENT_RE.search(desc), f"Retirement item found in Schedule A: {desc}"
        print(f"PASS: Schedule A contains {len(all_items)} items, none with retirement keywords")


class TestAdminGetCase:
    """Admin GET case detail endpoints work."""

    def test_admin_get_case_detail(self, admin_session, any_case_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{any_case_id}")
        assert r.status_code == 200
        data = r.json()
        assert "id" in data
        print(f"PASS: Admin can get case detail for {any_case_id}")

    def test_admin_intake_summary(self, admin_session, any_case_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/intake-summary")
        assert r.status_code == 200
        data = r.json()
        assert "total_items" in data
        assert "retirement_items_in_list" in data
        print(f"PASS: Intake summary returned, total_items={data['total_items']}")

    def test_admin_schedule_a(self, admin_session, any_case_id):
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{any_case_id}/schedule-a")
        assert r.status_code == 200
        data = r.json()
        assert "part_i" in data and "part_ii" in data
        print(f"PASS: Schedule A returned part_i={len(data['part_i'])}, part_ii={len(data['part_ii'])}")
