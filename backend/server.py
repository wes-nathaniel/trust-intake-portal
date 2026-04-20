from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import uuid
import logging
import secrets
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

import bcrypt
import jwt
import requests
import resend
from bson import ObjectId
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Header, Query
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from starlette.middleware.cors import CORSMiddleware
import io
from pdf_export import build_intake_pdf
import esign
import sms
from ai_assistant import answer_question as ai_answer_question

# ---------- CONFIG ----------
JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 60 * 12          # 12 hours for client convenience
REFRESH_TTL_DAYS = 14
APP_NAME = os.environ.get("APP_NAME", "trust-portal")
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "onboarding@resend.dev")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# ---------- DATABASE ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

# ---------- APP ----------
app = FastAPI(title="Trust Intake & Client Portal")
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("trust-portal")

# ---------- HELPERS ----------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def new_id() -> str:
    return str(uuid.uuid4())

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

def create_access_token(user_id: str, email: str, role: str) -> str:
    payload = {"sub": user_id, "email": email, "role": role,
               "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TTL_MIN),
               "type": "access"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {"sub": user_id, "exp": datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS),
               "type": "refresh"}
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def set_auth_cookies(response: Response, access: str, refresh: str):
    # secure=True requires HTTPS. Using samesite='none' for cross-site preview + secure
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none",
                        max_age=ACCESS_TTL_MIN * 60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none",
                        max_age=REFRESH_TTL_DAYS * 86400, path="/")

def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0, "password_hash": 0})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

# ---------- STORAGE ----------
storage_key: Optional[str] = None

def init_storage() -> Optional[str]:
    global storage_key
    if storage_key:
        return storage_key
    if not EMERGENT_KEY:
        logger.warning("EMERGENT_LLM_KEY not set — storage disabled")
        return None
    try:
        r = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
        r.raise_for_status()
        storage_key = r.json()["storage_key"]
        logger.info("Object storage initialized")
        return storage_key
    except Exception as e:
        logger.error(f"Storage init failed: {e}")
        return None

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage service unavailable")
    r = requests.put(f"{STORAGE_URL}/objects/{path}",
                     headers={"X-Storage-Key": key, "Content-Type": content_type},
                     data=data, timeout=120)
    r.raise_for_status()
    return r.json()

def get_object(path: str) -> tuple:
    key = init_storage()
    if not key:
        raise HTTPException(status_code=503, detail="Storage service unavailable")
    r = requests.get(f"{STORAGE_URL}/objects/{path}",
                     headers={"X-Storage-Key": key}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")

# ---------- EMAIL ----------
async def _branding_doc() -> dict:
    rec = await db.branding.find_one({"id": "global"}, {"_id": 0})
    return {**DEFAULT_BRANDING, **(rec or {})}


def _email_shell(business, primary, accent, inner_html):
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="font-family:Georgia,serif;background:#F6F4F0;padding:24px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid #EBE7DF;border-radius:10px;overflow:hidden;">
      <tr><td style="background:{primary};padding:24px;color:#F6F4F0;">
        <div style="font-size:11px;letter-spacing:3px;color:{accent};text-transform:uppercase;margin-bottom:6px;">Trust & Estate Portal</div>
        <div style="font-size:24px;font-family:Georgia,serif;">{business}</div>
      </td></tr>
      <tr><td style="padding:28px;color:#1C252E;font-size:15px;line-height:1.55;">{inner_html}</td></tr>
      <tr><td style="background:#F6F4F0;padding:16px;text-align:center;color:#64748B;font-size:11px;">
        &copy; {business} &middot; Secure Trust Intake Portal
      </td></tr>
    </table>
  </td></tr>
</table>
"""


def _cta(link, label, accent):
    return (f'<p style="text-align:center;margin:28px 0;">'
            f'<a href="{link}" style="display:inline-block;background:{accent};color:#ffffff;'
            f'padding:12px 26px;border-radius:6px;text-decoration:none;font-weight:600;">{label}</a></p>')


def _referral_block(business, accent, referral_link):
    return f"""
<div style="margin-top:24px;border-top:1px dashed #EBE7DF;padding-top:20px;">
  <p style="font-family:Georgia,serif;font-size:18px;color:#1C252E;margin:0 0 6px 0;">Your family deserves the same peace of mind.</p>
  <p style="color:#64748B;font-size:13px;margin:0 0 14px 0;">If {business} has been valuable for you, share us with family or friends who might be putting off their own estate plan.</p>
  <p style="text-align:center;margin:0;">
    <a href="{referral_link}" style="display:inline-block;background:transparent;color:#1C252E;border:1px solid #1C252E;padding:10px 22px;border-radius:6px;text-decoration:none;font-weight:600;">Refer a family</a>
  </p>
</div>
"""


def _welcome_email_html(business, accent, primary, client_name, trust_label, case_id, link):
    inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Welcome, {client_name}.</p>
<p>Your <b>{trust_label}</b> intake has been started with us.</p>
<p>Case reference: <span style="font-family:monospace;background:#EBE7DF;padding:2px 6px;border-radius:4px;">{case_id}</span></p>
<p>You can pick up where you left off at any time. We'll guide you section-by-section and flag anything still required.</p>
{_cta(link, "Continue your intake", accent)}
<p style="color:#64748B;font-size:13px;">If you have questions at any step, use the "Questions about this section?" box inside the portal — your message goes directly to our team.</p>
"""
    return _email_shell(business, primary, accent, inner)


def _invite_email_html(business, accent, primary, client_name, trust_label, sender_name, link):
    inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Welcome, {client_name}.</p>
<p>{sender_name} at <b>{business}</b> has started a <b>{trust_label}</b> intake for you in our secure portal.</p>
<p>Click the button below to set your password and begin. Your intake is saved section-by-section — feel free to pause and return any time.</p>
{_cta(link, "Accept invitation & begin", accent)}
<p style="color:#64748B;font-size:13px;">This invitation link is valid for 7 days. If you weren't expecting this email, please ignore it.</p>
"""
    return _email_shell(business, primary, accent, inner)


def _status_change_email_html(business, accent, primary, client_name, status, case_id, link, pending_items=None):
    nice_copy = {
        "Intake In Progress": "Your intake is now marked as in progress. Thanks for the information so far.",
        "Waiting on Documents": "We're waiting on a few documents from you to move forward. Please sign in to upload them.",
        "In Review": "Your intake is now under attorney review. No action is required from you at this time.",
        "Drafting Trust": "Our team is now drafting your trust documents. We'll reach out if we need anything.",
        "Ready for Signing": "Your trust documents are ready for signing. Please review and sign at your earliest convenience.",
        "Completed": "Your trust is now complete. A PDF summary is attached in a separate email.",
    }.get(status, f"Your case status has been updated to: {status}.")

    pending_html = ""
    if pending_items:
        rows = []
        for p in pending_items:
            note = f'<span style="color:#64748B;font-size:13px;"> — {p.get("note")}</span>' if p.get("note") else ""
            rows.append(f'<li style="padding:6px 0;border-bottom:1px dashed #EBE7DF;"><b>{p.get("label")}</b>{note}</li>')
        pending_html = f"""
<div style="margin-top:16px;background:#FEF6E0;border:1px solid #F4D58D;border-radius:8px;padding:14px 16px;">
  <p style="margin:0 0 8px 0;font-family:Georgia,serif;font-size:16px;color:#78350F;">We still need:</p>
  <ul style="margin:0;padding-left:18px;color:#1C252E;font-size:14px;line-height:1.55;">{"".join(rows)}</ul>
</div>
"""

    inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Status update, {client_name}.</p>
<p style="margin:0 0 8px 0;">Your case <span style="font-family:monospace;background:#EBE7DF;padding:2px 6px;border-radius:4px;">{case_id}</span> is now:</p>
<p style="font-family:Georgia,serif;font-size:22px;color:{accent};margin:0 0 16px 0;">{status}</p>
<p>{nice_copy}</p>
{pending_html}
{_cta(link, "Open your portal" if not pending_items else "Upload the documents", accent)}
"""
    return _email_shell(business, primary, accent, inner)


async def send_email_notification(to_email: str, subject: str, html_body: str):
    if not RESEND_API_KEY:
        logger.info(f"[email-mock] to={to_email} subject={subject}")
        return
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html_body}
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.error(f"Resend send failed: {e}")


