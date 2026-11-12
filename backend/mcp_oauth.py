"""OAuth 2.1 Authorization Code + PKCE server for the MCP endpoint.

Endpoints (all under /api prefix, served by api_router):
  GET  /mcp/.well-known/oauth-protected-resource      RFC 9728 resource metadata
  GET  /mcp/oauth/.well-known/oauth-authorization-server  RFC 8414 AS metadata
  POST /mcp/oauth/register                             RFC 7591 dynamic client registration
  GET  /mcp/oauth/authorize                            HTML authorization page
  POST /mcp/oauth/authorize                            process authorize/deny
  POST /mcp/oauth/token                               exchange code for JWT token
  GET  /admin/mcp/oauth-tokens                        list active tokens (admin)
  DELETE /admin/mcp/oauth-tokens/{jti}                revoke single token
  DELETE /admin/mcp/oauth-tokens                      revoke ALL tokens (nuclear)

Bearer token validation for the keyless MCP endpoint in server.py:
  validate_bearer_token(token_str, db) -> admin dict or None
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json as _json
import logging
import os
import secrets
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jose import JWTError, jwt

logger = logging.getLogger("mcp-oauth")
router = APIRouter()

OAUTH_TOKEN_TTL_HOURS = int(os.environ.get("MCP_OAUTH_TOKEN_TTL_HOURS", "720"))  # 30 days
CODE_TTL_SECONDS = 600  # 10 minutes

# ─── Allowed redirect URI prefixes ───────────────────────────────────────────
# Any redirect_uri starting with one of these is accepted.
ALLOWED_REDIRECT_PREFIXES = [
    "https://claude.ai/",
    "https://claude.com/",
    "https://app.claude.ai/",
    "https://www.claude.ai/",
    # Desktop app
    "claude://",
    "claude-desktop://",
    # Mobile
    "com.anthropic.claude://",
    # localhost for development tools
    "http://localhost:",
    "http://127.0.0.1:",
]

# Pre-loaded metadata for known CIMD clients — no runtime HTTP fetch needed.
# Sourced from https://claude.ai/oauth/mcp-oauth-client-metadata (confirmed live).
KNOWN_CIMD_CLIENTS: dict[str, dict] = {
    "https://claude.ai/oauth/mcp-oauth-client-metadata": {
        "client_id": "https://claude.ai/oauth/mcp-oauth-client-metadata",
        "client_name": "Claude",
        "redirect_uris": [
            "https://claude.ai/api/mcp/auth_callback",
            "https://claude.com/api/mcp/auth_callback",
        ],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    },
    # Claude.com variant (same metadata, different host)
    "https://claude.com/oauth/mcp-oauth-client-metadata": {
        "client_id": "https://claude.com/oauth/mcp-oauth-client-metadata",
        "client_name": "Claude",
        "redirect_uris": [
            "https://claude.ai/api/mcp/auth_callback",
            "https://claude.com/api/mcp/auth_callback",
        ],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    },
}


def _jwt_secret() -> str:
    return os.environ.get("JWT_SECRET", "change-me")


def _base_url(request: Request) -> str:
    """External base URL — prefer FRONTEND_URL env so links work from Claude."""
    fe = os.environ.get("FRONTEND_URL", "").rstrip("/")
    return fe if fe else str(request.base_url).rstrip("/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _as_aware(dt) -> datetime:
    """Coerce mongo datetime or ISO string to aware UTC datetime."""
    if isinstance(dt, str):
        s = dt.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(s)
        except ValueError:
            return _now()
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return _now()


def _verify_pw(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def _is_allowed_redirect(uri: str) -> bool:
    return any(uri.startswith(p) for p in ALLOWED_REDIRECT_PREFIXES)


async def _fetch_cimd(url: str) -> Optional[dict]:
    """Fetch a Client ID Metadata Document. Runs blocking urllib in a thread.
    Only called for unknown CIMD URLs not in KNOWN_CIMD_CLIENTS.
    Times out after 5 seconds."""
    def _get() -> dict:
        req = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "IGC-MCP-Server/1.0"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return _json.loads(resp.read().decode())
    try:
        return await asyncio.to_thread(_get)
    except Exception as e:
        logger.warning(f"CIMD fetch failed for {url}: {e}")
        return None


async def _resolve_client(client_id: str, redirect_uri: str, db) -> tuple[bool, str]:
    """
    Returns (is_valid, error_message).
    Resolution order:
      1. Known CIMD clients (pre-loaded, no network)
      2. Dynamically registered clients (DB lookup)
      3. URL-based CIMD (fetch + cache)
      4. Fallback: redirect_uri prefix check
    """
    # 1. Known CIMD clients
    if client_id in KNOWN_CIMD_CLIENTS:
        meta = KNOWN_CIMD_CLIENTS[client_id]
        if redirect_uri in meta.get("redirect_uris", []):
            return True, ""
        # Also allow prefix match for new Claude callback paths
        if _is_allowed_redirect(redirect_uri):
            return True, ""
        return False, "redirect_uri not in known client metadata"

    # 2. Dynamically registered clients
    client = await db.mcp_oauth_clients.find_one({"client_id": client_id}, {"_id": 0})
    if client:
        if redirect_uri in client.get("redirect_uris", []):
            return True, ""
        return False, "redirect_uri not registered for this client"

    # 3. URL-based CIMD (unknown URL)
    if client_id.startswith("https://"):
        meta = await _fetch_cimd(client_id)
        if meta:
            if redirect_uri in (meta.get("redirect_uris") or []):
                # Cache in DB for future requests
                try:
                    await db.mcp_oauth_clients.update_one(
                        {"client_id": client_id},
                        {"$setOnInsert": {
                            "client_id": client_id,
                            "client_name": meta.get("client_name", "CIMD Client"),
                            "redirect_uris": meta.get("redirect_uris", []),
                            "created_at": _now_iso(),
                            "source": "cimd_fetch",
                        }},
                        upsert=True,
                    )
                except Exception:
                    pass
                return True, ""
            return False, "redirect_uri not in fetched CIMD metadata"
        # Fetch failed — allow if redirect_uri matches a known prefix
        if _is_allowed_redirect(redirect_uri):
            logger.info(f"CIMD fetch failed for {client_id}; allowing via redirect prefix match")
            return True, ""
        return False, "Could not fetch CIMD and redirect_uri not in allowed list"

    # 4. Unknown opaque client_id — allow if redirect_uri prefix is known
    if _is_allowed_redirect(redirect_uri):
        return True, ""

    return False, "Unknown client_id and redirect_uri not in allowed list"


# ─── CORS helper — public OAuth endpoints need wildcard origin ────────────────

def _public_cors_headers() -> dict:
    """Headers for public OAuth endpoints (no credentials — wildcard origin OK)."""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization",
        "Cache-Control": "no-cache",
    }


# ─── Discovery endpoints ──────────────────────────────────────────────────────

@router.get("/mcp/.well-known/oauth-protected-resource")
async def mcp_resource_metadata(request: Request):
    """RFC 9728: Protected Resource Metadata."""
    base = _base_url(request)
    return JSONResponse({
        "resource": f"{base}/api/mcp",
        "authorization_servers": [f"{base}/api/mcp/oauth"],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/admin/mcp",
    }, headers=_public_cors_headers())


@router.options("/mcp/.well-known/oauth-protected-resource")
async def mcp_resource_metadata_options():
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


@router.get("/mcp/oauth/.well-known/oauth-authorization-server")
async def mcp_as_metadata(request: Request):
    """RFC 8414: Authorization Server Metadata."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": f"{base}/api/mcp/oauth",
        "authorization_endpoint": f"{base}/api/mcp/oauth/authorize",
        "token_endpoint": f"{base}/api/mcp/oauth/token",
        "registration_endpoint": f"{base}/api/mcp/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp:read", "mcp:propose"],
        "client_id_metadata_document_supported": True,
        "revocation_endpoint": f"{base}/api/mcp/oauth/revoke",
        "subject_types_supported": ["public"],
    }, headers=_public_cors_headers())


