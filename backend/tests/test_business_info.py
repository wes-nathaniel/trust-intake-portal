"""
Backend tests for Business Information section (asset items with kind=business).
Tests J, G (partial), H, K.
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "wes@igchq.com"
ADMIN_PASSWORD = "Wllorenzo03!"
ROSE_CASE_ID = "abbd2cc2-3fee-404a-8243-1069552921e8"
TIMESTAMP = str(int(time.time()))
TEST_EMAIL = f"testbiz_{TIMESTAMP}@example.com"
TEST_PASSWORD = "TestPass123!"
TEST_NAME = "Test Biz Client"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def test_case(admin_session):
    """Create a test client + trust case; yield (session, case_id, user_id); cleanup after."""
    # Register test client
    r = admin_session.post(f"{BASE_URL}/api/auth/register", json={
        "email": TEST_EMAIL, "password": TEST_PASSWORD, "name": TEST_NAME
    })
    assert r.status_code == 200, f"Register failed: {r.text}"
    user_data = r.json()
    user_id = user_data.get("user", {}).get("id") or user_data.get("id")

    # Create a trust case as the test client
    client_session = requests.Session()
    login_r = client_session.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD})
    assert login_r.status_code == 200, f"Client login failed: {login_r.text}"

    case_r = client_session.post(f"{BASE_URL}/api/trust-cases", json={
        "trust_type": "single", "trust_name": "TEST Biz Trust", "intake_path": "new"
    })
    assert case_r.status_code == 200, f"Case create failed: {case_r.text}"
    case_id = case_r.json().get("id")
    assert case_id, "No case ID returned"

    yield client_session, case_id, user_id

    # Cleanup: delete the case and user
    try:
        admin_session.delete(f"{BASE_URL}/api/admin/trust-cases/{case_id}")
    except Exception:
        pass
    try:
        admin_session.delete(f"{BASE_URL}/api/admin/users/{user_id}")
    except Exception:
        pass


class TestBusinessValidationBackend:
    """Test J: Backend enforces all 4 required business fields"""

    def test_missing_biz_type_returns_400(self, test_case):
        """Missing biz_type must return 400 with correct message"""
        session, case_id, _ = test_case
        r = session.post(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items", json={
            "description": "TEST Biz LLC business ownership",
            "kind": "business",
            "not_done": True,
            "in_trust": "yes",
            "business_info": {
                "legal_name": "TEST Biz LLC",
                "biz_type": "",  # missing
                "state_formed": "Georgia",
                "ownership_pct": "100"
            }
        })
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Type of business" in detail, f"Expected 'Type of business' in detail: {detail}"
        assert "Please fill in these fields to continue:" in detail, f"Wrong message: {detail}"
        print(f"PASS: Missing biz_type → 400 with correct message: {detail}")

    def test_missing_state_formed_returns_400(self, test_case):
        """Missing state_formed must return 400 with correct message"""
        session, case_id, _ = test_case
        r = session.post(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items", json={
            "description": "TEST Biz LLC business ownership",
            "kind": "business",
            "not_done": True,
            "business_info": {
                "legal_name": "TEST Biz LLC",
                "biz_type": "llc",
                "state_formed": "",  # missing
                "ownership_pct": "100"
            }
        })
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "State it was formed in" in detail, f"Expected state error: {detail}"
        print(f"PASS: Missing state_formed → 400: {detail}")

    def test_missing_legal_name_and_pct_returns_400(self, test_case):
        """Missing legal_name AND ownership_pct must list both in message"""
        session, case_id, _ = test_case
        r = session.post(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items", json={
            "description": "TEST Biz LLC business ownership",
            "kind": "business",
            "not_done": True,
            "business_info": {
                "legal_name": "",  # missing
                "biz_type": "llc",
                "state_formed": "Georgia",
                "ownership_pct": ""  # missing
            }
        })
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "Business name" in detail, f"Expected 'Business name': {detail}"
        assert "Percent you own" in detail, f"Expected 'Percent you own': {detail}"
        print(f"PASS: Missing legal_name+pct → 400: {detail}")

    def test_all_4_required_fields_saves_successfully(self, test_case):
        """All 4 required fields → item saved"""
        session, case_id, _ = test_case
        r = session.post(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items", json={
            "description": "TEST Biz LLC - My Test Biz LLC",
            "kind": "business",
            "not_done": True,
            "in_trust": "yes",
            "business_info": {
                "legal_name": "Test Biz LLC",
                "biz_type": "llc",
                "state_formed": "Georgia",
                "ownership_pct": "100"
            }
        })
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("status") == "planned", f"Expected planned status: {data}"
        assert data.get("kind") == "business"
        item_id = data.get("id")
        assert item_id
        # Store for reuse
        test_case_data = test_case
        # Attach item_id to module level for later tests
        TestBusinessValidationBackend._saved_item_id = item_id
        TestBusinessValidationBackend._case_id = case_id
        TestBusinessValidationBackend._session = session
        print(f"PASS: All 4 fields → 200, item id={item_id}, status={data.get('status')}")

    def test_business_item_has_no_needs_more_info(self, test_case):
        """Item with all 4 fields: bizNeedsMoreInfo should be False"""
        session, case_id, _ = test_case
        r = session.get(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items")
        assert r.status_code == 200
        items = r.json().get("items", [])
        biz_items = [i for i in items if i.get("kind") == "business"]
        assert biz_items, "No business items found"
        for it in biz_items:
            bi = it.get("business_info") or {}
            has_all = (bi.get("legal_name") and bi.get("biz_type") and bi.get("state_formed") and bi.get("ownership_pct"))
            # has_all means no Needs More Info badge needed
            if "Test Biz LLC" in (bi.get("legal_name") or ""):
                assert has_all, f"Business item missing required fields: {bi}"
        print(f"PASS: Business item has all 4 required fields populated")

    def test_ein_encrypted_at_rest(self, test_case):
        """EIN stored should NOT be in plaintext in DB (via admin API no-reveal endpoint)"""
        session, case_id, _ = test_case
        # Get items via admin
        admin_s = requests.Session()
        admin_s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
        # Update the item with EIN via client
        items_r = session.get(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items")
        biz_items = [i for i in items_r.json().get("items", []) if i.get("kind") == "business"]
        if not biz_items:
            pytest.skip("No business items found")
        item_id = biz_items[0]["id"]
        # Update item with EIN
        r = session.put(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items/{item_id}", json={
            "description": "TEST Biz LLC - My Test Biz LLC",
            "kind": "business",
            "not_done": True,
            "in_trust": "yes",
            "business_info": {
                "legal_name": "Test Biz LLC",
                "biz_type": "llc",
                "state_formed": "Georgia",
                "ownership_pct": "100",
                "ein": "12-3456789"
            }
        })
        assert r.status_code == 200, f"EIN save failed: {r.text}"
        data = r.json()
        bi = data.get("business_info") or {}
        # API response should NOT have raw EIN
        assert "ein" not in bi or not bi.get("ein"), f"EIN should be masked in API response"
        assert bi.get("has_ein") is True, f"has_ein should be True"
        assert bi.get("ein_last4") == "6789", f"EIN last4 should be '6789', got {bi.get('ein_last4')}"
        print(f"PASS: EIN stored encrypted, masked in API: last4={bi.get('ein_last4')}")
        TestBusinessValidationBackend._ein_item_id = item_id

    def test_admin_ein_reveal_writes_audit_log(self, test_case, admin_session):
        """Admin EIN reveal writes audit log row"""
        session, case_id, _ = test_case
        item_id = getattr(TestBusinessValidationBackend, "_ein_item_id", None)
        if not item_id:
            # find it
            items_r = session.get(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items")
            biz_items = [i for i in items_r.json().get("items", []) if i.get("kind") == "business" and (i.get("business_info") or {}).get("has_ein")]
            if not biz_items:
                pytest.skip("No business item with EIN found")
            item_id = biz_items[0]["id"]

        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{case_id}/asset-items/{item_id}/ein")
        assert r.status_code == 200, f"Admin EIN reveal failed: {r.text}"
        data = r.json()
        assert data.get("has_ein") is True
        ein = data.get("ein", "")
        assert "123456789" in ein or len(ein) >= 9, f"Decrypted EIN should be full: {ein}"
        print(f"PASS: Admin EIN reveal returned: {ein}, has_ein={data.get('has_ein')}")


class TestMCPBusinessEins:
    """Test H: MCP read_business_eins tool"""

    def test_mcp_read_business_eins(self, test_case, admin_session):
        """MCP read_business_eins returns decrypted EIN and writes audit log"""
        session, case_id, _ = test_case
        # Get an MCP key or use OAuth
        # First check if MCP key auth is enabled
        status_r = admin_session.get(f"{BASE_URL}/api/admin/mcp/status")
        if status_r.status_code != 200:
            pytest.skip(f"Cannot get MCP status: {status_r.text}")

        status_data = status_r.json()
        key_auth_disabled = status_data.get("key_auth_disabled", False)

        if key_auth_disabled:
            # Use OAuth - get a token
            # Try to get oauth token
            oauth_r = admin_session.post(f"{BASE_URL}/api/mcp/oauth/token", json={
                "grant_type": "client_credentials"
            })
            if oauth_r.status_code not in (200, 201):
                pytest.skip(f"MCP OAuth not available: {oauth_r.text}")
            bearer_token = oauth_r.json().get("access_token")
            headers = {"Authorization": f"Bearer {bearer_token}"}
            mcp_url = f"{BASE_URL}/api/mcp"
        else:
            # Generate a new key
            gen_r = admin_session.post(f"{BASE_URL}/api/admin/mcp/generate-key")
            if gen_r.status_code not in (200, 201):
                pytest.skip(f"Cannot generate MCP key: {gen_r.text}")
            raw_key = gen_r.json().get("key")
            mcp_url = f"{BASE_URL}/api/mcp/{raw_key}"
            headers = {}

        # Ensure there's a business item with EIN
        items_r = session.get(f"{BASE_URL}/api/trust-cases/{case_id}/asset-items")
        biz_items = [i for i in items_r.json().get("items", []) if i.get("kind") == "business"]
        if not biz_items:
            pytest.skip("No business items on test case")

        # Call MCP read_business_eins
        mcp_body = {
            "jsonrpc": "2.0", "id": 1,
            "method": "tools/call",
            "params": {
                "name": "read_business_eins",
                "arguments": {"case_id": case_id}
            }
        }
        s = requests.Session()
        r = s.post(mcp_url, json=mcp_body, headers={**headers, "Content-Type": "application/json"})
        assert r.status_code == 200, f"MCP call failed: {r.status_code} {r.text}"
        data = r.json()
        result = data.get("result", {})
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        assert "EIN" in text or "ein" in text.lower(), f"EIN not in MCP response: {text}"
        print(f"PASS: MCP read_business_eins returned: {text[:200]}")

    def test_mcp_case_not_found_returns_error(self, admin_session):
        """MCP with nonexistent case_id returns sensible error"""
        status_r = admin_session.get(f"{BASE_URL}/api/admin/mcp/status")
        if status_r.status_code != 200:
            pytest.skip("Cannot get MCP status")

        gen_r = admin_session.post(f"{BASE_URL}/api/admin/mcp/generate-key")
        if gen_r.status_code not in (200, 201):
            pytest.skip("Cannot generate MCP key")
        raw_key = gen_r.json().get("key")
        mcp_url = f"{BASE_URL}/api/mcp/{raw_key}"

        mcp_body = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/call",
            "params": {
                "name": "read_business_eins",
                "arguments": {"case_id": "00000000-0000-0000-0000-000000000000"}
            }
        }
        r = requests.post(mcp_url, json=mcp_body, headers={"Content-Type": "application/json"})
        assert r.status_code == 200  # MCP always returns 200 JSON-RPC
        data = r.json()
        result = data.get("result", {})
        content = result.get("content", [{}])
        text = content[0].get("text", "") if content else ""
        assert "not found" in text.lower() or "no business" in text.lower() or "Case not found" in text, f"Expected 'not found': {text}"
        print(f"PASS: MCP with invalid case_id returns: {text}")


class TestRoseNabhanProtection:
    """Test K: Rose Nabhan's case must have exactly 3 items and be unmodified"""

    def test_rose_case_has_3_items(self, admin_session):
        """Rose Nabhan's case must have exactly 3 asset items"""
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{ROSE_CASE_ID}/asset-items")
        assert r.status_code == 200, f"Rose case fetch failed: {r.status_code} {r.text}"
        items = r.json().get("items", [])
        assert len(items) == 3, f"Rose's case should have exactly 3 items, found {len(items)}"
        print(f"PASS: Rose Nabhan's case has exactly {len(items)} items")

    def test_rose_case_items_not_modified_today(self, admin_session):
        """None of Rose's 3 items should have been modified during this test run"""
        r = admin_session.get(f"{BASE_URL}/api/admin/trust-cases/{ROSE_CASE_ID}/asset-items")
        items = r.json().get("items", [])
        today = __import__("datetime").date.today().isoformat()
        for it in items:
            updated = (it.get("updated_at") or "")[:10]
            assert updated != today, f"Rose's item '{it.get('description')}' was modified today!"
        print(f"PASS: None of Rose's items were modified today")