async def send_email_notification_with_attachment(to_email: str, subject: str, html_body: str,
                                                  attachment_name: str, attachment_bytes: bytes,
                                                  content_type: str = "application/pdf"):
    if not RESEND_API_KEY:
        logger.info(f"[email-mock-attach] to={to_email} subject={subject} attachment={attachment_name} ({len(attachment_bytes)} bytes)")
        return
    try:
        import base64
        params = {
            "from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html_body,
            "attachments": [{
                "filename": attachment_name,
                "content": base64.b64encode(attachment_bytes).decode("utf-8"),
                "content_type": content_type,
            }],
        }
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.error(f"Resend send (attachment) failed: {e}")

# ---------- MODELS ----------
class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str

class LoginReq(BaseModel):
    email: EmailStr
    password: str

class ForgotReq(BaseModel):
    email: EmailStr

class ResetReq(BaseModel):
    token: str
    password: str = Field(min_length=6)

class InviteReq(BaseModel):
    name: str
    email: EmailStr
    trust_type: Literal["single", "joint"] = "single"
    message: Optional[str] = ""

class AcceptInviteReq(BaseModel):
    token: str
    password: str = Field(min_length=6)

class QuestionCreate(BaseModel):
    section: str
    question: str = Field(min_length=1, max_length=2000)

class QuestionReply(BaseModel):
    reply: str = Field(min_length=1, max_length=4000)

TrustType = Literal["single", "joint"]

class TrustCaseCreate(BaseModel):
    trust_type: TrustType

class Address(BaseModel):
    line1: str = ""
    line2: str = ""
    city: str = ""
    state: str = ""
    zip: str = ""
    country: str = "USA"

class Grantor(BaseModel):
    id: str = Field(default_factory=new_id)
    full_legal_name: str
    middle_name: Optional[str] = ""
    date_of_birth: str
    ssn: str
    phone: str
    secondary_phone: Optional[str] = ""
    email: EmailStr
    address: Address
    marital_status: str
    citizenship: str
    notes: Optional[str] = ""

class Trustee(BaseModel):
    id: str = Field(default_factory=new_id)
    full_legal_name: str
    relationship: str
    phone: str
    email: EmailStr
    address: Optional[Address] = None
    notes: Optional[str] = ""

class SuccessorTrustee(Trustee):
    pass

class Beneficiary(BaseModel):
    id: str = Field(default_factory=new_id)
    full_legal_name: str
    date_of_birth: str
    relationship: str
    percentage: float
    address: Optional[Address] = None
    phone: Optional[str] = ""
    email: Optional[str] = ""
    special_instructions: Optional[str] = ""
    contingent_name: Optional[str] = ""
    contingent_relationship: Optional[str] = ""
    contingent_phone: Optional[str] = ""
    notes: Optional[str] = ""

AssetType = Literal["bank", "real_estate", "vehicle", "life_insurance", "investment", "business", "digital"]

class Asset(BaseModel):
    id: str = Field(default_factory=new_id)
    asset_type: AssetType
    institution_name: Optional[str] = ""
    property_address: Optional[str] = ""
    account_number: Optional[str] = ""
    institution_address: Optional[str] = ""
    estimated_value: Optional[float] = None
    notes: Optional[str] = ""

class EINInfo(BaseModel):
    ssn: str
    authorized: bool = False

STATUSES = [
    "Intake Started",
    "Intake In Progress",
    "Waiting on Documents",
    "In Review",
    "Drafting Trust",
    "Ready for Signing",
    "Completed",
]

class StatusUpdate(BaseModel):
    status: str

class NoteCreate(BaseModel):
    note: str

class MessageCreate(BaseModel):
    body: str
    section: Optional[str] = None  # e.g., "grantor", "help"

class BrandingUpdate(BaseModel):
    business_name: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    logo_url: Optional[str] = None
    header_image_url: Optional[str] = None