@router.options("/mcp/oauth/.well-known/oauth-authorization-server")
async def mcp_as_metadata_options():
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


# ─── RFC 8414 strict discovery (host-relative, no /api prefix) ───────────────
# Mounted directly on `app` in server.py so it is accessible without /api prefix.
well_known_router = APIRouter()


@well_known_router.get("/.well-known/oauth-authorization-server/api/mcp/oauth")
async def mcp_strict_discovery(request: Request):
    """RFC 8414 strict discovery URL constructed by Claude from the issuer path."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": f"{base}/api/mcp/oauth",
        "authorization_endpoint": f"{base}/api/mcp/oauth/authorize",
        "token_endpoint": f"{base}/api/mcp/oauth/token",
        "registration_endpoint": f"{base}/api/mcp/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp:read", "mcp:propose"],
        "client_id_metadata_document_supported": True,
        "revocation_endpoint": f"{base}/api/mcp/oauth/revoke",
        "subject_types_supported": ["public"],
    }, headers=_public_cors_headers())


@well_known_router.options("/.well-known/oauth-authorization-server/api/mcp/oauth")
async def mcp_strict_discovery_options():
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


# ─── Dynamic Client Registration (RFC 7591) ───────────────────────────────────

@router.options("/mcp/oauth/register")
async def mcp_oauth_register_options():
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


@router.post("/mcp/oauth/register")
async def mcp_oauth_register(request: Request):
    """RFC 7591 Dynamic Client Registration. No authentication required.

    Accepts any client registration that includes at least one redirect_uri
    matching an allowed prefix. Stores in mcp_oauth_clients collection.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Body must be JSON"},
            status_code=400,
            headers=_public_cors_headers(),
        )

    redirect_uris = body.get("redirect_uris") or []
    if not redirect_uris or not isinstance(redirect_uris, list):
        return JSONResponse(
            {"error": "invalid_client_metadata", "error_description": "redirect_uris is required and must be an array"},
            status_code=400,
            headers=_public_cors_headers(),
        )

    # Validate every redirect_uri
    for uri in redirect_uris:
        if not isinstance(uri, str):
            return JSONResponse(
                {"error": "invalid_redirect_uri", "error_description": "All redirect_uris must be strings"},
                status_code=400,
                headers=_public_cors_headers(),
            )
        if not _is_allowed_redirect(uri):
            return JSONResponse(
                {"error": "invalid_redirect_uri",
                 "error_description": f"redirect_uri not permitted: {uri}. Must use an approved callback domain."},
                status_code=400,
                headers=_public_cors_headers(),
            )

    client_id = uuid.uuid4().hex
    client_name = str(body.get("client_name") or "MCP Client")[:200]
    # We only issue authorization_code grants; advertise that back to the client.
    # RFC 7591 permits the server to return a subset of requested grant_types.
    supported_grants = ["authorization_code"]
    now = _now_iso()

    from routes._neo_state import state as _st
    await _st.db.mcp_oauth_clients.insert_one({
        "client_id": client_id,
        "client_name": client_name,
        "redirect_uris": redirect_uris,
        "grant_types": supported_grants,
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "created_at": now,
        "source": "dynamic_registration",
        "raw_request": {k: v for k, v in body.items() if k not in ("client_secret",)},
    })
    logger.info(f"DCR: registered client '{client_name}' ({client_id}) with {len(redirect_uris)} redirect_uris")

    return JSONResponse(
        {
            "client_id": client_id,
            "client_name": client_name,
            "redirect_uris": redirect_uris,
            "grant_types": supported_grants,
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "client_id_issued_at": int(_now().timestamp()),
        },
        status_code=201,
        headers=_public_cors_headers(),
    )


