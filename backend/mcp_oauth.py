"""OAuth 2.1 Authorization Code + PKCE server for the MCP endpoint.

Endpoints (all under /api prefix, served by api_router):
  GET  /mcp/.well-known/oauth-protected-resource      RFC 9728 resource metadata
  GET  /mcp/oauth/.well-known/oauth-authorization-server  RFC 8414 AS metadata
  GET  /mcp/oauth/authorize                           HTML authorization page
  POST /mcp/oauth/authorize                           process authorize/deny
  POST /mcp/oauth/token                               exchange code for JWT token
  GET  /admin/mcp/oauth-tokens                        list active tokens (admin)
  DELETE /admin/mcp/oauth-tokens/{jti}                revoke single token
  DELETE /admin/mcp/oauth-tokens                      revoke ALL tokens (nuclear)

Bearer token validation for the keyless MCP endpoint in server.py:
  validate_bearer_token(token_str, db) -> admin dict or None
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
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
    }, headers={"Cache-Control": "no-cache"})


@router.get("/mcp/oauth/.well-known/oauth-authorization-server")
async def mcp_as_metadata(request: Request):
    """RFC 8414: Authorization Server Metadata."""
    base = _base_url(request)
    return JSONResponse({
        "issuer": f"{base}/api/mcp/oauth",
        "authorization_endpoint": f"{base}/api/mcp/oauth/authorize",
        "token_endpoint": f"{base}/api/mcp/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp:read", "mcp:propose"],
    }, headers={"Cache-Control": "no-cache"})


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
    greeting = (f"<p style='color:#475569;font-size:14px;margin-bottom:16px;'>"
                f"Signed in as <strong>{admin_name}</strong></p>") if admin_name and not not_logged_in else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Authorize Claude — IGC Trust Portal</title>
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
  <h3 style="text-align:center;font-size:16px;margin-bottom:12px;">Claude is requesting access</h3>
  {greeting}
  <div class="box can">
    <h3>Claude can:</h3>
    <ul>
      <li>Read your trust cases and schedules</li>
      <li>Read intake summaries</li>
      <li>Propose field changes (you approve)</li>
      <li>Propose messages to clients (you approve)</li>
    </ul>
  </div>
  <div class="box cant">
    <h3>Claude cannot:</h3>
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

    # Authenticate — try cookie first, then form credentials
    admin = await _get_admin_from_cookie(request)
    if not admin and admin_email:
        from routes._neo_state import state as _st
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

    from routes._neo_state import state as _st
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
            return JSONResponse({"error": "invalid_request"}, status_code=400)

    if body.get("grant_type") != "authorization_code":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    code = body.get("code", "")
    code_verifier = body.get("code_verifier", "")
    redirect_uri = body.get("redirect_uri", "")
    client_id = body.get("client_id", "")

    code_doc = await db.mcp_oauth_codes.find_one({"code": code, "used": False}, {"_id": 0})
    if not code_doc:
        return JSONResponse({"error": "invalid_grant", "error_description": "Code not found or already used"}, status_code=400)
    if _now() > _as_aware(code_doc["expires_at"]):
        await db.mcp_oauth_codes.update_one({"code": code}, {"$set": {"used": True}})
        return JSONResponse({"error": "invalid_grant", "error_description": "Code expired"}, status_code=400)
    if code_doc.get("redirect_uri") != redirect_uri:
        return JSONResponse({"error": "invalid_grant", "error_description": "redirect_uri mismatch"}, status_code=400)
    if code_doc.get("client_id") != client_id:
        return JSONResponse({"error": "invalid_client"}, status_code=400)

    # PKCE S256 validation
    computed = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    if computed != code_doc.get("code_challenge", ""):
        return JSONResponse({"error": "invalid_grant", "error_description": "PKCE verification failed"}, status_code=400)

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
    })


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