# ---------- BRUTE FORCE ----------
async def check_lockout(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if not rec:
        return
    if rec.get("locked_until"):
        locked_until = datetime.fromisoformat(rec["locked_until"])
        if locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")

async def record_failure(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    count = (rec.get("count", 0) if rec else 0) + 1
    update = {"identifier": identifier, "count": count, "last": now_iso()}
    if count >= 5:
        update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()
        update["count"] = 0
    await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)

async def clear_failures(identifier: str):
    await db.login_attempts.delete_one({"identifier": identifier})

# ---------- AUTH ENDPOINTS ----------
def public_user(u: dict) -> dict:
    return {"id": u["id"], "email": u["email"], "name": u.get("name", ""), "role": u.get("role", "client")}

@api_router.post("/auth/register")
async def register(body: RegisterReq, response: Response):
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = {
        "id": new_id(),
        "email": email,
        "name": body.name,
        "password_hash": hash_password(body.password),
        "role": "client",
        "created_at": now_iso(),
    }
    await db.users.insert_one(user)
    access = create_access_token(user["id"], email, "client")
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return public_user(user)

@api_router.post("/auth/login")
async def login(body: LoginReq, request: Request, response: Response):
    email = body.email.lower()
    # Derive real client IP from proxy headers (K8s ingress)
    xff = request.headers.get("x-forwarded-for", "")
    real_ip = xff.split(",")[0].strip() if xff else (request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown"))
    identifier = f"{real_ip}:{email}"
    email_identifier = f"email:{email}"
    await check_lockout(identifier)
    await check_lockout(email_identifier)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await record_failure(identifier)
        await record_failure(email_identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await clear_failures(identifier)
    await clear_failures(email_identifier)
    access = create_access_token(user["id"], email, user.get("role", "client"))
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return public_user(user)

@api_router.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

@api_router.post("/auth/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = create_access_token(user["id"], user["email"], user.get("role", "client"))
        response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none",
                            max_age=ACCESS_TTL_MIN * 60, path="/")
        return {"ok": True}
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

@api_router.post("/auth/forgot-password")
async def forgot_password(body: ForgotReq):
    user = await db.users.find_one({"email": body.email.lower()})
    if user:
        token = secrets.token_urlsafe(32)
        await db.password_reset_tokens.insert_one({
            "token": token,
            "user_id": user["id"],
            "used": False,
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "created_at": now_iso(),
        })
        reset_link = f"{FRONTEND_URL}/reset-password?token={token}"
        logger.info(f"Password reset link for {body.email}: {reset_link}")
        await send_email_notification(
            body.email, "Reset your Trust Portal password",
            f"<p>Click the link below to reset your password (valid for 1 hour):</p><p><a href='{reset_link}'>Reset Password</a></p>"
        )
    return {"ok": True}

@api_router.post("/auth/reset-password")
async def reset_password(body: ResetReq):
    rec = await db.password_reset_tokens.find_one({"token": body.token, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    expires_at = rec["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Token expired")
    await db.users.update_one({"id": rec["user_id"]}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.password_reset_tokens.update_one({"token": body.token}, {"$set": {"used": True}})
    return {"ok": True}


# ---------- CLIENT INVITES ----------
@api_router.post("/admin/invite-client")
async def admin_invite_client(body: InviteReq, admin: dict = Depends(require_admin)):
    email = body.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing and existing.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Cannot invite an admin email")
    # Create user if needed (random password, requires invite-acceptance to set real one)
    if not existing:
        user_id = new_id()
        await db.users.insert_one({
            "id": user_id,
            "email": email,
            "name": body.name,
            "password_hash": hash_password(secrets.token_urlsafe(24)),
            "role": "client",
            "created_at": now_iso(),
            "invited_by": admin["id"],
        })
    else:
        user_id = existing["id"]
        # Update name if blank
        if not existing.get("name"):
            await db.users.update_one({"id": user_id}, {"$set": {"name": body.name}})
    # Create a trust case for them
    case = {
        "id": new_id(),
        "client_id": user_id,
        "client_email": email,
        "client_name": body.name,
        "trust_type": body.trust_type,
        "status": "Intake Started",
        "grantors": [], "trustees": [], "successor_trustees": [],
        "beneficiaries": [], "assets": [],
        "ein": None, "ein_requested": False, "ein_letter": None,
        "documents": [], "admin_notes": [], "branding": {},
        "created_at": now_iso(), "updated_at": now_iso(),
        "invited": True,
    }
    await db.trust_cases.insert_one(case)
    # Invite token (7-day expiry, stored in DB)
    token = secrets.token_urlsafe(32)
    await db.invites.insert_one({
        "token": token,
        "user_id": user_id,
        "case_id": case["id"],
        "email": email,
        "name": body.name,
        "used": False,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": now_iso(),
    })
    # Branded invite email
    branding = await _branding_doc()
    link = f"{FRONTEND_URL}/accept-invite?token={token}"
    html = _invite_email_html(
        business=branding.get("business_name", "Trust Portal"),
        accent=branding.get("accent_color", "#C5A880"),
        primary=branding.get("primary_color", "#1C252E"),
        client_name=body.name,
        trust_label="Joint Trust" if body.trust_type == "joint" else "Single Trust",
        sender_name=admin.get("name") or "Your trust team",
        link=link,
    )
    await send_email_notification(email, f"You're invited — {branding.get('business_name','Trust Portal')}", html)
    return {"ok": True, "case_id": case["id"], "user_id": user_id}


@api_router.get("/auth/invite-info")
async def invite_info(token: str):
    rec = await db.invites.find_one({"token": token, "used": False}, {"_id": 0})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or used invitation")
    expires_at = rec["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")
    return {"email": rec["email"], "name": rec["name"], "case_id": rec["case_id"]}


@api_router.post("/auth/accept-invite")
async def accept_invite(body: AcceptInviteReq, response: Response):
    rec = await db.invites.find_one({"token": body.token, "used": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Invalid or used invitation")
    expires_at = rec["expires_at"]
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation expired")
    user = await db.users.find_one({"id": rec["user_id"]})
    if not user:
        raise HTTPException(status_code=400, detail="User not found")
    # Set password & log in
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(body.password)}})
    await db.invites.update_one({"token": body.token}, {"$set": {"used": True, "used_at": now_iso()}})
    access = create_access_token(user["id"], user["email"], user.get("role", "client"))
    refresh = create_refresh_token(user["id"])
    set_auth_cookies(response, access, refresh)
    return {**public_user(user), "case_id": rec["case_id"]}

# ---------- TRUST CASES ----------
async def get_case(case_id: str, user: dict) -> dict:
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Trust case not found")
    if user.get("role") != "admin" and case["client_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not authorized")
    return case

async def update_case(case_id: str, updates: dict):
    updates["updated_at"] = now_iso()
    await db.trust_cases.update_one({"id": case_id}, {"$set": updates})

@api_router.post("/trust-cases")
async def create_trust_case(body: TrustCaseCreate, user: dict = Depends(get_current_user)):
    case = {
        "id": new_id(),
        "client_id": user["id"],
        "client_email": user["email"],
        "client_name": user.get("name", ""),
        "trust_type": body.trust_type,
        "status": "Intake Started",
        "grantors": [],
        "trustees": [],
        "successor_trustees": [],
        "beneficiaries": [],
        "assets": [],
        "ein": None,
        "ein_requested": False,
        "ein_letter": None,
        "documents": [],
        "admin_notes": [],
        "branding": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.trust_cases.insert_one(case)
    case.pop("_id", None)
    # Branded welcome email
    branding = await _branding_doc()
    biz = branding.get("business_name", "our firm")
    trust_label = "Joint Trust" if body.trust_type == "joint" else "Single Trust"
    welcome_html = _welcome_email_html(
        business=biz,
        accent=branding.get("accent_color", "#C5A880"),
        primary=branding.get("primary_color", "#1C252E"),
        client_name=user.get("name") or user["email"],
        trust_label=trust_label,
        case_id=case["id"][:8].upper(),
        link=f"{FRONTEND_URL}/intake/{case['id']}",
    )
    await send_email_notification(user["email"], f"Welcome to {biz} — your trust intake has begun", welcome_html)
    # Notify admin too
    admin = await db.users.find_one({"role": "admin"})
    if admin:
        await send_email_notification(
            admin["email"],
            f"New trust intake started — {user.get('name') or user['email']}",
            f"<p>A new <b>{trust_label}</b> case has been started by "
            f"<b>{user.get('name') or user['email']}</b>.</p>"
            f"<p><a href='{FRONTEND_URL}/admin/cases/{case['id']}'>Open case in admin</a></p>",
        )
    return case

@api_router.get("/trust-cases/mine")
async def my_cases(user: dict = Depends(get_current_user)):
    cases = await db.trust_cases.find({"client_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [_attach_pending(c) for c in cases]

@api_router.get("/trust-cases/{case_id}")
async def get_case_endpoint(case_id: str, user: dict = Depends(get_current_user)):
    c = await get_case(case_id, user)
    return _attach_pending(c)

# --- Grantor ---
@api_router.post("/trust-cases/{case_id}/grantors")
async def add_grantor(case_id: str, g: Grantor, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    max_grantors = 2 if case["trust_type"] == "joint" else 1
    grantors = case.get("grantors", [])
    if len(grantors) >= max_grantors:
        raise HTTPException(status_code=400, detail=f"Max {max_grantors} grantor(s) allowed")
    grantors.append(g.model_dump())
    await update_case(case_id, {"grantors": grantors, "status": "Intake In Progress"})
    return g.model_dump()

@api_router.put("/trust-cases/{case_id}/grantors/{grantor_id}")
async def update_grantor(case_id: str, grantor_id: str, g: Grantor, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    grantors = case.get("grantors", [])
    found = False
    for i, x in enumerate(grantors):
        if x["id"] == grantor_id:
            g_data = g.model_dump()
            g_data["id"] = grantor_id
            grantors[i] = g_data
            found = True
            break
    if not found:
        raise HTTPException(status_code=404, detail="Grantor not found")
    await update_case(case_id, {"grantors": grantors})
    return grantors[i]

@api_router.delete("/trust-cases/{case_id}/grantors/{grantor_id}")
async def delete_grantor(case_id: str, grantor_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    grantors = [x for x in case.get("grantors", []) if x["id"] != grantor_id]
    await update_case(case_id, {"grantors": grantors})
    return {"ok": True}

# --- Trustee (one) ---
@api_router.put("/trust-cases/{case_id}/trustee")
async def set_trustee(case_id: str, t: Trustee, user: dict = Depends(get_current_user)):
    await get_case(case_id, user)
    await update_case(case_id, {"trustees": [t.model_dump()]})
    return t.model_dump()

# --- Successor Trustees (up to 3) ---
@api_router.post("/trust-cases/{case_id}/successor-trustees")
async def add_successor(case_id: str, t: SuccessorTrustee, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    succ = case.get("successor_trustees", [])
    if len(succ) >= 3:
        raise HTTPException(status_code=400, detail="Maximum 3 successor trustees")
    succ.append(t.model_dump())
    await update_case(case_id, {"successor_trustees": succ})
    return t.model_dump()

@api_router.put("/trust-cases/{case_id}/successor-trustees/{sid}")
async def update_successor(case_id: str, sid: str, t: SuccessorTrustee, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    succ = case.get("successor_trustees", [])
    for i, x in enumerate(succ):
        if x["id"] == sid:
            data = t.model_dump(); data["id"] = sid; succ[i] = data
            await update_case(case_id, {"successor_trustees": succ})
            return data
    raise HTTPException(status_code=404, detail="Successor trustee not found")

@api_router.delete("/trust-cases/{case_id}/successor-trustees/{sid}")
async def delete_successor(case_id: str, sid: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    succ = [x for x in case.get("successor_trustees", []) if x["id"] != sid]
    await update_case(case_id, {"successor_trustees": succ})
    return {"ok": True}

# --- Beneficiaries ---
def _validate_pct_total(bens: list) -> float:
    total = sum(float(b.get("percentage", 0) or 0) for b in bens)
    if total > 100.0001:
        raise HTTPException(status_code=400,
                            detail=f"Beneficiary shares total {total}% — cannot exceed 100%.")
    return total

@api_router.post("/trust-cases/{case_id}/beneficiaries")
async def add_beneficiary(case_id: str, b: Beneficiary, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    bens = case.get("beneficiaries", [])
    if float(b.percentage or 0) <= 0:
        raise HTTPException(status_code=400, detail="Beneficiary share must be greater than 0.")
    new_list = bens + [b.model_dump()]
    _validate_pct_total(new_list)
    await update_case(case_id, {"beneficiaries": new_list})
    return b.model_dump()

@api_router.put("/trust-cases/{case_id}/beneficiaries/{bid}")
async def update_beneficiary(case_id: str, bid: str, b: Beneficiary, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    bens = case.get("beneficiaries", [])
    if float(b.percentage or 0) <= 0:
        raise HTTPException(status_code=400, detail="Beneficiary share must be greater than 0.")
    for i, x in enumerate(bens):
        if x["id"] == bid:
            data = b.model_dump(); data["id"] = bid; bens[i] = data
            _validate_pct_total(bens)
            await update_case(case_id, {"beneficiaries": bens})
            return data
    raise HTTPException(status_code=404, detail="Beneficiary not found")

@api_router.delete("/trust-cases/{case_id}/beneficiaries/{bid}")
async def delete_beneficiary(case_id: str, bid: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    bens = [x for x in case.get("beneficiaries", []) if x["id"] != bid]
    await update_case(case_id, {"beneficiaries": bens})
    return {"ok": True}

# --- Assets ---
@api_router.post("/trust-cases/{case_id}/assets")
async def add_asset(case_id: str, a: Asset, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    # Validation: real_estate needs property_address, others need institution_name
    if a.asset_type == "real_estate":
        if not a.property_address:
            raise HTTPException(status_code=400, detail="Property address required for real estate")
    else:
        if not a.institution_name:
            raise HTTPException(status_code=400, detail="Institution name required")
    assets = case.get("assets", [])
    assets.append(a.model_dump())
    await update_case(case_id, {"assets": assets})
    return a.model_dump()

@api_router.put("/trust-cases/{case_id}/assets/{aid}")
async def update_asset(case_id: str, aid: str, a: Asset, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    assets = case.get("assets", [])
    for i, x in enumerate(assets):
        if x["id"] == aid:
            data = a.model_dump(); data["id"] = aid; assets[i] = data
            await update_case(case_id, {"assets": assets})
            return data
    raise HTTPException(status_code=404, detail="Asset not found")

@api_router.delete("/trust-cases/{case_id}/assets/{aid}")
async def delete_asset(case_id: str, aid: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    assets = [x for x in case.get("assets", []) if x["id"] != aid]
    await update_case(case_id, {"assets": assets})
    return {"ok": True}

# --- EIN ---
@api_router.put("/trust-cases/{case_id}/ein")
async def set_ein(case_id: str, body: EINInfo, user: dict = Depends(get_current_user)):
    await get_case(case_id, user)
    if not body.authorized:
        raise HTTPException(status_code=400, detail="EIN authorization is required")
    await update_case(case_id, {"ein": body.model_dump()})
    return body.model_dump()

# --- Documents ---
REQUIRED_DOC_TYPES = {"government_id", "proof_of_address"}
ALLOWED_DOC_TYPES = REQUIRED_DOC_TYPES | {
    "existing_trust", "bank_statement", "deed", "title", "insurance_policy",
    "business_document", "supporting_file", "ein_letter"
}

# ---------- DOC REQUESTS / PENDING ITEMS ----------
DOC_TYPE_LABELS = {
    "government_id": "Government-issued ID",
    "proof_of_address": "Proof of Address",
    "existing_trust": "Existing Trust Document",
    "bank_statement": "Bank Statement",
    "deed": "Deed",
    "title": "Title",
    "insurance_policy": "Insurance Policy",
    "business_document": "Business Document",
    "supporting_file": "Supporting File",
    "ein_letter": "EIN Letter",
}

ASSET_DOC_TYPES = {"bank_statement", "deed", "title", "insurance_policy", "business_document"}

class DocRequestCreate(BaseModel):
    doc_type: str
    label: Optional[str] = None
    note: Optional[str] = ""

def _doc_label(dtype: str, override: Optional[str] = None) -> str:
    return override or DOC_TYPE_LABELS.get(dtype, dtype.replace("_", " ").title())

def _compute_pending(case: dict) -> list:
    """Return a list of pending items for the client: required missing docs, admin doc requests, messages needing reply."""
    pending = []
    docs = [d for d in (case.get("documents") or []) if not d.get("is_deleted")]
    types_uploaded = {d["doc_type"] for d in docs}

    # Required docs
    for dt in ("government_id", "proof_of_address"):
        if dt not in types_uploaded:
            pending.append({
                "kind": "required_doc",
                "doc_type": dt,
                "label": _doc_label(dt),
                "step": "documents",
            })

    # Admin-initiated doc requests (not fulfilled, not cancelled)
    for r in case.get("requested_documents", []) or []:
        if not r.get("fulfilled") and not r.get("cancelled"):
            pending.append({
                "kind": "requested_doc",
                "request_id": r["id"],
                "doc_type": r.get("doc_type"),
                "label": _doc_label(r.get("doc_type", ""), r.get("label")),
                "note": r.get("note", ""),
                "step": "documents",
            })
    return pending


def _attach_pending(case: dict) -> dict:
    case["pending_items"] = _compute_pending(case)
    return case




@api_router.post("/trust-cases/{case_id}/documents")
async def upload_document(case_id: str,
                          doc_type: str = Form(...),
                          file: UploadFile = File(...),
                          user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    if doc_type not in ALLOWED_DOC_TYPES:
        raise HTTPException(status_code=400, detail="Invalid document type")
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "bin").lower()
    path = f"{APP_NAME}/uploads/{user['id']}/{case_id}/{new_id()}.{ext}"
    data = await file.read()
    result = put_object(path, data, file.content_type or "application/octet-stream")
    doc = {
        "id": new_id(),
        "doc_type": doc_type,
        "storage_path": result["path"],
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": result.get("size", len(data)),
        "uploaded_by": user["id"],
        "uploaded_by_role": user.get("role", "client"),
        "uploaded_at": now_iso(),
        "is_deleted": False,
    }
    docs = case.get("documents", [])
    docs.append(doc)
    updates = {"documents": docs}
    if doc_type == "ein_letter" and user.get("role") == "admin":
        updates["ein_letter"] = doc
    # Auto-fulfill any matching open doc request
    reqs = list(case.get("requested_documents", []) or [])
    changed = False
    for r in reqs:
        if (not r.get("fulfilled") and not r.get("cancelled")
                and r.get("doc_type") == doc_type):
            r["fulfilled"] = True
            r["fulfilled_at"] = now_iso()
            r["fulfilled_doc_id"] = doc["id"]
            changed = True
            break
    if changed:
        updates["requested_documents"] = reqs
    await update_case(case_id, updates)
    return doc

@api_router.get("/trust-cases/{case_id}/documents/{doc_id}/download")
async def download_document(case_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    doc = next((d for d in case.get("documents", []) if d["id"] == doc_id and not d.get("is_deleted")), None)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    data, ct = get_object(doc["storage_path"])
    return StreamingResponse(io.BytesIO(data), media_type=doc.get("content_type", ct),
                             headers={"Content-Disposition": f'attachment; filename="{doc.get("filename","file")}"'})

@api_router.delete("/trust-cases/{case_id}/documents/{doc_id}")
async def delete_document(case_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    docs = case.get("documents", [])
    for d in docs:
        if d["id"] == doc_id:
            d["is_deleted"] = True
    await update_case(case_id, {"documents": docs})
    return {"ok": True}

# --- Messages ---
@api_router.post("/trust-cases/{case_id}/messages")
async def post_message(case_id: str, body: MessageCreate, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    msg = {
        "id": new_id(),
        "case_id": case_id,
        "sender_id": user["id"],
        "sender_name": user.get("name", ""),
        "sender_role": user.get("role", "client"),
        "body": body.body,
        "section": body.section,
        "read": False,
        "created_at": now_iso(),
    }
    await db.messages.insert_one(msg)
    msg.pop("_id", None)
    # Notify recipient by email
    if user.get("role") == "client":
        # notify admin
        admin = await db.users.find_one({"role": "admin"})
        if admin:
            await send_email_notification(
                admin["email"],
                f"New message from {user.get('name','client')} — Trust Portal",
                f"<p><b>{user.get('name','Client')}</b> sent a message:</p><blockquote>{body.body}</blockquote><p><a href='{FRONTEND_URL}/admin/cases/{case_id}'>View in portal</a></p>"
            )
    else:
        # notify client
        await send_email_notification(
            case["client_email"],
            "New message from your trust team — Trust Portal",
            f"<p>You have a new message:</p><blockquote>{body.body}</blockquote><p><a href='{FRONTEND_URL}/portal'>View in portal</a></p>"
        )
    return msg

@api_router.get("/trust-cases/{case_id}/messages")
async def list_messages(case_id: str, user: dict = Depends(get_current_user)):
    await get_case(case_id, user)
    msgs = await db.messages.find({"case_id": case_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    # Mark messages as read by the viewer (those not sent by the viewer)
    await db.messages.update_many({"case_id": case_id, "sender_id": {"$ne": user["id"]}}, {"$set": {"read": True}})
    return msgs

@api_router.get("/messages/unread-count")
async def unread_count(user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        count = await db.messages.count_documents({"sender_role": "client", "read": False})
    else:
        # messages in my cases from admin that I haven't read
        my_cases = await db.trust_cases.find({"client_id": user["id"]}, {"_id": 0, "id": 1}).to_list(500)
        case_ids = [c["id"] for c in my_cases]
        count = await db.messages.count_documents({"case_id": {"$in": case_ids}, "sender_role": "admin", "read": False})
    return {"unread": count}

# --- Status (client-visible) ---
@api_router.get("/trust-cases/{case_id}/status")
async def status_get(case_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    return {"status": case.get("status"), "updated_at": case.get("updated_at")}

# ---------- CLIENT QUESTIONS / AI ASSISTANT ----------
SECTION_LABELS = {
    "grantors": "Grantor / Settlor",
    "trustee": "Trustee",
    "successor": "Successor Trustee",
    "beneficiaries": "Beneficiaries",
    "assets": "Assets",
    "ein": "EIN",
    "documents": "Documents",
    "review": "Review",
    "help": "General",
}


@api_router.post("/trust-cases/{case_id}/questions")
async def post_question(case_id: str, body: QuestionCreate, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    section_label = SECTION_LABELS.get(body.section, body.section.title())

    # Run AI assistant
    ai_result = await ai_answer_question(section=section_label, question=body.question,
                                         client_name=user.get("name", ""))

    qid = new_id()
    now = now_iso()
    q = {
        "id": qid,
        "case_id": case_id,
        "client_id": user["id"],
        "client_name": user.get("name", case.get("client_name", "")),
        "client_email": user.get("email", ""),
        "section": body.section,
        "section_label": section_label,
        "question": body.question,
        "ai_response": ai_result.get("text"),
        "ai_confident": bool(ai_result.get("confident")),
        "admin_reply": None,
        "admin_replied_at": None,
        "admin_replied_by": None,
        "status": "ai_answered" if ai_result.get("confident") else "escalated",
        "created_at": now,
        "updated_at": now,
    }
    await db.questions.insert_one(q)
    q.pop("_id", None)

    # Escalate via SMS (key-gated) + email fallback
    if not ai_result.get("confident"):
        admin_link = f"{FRONTEND_URL}/admin/questions"
        sms_body = (
            f"[IGC Trust Portal] New question from {q['client_name']} in '{section_label}': "
            f"\"{body.question[:180]}{'…' if len(body.question) > 180 else ''}\" — Reply: {admin_link}"
        )
        sms_sent = sms.send_admin_sms(sms_body)
        if not sms_sent:
            # Fallback to email (keeps admin in the loop while SMS is not configured)
            try:
                branding = await _branding_doc()
                biz = branding.get("business_name", "Trust Portal")
                accent = branding.get("accent_color", "#C5A880")
                primary = branding.get("primary_color", "#1C252E")
                inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">New question from {q['client_name']}</p>
<p style="color:#64748B;margin:0 0 12px 0;">Section: <b>{section_label}</b> · {now[:19].replace('T',' ')}</p>
<blockquote style="margin:0 0 16px 0;padding:12px 14px;background:#F6F4F0;border-left:3px solid {accent};font-style:italic;">{body.question}</blockquote>
{_cta(admin_link, "Reply in admin dashboard", accent)}
"""
                html = _email_shell(biz, primary, accent, inner)
                admin_rec = await db.users.find_one({"role": "admin"})
                if admin_rec:
                    await send_email_notification(
                        admin_rec["email"],
                        f"Client question ({section_label}) — {q['client_name']}",
                        html,
                    )
            except Exception as e:
                logger.error(f"Escalation email failed: {e}")
    return q


@api_router.get("/trust-cases/{case_id}/questions")
async def list_questions(case_id: str, section: Optional[str] = None,
                         user: dict = Depends(get_current_user)):
    await get_case(case_id, user)
    flt = {"case_id": case_id}
    if section:
        flt["section"] = section
    qs = await db.questions.find(flt, {"_id": 0}).sort("created_at", 1).to_list(500)
    return qs


@api_router.get("/admin/questions")
async def admin_list_questions(status: Optional[str] = None, case_id: Optional[str] = None,
                               _: dict = Depends(require_admin)):
    flt = {}
    if status:
        flt["status"] = status
    if case_id:
        flt["case_id"] = case_id
    qs = await db.questions.find(flt, {"_id": 0}).sort("created_at", -1).to_list(500)
    # counts
    pending = await db.questions.count_documents({"status": "escalated"})
    ai_answered = await db.questions.count_documents({"status": "ai_answered"})
    admin_replied = await db.questions.count_documents({"status": "admin_replied"})
    return {"questions": qs, "counts": {"escalated": pending, "ai_answered": ai_answered, "admin_replied": admin_replied}}


@api_router.post("/admin/questions/{qid}/reply")
async def admin_reply_question(qid: str, body: QuestionReply, admin: dict = Depends(require_admin)):
    q = await db.questions.find_one({"id": qid}, {"_id": 0})
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    now = now_iso()
    await db.questions.update_one(
        {"id": qid},
        {"$set": {
            "admin_reply": body.reply,
            "admin_replied_at": now,
            "admin_replied_by": admin.get("name") or "Admin",
            "status": "admin_replied",
            "updated_at": now,
        }},
    )
    # Email the client with the reply
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        section_label = q.get("section_label") or SECTION_LABELS.get(q.get("section", ""), "your intake")
        link = f"{FRONTEND_URL}/intake/{q['case_id']}?step={q['section']}"
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Reply from your trust team</p>
<p style="color:#64748B;margin:0 0 10px 0;">Section: <b>{section_label}</b></p>
<blockquote style="margin:0 0 10px 0;padding:10px 14px;background:#F6F4F0;border-left:3px solid {accent};font-style:italic;color:#64748B;">{q.get('question')}</blockquote>
<div style="padding:12px 14px;background:#ffffff;border:1px solid #EBE7DF;border-radius:6px;">{body.reply}</div>
{_cta(link, "Open your portal", accent)}
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(q["client_email"],
                                      f"{biz} replied to your question",
                                      html)
    except Exception as e:
        logger.error(f"Reply email failed: {e}")
    q["admin_reply"] = body.reply
    q["status"] = "admin_replied"
    q["admin_replied_at"] = now
    q["admin_replied_by"] = admin.get("name") or "Admin"
    return q


# ---------- ADMIN ----------
@api_router.get("/admin/trust-cases")
async def admin_list_cases(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    _: dict = Depends(require_admin),
):
    flt = {}
    if status:
        flt["status"] = status
    if q:
        flt["$or"] = [
            {"client_name": {"$regex": q, "$options": "i"}},
            {"client_email": {"$regex": q, "$options": "i"}},
        ]
    cases = await db.trust_cases.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return cases

@api_router.get("/admin/trust-cases/{case_id}")
async def admin_get_case(case_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    # Attach pending_invite info (case was invited and client hasn't accepted yet)
    pending = None
    if case.get("invited"):
        active = await db.invites.find_one(
            {"case_id": case_id, "used": False},
            {"_id": 0, "expires_at": 1, "created_at": 1, "email": 1},
            sort=[("created_at", -1)],
        )
        if active:
            exp = active.get("expires_at")
            if isinstance(exp, datetime):
                exp = exp.isoformat()
            pending = {
                "email": active.get("email"),
                "expires_at": exp,
                "created_at": active.get("created_at"),
            }
    case["pending_invite"] = pending
    return _attach_pending(case)

@api_router.put("/admin/trust-cases/{case_id}/status")
async def admin_update_status(case_id: str, body: StatusUpdate, admin: dict = Depends(require_admin)):
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    prev_status = case.get("status")
    await update_case(case_id, {"status": body.status})
    if body.status == prev_status:
        return {"ok": True, "status": body.status}

    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    accent = branding.get("accent_color", "#C5A880")
    primary = branding.get("primary_color", "#1C252E")

    # Progress-status email on every status change (incl. Completed below which adds attachment)
    if body.status != "Completed":
        try:
            pending = _compute_pending(case) if body.status == "Waiting on Documents" else None
            portal_link = f"{FRONTEND_URL}/intake/{case_id}?step=documents" if pending else f"{FRONTEND_URL}/portal"
            html = _status_change_email_html(
                business=biz, accent=accent, primary=primary,
                client_name=case.get("client_name") or case.get("client_email"),
                status=body.status,
                case_id=case_id[:8].upper(),
                link=portal_link,
                pending_items=pending,
            )
            await send_email_notification(
                case.get("client_email"),
                f"Status update: {body.status} — {biz}",
                html,
            )
        except Exception as e:
            logger.error(f"Status change email failed: {e}")

    # Completion email with PDF + referral block
    if body.status == "Completed" and prev_status != "Completed":
        try:
            case["status"] = "Completed"
            pdf_bytes = build_intake_pdf(case, branding)
            referral_link = f"{FRONTEND_URL}/register?ref={case_id[:8]}"
            referral_html = _referral_block(biz, accent, referral_link)
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Your trust intake is complete.</p>
<p>Thank you for trusting {biz}. A PDF summary of your intake is attached for your records.</p>
<p>You can download it again anytime from your portal.</p>
{_cta(f'{FRONTEND_URL}/portal', 'Open your portal', accent)}
{referral_html}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification_with_attachment(
                to_email=case.get("client_email"),
                subject=f"Your trust intake is complete — {biz}",
                html_body=html,
                attachment_name=f"trust-intake-{case_id[:8]}.pdf",
                attachment_bytes=pdf_bytes,
                content_type="application/pdf",
            )
        except Exception as e:
            logger.error(f"Completion email failed: {e}")
    return {"ok": True, "status": body.status}


@api_router.get("/trust-cases/{case_id}/export.pdf")
async def export_pdf(case_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    branding = await _branding_doc()
    pdf_bytes = build_intake_pdf(case, branding)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trust-intake-{case_id[:8]}.pdf"'
        },
    )


# ---------- E-SIGN (Dropbox Sign) ----------
@api_router.get("/admin/esign/health")
async def esign_health(_: dict = Depends(require_admin)):
    return {"enabled": esign.is_enabled(), "test_mode": esign.TEST_MODE}


@api_router.post("/admin/trust-cases/{case_id}/send-for-signing")
async def admin_send_for_signing(
    case_id: str,
    file: UploadFile = File(...),
    signer_email: str = Form(...),
    signer_name: str = Form(...),
    title: Optional[str] = Form(None),
    admin: dict = Depends(require_admin),
):
    if not esign.is_enabled():
        raise HTTPException(status_code=503, detail="E-sign is not configured. Add DROPBOX_SIGN_API_KEY in backend/.env and restart backend.")
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    # Read file bytes
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="File is empty")

    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    doc_title = title or f"Trust Document — Case #{case_id[:8].upper()}"
    try:
        result = esign.send_signature_request(
            pdf_bytes=pdf_bytes,
            filename=file.filename or "trust.pdf",
            signer_email=signer_email,
            signer_name=signer_name,
            title=doc_title,
            subject=f"Please sign your trust document — {biz}",
            message=f"Your trust is ready for signing. Please review and sign this document at your convenience. — {biz}",
        )
    except Exception as e:
        logger.error(f"Dropbox Sign send failed: {e}")
        raise HTTPException(status_code=502, detail=f"Dropbox Sign error: {e}")

    # Also store the unsigned PDF in object storage for record-keeping
    stored_path = None
    try:
        ext = "pdf"
        stored_path = f"{APP_NAME}/uploads/{admin['id']}/{case_id}/unsigned-{new_id()}.{ext}"
        put_object(stored_path, pdf_bytes, "application/pdf")
    except Exception as e:
        logger.warning(f"Unsigned doc storage failed (non-fatal): {e}")

    esign_record = {
        "signature_request_id": result["signature_request_id"],
        "title": doc_title,
        "signer_email": signer_email,
        "signer_name": signer_name,
        "status": "sent",
        "created_at": now_iso(),
        "stored_unsigned_path": stored_path,
        "details_url": result.get("details_url"),
    }
    await update_case(case_id, {
        "esign": esign_record,
        "status": "Ready for Signing",
    })

    # Status-change email already fires from admin_update_status; here we hand-send because we bypassed it
    try:
        html = _status_change_email_html(
            business=biz,
            accent=branding.get("accent_color", "#C5A880"),
            primary=branding.get("primary_color", "#1C252E"),
            client_name=case.get("client_name") or case.get("client_email"),
            status="Ready for Signing",
            case_id=case_id[:8].upper(),
            link=f"{FRONTEND_URL}/portal",
        )
        await send_email_notification(
            case.get("client_email"),
            f"Your trust is ready for signing — {biz}",
            html,
        )
    except Exception as e:
        logger.error(f"Ready-for-signing email failed: {e}")

    return {"ok": True, **esign_record}


@api_router.get("/admin/trust-cases/{case_id}/signature-status")
async def admin_signature_status(case_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rec = case.get("esign")
    if not rec:
        raise HTTPException(status_code=404, detail="No signature request for this case")
    try:
        status = esign.get_status(rec["signature_request_id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dropbox Sign error: {e}")

    new_status = rec.get("status")
    if status.get("is_complete") and rec.get("status") != "signed":
        new_status = "signed"
        rec["status"] = new_status
        rec["signed_at"] = now_iso()
        await update_case(case_id, {"esign": rec, "status": "Completed"})
        # admin_update_status email side-effect won't fire (we set directly); mimic completion email w/ PDF
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            case["status"] = "Completed"
            pdf_bytes = build_intake_pdf(case, branding)
            referral_link = f"{FRONTEND_URL}/register?ref={case_id[:8]}"
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Your signed trust is complete.</p>
<p>Thank you. A PDF intake summary is attached for your records; the signed trust document itself will be available in your portal.</p>
{_cta(f'{FRONTEND_URL}/portal', 'Open your portal', accent)}
{_referral_block(biz, accent, referral_link)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification_with_attachment(
                to_email=case.get("client_email"),
                subject=f"Your trust is signed & complete — {biz}",
                html_body=html,
                attachment_name=f"trust-intake-{case_id[:8]}.pdf",
                attachment_bytes=pdf_bytes,
                content_type="application/pdf",
            )
        except Exception as e:
            logger.error(f"Post-sign email failed: {e}")
    else:
        rec.update({k: v for k, v in status.items() if k in ("signatures", "details_url")})
        await update_case(case_id, {"esign": rec})
    return {**rec, "remote_status": status}


@api_router.get("/admin/trust-cases/{case_id}/download-signed")
async def admin_download_signed(case_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    rec = case.get("esign")
    if not rec:
        raise HTTPException(status_code=404, detail="No signature request")
    try:
        data = esign.download_signed_pdf(rec["signature_request_id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dropbox Sign error: {e}")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="signed-trust-{case_id[:8]}.pdf"'},
    )


@api_router.get("/trust-cases/{case_id}/download-signed")
async def client_download_signed(case_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    rec = case.get("esign")
    if not rec or rec.get("status") != "signed":
        raise HTTPException(status_code=404, detail="No signed document available yet")
    try:
        data = esign.download_signed_pdf(rec["signature_request_id"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Dropbox Sign error: {e}")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="signed-trust-{case_id[:8]}.pdf"'},
    )

@api_router.post("/admin/trust-cases/{case_id}/notes")
async def admin_add_note(case_id: str, body: NoteCreate, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    notes = case.get("admin_notes", [])
    note = {"id": new_id(), "note": body.note, "author": admin.get("name", "Admin"), "created_at": now_iso()}
    notes.append(note)
    await update_case(case_id, {"admin_notes": notes})
    return note

@api_router.post("/admin/trust-cases/{case_id}/ein-request")
async def admin_mark_ein_requested(case_id: str, _: dict = Depends(require_admin)):
    await update_case(case_id, {"ein_requested": True})
    return {"ok": True}


# --- Admin: request specific documents from the client ---
@api_router.post("/admin/trust-cases/{case_id}/doc-requests")
async def admin_create_doc_request(case_id: str, body: DocRequestCreate,
                                   admin: dict = Depends(require_admin),
                                   notify: bool = True):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if body.doc_type not in ALLOWED_DOC_TYPES and body.doc_type != "other":
        # Allow "other" for custom requests
        pass
    req = {
        "id": new_id(),
        "doc_type": body.doc_type,
        "label": body.label or _doc_label(body.doc_type),
        "note": body.note or "",
        "requested_by": admin["id"],
        "requested_by_name": admin.get("name") or "Admin",
        "created_at": now_iso(),
        "fulfilled": False,
        "cancelled": False,
    }
    reqs = list(case.get("requested_documents", []) or [])
    reqs.append(req)
    await update_case(case_id, {"requested_documents": reqs})

    # Notify client via email if status emails desired
    if notify:
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            link = f"{FRONTEND_URL}/intake/{case_id}?step=documents"
            note_html = f'<p style="color:#64748B;font-size:14px;">{body.note}</p>' if body.note else ""
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">We need a document from you.</p>
<p>Our team has requested the following document for your case <span style="font-family:monospace;background:#EBE7DF;padding:2px 6px;border-radius:4px;">{case_id[:8].upper()}</span>:</p>
<p style="font-family:Georgia,serif;font-size:22px;color:{accent};margin:10px 0;">{req['label']}</p>
{note_html}
{_cta(link, "Upload now", accent)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(
                case.get("client_email"),
                f"Document requested: {req['label']} — {biz}",
                html,
            )
        except Exception as e:
            logger.error(f"Doc-request email failed: {e}")
    return req


@api_router.delete("/admin/trust-cases/{case_id}/doc-requests/{req_id}")
async def admin_cancel_doc_request(case_id: str, req_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    reqs = list(case.get("requested_documents", []) or [])
    for r in reqs:
        if r["id"] == req_id:
            r["cancelled"] = True
            r["cancelled_at"] = now_iso()
    await update_case(case_id, {"requested_documents": reqs})
    return {"ok": True}


@api_router.post("/admin/trust-cases/{case_id}/doc-requests/{req_id}/mark-fulfilled")
async def admin_mark_doc_request_fulfilled(case_id: str, req_id: str, admin: dict = Depends(require_admin)):
    """Manual 'Mark received' for offline-delivered docs."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    reqs = list(case.get("requested_documents", []) or [])
    for r in reqs:
        if r["id"] == req_id:
            r["fulfilled"] = True
            r["fulfilled_at"] = now_iso()
            r["fulfilled_by"] = admin["id"]
    await update_case(case_id, {"requested_documents": reqs})
    return {"ok": True}

@api_router.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    total = await db.trust_cases.count_documents({})
    by_status = {}
    for s in STATUSES:
        by_status[s] = await db.trust_cases.count_documents({"status": s})
    clients = await db.users.count_documents({"role": "client"})
    return {"total_cases": total, "total_clients": clients, "by_status": by_status}


# --- Admin notifications: unread messages grouped by case ---
@api_router.get("/admin/notifications")
async def admin_notifications(_: dict = Depends(require_admin), limit: int = 50):
    msgs = await db.messages.find(
        {"sender_role": "client", "read": False},
        {"_id": 0}
    ).sort("created_at", -1).to_list(limit)
    # Group by case_id
    by_case: dict = {}
    case_ids = []
    for m in msgs:
        by_case.setdefault(m["case_id"], []).append(m)
        if m["case_id"] not in case_ids:
            case_ids.append(m["case_id"])
    cases = {}
    if case_ids:
        async for c in db.trust_cases.find(
            {"id": {"$in": case_ids}},
            {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "trust_type": 1, "status": 1}
        ):
            cases[c["id"]] = c
    groups = []
    for cid in case_ids:
        c = cases.get(cid, {})
        groups.append({
            "case_id": cid,
            "client_name": c.get("client_name") or c.get("client_email") or "(unknown)",
            "client_email": c.get("client_email", ""),
            "trust_type": c.get("trust_type"),
            "status": c.get("status"),
            "unread_count": len(by_case[cid]),
            "latest_message": by_case[cid][0],
            "messages": by_case[cid][:5],
        })
    total = await db.messages.count_documents({"sender_role": "client", "read": False})
    return {"total_unread": total, "groups": groups}


# --- Resend invite ---
@api_router.post("/admin/trust-cases/{case_id}/resend-invite")
async def admin_resend_invite(case_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    user = await db.users.find_one({"id": case["client_id"]})
    if not user:
        raise HTTPException(status_code=404, detail="Client user not found")
    # Mark any outstanding invites as used so only the new one is valid
    await db.invites.update_many(
        {"user_id": user["id"], "case_id": case_id, "used": False},
        {"$set": {"used": True, "used_at": now_iso(), "invalidated": True}}
    )
    token = secrets.token_urlsafe(32)
    await db.invites.insert_one({
        "token": token,
        "user_id": user["id"],
        "case_id": case_id,
        "email": user["email"],
        "name": user.get("name", case.get("client_name", "")),
        "used": False,
        "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
        "created_at": now_iso(),
        "resent_by": admin["id"],
    })
    branding = await _branding_doc()
    link = f"{FRONTEND_URL}/accept-invite?token={token}"
    html = _invite_email_html(
        business=branding.get("business_name", "Trust Portal"),
        accent=branding.get("accent_color", "#C5A880"),
        primary=branding.get("primary_color", "#1C252E"),
        client_name=user.get("name") or case.get("client_name", "there"),
        trust_label="Joint Trust" if case.get("trust_type") == "joint" else "Single Trust",
        sender_name=admin.get("name") or "Your trust team",
        link=link,
    )
    await send_email_notification(
        user["email"],
        f"Reminder: your invitation — {branding.get('business_name', 'Trust Portal')}",
        html,
    )
    return {"ok": True, "sent_to": user["email"]}


# ---------- BRANDING ----------
DEFAULT_BRANDING = {
    "business_name": "IGC Trust Portal",
    "primary_color": "#1C252E",
    "accent_color": "#C5A880",
    "logo_url": "",
    "header_image_url": "https://images.unsplash.com/photo-1598139384902-5a8217874645?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NTYxOTF8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBsYXclMjBvZmZpY2UlMjBpbnRlcmlvciUyMG1haG9nYW55JTIwZ2xhc3N8ZW58MHx8fHwxNzc2NTQwNDg3fDA&ixlib=rb-4.1.0&q=85",
}

@api_router.get("/branding")
async def get_branding():
    rec = await db.branding.find_one({"id": "global"}, {"_id": 0})
    if not rec:
        return DEFAULT_BRANDING
    return {**DEFAULT_BRANDING, **rec}

@api_router.put("/branding")
async def update_branding(body: BrandingUpdate, _: dict = Depends(require_admin)):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updates["id"] = "global"
    await db.branding.update_one({"id": "global"}, {"$set": updates}, upsert=True)
    rec = await db.branding.find_one({"id": "global"}, {"_id": 0})
    return {**DEFAULT_BRANDING, **rec}

# ---------- HEALTH ----------
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "trust-portal"}

# ---------- STARTUP ----------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    # Indexes
    await db.users.create_index("email", unique=True)
    await db.users.create_index("id", unique=True)
    await db.trust_cases.create_index("id", unique=True)
    await db.trust_cases.create_index("client_id")
    await db.messages.create_index([("case_id", 1), ("created_at", 1)])
    await db.login_attempts.create_index("identifier")
    await db.password_reset_tokens.create_index("expires_at", expireAfterSeconds=3600)
    await db.invites.create_index("token", unique=True)
    await db.invites.create_index("expires_at", expireAfterSeconds=0)
    await db.questions.create_index([("case_id", 1), ("created_at", 1)])
    await db.questions.create_index("status")

    # Seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "id": new_id(),
            "email": admin_email,
            "name": "Administrator",
            "password_hash": hash_password(admin_password),
            "role": "admin",
            "created_at": now_iso(),
        })
        logger.info(f"Admin seeded: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}})
        logger.info(f"Admin password refreshed: {admin_email}")

    # Init storage
    init_storage()

@app.on_event("shutdown")
async def shutdown():
    client.close()