# ─── Authorization page ───────────────────────────────────────────────────────

def _auth_page_html(*, base, client_id, redirect_uri, state, code_challenge,
                    code_challenge_method, scope, admin_name="", error="", not_logged_in=False):
    hidden = (
        f'<input type="hidden" name="client_id" value="{client_id}">'
        f'<input type="hidden" name="redirect_uri" value="{redirect_uri}">'
        f'<input type="hidden" name="state" value="{state}">'
        f'<input type="hidden" name="code_challenge" value="{code_challenge}">'
        f'<input type="hidden" name="code_challenge_method" value="{code_challenge_method}">'
        f'<input type="hidden" name="scope" value="{scope}">'
    )
    error_html = f'<p style="color:#ef4444;text-align:center;font-size:14px;margin-top:12px;">{error}</p>' if error else ""
    login_html = ""
    if not_logged_in:
        login_html = (
            '<p style="color:#64748b;font-size:14px;margin-bottom:16px;">Sign in to authorize this connection.</p>'
            '<label style="display:block;font-size:13px;font-weight:600;color:#1c252e;margin-bottom:4px;">Email</label>'
            '<input type="email" name="admin_email" autocomplete="email" autofocus '
            '       style="width:100%;box-sizing:border-box;border:1px solid #d1cfc9;border-radius:8px;padding:12px;font-size:16px;margin-bottom:12px;">'
            '<label style="display:block;font-size:13px;font-weight:600;color:#1c252e;margin-bottom:4px;">Password</label>'
            '<input type="password" name="admin_password" autocomplete="current-password" '
            '       style="width:100%;box-sizing:border-box;border:1px solid #d1cfc9;border-radius:8px;padding:12px;font-size:16px;margin-bottom:16px;">'
        )
    btn_label = "Sign in and Authorize" if not_logged_in else "Authorize Claude"
    # Determine display name for the client
    client_display = "Claude"
    if client_id in KNOWN_CIMD_CLIENTS:
        client_display = KNOWN_CIMD_CLIENTS[client_id].get("client_name", "Claude")
    greeting = (f"<p style='color:#475569;font-size:14px;margin-bottom:16px;'>"
                f"Signed in as <strong>{admin_name}</strong></p>") if admin_name and not not_logged_in else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Authorize {client_display} — IGC Trust Portal</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f6f4f0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px}}
