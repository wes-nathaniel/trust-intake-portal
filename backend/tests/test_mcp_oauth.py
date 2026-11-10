"""Tests for MCP OAuth 2.1 endpoints and admin token management."""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"Admin login failed: {r.text}"
    return s


class TestOAuthDiscovery:
    """OAuth discovery endpoints - RFC 9728 and RFC 8414"""

    def test_resource_metadata_status(self):
        r = requests.get(f"{BASE_URL}/api/mcp/.well-known/oauth-protected-resource")
        assert r.status_code == 200

    def test_resource_metadata_fields(self):
        r = requests.get(f"{BASE_URL}/api/mcp/.well-known/oauth-protected-resource")
        data = r.json()
        assert "resource" in data, "Missing 'resource' field"
        assert "authorization_servers" in data, "Missing 'authorization_servers' field"
        assert isinstance(data["authorization_servers"], list)

    def test_as_metadata_status(self):
        r = requests.get(f"{BASE_URL}/api/mcp/oauth/.well-known/oauth-authorization-server")
        assert r.status_code == 200

    def test_as_metadata_fields(self):
        r = requests.get(f"{BASE_URL}/api/mcp/oauth/.well-known/oauth-authorization-server")
        data = r.json()
        assert "authorization_endpoint" in data
        assert "token_endpoint" in data
        assert "code_challenge_methods_supported" in data
        assert "S256" in data["code_challenge_methods_supported"]


class TestMcpBearerAuth:
    """POST /api/mcp authentication checks"""

    def test_no_token_returns_401(self):
        r = requests.post(f"{BASE_URL}/api/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        assert r.status_code == 401

    def test_no_token_has_www_authenticate_header(self):
        r = requests.post(f"{BASE_URL}/api/mcp", json={"jsonrpc": "2.0", "method": "tools/list", "id": 1})
        www_auth = r.headers.get("WWW-Authenticate", "")
        assert "Bearer" in www_auth
        assert "resource_metadata" in www_auth

    def test_invalid_token_returns_401(self):
        r = requests.post(
            f"{BASE_URL}/api/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        assert r.status_code == 401

    def test_invalid_token_www_authenticate_error(self):
        r = requests.post(
            f"{BASE_URL}/api/mcp",
            json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        www_auth = r.headers.get("WWW-Authenticate", "")
        assert "invalid_token" in www_auth


class TestOAuthAuthorizePage:
    """GET /api/mcp/oauth/authorize HTML page"""

    def test_authorize_page_renders_html(self):
        r = requests.get(
            f"{BASE_URL}/api/mcp/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": "test",
                "redirect_uri": "https://example.com/cb",
                "code_challenge": "abc",
                "state": "xyz",
            }
        )
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

    def test_authorize_page_has_iron_gate_title(self):
        r = requests.get(
            f"{BASE_URL}/api/mcp/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": "test",
                "redirect_uri": "https://example.com/cb",
                "code_challenge": "abc",
                "state": "xyz",
            }
        )
        assert "Iron Gate Consulting" in r.text

    def test_authorize_page_has_login_form(self):
        """Not logged in - should show email/password fields"""
        r = requests.get(
            f"{BASE_URL}/api/mcp/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": "test",
                "redirect_uri": "https://example.com/cb",
                "code_challenge": "abc",
                "state": "xyz",
            }
        )
        assert 'type="email"' in r.text or 'name="admin_email"' in r.text

    def test_authorize_page_bad_response_type_returns_400(self):
        r = requests.get(
            f"{BASE_URL}/api/mcp/oauth/authorize",
            params={
                "response_type": "token",
                "client_id": "test",
                "redirect_uri": "https://example.com/cb",
                "code_challenge": "abc",
            }
        )
        assert r.status_code == 400


class TestAdminOAuthTokens:
    """Admin endpoints for OAuth token management"""

    def test_list_tokens_status(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/mcp/oauth-tokens")
        assert r.status_code == 200

    def test_list_tokens_structure(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/mcp/oauth-tokens")
        data = r.json()
        assert "tokens" in data
        assert "count" in data
        assert isinstance(data["tokens"], list)
        assert isinstance(data["count"], int)

    def test_revoke_all_tokens_status(self, admin_session):
        r = admin_session.delete(f"{BASE_URL}/api/admin/mcp/oauth-tokens")
        assert r.status_code == 200

    def test_revoke_all_tokens_structure(self, admin_session):
        r = admin_session.delete(f"{BASE_URL}/api/admin/mcp/oauth-tokens")
        data = r.json()
        assert data.get("ok") is True
        assert "revoked" in data