.card{{background:#fff;border:1px solid #e2e0da;border-radius:16px;padding:32px;max-width:400px;width:100%;box-shadow:0 4px 24px rgba(28,37,46,.07)}}
.logo{{font-family:Georgia,serif;font-size:22px;color:#1c252e;text-align:center;margin-bottom:4px}}
.sub{{color:#64748b;font-size:13px;text-align:center;margin-bottom:24px}}
hr{{border:none;border-top:1px solid #e2e0da;margin:20px 0}}
.box{{background:#f6f4f0;border:1px solid #e2e0da;border-radius:10px;padding:14px;margin-bottom:16px}}
.box ul{{list-style:none;padding:0}} .box li{{font-size:13px;color:#1c252e;padding:2px 0}}
.can li::before{{content:"yes ";color:#059669;font-weight:600}}
.cant li::before{{content:"no ";color:#94a3b8;font-weight:600}}
h3{{font-size:14px;font-weight:600;color:#1c252e;margin-bottom:8px}}
.btn-auth{{width:100%;background:#1c252e;color:#fff;border:none;border-radius:10px;padding:14px;font-size:16px;font-weight:600;cursor:pointer;margin-bottom:10px;min-height:48px}}
.btn-deny{{width:100%;background:transparent;color:#64748b;border:1px solid #d1cfc9;border-radius:10px;padding:14px;font-size:16px;cursor:pointer;min-height:48px}}
</style>
</head>
<body>
<div class="card">
  <div class="logo">Iron Gate Consulting</div>
  <div class="sub">IGC Trust Portal</div>
  <hr>
  <h3 style="text-align:center;font-size:16px;margin-bottom:12px;">{client_display} is requesting access</h3>
  {greeting}
  <div class="box can">
    <h3>{client_display} can:</h3>
    <ul>
      <li>Read your trust cases and schedules</li>
      <li>Read intake summaries</li>
      <li>Propose field changes (you approve)</li>
      <li>Propose messages to clients (you approve)</li>
    </ul>
  </div>
  <div class="box cant">
    <h3>{client_display} cannot:</h3>
    <ul>
      <li>Release to client or change status</li>
      <li>Touch payments or delete data</li>
      <li>Send any email without your approval</li>
    </ul>
  </div>
  {error_html}
  <form method="POST" action="{base}/api/mcp/oauth/authorize">
    {hidden}
    {login_html}
    <button type="submit" name="action" value="authorize" class="btn-auth">{btn_label}</button>
    <button type="submit" name="action" value="deny" class="btn-deny">Deny access</button>
  </form>
</div>
</body>
</html>"""


@router.get("/mcp/oauth/authorize", response_class=HTMLResponse)
async def mcp_oauth_authorize_page(
    request: Request,
    response_type: str = Query(...),
    client_id: str = Query(...),
    redirect_uri: str = Query(...),
    code_challenge: str = Query(...),
    code_challenge_method: str = Query("S256"),
    state: str = Query(""),
    scope: str = Query("mcp:read mcp:propose"),
):
    if response_type != "code":
        return HTMLResponse("Invalid response_type. Only 'code' is supported.", status_code=400)
    if code_challenge_method.upper() != "S256":
        return HTMLResponse("Only S256 code_challenge_method is supported.", status_code=400)

    # Validate client_id and redirect_uri before showing the auth page
    from routes._neo_state import state as _st
    valid, err = await _resolve_client(client_id, redirect_uri, _st.db)
    if not valid:
        return HTMLResponse(
            f"Invalid client or redirect_uri: {err}",
            status_code=400,
        )

    base = _base_url(request)
    admin = await _get_admin_from_cookie(request)
    kwargs = dict(base=base, client_id=client_id, redirect_uri=redirect_uri, state=state,
                  code_challenge=code_challenge, code_challenge_method=code_challenge_method, scope=scope)
    if admin:
        return HTMLResponse(_auth_page_html(**kwargs, admin_name=admin.get("name") or admin.get("email", "")))
    return HTMLResponse(_auth_page_html(**kwargs, not_logged_in=True))


@router.post("/mcp/oauth/authorize")
async def mcp_oauth_authorize_submit(
    request: Request,
    action: str = Form(...),
    client_id: str = Form(...),
    redirect_uri: str = Form(...),
    state: str = Form(""),
    code_challenge: str = Form(...),
    code_challenge_method: str = Form("S256"),
    scope: str = Form("mcp:read mcp:propose"),
    admin_email: str = Form(default=""),
    admin_password: str = Form(default=""),
):
    base = _base_url(request)

    if action == "deny":
        return RedirectResponse(_build_redirect(redirect_uri, state=state, error="access_denied"), status_code=302)

    # Validate client_id and redirect_uri before issuing a code
    from routes._neo_state import state as _st
    valid, err = await _resolve_client(client_id, redirect_uri, _st.db)
    if not valid:
        return RedirectResponse(_build_redirect(redirect_uri, state=state, error="unauthorized_client"), status_code=302)

    # Authenticate — try cookie first, then form credentials
    admin = await _get_admin_from_cookie(request)
    if not admin and admin_email:
        user = await _st.db.users.find_one({"email": admin_email.strip(), "role": "admin"}, {"_id": 0})
        if user and _verify_pw(admin_password, user.get("password_hash", "")):
            admin = user
        else:
            kwargs = dict(base=base, client_id=client_id, redirect_uri=redirect_uri, state=state,
                          code_challenge=code_challenge, code_challenge_method=code_challenge_method, scope=scope)
            return HTMLResponse(_auth_page_html(**kwargs, not_logged_in=True, error="Wrong email or password."))

    if not admin:
        kwargs = dict(base=base, client_id=client_id, redirect_uri=redirect_uri, state=state,
                      code_challenge=code_challenge, code_challenge_method=code_challenge_method, scope=scope)
        return HTMLResponse(_auth_page_html(**kwargs, not_logged_in=True, error="Please sign in first."))

    code = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=CODE_TTL_SECONDS)
    await _st.db.mcp_oauth_codes.insert_one({
        "code": code, "client_id": client_id, "redirect_uri": redirect_uri,
        "code_challenge": code_challenge, "code_challenge_method": code_challenge_method.upper(),
        "scope": scope, "admin_id": admin["id"], "admin_email": admin["email"],
        "created_at": _now_iso(), "expires_at": expires_at, "used": False,
    })
    return RedirectResponse(_build_redirect(redirect_uri, state=state, code=code), status_code=302)


# ─── Token endpoint ───────────────────────────────────────────────────────────

@router.options("/mcp/oauth/token")
async def mcp_oauth_token_options():
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


@router.post("/mcp/oauth/token")
async def mcp_oauth_token(request: Request):
    """Exchange authorization code for JWT access token (PKCE S256 required)."""
    from routes._neo_state import state as _st
    db = _st.db

    # Accept both form and JSON
    ct = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in ct or "multipart" in ct:
        body = dict(await request.form())
    else:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400,
                                headers=_public_cors_headers())

    if body.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400,
                            headers=_public_cors_headers())

    code = body.get("code", "")
    code_verifier = body.get("code_verifier", "")
    redirect_uri = body.get("redirect_uri", "")
    client_id = body.get("client_id", "")

    code_doc = await db.mcp_oauth_codes.find_one({"code": code, "used": False}, {"_id": 0})
    if not code_doc:
        return JSONResponse({"error": "invalid_grant", "error_description": "Code not found or already used"},
                            status_code=400, headers=_public_cors_headers())
    if _now() > _as_aware(code_doc["expires_at"]):
        await db.mcp_oauth_codes.update_one({"code": code}, {"$set": {"used": True}})
        return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"},
                            status_code=400, headers=_public_cors_headers())
    if code_doc.get("redirect_uri") != redirect_uri:
        return JSONResponse({"error": "invalid_grant", "error_description": "redirect_uri mismatch"},
                            status_code=400, headers=_public_cors_headers())
    if code_doc.get("client_id") != client_id:
        return JSONResponse({"error": "invalid_client"}, status_code=400,
                            headers=_public_cors_headers())

    # PKCE S256 validation
    computed = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    if computed != code_doc.get("code_challenge", ""):
        return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"},
                            status_code=400, headers=_public_cors_headers())

    await db.mcp_oauth_codes.update_one({"code": code}, {"$set": {"used": True}})

    jti = uuid.uuid4().hex
    exp = _now() + timedelta(hours=OAUTH_TOKEN_TTL_HOURS)
    payload = {
        "iss": f"{_base_url(request)}/api/mcp/oauth",
        "sub": code_doc["admin_id"],
        "jti": jti,
        "aud": "igc-mcp",
        "exp": exp,
        "iat": _now(),
        "scope": code_doc.get("scope", "mcp:read mcp:propose"),
        "client_id": client_id,
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")

    await db.mcp_oauth_tokens.insert_one({
        "jti": jti,
        "admin_id": code_doc["admin_id"],
        "admin_email": code_doc["admin_email"],
        "client_id": client_id,
        "scope": code_doc.get("scope", ""),
        "created_at": _now_iso(),
        "expires_at": exp.isoformat(),
        "revoked": False,
        "last_used_at": None,
    })
    return JSONResponse({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": OAUTH_TOKEN_TTL_HOURS * 3600,
        "scope": code_doc.get("scope", ""),
    }, headers=_public_cors_headers())


# ─── Revocation endpoint (RFC 7009) ──────────────────────────────────────────

@router.post("/mcp/oauth/revoke")
async def mcp_oauth_revoke(request: Request):
    """RFC 7009 token revocation. Used by clients on logout."""
    from routes._neo_state import state as _st
    ct = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in ct:
        body = dict(await request.form())
    else:
        try:
            body = await request.json()
        except Exception:
            body = {}
    token_str = body.get("token", "")
    try:
        payload = jwt.decode(token_str, _jwt_secret(), algorithms=["HS256"], audience="igc-mcp")
        jti = payload.get("jti")
        if jti:
            await _st.db.mcp_oauth_tokens.update_one(
                {"jti": jti}, {"$set": {"revoked": True, "revoked_at": _now_iso()}}
            )
    except Exception:
        pass  # RFC 7009: always return 200 regardless
    return JSONResponse({}, status_code=200, headers=_public_cors_headers())


# ─── Admin token management ───────────────────────────────────────────────────

@router.get("/admin/mcp/oauth-tokens")
async def mcp_list_oauth_tokens(request: Request):
    from routes._neo_state import state as _st
    docs = await _st.db.mcp_oauth_tokens.find(
        {"revoked": False},
        {"_id": 0, "jti": 1, "admin_email": 1, "client_id": 1, "scope": 1,
         "created_at": 1, "expires_at": 1, "last_used_at": 1},
    ).sort("created_at", -1).to_list(50)
    # Filter out expired
    now = _now_iso()
    active = [d for d in docs if (d.get("expires_at") or "9999") > now]
    return {"tokens": active, "count": len(active)}


@router.delete("/admin/mcp/oauth-tokens/{jti}")
async def mcp_revoke_oauth_token(jti: str, request: Request):
    from routes._neo_state import state as _st
    r = await _st.db.mcp_oauth_tokens.update_one(
        {"jti": jti}, {"$set": {"revoked": True, "revoked_at": _now_iso()}}
    )
    return {"ok": True, "revoked": r.modified_count}


@router.delete("/admin/mcp/oauth-tokens")
async def mcp_revoke_all_oauth_tokens(request: Request):
    """Revoke ALL active OAuth tokens — nuclear option available from phone."""
    from routes._neo_state import state as _st
    r = await _st.db.mcp_oauth_tokens.update_many(
        {"revoked": False}, {"$set": {"revoked": True, "revoked_at": _now_iso()}}
    )
    return {"ok": True, "revoked": r.modified_count}


# ─── Bearer token validation ──────────────────────────────────────────────────

async def validate_bearer_token(token_str: str, db) -> Optional[dict]:
    """Called by the keyless POST /api/mcp endpoint in server.py."""
    try:
        payload = jwt.decode(token_str, _jwt_secret(), algorithms=["HS256"], audience="igc-mcp")
    except JWTError as e:
        logger.debug(f"OAuth token decode failed: {e}")
        return None
    jti = payload.get("jti")
    if not jti:
        return None
    token_doc = await db.mcp_oauth_tokens.find_one({"jti": jti}, {"_id": 0, "revoked": 1})
    if not token_doc or token_doc.get("revoked"):
        return None
    try:
        await db.mcp_oauth_tokens.update_one({"jti": jti}, {"$set": {"last_used_at": _now_iso()}})
    except Exception:
        pass
    admin_id = payload.get("sub")
    return await db.users.find_one({"id": admin_id, "role": "admin"}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1})


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_admin_from_cookie(request: Request) -> Optional[dict]:
    """Read admin user from the httpOnly session cookie, same logic as get_current_user."""
    try:
        from routes._neo_state import state as _st
        token = request.cookies.get("access_token")
        if not token:
            return None
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return await _st.db.users.find_one({"id": user_id, "role": "admin"}, {"_id": 0})
    except Exception:
        return None


def _build_redirect(redirect_uri: str, *, state: str = "", code: str = "", error: str = "") -> str:
    sep = "&" if "?" in redirect_uri else "?"
    url = f"{redirect_uri}{sep}{'error=' + error if error else 'code=' + code}"
    if state:
        url += f"&state={state}"
    return url
