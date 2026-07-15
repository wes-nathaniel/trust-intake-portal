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
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, UploadFile, File, Form, Header, Query, Body
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr
from starlette.middleware.cors import CORSMiddleware
import io
from pdf_export import build_intake_pdf
import esign
import sms
import whatsapp
import notify
import whatsapp_commands
import extract_jobs
import page_explanation_jobs
from ai_assistant import answer_question as ai_answer_question
from trust_preview import pdf_bytes_to_preview_pages, pdf_bytes_to_preview_page, page_count as pdf_page_count
import square_service
import doc_explainer
from functools import lru_cache
import threading

# In-process preview page cache — keyed by (draft_storage_path, page_index) → JPEG bytes
# Small bounded cache so a single trust draft doesn't have to re-render every click.
_preview_cache: dict = {}
_preview_cache_order: list = []
_preview_cache_lock = threading.Lock()
_PREVIEW_CACHE_MAX = 200  # ~20MB with ~100KB JPEGs

def _cache_get(key):
    with _preview_cache_lock:
        return _preview_cache.get(key)

def _cache_put(key, value):
    with _preview_cache_lock:
        if key in _preview_cache:
            return
        _preview_cache[key] = value
        _preview_cache_order.append(key)
        while len(_preview_cache_order) > _PREVIEW_CACHE_MAX:
            old = _preview_cache_order.pop(0)
            _preview_cache.pop(old, None)

def _cache_bust_prefix(prefix: str):
    with _preview_cache_lock:
        bad = [k for k in _preview_cache_order if k[0] == prefix]
        for k in bad:
            _preview_cache.pop(k, None)
            try: _preview_cache_order.remove(k)
            except ValueError: pass

# ---------- CONFIG ----------
JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 60 * 12          # 12 hours for client convenience
REFRESH_TTL_DAYS = 14
APP_NAME = os.environ.get("APP_NAME", "trust-portal")
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ADMIN_NOTIFY_EMAIL = os.environ.get("ADMIN_NOTIFY_EMAIL", "support@igcfirm.com").strip().lower()
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
@app.get("/health")
async def health():
    return {"status": "ok"}
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


def delete_object(path: str) -> bool:
    """Best-effort deletion of an object from storage. Returns True on 2xx."""
    key = init_storage()
    if not key:
        return False
    try:
        r = requests.delete(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key}, timeout=30)
        return r.status_code < 400
    except Exception as e:
        logger.warning(f"delete_object({path}) failed: {e}")
        return False

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
      <tr><td style="background:#F6F4F0;padding:16px 20px;text-align:center;color:#64748B;font-size:11px;border-top:1px solid #EBE7DF;">
        <div style="margin-bottom:6px;font-family:Georgia,serif;font-size:12px;color:#1C252E;">Prepared by Iron Gate Consulting · Reviewed through military legal benefits</div>
        <div style="color:#94A3B8;font-size:10px;line-height:1.5;">This trust has been reviewed for accuracy and completeness through my military legal benefits. All documents are prepared using standardized trust templates that are commonly reviewed by military legal professionals. I am not an attorney and do not provide legal advice. Clients may seek independent legal counsel at any time. Trust laws vary by state.</div>
        <div style="margin-top:8px;">&copy; {business} &middot; Secure Trust Intake Portal</div>
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
        "Ready for Client Review": "Your draft trust is ready. Please review it in the secure portal.",
        "Ready for Payment": "Your draft trust is ready. Choose your payment method in the portal to continue.",
        "Pending Payment Verification": "Thank you, your payment has been received. Your application is now pending verification.",
        "Payment Verified": "Your payment has been verified. Your final trust is being prepared and will be unlocked shortly.",
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
    trust_name: Optional[str] = ""
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
IntakePath = Literal["new", "review"]

# Suggested invoice amount (in cents) per intake path. Admin can override.
INTAKE_PATH_PRICE_CENTS = {
    "new": 99700,    # $997.00 — full new-trust drafting
    "review": 29700, # $297.00 — existing trust review + credit repair + 90-day cash settlement
}

class TrustCaseCreate(BaseModel):
    trust_type: TrustType = "single"
    trust_name: Optional[str] = ""
    intake_path: IntakePath = "new"
    client_phone: Optional[str] = Field(default="", max_length=30)

class TrustNameUpdate(BaseModel):
    trust_name: str = Field(min_length=3, max_length=200)

class AcknowledgmentsUpdate(BaseModel):
    state_laws_ack: Optional[bool] = None
    notarization_ack: Optional[bool] = None
    review_completed_ack: Optional[bool] = None
    business_sos_ack: Optional[bool] = None
    disclosure_ack: Optional[bool] = None

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
    ssn: Optional[str] = ""
    authorized: bool = False
    # New: admin-filed flag. Client only authorizes; firm files.
    firm_will_file: bool = True

STATUSES = [
    "Intake Started",
    "Intake In Progress",
    "Waiting on Documents",
    "In Review",
    "Drafting Trust",
    "Ready for Client Review",
    "Ready for Payment",
    "Pending Payment Verification",
    "Payment Verified",
    "Completed",
]

# Ordered phase mapping for auto-advance logic during intake.
_INTAKE_PHASE_ORDER = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review"]


def _has_any_intake_data(case: dict) -> bool:
    return bool(
        (case.get("grantors") or []) or (case.get("trustees") or []) or
        (case.get("successor_trustees") or []) or (case.get("beneficiaries") or []) or
        (case.get("assets") or []) or (case.get("ein") or {}).get("authorized")
    )


def _has_required_intake_docs(case: dict) -> bool:
    docs = (case.get("documents") or [])
    types = {d.get("doc_type") for d in docs if not d.get("is_deleted")}
    base = "government_id" in types and "proof_of_address" in types
    if (case.get("intake_path") or "new") == "review":
        return base and "existing_trust" in types
    return base


def _auto_intake_status(case: dict) -> Optional[str]:
    """Return a forward-only intake-phase status for the given case state,
    or None if the case is past the intake phase. The admin pipeline
    (In Review → Drafting Trust → ... → Completed) is never auto-touched."""
    cur = case.get("status") or "Intake Started"
    if cur not in _INTAKE_PHASE_ORDER:
        return None  # Case is past intake; admin owns the status.

    if (case.get("acknowledgments") or {}).get("review_completed_ack"):
        target = "In Review"
    elif _has_required_intake_docs(case):
        target = "In Review" if (case.get("intake_path") or "new") == "review" else "Waiting on Documents"
        # For "new" path, after all required docs are uploaded but before they click Complete Review,
        # we keep them at Waiting on Documents (they have docs but still owe acknowledgments / final review).
        # If they have ALL data, they probably will click Complete Review themselves.
    elif _has_any_intake_data(case) or (case.get("documents") or []):
        target = "Waiting on Documents" if (case.get("intake_path") or "new") == "review" else "Intake In Progress"
    else:
        target = "Intake Started"

    # Forward-only — never roll back during intake.
    try:
        cur_idx = _INTAKE_PHASE_ORDER.index(cur)
        tgt_idx = _INTAKE_PHASE_ORDER.index(target)
    except ValueError:
        return None
    return target if tgt_idx > cur_idx else None


async def maybe_auto_advance_intake(case_id: str) -> Optional[str]:
    """Refresh case state and, if appropriate, advance the intake-phase status.
    Returns the new status (or None). Also fires the admin status-change email."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        return None
    new_status = _auto_intake_status(case)
    if not new_status or new_status == case.get("status"):
        return None
    prev = case.get("status")
    await update_case(case_id, {"status": new_status})
    case["status"] = new_status
    # Fire status-change notifications (admin email + optional client email)
    try:
        await _notify_status_change(case, prev_status=prev, new_status=new_status, source="auto")
    except Exception as e:
        logger.error(f"auto-advance notify failed: {e}")
    return new_status


async def _notify_status_change(case: dict, prev_status: str, new_status: str, source: str = "admin"):
    """Centralized status-change notifications. Fires:
       - Admin email to ADMIN_NOTIFY_EMAIL for every change
       - Client email for client-visible changes (skipped for Pending/Verified — those have their own emails)
    """
    if new_status == prev_status:
        return
    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    accent = branding.get("accent_color", "#C5A880")
    primary = branding.get("primary_color", "#1C252E")
    case_id = case.get("id")

    # --- ADMIN email (every change) ---
    try:
        admin_link = f"{FRONTEND_URL}/admin/cases/{case_id}"
        admin_inner = f"""
<p style="font-size:18px;margin:0 0 12px 0;font-family:Georgia,serif;">Case status changed: <b>{new_status}</b></p>
<p>Client: <b>{case.get('client_name') or case.get('client_email')}</b> · {case.get('client_email')}{(' · ' + case.get('client_phone')) if case.get('client_phone') else ''}</p>
<p>Previous status: <span style="color:#64748B;">{prev_status or '—'}</span></p>
<p>Case #{case_id[:8].upper()} · {case.get('trust_name') or ''}{' · ' + ('Existing Trust Review' if (case.get('intake_path') or 'new') == 'review' else 'New Trust') }</p>
{_cta(admin_link, "Open case", accent)}
<p style="color:#94A3B8;font-size:12px;">Triggered by: {source}</p>
"""
        admin_html = _email_shell(biz, primary, accent, admin_inner)
        await send_email_notification(
            ADMIN_NOTIFY_EMAIL,
            f"[{biz}] {new_status} — {case.get('client_name') or case.get('client_email')}",
            admin_html,
        )
    except Exception as e:
        logger.error(f"admin status-change email failed: {e}")

    # --- CLIENT email (subset of statuses; others have dedicated emails elsewhere) ---
    CLIENT_AUTO_EMAIL_STATUSES = {
        "Intake In Progress", "Waiting on Documents", "In Review",
        "Drafting Trust", "Ready for Client Review", "Ready for Payment",
    }
    if new_status in CLIENT_AUTO_EMAIL_STATUSES:
        try:
            pending = _compute_pending(case) if new_status == "Waiting on Documents" else None
            portal_link = f"{FRONTEND_URL}/intake/{case_id}?step=documents" if pending else f"{FRONTEND_URL}/portal"
            html = _status_change_email_html(
                business=biz, accent=accent, primary=primary,
                client_name=case.get("client_name") or case.get("client_email"),
                status=new_status,
                case_id=case_id[:8].upper(),
                link=portal_link,
                pending_items=pending,
            )
            await send_email_notification(
                case.get("client_email"),
                f"Status update: {new_status} — {biz}",
                html,
            )
        except Exception as e:
            logger.error(f"client status-change email failed: {e}")

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

async def _log_login_activity(user: dict, request: Request, kind: str):
    """Persist a login/logout activity row and email ADMIN_NOTIFY_EMAIL with
    the client's name, case number, and timestamp. `kind` is "login" or "logout".
    Best-effort: failures are logged but never raised.
    """
    ts_iso = now_iso()
    # Derive client IP from proxy headers (K8s ingress)
    try:
        xff = request.headers.get("x-forwarded-for", "")
        ip = xff.split(",")[0].strip() if xff else (request.headers.get("x-real-ip") or (request.client.host if request.client else ""))
    except Exception:
        ip = ""
    user_agent = (request.headers.get("user-agent") or "")[:300]
    # Persist activity row
    try:
        await db.login_activity.insert_one({
            "user_id": user["id"],
            "email": user.get("email"),
            "name": user.get("name") or "",
            "role": user.get("role", "client"),
            "kind": kind,
            "ip": ip,
            "user_agent": user_agent,
            "ts": ts_iso,
        })
    except Exception as e:
        logger.error(f"login_activity insert failed: {e}")
    # Update last_login_at / last_logout_at on user record (for admin case page)
    try:
        field = "last_login_at" if kind == "login" else "last_logout_at"
        await db.users.update_one({"id": user["id"]}, {"$set": {field: ts_iso}})
    except Exception as e:
        logger.error(f"users.{kind}_at update failed: {e}")
    # Admin-only users don't need a per-login notification email.
    if user.get("role") == "admin":
        return
    # Look up the most-recent (active or any) trust case for this client so we
    # can surface a case number in the email.
    try:
        case = await db.trust_cases.find_one(
            {"client_id": user["id"]},
            {"_id": 0, "id": 1, "trust_name": 1, "status": 1},
            sort=[("created_at", -1)],
        )
        case_label = (
            f"#{case['id'][:8].upper()}" + (f" · {case['trust_name']}" if case.get("trust_name") else "")
        ) if case else "(no active case)"
    except Exception as e:
        logger.error(f"login_activity case lookup failed: {e}")
        case_label = "(case lookup failed)"
    # Email admin
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        client_name = user.get("name") or user.get("email") or "(unnamed client)"
        verb = "logged in" if kind == "login" else "logged out"
        subject = f"Client {verb} — {client_name}"
        inner = f"""
<p style="font-size:18px;margin:0 0 12px 0;font-family:Georgia,serif;">Client {verb}</p>
<p><b>{client_name}</b> &lt;{user.get('email','')}&gt;</p>
<p>Case: <b>{case_label}</b></p>
<p>Time: <b>{ts_iso}</b></p>
<p style="color:#64748B;font-size:12px;">IP {ip or 'unknown'} · {user_agent[:120]}</p>
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(ADMIN_NOTIFY_EMAIL, subject, html)
    except Exception as e:
        logger.error(f"login_activity admin email failed: {e}")


# ---------- AUTH ENDPOINTS ----------
def _first_name(full_name: str) -> str:
    return (full_name or "").strip().split(" ")[0] if (full_name or "").strip() else ""

def public_user(u: dict) -> dict:
    name = u.get("name", "")
    return {
        "id": u["id"],
        "email": u["email"],
        "name": name,
        "first_name": _first_name(name),
        "role": u.get("role", "client"),
        "is_first_login": not bool(u.get("has_logged_in_before")),
        "has_seen_tour": bool(u.get("has_seen_tour")),
    }

@api_router.post("/auth/register")
async def register(body: RegisterReq, request: Request, response: Response):
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
    body_resp = public_user(user)
    # Mark this user as having logged in at least once so subsequent
    # sessions show "Welcome Back, {first name}" instead of the generic
    # first-time welcome.
    await db.users.update_one({"id": user["id"]}, {"$set": {"has_logged_in_before": True, "first_login_at": now_iso()}})
    await _log_login_activity(user, request, "login")
    return body_resp

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
    # Build response BEFORE flipping the flag so the client sees
    # is_first_login=true on the very first login of their account.
    body_resp = public_user(user)
    if not user.get("has_logged_in_before"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"has_logged_in_before": True, "first_login_at": now_iso()}})
    await _log_login_activity(user, request, "login")
    return body_resp

@api_router.post("/auth/logout")
async def logout(request: Request, response: Response, user: dict = Depends(get_current_user)):
    clear_auth_cookies(response)
    await _log_login_activity(user, request, "logout")
    return {"ok": True}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)

@api_router.post("/auth/dismiss-tour")
async def dismiss_tour(user: dict = Depends(get_current_user)):
    if not user.get("has_seen_tour"):
        await db.users.update_one(
            {"id": user["id"]},
            {"$set": {"has_seen_tour": True, "tour_dismissed_at": now_iso()}},
        )
    return {"ok": True, "has_seen_tour": True}

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
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            display_name = user.get("name") or user["email"]
            inner = f"""
<p style="font-size:22px;margin:0 0 12px 0;font-family:Georgia,serif;">Reset your password</p>
<p>Hi {display_name},</p>
<p>We received a request to reset the password for your {biz} account. If this was you, click the button below to choose a new password. The link is valid for <b>one hour</b>.</p>
{_cta(reset_link, "Reset password", accent)}
<p style="color:#64748B;font-size:13px;">If the button doesn't work, copy and paste this URL into your browser:<br/><span style="word-break:break-all;">{reset_link}</span></p>
<p style="color:#64748B;font-size:13px;">If you did not request a password reset, you can safely ignore this email — your password will remain unchanged.</p>
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(body.email, f"Reset your {biz} password", html)
        except Exception as e:
            logger.error(f"Forgot-password email failed: {e}")
            # Fallback plain link so the user is never stranded
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
        "trust_name": (body.trust_name or "").strip(),
        "status": "Intake Started",
        "grantors": [], "trustees": [], "successor_trustees": [],
        "beneficiaries": [], "assets": [],
        "ein": None, "ein_requested": False, "ein_letter": None,
        "documents": [], "admin_notes": [], "branding": {},
        "acknowledgments": {
            "state_laws_ack": False,
            "notarization_ack": False,
            "review_completed_ack": False,
            "business_sos_ack": False,
            "disclosure_ack": False,
        },
        "payment": {"status": "none"},
        "trust_unlocked": False,
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
async def accept_invite(body: AcceptInviteReq, request: Request, response: Response):
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
    # Accept-invite counts as "creating their password" — the welcome screen
    # should show the generic Iron Gate intro the first time. Build response
    # before flipping the flag.
    body_resp = {**public_user(user), "case_id": rec["case_id"]}
    if not user.get("has_logged_in_before"):
        await db.users.update_one({"id": user["id"]}, {"$set": {"has_logged_in_before": True, "first_login_at": now_iso()}})
    await _log_login_activity(user, request, "login")
    return body_resp

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
    # Intake-phase auto-advance. Safe to call unconditionally: helper is a no-op
    # for cases past the intake phase, and refuses to roll status backward.
    # When the caller is *itself* setting `status`, auto-advance won't override it
    # because the helper compares forward indices and is keyed off the freshly
    # written value.
    try:
        if "status" not in updates:
            await maybe_auto_advance_intake(case_id)
    except Exception as e:
        logger.error(f"update_case auto-advance failed: {e}")

@api_router.post("/trust-cases")
async def create_trust_case(body: TrustCaseCreate, user: dict = Depends(get_current_user)):
    intake_path = body.intake_path or "new"
    suggested_amount = INTAKE_PATH_PRICE_CENTS.get(intake_path, INTAKE_PATH_PRICE_CENTS["new"])
    case = {
        "id": new_id(),
        "client_id": user["id"],
        "client_email": user["email"],
        "client_name": user.get("name", ""),
        "client_phone": (body.client_phone or "").strip()[:30],
        "trust_type": body.trust_type,
        "trust_name": (body.trust_name or "").strip(),
        "intake_path": intake_path,
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
        "acknowledgments": {
            "state_laws_ack": False,
            "notarization_ack": False,
            "review_completed_ack": False,
            "business_sos_ack": False,
            "disclosure_ack": False,
        },
        "payment": {"status": "none", "suggested_amount_cents": suggested_amount},
        "trust_unlocked": False,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    await db.trust_cases.insert_one(case)
    case.pop("_id", None)
    # Branded welcome email
    branding = await _branding_doc()
    biz = branding.get("business_name", "our firm")
    if intake_path == "review":
        trust_label = "Existing Trust Review"
    else:
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
    cases = await db.trust_cases.find(
        {"client_id": user["id"], "archived": {"$ne": True}},
        {"_id": 0},
    ).sort("created_at", -1).to_list(100)
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
    payload = body.model_dump()
    payload["firm_will_file"] = True  # Client never self-files
    await update_case(case_id, {"ein": payload})
    return payload


# --- Trust Name ---
@api_router.put("/trust-cases/{case_id}/trust-name")
async def set_trust_name(case_id: str, body: TrustNameUpdate, user: dict = Depends(get_current_user)):
    await get_case(case_id, user)
    await update_case(case_id, {"trust_name": body.trust_name.strip()})
    return {"trust_name": body.trust_name.strip()}


# --- Client Acknowledgments (legal disclosures, notarization, review completed) ---
@api_router.put("/trust-cases/{case_id}/acknowledgments")
async def set_acknowledgments(case_id: str, body: AcknowledgmentsUpdate, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    current = dict(case.get("acknowledgments") or {})
    for k, v in body.model_dump(exclude_none=True).items():
        current[k] = bool(v)
    updates = {"acknowledgments": current}

    # If client marks review completed:
    #   - From intake wizard step 8 (status is intake-y) → flip status to "In Review"
    #     (admin then manually advances to Drafting Trust, etc.)
    #   - From drafted-trust preview (status="Ready for Client Review") → leave status alone;
    #     admin manually advances to "Ready for Payment".
    # Always notify admin (email + SMS) on the transition.
    INTAKE_STATUSES = {"Intake Started", "Intake In Progress", "Waiting on Documents", "In Review"}
    was_review_ack = bool((case.get("acknowledgments") or {}).get("review_completed_ack"))
    now_review_ack = bool(current.get("review_completed_ack"))
    is_client_completing = now_review_ack and not was_review_ack and user.get("role") != "admin"
    cur_status = case.get("status") or ""

    if is_client_completing and cur_status in INTAKE_STATUSES:
        updates["status"] = "In Review"
        review_kind = "intake"
    elif is_client_completing and cur_status == "Ready for Client Review":
        review_kind = "trust_draft"
    else:
        review_kind = None

    await update_case(case_id, updates)

    if is_client_completing:
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            admin_rec = await db.users.find_one({"role": "admin"})
            if admin_rec:
                link = f"{FRONTEND_URL}/admin/cases/{case_id}"
                if review_kind == "intake":
                    headline = "Client completed intake — In Review"
                    body_p = (
                        f"<b>{case.get('client_name') or case.get('client_email')}</b> has completed the intake wizard. "
                        f"Case status has moved to <b>In Review</b>."
                    )
                    cta_label = "Open case in admin"
                elif review_kind == "trust_draft":
                    headline = "Client approved drafted trust — please advance"
                    body_p = (
                        f"<b>{case.get('client_name') or case.get('client_email')}</b> has reviewed the drafted trust and is satisfied. "
                        f"When ready, manually move the status to <b>Ready for Payment</b> and set the amount."
                    )
                    cta_label = "Open case to advance"
                else:
                    headline = "Client completed review"
                    body_p = (
                        f"<b>{case.get('client_name') or case.get('client_email')}</b> marked review complete."
                    )
                    cta_label = "Open case in admin"
                inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">{headline}</p>
<p>{body_p}</p>
<p>Case #{case_id[:8].upper()} · {case.get('trust_name') or ''}</p>
{_cta(link, cta_label, accent)}
"""
                html = _email_shell(biz, primary, accent, inner)
                await send_email_notification(
                    admin_rec["email"],
                    f"{headline} — {case.get('client_name') or case.get('client_email')}",
                    html,
                )
        except Exception as e:
            logger.error(f"Review-completed admin email failed: {e}")

        # --- SMS to admin ---
        try:
            if review_kind == "intake":
                sms_body = (
                    f"IGC: {case.get('client_name') or case.get('client_email')} completed intake. "
                    f"Case #{case_id[:8].upper()} → In Review."
                )
            elif review_kind == "trust_draft":
                sms_body = (
                    f"IGC: {case.get('client_name') or case.get('client_email')} approved drafted trust. "
                    f"Case #{case_id[:8].upper()}. Open admin to advance to Ready for Payment."
                )
            else:
                sms_body = (
                    f"IGC: {case.get('client_name') or case.get('client_email')} completed review. "
                    f"Case #{case_id[:8].upper()}."
                )
            notify.notify_admin(sms_body)
        except Exception as e:
            logger.error(f"Review-completed SMS failed: {e}")

    return current


class ScheduleCallReq(BaseModel):
    note: Optional[str] = None


@api_router.post("/trust-cases/{case_id}/schedule-call")
async def client_schedule_call(case_id: str, body: ScheduleCallReq, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    stamp = now_iso()
    await update_case(case_id, {"call_requested_at": stamp, "call_requested_note": (body.note or "")[:500]})

    # SMS admin
    try:
        notify.notify_admin(
            f"IGC: {case.get('client_name') or case.get('client_email')} requested a call. "
            f"Case #{case_id[:8].upper()}. Call them back from a 954 number within 10 minutes."
        )
    except Exception as e:
        logger.error(f"Schedule-call SMS failed: {e}")

    # Email admin
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        admin_rec = await db.users.find_one({"role": "admin"})
        if admin_rec:
            link = f"{FRONTEND_URL}/admin/cases/{case_id}"
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Client requested a call</p>
<p><b>{case.get('client_name') or case.get('client_email')}</b> is waiting for a callback on case #{case_id[:8].upper()}.</p>
<p style="color:#64748B;">Note: {body.note or '(no note)'}</p>
{_cta(link, "Open case", accent)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(admin_rec["email"],
                                          f"Call requested — {case.get('client_name') or case.get('client_email')}",
                                          html)
    except Exception as e:
        logger.error(f"Schedule-call email failed: {e}")

    return {"ok": True, "message": "Thank you. A team member will call you from a 954 number within 10 minutes."}


class CallbackRequestReq(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    callback_phone: str = Field(min_length=7, max_length=30)
    note: Optional[str] = Field(default=None, max_length=500)


@api_router.post("/trust-cases/{case_id}/callback-request")
async def client_callback_request(case_id: str, body: CallbackRequestReq, user: dict = Depends(get_current_user)):
    """Client-initiated callback request from the 'Need to speak with an agent?' button on the trust preview.
    Stores the request on the case and emails + SMSs the admin. Phone number is never displayed publicly."""
    case = await get_case(case_id, user)
    if user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admins cannot submit a callback request on behalf of a client.")

    stamp = now_iso()
    record = {
        "name": body.name.strip()[:120],
        "callback_phone": body.callback_phone.strip()[:30],
        "note": (body.note or "").strip()[:500],
        "requested_at": stamp,
        "requested_by": user["id"],
    }
    history = list(case.get("callback_requests") or [])
    history.append(record)
    await update_case(case_id, {"callback_requests": history, "last_callback_request_at": stamp})

    # --- Email admin ---
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        admin_rec = await db.users.find_one({"role": "admin"})
        if admin_rec:
            link = f"{FRONTEND_URL}/admin/cases/{case_id}"
            note_html = f"<p style='color:#64748B;'>Note: {record['note']}</p>" if record["note"] else ""
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Client requested a callback</p>
<p><b>{record['name']}</b> requested a callback regarding their trust draft.</p>
<p>Callback number: <b style="font-family:monospace;">{record['callback_phone']}</b></p>
{note_html}
<p style="color:#64748B;">Case #{case_id[:8].upper()} · {case.get('trust_name') or ''} · Account: {case.get('client_email')}</p>
{_cta(link, "Open case in admin", accent)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(
                admin_rec["email"],
                f"Callback requested — {record['name']} ({record['callback_phone']})",
                html,
            )
    except Exception as e:
        logger.error(f"Callback-request email failed: {e}")

    # --- SMS admin ---
    try:
        notify.notify_admin(
            f"IGC: {record['name']} requested a callback at {record['callback_phone']} re trust draft. "
            f"Case #{case_id[:8].upper()}."
        )
    except Exception as e:
        logger.error(f"Callback-request SMS failed: {e}")

    return {"ok": True, "message": "Thank you — your agent will call you back shortly."}

# --- Documents ---
REQUIRED_DOC_TYPES = {"government_id", "proof_of_address"}
ALLOWED_DOC_TYPES = REQUIRED_DOC_TYPES | {
    "existing_trust", "bank_statement", "deed", "title", "insurance_policy",
    "business_document", "supporting_file", "ein_letter", "trust_draft"
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
    # EIN letter may ONLY be uploaded by admin (IRS CP-575 / confirmation letter)
    if doc_type == "ein_letter" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only your trust team can upload the EIN letter.")
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

    # Admin notification when a CLIENT uploads a new document
    if user.get("role") == "client":
        try:
            admin_rec = await db.users.find_one({"role": "admin"})
            if admin_rec:
                branding = await _branding_doc()
                biz = branding.get("business_name", "Trust Portal")
                accent = branding.get("accent_color", "#C5A880")
                primary = branding.get("primary_color", "#1C252E")
                link = f"{FRONTEND_URL}/admin/cases/{case_id}"
                label = _doc_label(doc_type)
                inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">New document uploaded</p>
<p><b>{case.get('client_name') or case.get('client_email')}</b> uploaded a new document to their case.</p>
<p style="color:#64748B;margin:0 0 8px 0;">
  Type: <b>{label}</b><br>
  File: {file.filename or 'file'}<br>
  Case: #{case_id[:8].upper()}
</p>
{_cta(link, "Open case in admin", accent)}
"""
                html = _email_shell(biz, primary, accent, inner)
                await send_email_notification(
                    admin_rec["email"],
                    f"New document: {label} — {case.get('client_name') or case.get('client_email')}",
                    html,
                )
        except Exception as e:
            logger.error(f"Doc-upload admin email failed: {e}")

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
        notify_result = notify.notify_admin(sms_body)
        if not (notify_result.get("sms") or notify_result.get("whatsapp")):
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
STORAGE_HEAVY_CASE_BYTES = 100 * 1024 * 1024  # per-case threshold used by the storage rollup


@api_router.get("/admin/storage-rollup")
async def admin_storage_rollup(_: dict = Depends(require_admin)):
    """Aggregate storage usage across ALL non-archived cases. Covers three
    sources: AI Explainer docs (current + archived versions), client-uploaded
    documents (IDs, bills, etc.), and the Trust Draft PDF. Returns totals +
    a small "top offenders" list so admin can plan trim sweeps."""
    cursor = db.trust_cases.find(
        {"archived": {"$ne": True}},
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "trust_name": 1,
         "admin_documents": 1, "documents": 1, "trust_draft": 1},
    )
    total_cases = 0
    cases_with_docs = 0
    # AI Explainer
    doc_count = 0
    version_count = 0
    current_bytes = 0
    version_bytes = 0
    # Client uploads
    client_doc_count = 0
    client_bytes = 0
    # Trust drafts
    draft_count = 0
    draft_bytes = 0
    per_case = []
    async for c in cursor:
        total_cases += 1
        admin_docs = c.get("admin_documents") or []
        client_docs = [d for d in (c.get("documents") or []) if not d.get("is_deleted")]
        draft = c.get("trust_draft") or {}
        draft_size = int(draft.get("size") or 0) if draft.get("storage_path") else 0

        # AI Explainer aggregates
        case_ai_current = 0
        case_ai_versions = 0
        case_ai_version_count = 0
        for d in admin_docs:
            doc_count += 1
            case_ai_current += int(d.get("size") or 0)
            for v in (d.get("versions") or []):
                case_ai_version_count += 1
                case_ai_versions += int(v.get("size") or 0)
        # Client uploads aggregate
        case_client_bytes = sum(int(d.get("size") or 0) for d in client_docs)

        if not admin_docs and not client_docs and not draft_size:
            continue
        cases_with_docs += 1
        current_bytes += case_ai_current
        version_bytes += case_ai_versions
        version_count += case_ai_version_count
        client_doc_count += len(client_docs)
        client_bytes += case_client_bytes
        if draft_size:
            draft_count += 1
            draft_bytes += draft_size

        case_total = case_ai_current + case_ai_versions + case_client_bytes + draft_size
        per_case.append({
            "case_id": c["id"],
            "client_name": c.get("client_name") or "",
            "client_email": c.get("client_email") or "",
            "trust_name": c.get("trust_name") or "",
            # AI explainer
            "doc_count": len(admin_docs),
            "version_count": case_ai_version_count,
            "ai_bytes": case_ai_current + case_ai_versions,
            # Client uploads
            "client_doc_count": len(client_docs),
            "client_bytes": case_client_bytes,
            # Trust draft
            "trust_draft_bytes": draft_size,
            # Grand total
            "total_bytes": case_total,
        })
    per_case.sort(key=lambda x: x["total_bytes"], reverse=True)
    heavy = [x for x in per_case if x["total_bytes"] >= STORAGE_HEAVY_CASE_BYTES]
    return {
        "total_cases": total_cases,
        "cases_with_docs": cases_with_docs,
        # AI Explainer
        "doc_count": doc_count,
        "version_count": version_count,
        "current_bytes": current_bytes,
        "version_bytes": version_bytes,
        "ai_bytes": current_bytes + version_bytes,
        # Client uploads
        "client_doc_count": client_doc_count,
        "client_bytes": client_bytes,
        # Trust drafts
        "draft_count": draft_count,
        "draft_bytes": draft_bytes,
        # Grand totals
        "total_bytes": current_bytes + version_bytes + client_bytes + draft_bytes,
        "heavy_threshold_bytes": STORAGE_HEAVY_CASE_BYTES,
        "heavy_case_count": len(heavy),
        "top_cases": per_case[:10],
    }


@api_router.get("/admin/trust-cases")
async def admin_list_cases(
    q: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    include_archived: bool = Query(False),
    _: dict = Depends(require_admin),
):
    flt = {}
    if not include_archived:
        flt["archived"] = {"$ne": True}
    if status:
        flt["status"] = status
    if q:
        flt["$or"] = [
            {"client_name": {"$regex": q, "$options": "i"}},
            {"client_email": {"$regex": q, "$options": "i"}},
            {"trust_name": {"$regex": q, "$options": "i"}},
        ]
    cases = await db.trust_cases.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return cases


@api_router.get("/admin/trust-cases.csv")
async def admin_export_cases_csv(
    include_archived: bool = Query(False),
    since: Optional[str] = Query(None, description="Inclusive lower bound on updated_at — YYYY-MM-DD"),
    until: Optional[str] = Query(None, description="Inclusive upper bound on updated_at — YYYY-MM-DD"),
    _: dict = Depends(require_admin),
):
    """One-click CSV export for monthly reports / outbound call lists.
    Optional ?since=YYYY-MM-DD&until=YYYY-MM-DD filters by updated_at."""
    import csv as _csv
    from datetime import datetime as _dt
    flt: dict = {} if include_archived else {"archived": {"$ne": True}}

    # Parse date range (inclusive). Storage is ISO-8601 strings, so a lexical
    # string range works for YYYY-MM-DD prefixes and full timestamps alike.
    if since or until:
        rng = {}
        if since:
            try:
                _dt.strptime(since, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'since' date — use YYYY-MM-DD")
            rng["$gte"] = since
        if until:
            try:
                _dt.strptime(until, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'until' date — use YYYY-MM-DD")
            # Make the upper bound inclusive of the whole day.
            rng["$lte"] = f"{until}T23:59:59.999999+00:00"
        flt["updated_at"] = rng

    cases = await db.trust_cases.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(2000)
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([
        "case_id", "client_name", "client_email", "client_phone",
        "trust_name", "intake_path", "trust_type", "status",
        "amount_usd", "payment_status", "credit_repair_released",
        "credit_repair_released_at", "created_at", "updated_at",
    ])
    for c in cases:
        p = c.get("payment") or {}
        amt_cents = p.get("amount_cents")
        amt_usd = f"{amt_cents/100:.2f}" if amt_cents else ""
        w.writerow([
            c.get("id", ""),
            c.get("client_name", ""),
            c.get("client_email", ""),
            c.get("client_phone", ""),
            c.get("trust_name", ""),
            c.get("intake_path", "new"),
            c.get("trust_type", ""),
            c.get("status", ""),
            amt_usd,
            p.get("status", ""),
            "yes" if c.get("credit_repair_released") else "no",
            c.get("credit_repair_released_at", ""),
            c.get("created_at", ""),
            c.get("updated_at", ""),
        ])
    suffix = ""
    if since or until:
        suffix = f"_{since or 'start'}_to_{until or 'now'}"
    fname = f"trust-cases-{datetime.now(timezone.utc).strftime('%Y%m%d')}{suffix}.csv"
    return StreamingResponse(
        io.BytesIO(buf.getvalue().encode("utf-8")),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@api_router.post("/admin/trust-cases/{case_id}/archive")
async def admin_archive_case(case_id: str, admin: dict = Depends(require_admin)):
    """Soft-archive a case: hides it from the default admin list and the client's portal.
    Reversible via /unarchive."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await update_case(case_id, {
        "archived": True,
        "archived_at": now_iso(),
        "archived_by": admin["id"],
    })
    return {"ok": True, "archived": True}


@api_router.post("/admin/trust-cases/{case_id}/unarchive")
async def admin_unarchive_case(case_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await update_case(case_id, {
        "archived": False,
        "archived_at": None,
        "archived_by": None,
    })
    return {"ok": True, "archived": False}


@api_router.delete("/admin/trust-cases/{case_id}")
async def admin_delete_case(
    case_id: str,
    delete_user: bool = Query(False, description="Also delete the client user + all their cases"),
    admin: dict = Depends(require_admin),
):
    """Permanently delete a case and all related records (messages, questions, invites,
    square events, object storage documents). Optionally also delete the client user account.
    This action is irreversible."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    client_id = case.get("client_id")
    client_email = case.get("client_email")

    # Try to delete uploaded documents from object storage (best-effort)
    removed_paths = 0
    try:
        for doc in (case.get("documents") or []):
            p = doc.get("storage_path")
            if p:
                try:
                    delete_object(p)
                    removed_paths += 1
                except Exception as e:
                    logger.warning(f"Failed to delete object {p}: {e}")
        # EIN letter
        ein = case.get("ein_letter") or {}
        if ein.get("storage_path"):
            try: delete_object(ein["storage_path"]); removed_paths += 1
            except Exception as e: logger.warning(f"delete ein_letter: {e}")
        # Trust draft
        draft = case.get("trust_draft") or {}
        if draft.get("storage_path"):
            try: delete_object(draft["storage_path"]); removed_paths += 1
            except Exception as e: logger.warning(f"delete trust_draft: {e}")
    except Exception as e:
        logger.error(f"Storage cleanup error for case {case_id}: {e}")

    # Delete related records
    deleted_counts = {}
    deleted_counts["case"] = (await db.trust_cases.delete_one({"id": case_id})).deleted_count
    deleted_counts["messages"] = (await db.messages.delete_many({"case_id": case_id})).deleted_count
    deleted_counts["questions"] = (await db.questions.delete_many({"case_id": case_id})).deleted_count
    deleted_counts["invites"] = (await db.invites.delete_many({"case_id": case_id})).deleted_count
    deleted_counts["square_events"] = 0  # leave audit trail
    if client_id:
        deleted_counts["notifications"] = (await db.notifications.delete_many({"case_id": case_id})).deleted_count

    # Optionally delete the client user (if they have no other cases)
    user_deleted = False
    if delete_user and client_id:
        other = await db.trust_cases.count_documents({"client_id": client_id})
        if other == 0:
            ures = await db.users.delete_one({"id": client_id, "role": "client"})
            user_deleted = bool(ures.deleted_count)

    logger.info("Admin %s deleted case %s (client %s): %s, objects=%d, user_deleted=%s",
                admin["id"], case_id, client_email, deleted_counts, removed_paths, user_deleted)
    return {
        "ok": True,
        "deleted": deleted_counts,
        "storage_objects_deleted": removed_paths,
        "user_deleted": user_deleted,
        "client_email": client_email,
    }

# ---------- Bulk archive / delete (routes must appear before /{case_id} for FastAPI matching) ----------
class BulkCaseIds(BaseModel):
    case_ids: List[str] = Field(min_length=1, max_length=500)


@api_router.post("/admin/trust-cases/bulk-archive")
async def admin_bulk_archive(body: BulkCaseIds, admin: dict = Depends(require_admin)):
    found = await db.trust_cases.find({"id": {"$in": body.case_ids}}, {"_id": 0, "id": 1}).to_list(1000)
    found_ids = [c["id"] for c in found]
    missing = [cid for cid in body.case_ids if cid not in found_ids]
    if found_ids:
        await db.trust_cases.update_many(
            {"id": {"$in": found_ids}},
            {"$set": {
                "archived": True, "archived_at": now_iso(),
                "archived_by": admin["id"], "updated_at": now_iso(),
            }},
        )
    logger.info("Admin %s bulk-archived %d cases (%d missing)", admin["id"], len(found_ids), len(missing))
    return {"ok": True, "archived": len(found_ids), "archived_ids": found_ids, "missing": missing}


@api_router.post("/admin/trust-cases/bulk-unarchive")
async def admin_bulk_unarchive(body: BulkCaseIds, _: dict = Depends(require_admin)):
    r = await db.trust_cases.update_many(
        {"id": {"$in": body.case_ids}},
        {"$set": {"archived": False, "archived_at": None, "archived_by": None, "updated_at": now_iso()}},
    )
    return {"ok": True, "restored": r.modified_count}


@api_router.post("/admin/trust-cases/bulk-delete")
async def admin_bulk_delete(
    body: BulkCaseIds,
    delete_user: bool = Query(False),
    admin: dict = Depends(require_admin),
):
    """Permanently delete many cases + their related records. Irreversible."""
    cases = await db.trust_cases.find({"id": {"$in": body.case_ids}}, {"_id": 0}).to_list(1000)
    found_ids = [c["id"] for c in cases]
    missing = [cid for cid in body.case_ids if cid not in found_ids]

    total_storage = 0
    total_messages = total_questions = total_invites = total_notifs = 0
    client_ids_touched = set()

    for case in cases:
        cid = case["id"]
        try:
            for doc in (case.get("documents") or []):
                if doc.get("storage_path") and delete_object(doc["storage_path"]): total_storage += 1
            ein = case.get("ein_letter") or {}
            if ein.get("storage_path") and delete_object(ein["storage_path"]): total_storage += 1
            draft = case.get("trust_draft") or {}
            if draft.get("storage_path") and delete_object(draft["storage_path"]): total_storage += 1
        except Exception as e:
            logger.warning(f"Storage cleanup error for case {cid}: {e}")

        if case.get("client_id"):
            client_ids_touched.add(case["client_id"])

        try:
            total_messages += (await db.messages.delete_many({"case_id": cid})).deleted_count
            total_questions += (await db.questions.delete_many({"case_id": cid})).deleted_count
            total_invites += (await db.invites.delete_many({"case_id": cid})).deleted_count
            total_notifs += (await db.notifications.delete_many({"case_id": cid})).deleted_count
        except Exception as e:
            logger.warning(f"Related cleanup error for case {cid}: {e}")

    deleted_cases = 0
    if found_ids:
        r = await db.trust_cases.delete_many({"id": {"$in": found_ids}})
        deleted_cases = r.deleted_count

    users_deleted = 0
    if delete_user and client_ids_touched:
        for uid in client_ids_touched:
            remaining = await db.trust_cases.count_documents({"client_id": uid})
            if remaining == 0:
                ur = await db.users.delete_one({"id": uid, "role": "client"})
                users_deleted += (ur.deleted_count or 0)

    logger.info(
        "Admin %s BULK-DELETED %d cases (missing=%d, storage=%d, msgs=%d, qs=%d, invites=%d, notifs=%d, users=%d)",
        admin["id"], deleted_cases, len(missing), total_storage,
        total_messages, total_questions, total_invites, total_notifs, users_deleted,
    )
    return {
        "ok": True,
        "deleted_cases": deleted_cases,
        "deleted_case_ids": found_ids,
        "missing": missing,
        "storage_objects_deleted": total_storage,
        "messages_deleted": total_messages,
        "questions_deleted": total_questions,
        "invites_deleted": total_invites,
        "notifications_deleted": total_notifs,
        "users_deleted": users_deleted,
    }




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
    # Attach the client's last login/logout timestamps so admin can see when
    # the client last accessed the portal.
    try:
        client_user = await db.users.find_one(
            {"id": case.get("client_id")},
            {"_id": 0, "last_login_at": 1, "last_logout_at": 1},
        )
        case["client_last_login_at"] = (client_user or {}).get("last_login_at")
        case["client_last_logout_at"] = (client_user or {}).get("last_logout_at")
    except Exception:
        case["client_last_login_at"] = None
        case["client_last_logout_at"] = None
    return _attach_pending(case)

@api_router.get("/admin/trust-cases/{case_id}/login-activity")
async def admin_case_login_activity(case_id: str, limit: int = 5, _: dict = Depends(require_admin)):
    """Return the most-recent login/logout rows for the client on this case."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0, "client_id": 1})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    limit = max(1, min(int(limit or 5), 50))
    rows = await db.login_activity.find(
        {"user_id": case.get("client_id")},
        {"_id": 0, "kind": 1, "ts": 1, "ip": 1, "user_agent": 1},
    ).sort("ts", -1).to_list(limit)
    return {"rows": rows}

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

    case["status"] = body.status

    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    accent = branding.get("accent_color", "#C5A880")
    primary = branding.get("primary_color", "#1C252E")

    # Centralized admin + client status-change notification (handles every status)
    try:
        await _notify_status_change(case, prev_status=prev_status, new_status=body.status, source="admin")
    except Exception as e:
        logger.error(f"admin update_status notify failed: {e}")

    # Special "Completed" client message (replaces the generic email)
    if body.status == "Completed" and prev_status != "Completed":
        try:
            portal_link = f"{FRONTEND_URL}/portal"
            inner = f"""
<p style="font-size:22px;margin:0 0 14px 0;font-family:Georgia,serif;">Congratulations — your trust is complete.</p>
<p>A member of our team will call you within 10 minutes. Please log back into your portal to access your complimentary credit review.</p>
{_cta(portal_link, "Open your portal", accent)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(
                case.get("client_email"),
                f"Your trust is complete — {biz}",
                html,
            )
        except Exception as e:
            logger.error(f"Completion email failed: {e}")
        # SMS admin so they can make the promised "within 10 minutes" call
        try:
            notify.notify_admin(
                f"IGC: Case #{case_id[:8].upper()} marked Completed for "
                f"{case.get('client_name') or case.get('client_email')}. "
                f"Promised call within 10 minutes."
            )
        except Exception as e:
            logger.error(f"completion SMS failed: {e}")
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


# ---------- CREDIT REPAIR RELEASE (admin-gated, portal-only) ----------

CREDIT_REPAIR_URL = (
    "https://forms.zohopublic.com/WBCGROUP/form/"
    "ConsumerLawAttorneyReferralNetworkIGCFIRM/formperma/"
    "qS39YSrNGsYAh6hDKZS1mu1Ys1SF2SP0C-Vea2l2ah8"
)


def _split_client_name(case: dict) -> tuple[str, str]:
    """Best-effort first/last from client_name or grantors[0].full_legal_name."""
    name = (case.get("client_name") or "").strip()
    if not name:
        g0 = (case.get("grantors") or [{}])[0] or {}
        name = (g0.get("full_legal_name") or "").strip()
    if not name:
        return ("", "")
    parts = name.split()
    if len(parts) == 1:
        return (parts[0], "")
    return (parts[0], " ".join(parts[1:]))


@api_router.post("/admin/trust-cases/{case_id}/release-credit-repair")
async def admin_release_credit_repair(case_id: str, admin: dict = Depends(require_admin)):
    """Admin-gated unlock. After admin has manually called the client and confirmed
    everything, this flips a boolean that surfaces the 'Start Your Free Credit Review'
    button inside the client's portal. The Zoho URL is never emailed; it is only
    returned via /credit-repair-link, behind the client's session.

    Maintains an append-only `credit_repair_log` of every release/revoke action."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    if case.get("credit_repair_released"):
        return {"ok": True, "already_released": True}
    stamp = now_iso()
    log = list(case.get("credit_repair_log") or [])
    log.append({
        "action": "released",
        "at": stamp,
        "admin_id": admin["id"],
        "admin_email": admin.get("email"),
        "admin_name": admin.get("name") or admin.get("email"),
    })
    await update_case(case_id, {
        "credit_repair_released": True,
        "credit_repair_released_at": stamp,
        "credit_repair_released_by": admin["id"],
        "credit_repair_log": log,
    })
    return {"ok": True, "released_at": stamp}


@api_router.post("/admin/trust-cases/{case_id}/revoke-credit-repair")
async def admin_revoke_credit_repair(case_id: str, admin: dict = Depends(require_admin)):
    """Reverses release_credit_repair in case it was clicked by mistake."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    stamp = now_iso()
    log = list(case.get("credit_repair_log") or [])
    log.append({
        "action": "revoked",
        "at": stamp,
        "admin_id": admin["id"],
        "admin_email": admin.get("email"),
        "admin_name": admin.get("name") or admin.get("email"),
    })
    await update_case(case_id, {
        "credit_repair_released": False,
        "credit_repair_log": log,
    })
    return {"ok": True, "revoked_at": stamp}


@api_router.get("/trust-cases/{case_id}/credit-repair-link")
async def client_credit_repair_link(case_id: str, user: dict = Depends(get_current_user)):
    """Returns the Zoho referral URL with ONLY first/last name pre-populated.
    Gated on: case ownership AND admin having released access. Never exposed
    by email or SMS — only behind the client's portal session."""
    case = await get_case(case_id, user)
    if not case.get("credit_repair_released"):
        raise HTTPException(status_code=403, detail="Credit repair has not been released for this case yet.")
    first, last = _split_client_name(case)
    # Zoho form prefill uses ?FirstName=&LastName= encoded params.
    from urllib.parse import urlencode
    qs = urlencode({"FirstName": first, "LastName": last})
    return {"url": f"{CREDIT_REPAIR_URL}?{qs}"}



# ---------- TRUST DRAFT PREVIEW (locked, page-by-page, watermarked) ----------
# Admin uploads the draft trust PDF. Clients can view page-by-page via image
# endpoints (low-res, watermarked). Raw PDF is NOT served to clients.

class TrustSection(BaseModel):
    """A single article: trust text on the left + matching explainer on the right.
    New canonical fields per the client-facing spec (article_number, article_title,
    article_text, explainer_text). Legacy aliases (title, trust_html, explainer_html)
    are kept so existing records continue to render without a migration."""
    # New canonical schema
    article_number: Optional[str] = Field(default="", max_length=20)
    article_title: Optional[str] = Field(default="", max_length=200)
    article_text: Optional[str] = Field(default="", max_length=50_000)
    explainer_text: Optional[str] = Field(default="", max_length=20_000)
    # Legacy aliases (kept in DB alongside the new fields)
    title: Optional[str] = Field(default="", max_length=200)
    trust_html: Optional[str] = Field(default="", max_length=50_000)
    explainer_html: Optional[str] = Field(default="", max_length=20_000)
    id: Optional[str] = None

    def normalized(self) -> dict:
        """Populate legacy aliases from canonical fields and vice-versa so both
        readers see consistent data. Applied on save so DB rows are self-healing."""
        num = (self.article_number or "").strip()
        atitle = (self.article_title or "").strip()
        atext = (self.article_text or self.trust_html or "").strip()
        etext = (self.explainer_text or self.explainer_html or "").strip()
        # Composite title for legacy consumers
        prefix = "" if num.lower() in {"", "preamble"} else f"Article {num} — "
        composite = self.title or f"{prefix}{atitle}".strip(" —")
        return {
            "id": self.id,
            "article_number": num,
            "article_title": atitle,
            "article_text": atext,
            "explainer_text": etext,
            "title": composite,
            "trust_html": atext,
            "explainer_html": etext,
        }


class TrustSectionsBody(BaseModel):
    sections: list[TrustSection] = Field(default_factory=list, max_length=60)


@api_router.put("/admin/trust-cases/{case_id}/trust-sections")
async def admin_set_trust_sections(case_id: str, body: TrustSectionsBody, admin: dict = Depends(require_admin)):
    """Save the structured two-panel trust viewer content. Article order is
    preserved. Empty array clears the viewer and reverts the client to the
    legacy PDF viewer (if a draft PDF is still on the case)."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    payload = [s.normalized() for s in body.sections]
    updates: dict = {
        "trust_sections": payload,
        "trust_sections_updated_at": now_iso(),
        "trust_sections_updated_by": admin["id"],
    }
    # NOTE: Status is intentionally NOT auto-advanced here. Saving trust
    # content is an admin action; the status must only move forward via a
    # real client action (or an explicit admin status change). Admin can use
    # the Status dropdown on the case page to move to "Ready for Client Review".
    await update_case(case_id, updates)
    return {"ok": True, "count": len(payload), "status": case.get("status")}


@api_router.post("/admin/trust-cases/{case_id}/trust-sections/auto-extract", status_code=202)
async def admin_auto_extract_trust_sections(case_id: str, response: Response,
                                            admin: dict = Depends(require_admin)):
    """Kick off a BACKGROUND Claude Sonnet 4.5 extraction on the already-uploaded
    trust_draft PDF. Returns 202 immediately with a task id. Poll
    `GET /admin/trust-cases/{case_id}/trust-sections/extract-status` every
    5-10 seconds until status='completed' (or 'failed').

    Sections are written to `trust_sections_draft[]` (NOT the live
    `trust_sections[]`) so the admin can review and edit before publishing."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_draft") or {}
    storage_path = draft.get("storage_path")
    if not storage_path:
        raise HTTPException(status_code=400, detail="No trust draft PDF uploaded yet.")
    try:
        data, _ct = get_object(storage_path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read PDF from storage: {e}")

    job = await extract_jobs.start_extract_job(
        case_id=case_id,
        pdf_bytes=data,
        filename=draft.get("filename") or "trust.pdf",
        admin_id=admin["id"],
        db=db,
        update_case_fn=update_case,
    )
    response.status_code = 202
    return {
        "ok": True,
        "task_id": job["task_id"],
        "status": job["status"],
        "already_running": job.get("already_running", False),
    }


@api_router.get("/admin/trust-cases/{case_id}/trust-sections/extract-status")
async def admin_auto_extract_status(case_id: str, _: dict = Depends(require_admin)):
    """Poll this every 5-10 seconds after firing auto-extract. Returns the
    current job state — one of `pending`, `completed`, `failed`, or `error`.

    Wrapped in a broad try/except so a transient DB or module fault still
    returns a valid JSON envelope instead of a 5xx (the frontend polls this
    every few seconds and can't cope with hard failures)."""
    try:
        case = await db.trust_cases.find_one(
            {"id": case_id},
            {"_id": 0, "id": 1, "trust_extract_job": 1, "trust_sections_draft": 1},
        )
        if case is None:
            raise HTTPException(status_code=404, detail="Case not found")
        job = await extract_jobs.get_status(case_id, db)
        # Watchdog: if a job has been pending >5 minutes with no progress,
        # treat it as failed here (defensive — the runner should also cover this).
        if job and job.get("status") == "pending":
            job = await extract_jobs.mark_failed_if_stuck(
                case_id=case_id,
                db=db,
                update_case_fn=update_case,
                max_age_seconds=300,
            ) or job
        if not job:
            return {
                "status": "idle",
                "sections_count": 0,
                "message": "No extraction has been run for this case yet.",
            }
        draft_len = len(case.get("trust_sections_draft") or [])
        return {
            "task_id": job.get("task_id"),
            "status": job.get("status"),
            "sections_count": max(int(job.get("sections_count") or 0), draft_len),
            "batches_done": job.get("batches_done") or 0,
            "batches_total": job.get("batches_total") or 0,
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "error": job.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"extract-status endpoint failed for {case_id}: {e}")
        return {
            "status": "error",
            "error": str(e)[:300],
            "sections_count": 0,
        }


@api_router.put("/admin/trust-cases/{case_id}/trust-sections/draft")
async def admin_update_draft_sections(case_id: str, body: TrustSectionsBody, admin: dict = Depends(require_admin)):
    """Save admin edits to the pending draft (before publishing to client)."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not (case.get("trust_sections_draft") or []):
        raise HTTPException(status_code=400, detail="No draft to update. Run auto-extract first.")
    payload = [s.normalized() for s in body.sections]
    await update_case(case_id, {
        "trust_sections_draft": payload,
        "trust_sections_draft_updated_at": now_iso(),
        "trust_sections_draft_updated_by": admin["id"],
    })
    return {"ok": True, "count": len(payload), "draft": True}


@api_router.post("/admin/trust-cases/{case_id}/trust-sections/publish-draft")
async def admin_publish_trust_sections_draft(case_id: str, admin: dict = Depends(require_admin)):
    """Promote `trust_sections_draft[]` → `trust_sections[]` so the client sees
    the reviewed content. Removes the draft field after promotion."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_sections_draft") or []
    if not draft:
        raise HTTPException(status_code=400, detail="No draft to publish.")
    await update_case(case_id, {
        "trust_sections": draft,
        "trust_sections_updated_at": now_iso(),
        "trust_sections_updated_by": admin["id"],
        "trust_sections_auto_extracted": True,
        "trust_sections_draft": [],
        "trust_sections_draft_published_at": now_iso(),
    })
    return {"ok": True, "count": len(draft), "published": True}


@api_router.delete("/admin/trust-cases/{case_id}/trust-sections/draft")
async def admin_discard_trust_sections_draft(case_id: str, _: dict = Depends(require_admin)):
    """Discard the pending draft without publishing."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    await update_case(case_id, {
        "trust_sections_draft": [],
        "trust_sections_draft_discarded_at": now_iso(),
    })
    return {"ok": True, "discarded": True}


@api_router.post("/admin/trust-cases/{case_id}/trust-draft")
async def admin_upload_trust_draft(case_id: str,
                                   file: UploadFile = File(...),
                                   admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted for trust drafts")
    try:
        num_pages = pdf_page_count(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse PDF: {e}")

    # Store the raw PDF privately (admin-only access)
    path = f"{APP_NAME}/trust-drafts/{case_id}/{new_id()}.pdf"
    put_object(path, data, "application/pdf")

    draft = {
        "id": new_id(),
        "storage_path": path,
        "filename": file.filename,
        "size": len(data),
        "pages": num_pages,
        "uploaded_by": admin["id"],
        "uploaded_at": now_iso(),
        "version": int((case.get("trust_draft") or {}).get("version", 0)) + 1,
    }
    updates = {"trust_draft": draft}
    # NOTE: Status is intentionally NOT auto-advanced here. Uploading a draft
    # is an admin action; the status must only move forward via a real client
    # action or an explicit admin status change.
    # Persist the draft record BEFORE kicking off any background jobs.
    await update_case(case_id, updates)
    # Bust any cached pages from a previous draft version
    try:
        old_path = (case.get("trust_draft") or {}).get("storage_path")
        if old_path:
            _cache_bust_prefix(old_path)
    except Exception:
        pass

    # AUTO-GENERATE page-by-page plain-English explanations — runs as a
    # BACKGROUND task so the upload response is instant. Personalized to the
    # client's intake (names, share percentages, assets, state). The old
    # article-extract path is no longer wired here — page-by-page is the
    # canonical explainer surface now.
    try:
        await page_explanation_jobs.start_page_explain_job(
            case_id=case_id,
            pdf_bytes=data,
            case_context=_build_case_context(case),
            admin_id=admin["id"],
            db=db,
            update_case_fn=update_case,
        )
        logger.info(f"trust_page_job kicked off for case {case_id}")
    except Exception as e:
        logger.error(f"Failed to schedule page-explanation job for case {case_id}: {e}")

    # Notify client: trust ready for review — fired as a background task so
    # the upload response returns immediately (Resend can take 20-30s from
    # some networks; that latency should not block the admin's UI).
    async def _send_trust_ready_email():
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name", "Trust Portal")
            accent = branding.get("accent_color", "#C5A880")
            primary = branding.get("primary_color", "#1C252E")
            link = f"{FRONTEND_URL}/portal/trust-preview/{case_id}"
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Your trust is ready for review.</p>
<p>Your draft trust for <b>{case.get('trust_name') or 'your case'}</b> is ready to review in the secure portal.</p>
<p style="color:#64748B;font-size:13px;">The draft is watermarked and cannot be printed or downloaded until payment is received. You can schedule a Zoom review call or complete your review inside the portal.</p>
{_cta(link, "Review your trust", accent)}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(
                case.get("client_email"),
                f"Your trust is ready for review — {biz}",
                html,
            )
        except Exception as e:
            logger.error(f"Trust-ready email failed: {e}")

    asyncio.create_task(_send_trust_ready_email())

    return {"ok": True, **draft}


@api_router.delete("/admin/trust-cases/{case_id}/trust-draft")
async def admin_delete_trust_draft(case_id: str, admin: dict = Depends(require_admin)):
    """Fully remove the uploaded trust draft PDF from a case.

    Also clears any auto-extracted `trust_sections` / `trust_sections_draft`
    that were derived from this PDF so the case starts clean. Any linked
    admin_documents that were "Import from Trust Draft" copies are marked
    orphaned (kept, so their AI explanations survive, but flagged)."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_draft") or {}
    if not draft:
        raise HTTPException(status_code=400, detail="No trust draft on file for this case")

    old_path = draft.get("storage_path")
    # Delete the underlying object (best-effort)
    if old_path:
        try:
            delete_object(old_path)
        except Exception as e:
            logger.warning(f"delete trust_draft object failed: {e}")
        try:
            _cache_bust_prefix(old_path)
        except Exception:
            pass

    # Mark any admin_documents that referenced this draft as orphaned so the
    # UI can indicate the source PDF is gone (their storage is untouched).
    admin_docs = [dict(d) for d in (case.get("admin_documents") or [])]
    for d in admin_docs:
        if d.get("source") == "trust_draft" and d.get("source_storage_path") == old_path:
            d["source_orphaned"] = True

    updates = {
        "trust_draft": None,
        "trust_draft_deleted_at": now_iso(),
        "trust_draft_deleted_by": admin["id"],
        # Auto-extracted sections were derived from this PDF — clear them
        "trust_sections": [],
        "trust_sections_draft": [],
        "admin_documents": admin_docs,
    }
    await update_case(case_id, updates)
    return {"ok": True, "deleted": True}
ALLOWED_EXPLAINER_EXTS = {"pdf", "docx", "doc", "txt", "jpg", "jpeg", "png"}
MAX_EXPLAINER_SIZE = 25 * 1024 * 1024  # 25 MB


def _explainer_ext(filename: str) -> str:
    return (filename.rsplit(".", 1)[-1] if "." in (filename or "") else "").lower()


def _find_admin_doc(case: dict, doc_id: str) -> Optional[dict]:
    for d in (case.get("admin_documents") or []):
        if d.get("id") == doc_id and not d.get("is_deleted"):
            return d
    return None


def _build_case_context(case: dict) -> dict:
    """Assemble a dict of everything Claude needs to personalize the client's
    plain-English trust explanation: full names, roles, share percentages,
    assets. Called by the import-trust-draft and regenerate paths."""
    if not case:
        return {}
    return {
        "client_name": case.get("client_name") or case.get("client_email") or "",
        "client_email": case.get("client_email") or "",
        "trust_name": case.get("trust_name") or "",
        "trust_type": case.get("trust_type") or "",
        "grantors": case.get("grantors") or [],
        "trustees": case.get("trustees") or [],
        "successor_trustees": case.get("successor_trustees") or [],
        "beneficiaries": case.get("beneficiaries") or [],
        "assets": case.get("assets") or [],
    }


@api_router.get("/trust-cases/{case_id}/trust-page-explanations")
async def client_trust_page_explanations(case_id: str, user: dict = Depends(get_current_user)):
    """Client-facing endpoint the trust preview page reads to display the
    per-page plain-English explanations alongside the watermarked PDF.

    Returns an ORDERED list of {page:int, text:html} plus job status so the UI
    can show a spinner while pages are still being generated."""
    case = await get_case(case_id, user)
    explanations = case.get("trust_page_explanations") or []
    job = case.get("trust_page_job") or {}
    return {
        "ok": True,
        "explanations": explanations,
        "status": job.get("status") or ("completed" if explanations else "idle"),
        "pages_done": job.get("pages_done") or len(explanations),
        "pages_total": job.get("pages_total") or 0,
        "batches_done": job.get("batches_done") or 0,
        "batches_total": job.get("batches_total") or 0,
        "error": job.get("error"),
    }


@api_router.post("/admin/trust-cases/{case_id}/trust-page-explanations/regenerate")
async def admin_regenerate_trust_page_explanations(case_id: str,
                                                   admin: dict = Depends(require_admin)):
    """Manually re-fire the page-by-page explanation job. Useful when the
    admin has updated intake data (names, beneficiary shares, assets) and
    wants the plain-English notes refreshed without re-uploading the PDF."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_draft") or {}
    if not draft.get("storage_path"):
        raise HTTPException(status_code=400, detail="No trust draft PDF uploaded yet.")
    try:
        data, _ct = get_object(draft["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read PDF from storage: {e}")
    job = await page_explanation_jobs.start_page_explain_job(
        case_id=case_id,
        pdf_bytes=data,
        case_context=_build_case_context(case),
        admin_id=admin["id"],
        db=db,
        update_case_fn=update_case,
    )
    return {"ok": True, **job}


@api_router.get("/trust-cases/{case_id}/trust-draft-explanation")
async def client_trust_draft_explanation(case_id: str, user: dict = Depends(get_current_user)):
    """Client-facing endpoint the trust preview page reads to display the
    personalized plain-English explanation alongside the watermarked PDF.

    Returns the AI explanation from the admin_documents entry whose
    `source == 'trust_draft'` (i.e., the one produced by "Import Trust Draft
    PDF"). Returns 404 if no such explanation has been generated yet."""
    case = await get_case(case_id, user)
    for d in (case.get("admin_documents") or []):
        if d.get("source") == "trust_draft" and not d.get("is_deleted"):
            ai = d.get("ai_explanation") or {}
            return {
                "ok": True,
                "explanation": ai,
                "label": d.get("label") or "",
                "generated_at": ai.get("generated_at") or d.get("uploaded_at") or "",
                "personalized": bool(ai.get("personalized")),
            }
    raise HTTPException(
        status_code=404,
        detail="Plain-English explanation has not been generated yet for this trust.",
    )



@api_router.post("/admin/trust-cases/{case_id}/admin-documents/from-trust-draft")
async def admin_import_trust_draft_to_explainer(case_id: str,
                                                admin: dict = Depends(require_admin)):
    """Take the currently uploaded `trust_draft` PDF and register it as an
    entry in the AI Document Explainer (`admin_documents[]`). Reuses the
    existing storage object — no double-storage. Runs Claude on the extracted
    text and stores the structured plain-English explanation.

    Idempotent: if an admin_document already exists with source='trust_draft'
    and the same source_storage_path, returns that entry instead of creating a
    duplicate."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_draft") or {}
    if not draft or not draft.get("storage_path"):
        raise HTTPException(status_code=400, detail="No trust draft PDF on this case. Upload one first.")

    src_path = draft["storage_path"]
    src_filename = draft.get("filename") or "trust-draft.pdf"

    # Idempotency: if we've already imported this exact draft, return existing entry.
    for d in (case.get("admin_documents") or []):
        if (
            d.get("source") == "trust_draft"
            and d.get("source_storage_path") == src_path
            and not d.get("is_deleted")
        ):
            return {"ok": True, "already_imported": True, **d}

    # Fetch the bytes from the existing storage object
    try:
        data, ct = get_object(src_path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read trust draft from storage: {e}")

    label = f"Trust Draft — {draft.get('filename') or 'v' + str(draft.get('version') or 1)}"[:160]
    text = doc_explainer.extract_text(data, src_filename, ct or "application/pdf")
    case_ctx = _build_case_context(case)
    ai = await doc_explainer.generate_explanation(label, src_filename, text, case_context=case_ctx)

    doc = {
        "id": new_id(),
        "label": label,
        "storage_path": src_path,             # reuse same object
        "source": "trust_draft",              # link marker
        "source_storage_path": src_path,      # for orphan detection on delete
        "source_draft_id": draft.get("id"),
        "source_draft_version": draft.get("version"),
        "filename": src_filename,
        "content_type": ct or "application/pdf",
        "size": draft.get("size") or len(data),
        "uploaded_by": admin["id"],
        "uploaded_at": now_iso(),
        "is_deleted": False,
        "ai_explanation": ai,
        "version": 1,
        "versions": [],
    }
    admin_docs = list(case.get("admin_documents") or [])
    admin_docs.append(doc)
    await update_case(case_id, {"admin_documents": admin_docs})
    return {"ok": True, "already_imported": False, **doc}


@api_router.post("/admin/trust-cases/{case_id}/admin-documents")
async def admin_upload_explainer_doc(case_id: str,
                                     label: str = Form(...),
                                     file: UploadFile = File(...),
                                     admin: dict = Depends(require_admin)):
    """Admin uploads a document (Operating Agreement, EIN letter, Membership Ledger,
    Schedule A amendment, etc.), types a friendly label, and the AI generates a
    short plain-English explanation for the client to read in the portal."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    label = (label or "").strip()[:160]
    if not label:
        raise HTTPException(status_code=400, detail="A document label is required.")

    ext = _explainer_ext(file.filename or "")
    if ext not in ALLOWED_EXPLAINER_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext or 'unknown'}'. Allowed: {', '.join(sorted(ALLOWED_EXPLAINER_EXTS))}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_EXPLAINER_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds max size ({MAX_EXPLAINER_SIZE // (1024*1024)} MB).")

    path = f"{APP_NAME}/admin-docs/{case_id}/{new_id()}.{ext}"
    result = put_object(path, data, file.content_type or "application/octet-stream")

    # Extract text (best-effort) and call the LLM for a structured explanation.
    text = doc_explainer.extract_text(data, file.filename or "", file.content_type or "")
    ai = await doc_explainer.generate_explanation(label, file.filename or "", text)

    doc = {
        "id": new_id(),
        "label": label,
        "storage_path": result["path"],
        "filename": file.filename,
        "content_type": file.content_type or "application/octet-stream",
        "size": result.get("size", len(data)),
        "uploaded_by": admin["id"],
        "uploaded_at": now_iso(),
        "is_deleted": False,
        "ai_explanation": ai,
        "version": 1,
        "versions": [],
    }
    admin_docs = list(case.get("admin_documents") or [])
    admin_docs.append(doc)
    await update_case(case_id, {"admin_documents": admin_docs})

    # Notify client by email (best-effort — never blocks the upload).
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        link = f"{FRONTEND_URL}/portal"
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">A new document is ready for you</p>
<p>Your trust team uploaded <b>{label}</b> to your secure portal.</p>
<p style="color:#64748B;font-size:13px;">Sign in to view the document alongside a plain-English explanation prepared by our AI assistant.</p>
{_cta(link, "Open your portal", accent)}
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            f"New document uploaded — {label}",
            html,
        )
    except Exception as e:
        logger.error(f"Admin-doc client email failed: {e}")

    return {"ok": True, **doc}


@api_router.post("/admin/trust-cases/{case_id}/admin-documents/{doc_id}/regenerate")
async def admin_regenerate_explainer(case_id: str, doc_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data, ct = get_object(doc["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read file from storage: {e}")
    text = doc_explainer.extract_text(data, doc.get("filename", ""), ct or doc.get("content_type", ""))
    # Personalize when this doc is the imported Trust Draft — clients see it in
    # the trust preview and need names, shares, and next steps.
    case_ctx = _build_case_context(case) if doc.get("source") == "trust_draft" else None
    ai = await doc_explainer.generate_explanation(
        doc.get("label", ""), doc.get("filename", ""), text, case_context=case_ctx,
    )
    # Update in place
    admin_docs = [dict(d) for d in (case.get("admin_documents") or [])]
    for d in admin_docs:
        if d.get("id") == doc_id:
            d["ai_explanation"] = ai
            break
    await update_case(case_id, {"admin_documents": admin_docs})
    return {"ok": True, "ai_explanation": ai}


@api_router.put("/admin/trust-cases/{case_id}/admin-documents/{doc_id}")
async def admin_replace_explainer_doc(case_id: str, doc_id: str,
                                      label: Optional[str] = Form(None),
                                      file: UploadFile = File(...),
                                      admin: dict = Depends(require_admin)):
    """Replace an existing admin-uploaded document IN PLACE — keeps the same
    doc_id, archives the current state to `versions[]`, stores the new file,
    and regenerates the AI explanation. Optionally updates the label."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    ext = _explainer_ext(file.filename or "")
    if ext not in ALLOWED_EXPLAINER_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '.{ext or 'unknown'}'. Allowed: {', '.join(sorted(ALLOWED_EXPLAINER_EXTS))}",
        )
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_EXPLAINER_SIZE:
        raise HTTPException(status_code=400, detail=f"File exceeds max size ({MAX_EXPLAINER_SIZE // (1024*1024)} MB).")

    new_path = f"{APP_NAME}/admin-docs/{case_id}/{new_id()}.{ext}"
    result = put_object(new_path, data, file.content_type or "application/octet-stream")

    # Regenerate AI explanation with the (possibly updated) label + new file
    new_label = (label or doc.get("label") or "").strip()[:160] or doc.get("label") or ""
    text = doc_explainer.extract_text(data, file.filename or "", file.content_type or "")
    ai = await doc_explainer.generate_explanation(new_label, file.filename or "", text)

    # Archive the CURRENT state as a prior version BEFORE overwriting.
    versions = list(doc.get("versions") or [])
    current_version_num = int(doc.get("version") or 1)
    archived = {
        "version": current_version_num,
        "storage_path": doc.get("storage_path"),
        "filename": doc.get("filename"),
        "content_type": doc.get("content_type"),
        "size": doc.get("size"),
        "label": doc.get("label"),
        "uploaded_by": doc.get("uploaded_by"),
        "uploaded_at": doc.get("uploaded_at"),
        "ai_explanation": doc.get("ai_explanation"),
        "archived_at": now_iso(),
    }
    versions.append(archived)

    admin_docs = [dict(d) for d in (case.get("admin_documents") or [])]
    for d in admin_docs:
        if d.get("id") == doc_id:
            d.update({
                "label": new_label,
                "storage_path": result["path"],
                "filename": file.filename,
                "content_type": file.content_type or "application/octet-stream",
                "size": result.get("size", len(data)),
                "uploaded_by": admin["id"],
                "uploaded_at": now_iso(),
                "ai_explanation": ai,
                "version": current_version_num + 1,
                "versions": versions,
                "replaced_at": now_iso(),
            })
            break
    await update_case(case_id, {"admin_documents": admin_docs})

    # Notify client that the document was updated (best-effort)
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        link = f"{FRONTEND_URL}/portal"
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">A document was updated</p>
<p>Your trust team replaced <b>{new_label}</b> with a new version in your secure portal.</p>
<p style="color:#64748B;font-size:13px;">Sign in to review the updated document and its refreshed AI explanation.</p>
{_cta(link, "Open your portal", accent)}
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            f"Document updated — {new_label}",
            html,
        )
    except Exception as e:
        logger.error(f"Admin-doc replace client email failed: {e}")

    return {"ok": True, "doc_id": doc_id, "label": new_label, "filename": file.filename,
            "version": current_version_num + 1, "ai_explanation": ai}


@api_router.get("/admin/trust-cases/{case_id}/admin-documents/{doc_id}/versions")
async def admin_list_explainer_versions(case_id: str, doc_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Newest first
    versions = sorted(list(doc.get("versions") or []), key=lambda v: v.get("archived_at") or "", reverse=True)
    return {
        "current_version": int(doc.get("version") or 1),
        "current_filename": doc.get("filename"),
        "current_uploaded_at": doc.get("uploaded_at"),
        "versions": versions,
    }


@api_router.post("/admin/trust-cases/{case_id}/admin-documents/{doc_id}/versions/{version_num}/restore")
async def admin_restore_explainer_version(case_id: str, doc_id: str, version_num: int,
                                          admin: dict = Depends(require_admin)):
    """Restore a specific prior version as the CURRENT file. The state at the
    time of restore is archived into `versions[]` so the operation is itself
    reversible."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = list(doc.get("versions") or [])
    target = next((v for v in versions if int(v.get("version") or 0) == int(version_num)), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Version {version_num} not found")

    # Archive the current state before swapping.
    current_version_num = int(doc.get("version") or 1)
    versions_next = [v for v in versions if int(v.get("version") or 0) != int(version_num)]
    versions_next.append({
        "version": current_version_num,
        "storage_path": doc.get("storage_path"),
        "filename": doc.get("filename"),
        "content_type": doc.get("content_type"),
        "size": doc.get("size"),
        "label": doc.get("label"),
        "uploaded_by": doc.get("uploaded_by"),
        "uploaded_at": doc.get("uploaded_at"),
        "ai_explanation": doc.get("ai_explanation"),
        "archived_at": now_iso(),
    })

    new_version_num = current_version_num + 1
    admin_docs = [dict(d) for d in (case.get("admin_documents") or [])]
    for d in admin_docs:
        if d.get("id") == doc_id:
            d.update({
                "label": target.get("label") or d.get("label") or "",
                "storage_path": target.get("storage_path"),
                "filename": target.get("filename"),
                "content_type": target.get("content_type") or "application/octet-stream",
                "size": target.get("size"),
                "ai_explanation": target.get("ai_explanation") or _empty_ai(),
                "uploaded_by": admin["id"],
                "uploaded_at": now_iso(),
                "version": new_version_num,
                "versions": versions_next,
                "restored_from_version": int(version_num),
                "restored_at": now_iso(),
            })
            break
    await update_case(case_id, {"admin_documents": admin_docs})
    return {"ok": True, "restored_version": int(version_num), "new_current_version": new_version_num}


def _empty_ai() -> dict:
    return {
        "what_is": "", "what_it_does": "", "why_it_matters": "",
        "notarization": "", "client_action": "",
        "generated_at": now_iso(), "error": "",
    }


@api_router.post("/admin/trust-cases/{case_id}/admin-documents/{doc_id}/trim-history")
async def admin_trim_version_history(case_id: str, doc_id: str,
                                     body: dict = Body(...),
                                     _: dict = Depends(require_admin)):
    """Trim `versions[]` so that only the newest N are kept. Older versions'
    storage files are deleted from object storage. Pass `{ "keep": N }` where
    N=0 means "clear all history"."""
    try:
        keep = int(body.get("keep", 5))
    except Exception:
        raise HTTPException(status_code=400, detail="`keep` must be an integer")
    if keep < 0 or keep > 100:
        raise HTTPException(status_code=400, detail="`keep` must be between 0 and 100")

    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = list(doc.get("versions") or [])
    # Newest archived_at first, then keep the top `keep`
    versions.sort(key=lambda v: v.get("archived_at") or "", reverse=True)
    kept = versions[:keep]
    trimmed = versions[keep:]
    for v in trimmed:
        sp = v.get("storage_path")
        if sp:
            try:
                delete_object(sp)
            except Exception as e:
                logger.warning(f"Trim: storage delete failed for {sp}: {e}")

    admin_docs = [dict(d) for d in (case.get("admin_documents") or [])]
    for d in admin_docs:
        if d.get("id") == doc_id:
            d["versions"] = kept
            d["history_trimmed_at"] = now_iso()
            break
    await update_case(case_id, {"admin_documents": admin_docs})
    return {"ok": True, "kept": len(kept), "removed": len(trimmed)}


@api_router.delete("/admin/trust-cases/{case_id}/admin-documents/{doc_id}")
async def admin_delete_explainer_doc(case_id: str, doc_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        delete_object(doc["storage_path"])
    except Exception as e:
        logger.warning(f"Storage delete failed for {doc['storage_path']}: {e}")
    # Also clean up any prior versioned files
    for v in (doc.get("versions") or []):
        vp = v.get("storage_path")
        if vp:
            try:
                delete_object(vp)
            except Exception as e:
                logger.warning(f"Version storage delete failed for {vp}: {e}")
    admin_docs = [d for d in (case.get("admin_documents") or []) if d.get("id") != doc_id]
    await update_case(case_id, {"admin_documents": admin_docs})
    return {"ok": True}


@api_router.get("/trust-cases/{case_id}/admin-documents/{doc_id}/download")
async def download_explainer_doc(case_id: str, doc_id: str, user: dict = Depends(get_current_user)):
    """Both admin and the case-owning client may download. Auth via get_case."""
    case = await get_case(case_id, user)
    doc = _find_admin_doc(case, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    try:
        data, ct = get_object(doc["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not read file from storage: {e}")
    safe_name = (doc.get("filename") or f"document-{doc_id[:8]}").replace('"', "'")
    return Response(
        content=data,
        media_type=doc.get("content_type") or ct or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


async def _get_trust_draft(case_id: str, user: dict):
    case = await get_case(case_id, user)
    draft = case.get("trust_draft")
    if not draft:
        raise HTTPException(status_code=404, detail="No trust draft available yet")
    return case, draft


@api_router.get("/trust-cases/{case_id}/trust-preview/meta")
async def trust_preview_meta(case_id: str, user: dict = Depends(get_current_user)):
    case, draft = await _get_trust_draft(case_id, user)
    unlocked = bool(case.get("trust_unlocked"))
    return {
        "pages": draft.get("pages", 0),
        "version": draft.get("version", 1),
        "uploaded_at": draft.get("uploaded_at"),
        "trust_name": case.get("trust_name") or "",
        "case_id": case_id,
        "status": case.get("status"),
        "unlocked": unlocked,
        "payment_status": (case.get("payment") or {}).get("status", "none"),
        "review_completed": bool((case.get("acknowledgments") or {}).get("review_completed_ack")),
    }


@api_router.get("/trust-cases/{case_id}/trust-preview/page/{page}.png")
async def trust_preview_page(case_id: str, page: int, user: dict = Depends(get_current_user)):
    case, draft = await _get_trust_draft(case_id, user)
    total = int(draft.get("pages", 0))
    if page < 1 or page > total:
        raise HTTPException(status_code=404, detail="Page out of range")
    storage_path = draft["storage_path"]
    cache_key = (storage_path, page)
    cached = _cache_get(cache_key)
    if cached is None:
        try:
            pdf_bytes, _ct = get_object(storage_path)
            img_bytes = pdf_bytes_to_preview_page(pdf_bytes, page - 1, fmt="JPEG")
            _cache_put(cache_key, img_bytes)
            cached = img_bytes
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to render preview: {e}")

    headers = {
        "Cache-Control": "private, no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "X-Frame-Options": "SAMEORIGIN",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(io.BytesIO(cached), media_type="image/jpeg", headers=headers)


# Admin-only: raw (no watermark) trust draft download
@api_router.get("/admin/trust-cases/{case_id}/trust-draft/raw")
async def admin_download_trust_draft(case_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    draft = case.get("trust_draft")
    if not draft:
        raise HTTPException(status_code=404, detail="No trust draft uploaded")
    data, _ct = get_object(draft["storage_path"])
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="draft-trust-{case_id[:8]}.pdf"'},
    )


# Admin unlocks final trust after payment (or manual override)
@api_router.post("/admin/trust-cases/{case_id}/unlock-final")
async def admin_unlock_final(case_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.get("trust_draft"):
        raise HTTPException(status_code=400, detail="No trust draft uploaded yet")
    await update_case(case_id, {
        "trust_unlocked": True,
        "trust_unlocked_at": now_iso(),
        "trust_unlocked_by": admin["id"],
        "status": "Completed",
    })

    # Final email with notarization instructions
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        link = f"{FRONTEND_URL}/portal/trust-final/{case_id}"
        inner = f"""
<p style="font-size:22px;margin:0 0 12px 0;font-family:Georgia,serif;">Your final trust is unlocked.</p>
<p>Thank you for your payment. Your final, clean trust documents for <b>{case.get('trust_name') or 'your case'}</b> are now available to print and download from the portal.</p>

<div style="margin-top:18px;background:#FEF6E0;border:1px solid #F4D58D;border-radius:8px;padding:14px 16px;">
  <p style="margin:0 0 6px 0;font-family:Georgia,serif;font-size:16px;color:#78350F;">Next step — Notarize</p>
  <p style="margin:0;color:#1C252E;font-size:14px;line-height:1.5;">
    Your trust must be <b>printed and notarized</b> to become legally valid. Please sign in the
    presence of a notary public and retain the original notarized copy with your important records.
  </p>
</div>

{_cta(link, "Open your final trust", accent)}
<p style="color:#64748B;font-size:13px;">If you placed a business under your trust, remember to file a Change of Ownership with your Secretary of State.</p>
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            f"Your final trust is ready — {biz}",
            html,
        )
    except Exception as e:
        logger.error(f"Final-unlock email failed: {e}")

    return {"ok": True, "trust_unlocked": True}


# Client downloads FINAL (clean, no watermark) trust PDF — only when unlocked
@api_router.get("/trust-cases/{case_id}/trust-final")
async def client_download_final_trust(case_id: str, user: dict = Depends(get_current_user)):
    case, draft = await _get_trust_draft(case_id, user)
    if not case.get("trust_unlocked"):
        raise HTTPException(status_code=403, detail="Final trust is locked. Payment required.")
    data, _ct = get_object(draft["storage_path"])
    safe_name = (case.get("trust_name") or f"trust-{case_id[:8]}").replace("/", "-")
    return StreamingResponse(
        io.BytesIO(data), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )


@api_router.post("/admin/trust-cases/{case_id}/send-review-reminder")
async def admin_send_review_reminder(case_id: str, admin: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not case.get("trust_draft"):
        raise HTTPException(status_code=400, detail="No trust draft uploaded — nothing to review")
    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    accent = branding.get("accent_color", "#C5A880")
    primary = branding.get("primary_color", "#1C252E")
    link = f"{FRONTEND_URL}/portal/trust-preview/{case_id}"
    inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">A friendly reminder</p>
<p>Your draft trust for <b>{case.get('trust_name') or 'your case'}</b> is ready and waiting for your review in the portal.</p>
<p>When you're done reviewing, click <b>"Review Completed — I Am Satisfied With My Trust"</b> to move to the payment phase.</p>
{_cta(link, "Review your trust", accent)}
"""
    html = _email_shell(biz, primary, accent, inner)
    await send_email_notification(
        case.get("client_email"),
        f"Reminder: your trust is ready for review — {biz}",
        html,
    )
    return {"ok": True, "sent_to": case.get("client_email")}


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
        "status": "Ready for Payment",
    })

    # Status-change email already fires from admin_update_status; here we hand-send because we bypassed it
    try:
        html = _status_change_email_html(
            business=biz,
            accent=branding.get("accent_color", "#C5A880"),
            primary=branding.get("primary_color", "#1C252E"),
            client_name=case.get("client_name") or case.get("client_email"),
            status="Ready for Payment",
            case_id=case_id[:8].upper(),
            link=f"{FRONTEND_URL}/portal",
        )
        await send_email_notification(
            case.get("client_email"),
            f"Your trust is ready — {biz}",
            html,
        )
    except Exception as e:
        logger.error(f"Ready-for-payment email failed: {e}")

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


# ---------- SQUARE: Payments & Invoices ----------
class InvoiceCreateReq(BaseModel):
    amount_cents: int = Field(gt=0, le=100_000_00)  # up to $100,000
    description: Optional[str] = None
    due_in_days: int = Field(default=14, ge=1, le=90)


@api_router.get("/admin/square/health")
async def square_health(_: dict = Depends(require_admin)):
    resolved_loc = None
    loc_ok = False
    try:
        if square_service.is_enabled():
            resolved_loc = square_service._resolve_location_id()
            loc_ok = bool(resolved_loc)
    except Exception as e:
        logger.warning(f"Square health: location resolution failed: {e}")
    return {
        "enabled": square_service.is_enabled(),
        "environment": os.environ.get("SQUARE_ENVIRONMENT", "production"),
        "location_id": loc_ok,
        "resolved_location_id": resolved_loc,
        "configured_location_id": os.environ.get("SQUARE_LOCATION_ID") or None,
        "webhook_configured": bool(os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY")),
        "twilio_configured": bool(
            os.environ.get("TWILIO_ACCOUNT_SID")
            and os.environ.get("TWILIO_AUTH_TOKEN")
            and os.environ.get("TWILIO_FROM_NUMBER")
        ),
    }


@api_router.get("/admin/diagnostics")
async def admin_diagnostics(_: dict = Depends(require_admin)):
    """One-shot production-readiness probe. Returns the live state of every
    third-party integration so admin can verify after a redeploy without
    reading server logs. Never exposes secret values — only booleans + the
    non-sensitive resolved Square location id."""
    # --- Square ---
    square_enabled = False
    square_location_resolved = None
    square_location_typo = False
    square_error = None
    try:
        square_enabled = square_service.is_enabled()
        if square_enabled:
            square_location_resolved = square_service._resolve_location_id()
            configured = (os.environ.get("SQUARE_LOCATION_ID") or "").strip()
            if configured and square_location_resolved and configured != square_location_resolved:
                square_location_typo = True
    except Exception as e:
        square_error = str(e)[:200]

    square_webhook_signed = bool(os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY"))

    # --- Twilio ---
    twilio_ready = sms.is_enabled()
    twilio_admin_phone_set = bool((os.environ.get("ADMIN_PHONE_NUMBER") or "").strip())

    # --- Resend (transactional email) ---
    resend_ready = bool(RESEND_API_KEY)

    # --- Emergent LLM (AI assistant) ---
    llm_ready = bool(EMERGENT_KEY)

    # --- Auth / DB sanity ---
    jwt_set = bool(os.environ.get("JWT_SECRET"))
    try:
        admin_count = await db.users.count_documents({"role": "admin"})
    except Exception:
        admin_count = -1

    all_ready = (
        square_enabled
        and bool(square_location_resolved)
        and not square_location_typo
        and square_webhook_signed
        and twilio_ready
        and twilio_admin_phone_set
        and resend_ready
        and llm_ready
        and jwt_set
        and admin_count >= 1
    )

    return {
        "all_ready": all_ready,
        "square": {
            "ready": square_enabled and bool(square_location_resolved),
            "environment": os.environ.get("SQUARE_ENVIRONMENT", "production"),
            "location_resolved": square_location_resolved,
            "location_id_typo": square_location_typo,
            "webhook_signed": square_webhook_signed,
            "error": square_error,
        },
        "twilio": {
            "ready": twilio_ready,
            "admin_phone_set": twilio_admin_phone_set,
            "from_number_set": bool((os.environ.get("TWILIO_FROM_NUMBER") or "").strip()),
        },
        "email": {"resend_ready": resend_ready},
        "ai": {"emergent_llm_ready": llm_ready},
        "auth": {"jwt_secret_set": jwt_set, "admin_count": admin_count},
        "frontend_url": FRONTEND_URL,
    }


@api_router.post("/admin/trust-cases/{case_id}/invoice")
async def admin_create_invoice(case_id: str, body: InvoiceCreateReq, admin: dict = Depends(require_admin)):
    if not square_service.is_enabled():
        raise HTTPException(status_code=503, detail="Square is not configured.")
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    if not (case.get("client_email") or "").strip():
        raise HTTPException(status_code=400, detail="Client has no email on file.")
    try:
        result = square_service.create_invoice(
            client_email=case["client_email"],
            client_name=case.get("client_name") or case.get("client_email"),
            amount_cents=body.amount_cents,
            description=body.description or f"Trust preparation & filing fee — {case.get('trust_name') or case['client_name']}",
            case_id=case_id,
            trust_name=case.get("trust_name") or f"Case #{case_id[:8].upper()}",
            due_in_days=body.due_in_days,
        )
    except Exception as e:
        logger.error(f"Square invoice create failed: {e}")
        raise HTTPException(status_code=502, detail=f"Square error: {e}")

    payment = dict(case.get("payment") or {})
    payment.update({
        "status": "invoice_sent",
        "amount_cents": body.amount_cents,
        "invoice_id": result["invoice_id"],
        "order_id": result["order_id"],
        "public_url": result["public_url"],
        "invoice_status": result["status"],
        "due_date": result["due_date"],
        "invoiced_at": now_iso(),
    })
    await update_case(case_id, {"payment": payment, "status": "Ready for Payment"})

    # Notify client with hosted payment link
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        amount_str = f"${body.amount_cents/100:,.2f}"
        pay_link = result["public_url"] or f"{FRONTEND_URL}/portal"
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Invoice ready for payment</p>
<p>Your trust preparation fee of <b>{amount_str}</b> is ready. Square will send you a separate secure payment email as well.</p>
<p style="color:#64748B;font-size:13px;">Once payment clears (ACH may take 3–5 business days), your final trust will be unlocked automatically.</p>
{_cta(pay_link, "Pay securely with Square", accent)}
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            f"Invoice for your trust — {biz}",
            html,
        )
    except Exception as e:
        logger.error(f"Invoice email failed: {e}")

    return {"ok": True, **result}


@api_router.get("/admin/trust-cases/{case_id}/invoice")
async def admin_get_invoice(case_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    payment = case.get("payment") or {}
    invoice_id = payment.get("invoice_id")
    if not invoice_id:
        return {"has_invoice": False}
    try:
        live = square_service.get_invoice(invoice_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Square error: {e}")
    payment_status = payment.get("status")
    status_live = live.get("status")
    # sync status mapping
    new_status = payment_status
    if status_live in ("PAID",):
        new_status = "paid"
    elif status_live in ("PAYMENT_PENDING",):
        new_status = "ach_pending"
    elif status_live in ("UNPAID", "SENT", "SCHEDULED"):
        new_status = "invoice_sent"
    elif status_live in ("CANCELED", "FAILED"):
        new_status = "canceled"
    if new_status != payment_status:
        payment["status"] = new_status
        payment["invoice_status"] = status_live
        payment["synced_at"] = now_iso()
        await update_case(case_id, {"payment": payment})
    return {"has_invoice": True, "local": payment, "remote": live}


@api_router.post("/admin/trust-cases/{case_id}/mark-payment-received")
async def admin_mark_payment_received(case_id: str, admin: dict = Depends(require_admin)):
    """Manual override — mark payment as received regardless of Square state."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    payment = dict(case.get("payment") or {})
    payment["status"] = "paid_manual"
    payment["manually_marked_at"] = now_iso()
    payment["manually_marked_by"] = admin["id"]
    await update_case(case_id, {"payment": payment, "status": "Completed"})
    # Notify client
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Payment confirmed</p>
<p>Thank you — we've confirmed receipt of your payment for <b>{case.get('trust_name') or 'your trust'}</b>.</p>
<p>Your final trust is next. We'll email you when it's unlocked.</p>
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(case.get("client_email"),
                                      f"Payment received — {biz}", html)
    except Exception as e:
        logger.error(f"Mark-paid email failed: {e}")
    # SMS admin
    try:
        notify.notify_admin(
            f"IGC: Payment manually marked RECEIVED for {case.get('client_name') or case.get('client_email')} "
            f"(case #{case_id[:8].upper()})."
        )
    except Exception as e:
        logger.error(f"Mark-paid SMS failed: {e}")
    return {"ok": True, "payment": payment}


@api_router.get("/trust-cases/{case_id}/payment-status")
async def client_payment_status(case_id: str, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    p = case.get("payment") or {}
    return {
        "status": p.get("status", "none"),
        "amount_cents": p.get("amount_cents"),
        "public_url": p.get("public_url"),
        "invoice_status": p.get("invoice_status"),
        "due_date": p.get("due_date"),
        "trust_unlocked": bool(case.get("trust_unlocked")),
    }


# ---------- Multi-method payment workflow (Zelle / CashApp / Square) ----------

class PaymentAmountReq(BaseModel):
    amount_cents: int = Field(gt=0, le=100_000_00)


class PaymentClaimedReq(BaseModel):
    method: Literal["zelle", "cashapp", "square", "other"] = "other"
    note: Optional[str] = None


@api_router.put("/admin/trust-cases/{case_id}/payment-amount")
async def admin_set_payment_amount(case_id: str, body: PaymentAmountReq, admin: dict = Depends(require_admin)):
    """Set just the payment amount on a case (for Zelle/CashApp clients).
    Does NOT create a Square invoice. Updates case status to Ready for Payment."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    payment = dict(case.get("payment") or {})
    payment["amount_cents"] = int(body.amount_cents)
    if not payment.get("status") or payment.get("status") == "none":
        payment["status"] = "amount_set"
    payment["amount_set_at"] = now_iso()
    payment["amount_set_by"] = admin["id"]
    await update_case(case_id, {"payment": payment, "status": "Ready for Payment"})
    return {"ok": True, "payment": payment}


@api_router.post("/trust-cases/{case_id}/payment-claimed")
async def client_claimed_payment(case_id: str, body: PaymentClaimedReq, user: dict = Depends(get_current_user)):
    """Client clicks 'I Made My Payment' — flips status to Pending Payment Verification
    and notifies admin. No screenshot/upload required; admin verifies manually."""
    case = await get_case(case_id, user)
    if user.get("role") == "admin":
        raise HTTPException(status_code=400, detail="Admins cannot claim a payment on behalf of a client.")

    payment = dict(case.get("payment") or {})
    if (payment.get("status") in {"paid", "paid_manual", "verified"}):
        return {"ok": True, "already_paid": True, "status": payment.get("status")}

    payment["claimed"] = True
    payment["claimed_method"] = body.method
    payment["claimed_at"] = now_iso()
    payment["claimed_by"] = user["id"]
    if body.note:
        payment["claimed_note"] = body.note[:500]
    payment["status"] = "pending_verification"

    await update_case(case_id, {"payment": payment, "status": "Pending Payment Verification"})

    # --- Email to client (subject + copy from spec) ---
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        method_label = {
            "zelle": "Zelle",
            "cashapp": "Cash App",
            "square": "Square (debit/credit card)",
            "other": "your selected method",
        }.get(body.method, "your selected method")
        inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Payment submitted — pending verification</p>
<p>Thank you, your payment has been received. Your application is now pending verification. You will receive another email once your payment has been fully verified and your next steps are ready.</p>
<p style="color:#64748B;font-size:13px;">Payment method: {method_label}</p>
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            "Payment Submitted – Pending Verification",
            html,
        )
    except Exception as e:
        logger.error(f"Payment-claimed client email failed: {e}")

    # --- Email + SMS admin ---
    try:
        admin_rec = await db.users.find_one({"role": "admin"})
        if admin_rec:
            link = f"{FRONTEND_URL}/admin/cases/{case_id}"
            inner = f"""
<p style="font-size:20px;margin:0 0 12px 0;font-family:Georgia,serif;">Client claims payment was made</p>
<p><b>{case.get('client_name') or case.get('client_email')}</b> reports they have completed payment via <b>{body.method.upper() if body.method else 'unspecified'}</b>.</p>
<p>Case #{case_id[:8].upper()} · {case.get('trust_name') or ''}</p>
<p style="color:#64748B;">Please verify the payment in your records and approve in the admin panel.</p>
{_cta(link, "Open case to verify", branding.get('accent_color', '#C5A880'))}
"""
            html = _email_shell(biz, primary, accent, inner)
            await send_email_notification(
                admin_rec["email"],
                f"Payment claimed — verify {case.get('client_name') or case.get('client_email')}",
                html,
            )
    except Exception as e:
        logger.error(f"Payment-claimed admin email failed: {e}")

    try:
        notify.notify_admin(
            f"IGC: {case.get('client_name') or case.get('client_email')} claims payment via "
            f"{body.method.upper()}. Case #{case_id[:8].upper()}. Please verify."
        )
    except Exception as e:
        logger.error(f"Payment-claimed SMS failed: {e}")

    return {"ok": True, "status": "pending_verification"}


class PaymentVerifyReq(BaseModel):
    amount_cents: Optional[int] = None  # final amount override
    note: Optional[str] = None


@api_router.post("/admin/trust-cases/{case_id}/payment-verify")
async def admin_verify_payment(case_id: str, body: PaymentVerifyReq, admin: dict = Depends(require_admin)):
    """Admin verifies a claimed payment. Sets status to Payment Verified and notifies client."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    payment = dict(case.get("payment") or {})
    payment["status"] = "verified"
    payment["verified_at"] = now_iso()
    payment["verified_by"] = admin["id"]
    if body.amount_cents:
        payment["amount_cents"] = int(body.amount_cents)
        payment["amount_finalized_at"] = now_iso()
    if body.note:
        payment["verified_note"] = body.note[:500]
    await update_case(case_id, {"payment": payment, "status": "Payment Verified"})

    # Notify client
    try:
        branding = await _branding_doc()
        biz = branding.get("business_name", "Trust Portal")
        accent = branding.get("accent_color", "#C5A880")
        primary = branding.get("primary_color", "#1C252E")
        link = f"{FRONTEND_URL}/portal"
        amount_str = f"${(payment.get('amount_cents') or 0)/100:,.2f}"
        inner = f"""
<p style="font-size:22px;margin:0 0 12px 0;font-family:Georgia,serif;">Your payment is verified.</p>
<p>Thank you — we've verified your payment of <b>{amount_str}</b> for <b>{case.get('trust_name') or 'your trust'}</b>. Your final trust documents will be unlocked shortly.</p>
{_cta(link, "Open your portal", accent)}
"""
        html = _email_shell(biz, primary, accent, inner)
        await send_email_notification(
            case.get("client_email"),
            f"Payment verified — {biz}",
            html,
        )
    except Exception as e:
        logger.error(f"Verify-payment email failed: {e}")

    try:
        notify.notify_admin(
            f"IGC: Payment VERIFIED for {case.get('client_name') or case.get('client_email')} (case #{case_id[:8].upper()})."
        )
    except Exception as e:
        logger.error(f"Verify-payment SMS failed: {e}")

    return {"ok": True, "payment": payment}





# Square webhook — receives invoice.* and payment.* events
@api_router.post("/webhooks/square")
async def square_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("x-square-hmacsha256-signature", "")
    # Notification URL must match what's configured in Square Dashboard
    # Reconstruct by concatenating base + /api/webhooks/square
    configured_url = os.environ.get("SQUARE_WEBHOOK_URL") or f"{FRONTEND_URL}/api/webhooks/square"
    sig_key = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "")

    if sig_key:
        ok = square_service.verify_webhook_signature(
            body_bytes=body, signature_header=signature, url=configured_url, signature_key=sig_key,
        )
        if not ok:
            logger.warning("Square webhook signature failed")
            raise HTTPException(status_code=401, detail="Bad signature")
    else:
        # Signature key not yet configured (user hasn't pasted it into .env after registering
        # the webhook in Square Dashboard). Log loudly but accept so the registration flow works.
        logger.warning("Square webhook received but SQUARE_WEBHOOK_SIGNATURE_KEY is unset — accepting unverified. Set the key to enable verification.")

    import json as _json
    try:
        payload = _json.loads(body.decode("utf-8") or "{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_id = payload.get("event_id") or payload.get("id") or new_id()
    event_type = payload.get("type") or ""
    data_obj = ((payload.get("data") or {}).get("object")) or {}

    # Idempotency
    existing = await db.square_events.find_one({"event_id": event_id})
    if existing:
        return {"status": "duplicate"}
    await db.square_events.insert_one({
        "event_id": event_id, "type": event_type,
        "payload": payload, "received_at": now_iso(),
        "processed": False,
    })

    case_id = None
    update = {}

    # --- Invoice events ---
    if event_type.startswith("invoice."):
        inv = data_obj.get("invoice", {})
        invoice_id = inv.get("id")
        status_ = inv.get("status")
        case = await db.trust_cases.find_one({"payment.invoice_id": invoice_id}, {"_id": 0})
        if case:
            case_id = case["id"]
            p = dict(case.get("payment") or {})
            p["invoice_status"] = status_
            mapping = {
                "PAID": "paid",
                "PAYMENT_PENDING": "ach_pending",
                "SENT": "invoice_sent",
                "SCHEDULED": "invoice_sent",
                "UNPAID": "invoice_sent",
                "CANCELED": "canceled",
                "FAILED": "failed",
                "DRAFT": "draft",
            }
            p["status"] = mapping.get(status_, p.get("status"))
            p["last_webhook_at"] = now_iso()
            update["payment"] = p
            if p["status"] in ("paid", "ach_pending"):
                update["status"] = "Ready for Payment"

    # --- Payment events (ACH state changes) ---
    elif event_type.startswith("payment."):
        payment = data_obj.get("payment", {})
        payment_id = payment.get("id")
        amount_money = payment.get("amount_money", {})
        p_status = payment.get("status")  # APPROVED/PENDING/COMPLETED/CANCELED/FAILED
        source_type = payment.get("source_type")  # CARD / BANK_ACCOUNT / EXTERNAL
        order_id = payment.get("order_id")
        risk_eval = payment.get("risk_evaluation") or {}

        # Find case by order_id (or invoice through order)
        case = None
        if order_id:
            case = await db.trust_cases.find_one({"payment.order_id": order_id}, {"_id": 0})
        if case:
            case_id = case["id"]
            p = dict(case.get("payment") or {})
            p["payment_id"] = payment_id
            p["amount_money"] = amount_money
            p["source_type"] = source_type
            p["square_payment_status"] = p_status
            p["risk_level"] = risk_eval.get("risk_level")
            p["last_webhook_at"] = now_iso()
            # Map to internal
            if source_type == "BANK_ACCOUNT":
                if p_status == "COMPLETED":
                    p["status"] = "paid"
                elif p_status in ("APPROVED", "PENDING"):
                    p["status"] = "ach_pending"
                elif p_status in ("FAILED", "CANCELED"):
                    p["status"] = "failed"
            else:
                # Card payments: APPROVED/COMPLETED = paid immediately
                if p_status == "COMPLETED":
                    p["status"] = "paid"
                elif p_status == "FAILED":
                    p["status"] = "failed"
            update["payment"] = p
            if p["status"] == "paid":
                update["status"] = "Ready for Payment"

    # --- Refunds ---
    elif event_type.startswith("refund."):
        refund = data_obj.get("refund", {})
        payment_id = refund.get("payment_id")
        case = await db.trust_cases.find_one({"payment.payment_id": payment_id}, {"_id": 0})
        if case:
            case_id = case["id"]
            p = dict(case.get("payment") or {})
            p["refund_initiated"] = True
            p["refund_id"] = refund.get("id")
            p["refund_status"] = refund.get("status")
            p["last_webhook_at"] = now_iso()
            update["payment"] = p

    if case_id and update:
        await update_case(case_id, update)

    # SMS admin on payment lifecycle changes
    try:
        if case_id and update.get("payment"):
            p_new = update["payment"]
            prev_status = (case.get("payment") if case else {}).get("status")
            new_status = p_new.get("status")
            if new_status != prev_status and case:
                client_label = case.get("client_name") or case.get("client_email") or "client"
                short = case_id[:8].upper()
                if new_status == "paid":
                    notify.notify_admin(f"IGC: Payment CLEARED for {client_label} (case #{short}).")
                elif new_status == "ach_pending":
                    notify.notify_admin(f"IGC: ACH pending for {client_label} (case #{short}). Waiting 3-5 business days.")
                elif new_status == "failed":
                    notify.notify_admin(f"IGC: Payment FAILED for {client_label} (case #{short}). Please follow up.")
                elif new_status == "canceled":
                    notify.notify_admin(f"IGC: Invoice canceled for {client_label} (case #{short}).")
    except Exception as e:
        logger.error(f"Payment webhook SMS failed: {e}")

    # --- Auto-unlock final trust when payment is fully paid (card or ACH cleared) ---
    auto_unlock = (os.environ.get("SQUARE_AUTO_UNLOCK_ON_PAID", "false").lower() == "true")
    if auto_unlock and case_id:
        fresh = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
        if fresh and (fresh.get("payment") or {}).get("status") == "paid" and not fresh.get("trust_unlocked") and fresh.get("trust_draft"):
            try:
                await update_case(case_id, {
                    "trust_unlocked": True,
                    "trust_unlocked_at": now_iso(),
                    "trust_unlocked_by": "auto-webhook",
                    "status": "Completed",
                })
                branding = await _branding_doc()
                biz = branding.get("business_name", "Trust Portal")
                accent = branding.get("accent_color", "#C5A880")
                primary = branding.get("primary_color", "#1C252E")
                link = f"{FRONTEND_URL}/portal/trust-final/{case_id}"
                inner = f"""
<p style="font-size:22px;margin:0 0 12px 0;font-family:Georgia,serif;">Your final trust is unlocked.</p>
<p>Thank you for your payment. Your final, clean trust documents are now available to print and download.</p>
<div style="margin-top:18px;background:#FEF6E0;border:1px solid #F4D58D;border-radius:8px;padding:14px 16px;">
  <p style="margin:0 0 6px 0;font-family:Georgia,serif;font-size:16px;color:#78350F;">Next step — Notarize</p>
  <p style="margin:0;color:#1C252E;font-size:14px;line-height:1.5;">Your trust must be printed and notarized to become legally valid.</p>
</div>
{_cta(link, "Open your final trust", accent)}
"""
                html = _email_shell(biz, primary, accent, inner)
                await send_email_notification(
                    fresh.get("client_email"),
                    f"Your final trust is ready — {biz}", html,
                )
            except Exception as e:
                logger.error(f"Auto-unlock failed: {e}")

    await db.square_events.update_one({"event_id": event_id},
                                      {"$set": {"processed": True, "processed_at": now_iso()}})
    return {"status": "ok"}


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
@api_router.post("/admin/monthly-summary/send")
async def admin_send_monthly_summary(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    force: bool = Query(False, description="Re-send even if already sent for this period"),
    admin: dict = Depends(require_admin),
):
    """Manually trigger a monthly summary email. Defaults to the previous calendar month.
    Pass ?force=true to override the idempotency guard."""
    now = datetime.now(timezone.utc)
    if year is None or month is None:
        py, pm = _previous_month(now)
        year = year or py
        month = month or pm
    if not (1 <= month <= 12):
        raise HTTPException(status_code=400, detail="Invalid month")
    if force:
        await db.monthly_summaries.delete_one({"period": f"{year:04d}-{month:02d}"})
    return await _build_and_send_monthly_summary(year, month)


@api_router.get("/admin/monthly-summary/history")
async def admin_monthly_summary_history(_: dict = Depends(require_admin)):
    """List of past monthly summaries that have been sent."""
    docs = await db.monthly_summaries.find({}, {"_id": 0}).sort("period", -1).to_list(36)
    return docs


# ---------- WHATSAPP ----------
class WhatsAppSendReq(BaseModel):
    to: Optional[str] = None  # E.164 number (if omitted, uses primary grantor / client_phone on the case)
    body: str


@api_router.get("/admin/whatsapp/status")
async def admin_whatsapp_status(_: dict = Depends(require_admin)):
    """Returns configuration state for the WhatsApp integration so admins can see
    at a glance whether outbound messages will actually deliver."""
    return {
        "enabled": whatsapp.is_enabled(),
        "from": whatsapp.TWILIO_WHATSAPP_FROM or None,
        "admin_number": whatsapp.ADMIN_WHATSAPP_NUMBER or None,
        "notify_admin_on_events": notify.WHATSAPP_NOTIFY_ADMIN,
    }


def _resolve_case_phone(case: dict) -> Optional[str]:
    """Find a phone number to WhatsApp for a given trust case."""
    if case.get("client_phone"):
        return case["client_phone"]
    for g in (case.get("grantors") or []):
        if g.get("phone"):
            return g["phone"]
    return None


@api_router.post("/admin/trust-cases/{case_id}/send-whatsapp")
async def admin_send_case_whatsapp(case_id: str, body: WhatsAppSendReq,
                                    admin: dict = Depends(require_admin)):
    """Send a WhatsApp message to the client attached to `case_id`.
    The message is also recorded on the case activity log."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise HTTPException(status_code=404, detail="Not found")
    to_number = (body.to or "").strip() or _resolve_case_phone(case)
    if not to_number:
        raise HTTPException(status_code=400, detail="No phone number on file for this client. Provide `to` explicitly.")
    text = (body.body or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Message body is empty")
    if len(text) > 1500:
        raise HTTPException(status_code=400, detail="Message exceeds 1500 characters")
    ok = whatsapp.send_whatsapp(to_number, text)

    stamp = now_iso()
    log_entry = {
        "id": str(uuid.uuid4()),
        "direction": "outbound",
        "to": to_number,
        "body": text,
        "at": stamp,
        "sent": bool(ok),
        "admin_id": admin["id"],
        "admin_email": admin.get("email"),
    }
    await db.trust_cases.update_one(
        {"id": case_id},
        {"$push": {"whatsapp_thread": log_entry}, "$set": {"updated_at": stamp}},
    )
    return {"ok": True, "sent": bool(ok), "entry": log_entry}


@api_router.get("/admin/trust-cases/{case_id}/whatsapp-thread")
async def admin_get_case_whatsapp_thread(case_id: str, _: dict = Depends(require_admin)):
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0, "whatsapp_thread": 1})
    if case is None:
        raise HTTPException(status_code=404, detail="Not found")
    return {"thread": case.get("whatsapp_thread") or []}


@api_router.post("/webhooks/twilio/whatsapp-inbound")
async def twilio_whatsapp_inbound(
    From: str = Form(""),
    To: str = Form(""),
    Body: str = Form(""),
    MessageSid: str = Form(""),
    ProfileName: str = Form(""),
):
    """Twilio posts here whenever a client (or the admin) replies on WhatsApp.

    Configure this URL in the Twilio Console under Messaging → Try WhatsApp →
    Sandbox settings (or WhatsApp Sender settings) as the 'When a message comes
    in' webhook (HTTP POST, form-encoded)."""
    raw_from = (From or "").replace("whatsapp:", "").strip()
    text = (Body or "").strip()
    stamp = now_iso()

    # --- Path 1: admin commands (message from ADMIN_WHATSAPP_NUMBER) ---
    admin_num = (whatsapp.ADMIN_WHATSAPP_NUMBER or "").strip()
    if admin_num and raw_from == admin_num:
        admin_email = os.environ.get("ADMIN_EMAIL", "").strip() or None
        try:
            reply = await whatsapp_commands.handle_admin_command(text, raw_from, admin_email)
        except Exception as e:
            logger.exception(f"WhatsApp admin command failed: {e}")
            reply = f"Command failed: {e}"
        # Reply back on WhatsApp; also persist both sides to whatsapp_admin_log
        whatsapp.send_whatsapp(raw_from, reply)
        try:
            await db.whatsapp_admin_log.insert_one({
                "id": str(uuid.uuid4()),
                "from": raw_from,
                "body": text,
                "reply": reply,
                "at": stamp,
                "message_sid": MessageSid,
            })
        except Exception as e:
            logger.error(f"whatsapp_admin_log insert failed: {e}")
        return Response(content="<Response></Response>", media_type="application/xml")

    # --- Path 2: client reply — try to match to an existing case ---
    case = None
    if raw_from:
        case = await db.trust_cases.find_one(
            {"$or": [
                {"client_phone": raw_from},
                {"grantors.phone": raw_from},
            ]},
            {"_id": 0, "id": 1, "client_name": 1, "client_email": 1},
        )

    entry = {
        "id": str(uuid.uuid4()),
        "direction": "inbound",
        "from": raw_from,
        "profile_name": ProfileName or "",
        "body": text,
        "message_sid": MessageSid,
        "at": stamp,
    }
    if case:
        await db.trust_cases.update_one(
            {"id": case["id"]},
            {"$push": {"whatsapp_thread": entry}, "$set": {"updated_at": stamp}},
        )
        preview = text[:180] + ("…" if len(text) > 180 else "")
        notify.notify_admin(
            f"IGC WhatsApp reply from {case.get('client_name') or case.get('client_email') or raw_from}: \"{preview}\""
        )
    else:
        # Unmatched — still log to an inbox collection so nothing is lost
        await db.whatsapp_inbox.insert_one({**entry, "matched": False, "archived": False})
        notify.notify_admin(f"IGC WhatsApp: message from unknown number {raw_from}. Check inbox.")

    return Response(content="<Response></Response>", media_type="application/xml")


# ---------- WHATSAPP INBOX (unmatched senders) ----------
@api_router.get("/admin/whatsapp/inbox")
async def admin_whatsapp_inbox(_: dict = Depends(require_admin)):
    """Group all unarchived inbox messages by sender number. Newest thread first."""
    docs = await db.whatsapp_inbox.find(
        {"archived": {"$ne": True}}, {"_id": 0}
    ).sort("at", -1).to_list(500)
    threads: dict = {}
    for d in docs:
        key = d.get("from") or "unknown"
        t = threads.setdefault(key, {
            "from": key,
            "profile_name": d.get("profile_name") or "",
            "messages": [],
            "latest_at": d.get("at"),
        })
        t["messages"].append(d)
        if not t["latest_at"] or d.get("at", "") > t["latest_at"]:
            t["latest_at"] = d.get("at")
            if d.get("profile_name"):
                t["profile_name"] = d["profile_name"]
    return {"threads": sorted(threads.values(), key=lambda x: x["latest_at"] or "", reverse=True)}


class InboxAttachReq(BaseModel):
    from_number: str  # E.164 sender to attach
    case_id: str      # target case
    save_phone: bool = True  # if True, sets client_phone on the case for future auto-routing


@api_router.post("/admin/whatsapp/inbox/attach")
async def admin_whatsapp_inbox_attach(body: InboxAttachReq, admin: dict = Depends(require_admin)):
    """Move every unarchived inbox message from `from_number` into the given
    case's `whatsapp_thread[]`, and optionally record the sender's phone on
    the case so future replies auto-route."""
    case = await db.trust_cases.find_one({"id": body.case_id}, {"_id": 0, "id": 1})
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    docs = await db.whatsapp_inbox.find(
        {"from": body.from_number, "archived": {"$ne": True}}, {"_id": 0}
    ).sort("at", 1).to_list(500)
    if not docs:
        raise HTTPException(status_code=404, detail="No inbox messages for that number")
    stamp = now_iso()
    entries = [{
        "id": d.get("id") or str(uuid.uuid4()),
        "direction": "inbound",
        "from": d.get("from"),
        "profile_name": d.get("profile_name") or "",
        "body": d.get("body") or "",
        "message_sid": d.get("message_sid"),
        "at": d.get("at") or stamp,
        "attached_by": admin.get("email"),
        "attached_at": stamp,
    } for d in docs]
    updates: dict = {
        "$push": {"whatsapp_thread": {"$each": entries}},
        "$set": {"updated_at": stamp},
    }
    if body.save_phone:
        updates["$set"]["client_phone"] = body.from_number
    await db.trust_cases.update_one({"id": body.case_id}, updates)
    # Mark those inbox docs archived (they now live on the case)
    await db.whatsapp_inbox.update_many(
        {"from": body.from_number, "archived": {"$ne": True}},
        {"$set": {"archived": True, "attached_to_case": body.case_id, "archived_at": stamp}},
    )
    return {"ok": True, "attached": len(entries), "case_id": body.case_id}


@api_router.post("/admin/whatsapp/inbox/archive")
async def admin_whatsapp_inbox_archive(body: dict = Body(...), _: dict = Depends(require_admin)):
    """Archive all unarchived messages from a given sender (spam / handled)."""
    from_number = (body.get("from_number") or "").strip()
    if not from_number:
        raise HTTPException(status_code=400, detail="from_number required")
    res = await db.whatsapp_inbox.update_many(
        {"from": from_number, "archived": {"$ne": True}},
        {"$set": {"archived": True, "archived_at": now_iso()}},
    )
    return {"ok": True, "archived": res.modified_count}


# ---------- WHATSAPP CLIENT OPT-IN ----------
class WhatsAppOptInReq(BaseModel):
    opt_in: bool
    phone: Optional[str] = None  # override phone; falls back to primary grantor's phone


@api_router.post("/trust-cases/{case_id}/whatsapp-opt-in")
async def client_whatsapp_opt_in(case_id: str, body: WhatsAppOptInReq, user: dict = Depends(get_current_user)):
    """Client toggles WhatsApp notifications for their case. On first opt-in
    we fire a friendly welcome message (once); subsequent flips only update
    the flag."""
    case = await get_case(case_id, user)
    phone = (body.phone or "").strip() or _resolve_case_phone(case)
    updates: dict = {
        "whatsapp_opt_in": bool(body.opt_in),
        "whatsapp_opt_in_at": now_iso(),
    }
    if phone:
        updates["client_phone"] = phone
    await update_case(case_id, updates)

    welcomed = bool(case.get("whatsapp_welcomed_at"))
    sent = False
    if body.opt_in and phone and not welcomed:
        biz = "IGC Trust Portal"
        try:
            branding = await _branding_doc()
            biz = branding.get("business_name") or biz
        except Exception:
            pass
        name = (case.get("client_name") or "").split(" ")[0] or "there"
        text = (
            f"Hi {name} — thanks for starting your trust with {biz}. "
            "You'll get case updates on this channel. Reply here anytime "
            "with questions or documents."
        )
        sent = whatsapp.send_whatsapp(phone, text)
        entry = {
            "id": str(uuid.uuid4()),
            "direction": "outbound",
            "to": phone,
            "body": text,
            "at": now_iso(),
            "sent": bool(sent),
            "system": "welcome",
        }
        await db.trust_cases.update_one(
            {"id": case_id},
            {
                "$push": {"whatsapp_thread": entry},
                "$set": {"whatsapp_welcomed_at": now_iso()},
            },
        )
    return {"ok": True, "welcome_sent": bool(sent), "opt_in": bool(body.opt_in)}


# ---------- COMMAND-HANDLER WIRING ----------
async def _wa_update_status(case_id: str, new_status: str):
    """Called by whatsapp_commands to change a case status via WhatsApp."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    prev = (case or {}).get("status")
    await update_case(case_id, {"status": new_status})
    if case:
        case["status"] = new_status
        try:
            await _notify_status_change(case, prev_status=prev, new_status=new_status, source="whatsapp")
        except Exception as e:
            logger.error(f"_wa_update_status notify failed: {e}")


async def _wa_append_note(case_id: str, body_text: str) -> dict:
    """Called by whatsapp_commands to append an internal admin note via WhatsApp."""
    case = await db.trust_cases.find_one({"id": case_id}, {"_id": 0})
    if not case:
        raise ValueError("case not found")
    notes = case.get("admin_notes", [])
    note = {"id": new_id(), "note": body_text, "author": "WhatsApp Admin", "created_at": now_iso()}
    notes.append(note)
    await update_case(case_id, {"admin_notes": notes})
    return note


whatsapp_commands.configure(
    db=db,
    statuses=STATUSES,
    now_iso=now_iso,
    update_status=_wa_update_status,
    append_note=_wa_append_note,
)


# ---------- ROOT ----------
@api_router.get("/")
async def root():
    return {"status": "ok", "service": "trust-portal"}

# ---------- STARTUP ----------
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://trust.igcfirm.com",
        "https://trust-intake-portal.preview.emergentagent.com",  # keep preview working for QA
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """FastAPI lifespan startup. EVERY step is individually guarded because
    an unhandled exception here causes uvicorn to shut down cleanly (exit 0),
    which manifests as constant pod restarts on Kubernetes with no request
    logs. Individual failures are logged and the app keeps running so at
    least the API surface stays up while an admin investigates."""
    logger.info("Lifespan startup begin")

    # --- Indexes --- MongoDB raises OperationFailure if a previously-created
    # index has different options (VERY common with TTL indexes across deploys).
    # Wrap each one individually so a single conflict cannot brick the app.
    def _idx(coll, spec, **kwargs):
        return coll, spec, kwargs

    _index_defs = [
        _idx(db.users, "email", unique=True),
        _idx(db.users, "id", unique=True),
        _idx(db.trust_cases, "id", unique=True),
        _idx(db.trust_cases, "client_id"),
        _idx(db.messages, [("case_id", 1), ("created_at", 1)]),
        _idx(db.login_attempts, "identifier"),
        _idx(db.password_reset_tokens, "expires_at", expireAfterSeconds=3600),
        _idx(db.invites, "token", unique=True),
        _idx(db.invites, "expires_at", expireAfterSeconds=0),
        _idx(db.questions, [("case_id", 1), ("created_at", 1)]),
        _idx(db.questions, "status"),
        _idx(db.monthly_summaries, "period", unique=True),
    ]
    for coll, spec, kwargs in _index_defs:
        try:
            await coll.create_index(spec, **kwargs)
        except Exception as e:
            logger.warning(f"Index create skipped on {coll.name}({spec}): {e}")

    # --- Stuck-job sweep ---
    try:
        await extract_jobs.sweep_stuck_jobs_on_startup(db, update_case)
    except Exception as e:
        logger.warning(f"extract_jobs sweep on startup failed: {e}")

    try:
        await page_explanation_jobs.sweep_stuck_jobs_on_startup(db, update_case)
    except Exception as e:
        logger.warning(f"page_explanation_jobs sweep on startup failed: {e}")

    # --- Seed admin --- bcrypt raises ValueError on malformed hashes, and the
    # password_hash key may be missing on legacy admin docs. Both must be caught.
    try:
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
        else:
            stored_hash = existing.get("password_hash") or ""
            needs_refresh = False
            if not stored_hash:
                needs_refresh = True
            else:
                try:
                    needs_refresh = not verify_password(admin_password, stored_hash)
                except Exception as ve:
                    # Malformed bcrypt hash on prod admin doc — refresh it.
                    logger.warning(f"Admin password_hash verify failed ({ve}); refreshing")
                    needs_refresh = True
            if needs_refresh:
                await db.users.update_one(
                    {"email": admin_email},
                    {"$set": {"password_hash": hash_password(admin_password), "role": "admin"}},
                )
                logger.info(f"Admin password refreshed: {admin_email}")
    except Exception as e:
        logger.error(f"Admin seed step failed (non-fatal): {e}")

    # --- Init object storage (already defensively wrapped internally) ---
    try:
        init_storage()
    except Exception as e:
        logger.error(f"init_storage failed (non-fatal): {e}")

    # --- Background schedulers ---
    try:
        asyncio.create_task(_monthly_summary_scheduler())
    except Exception as e:
        logger.error(f"Monthly summary scheduler failed to start: {e}")

    logger.info("Lifespan startup complete")


# ---------- MONTHLY SUMMARY EMAIL (fires on the 1st of every month) ----------

def _previous_month(now: datetime) -> tuple[int, int]:
    """Returns (year, month) for the calendar month before `now` (UTC)."""
    if now.month == 1:
        return (now.year - 1, 12)
    return (now.year, now.month - 1)


def _month_bounds_iso(year: int, month: int) -> tuple[str, str]:
    """ISO date strings (YYYY-MM-DD) for the first and last day of the given month."""
    first = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        last = datetime(year, 12, 31, tzinfo=timezone.utc)
    else:
        last = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    return (first.date().isoformat(), last.date().isoformat())


async def _build_and_send_monthly_summary(year: int, month: int) -> dict:
    """Build CSV + stats for the given month and email it to ADMIN_NOTIFY_EMAIL.
    Idempotent: writes a `monthly_summaries` doc keyed on YYYY-MM so re-runs no-op.
    Returns a dict with the headline stats."""
    import csv as _csv
    period = f"{year:04d}-{month:02d}"
    existing = await db.monthly_summaries.find_one({"period": period}, {"_id": 0})
    if existing and existing.get("sent_at"):
        return {"period": period, "already_sent": True, **existing}

    since, until = _month_bounds_iso(year, month)
    # Inclusive range on updated_at (ISO strings).
    flt = {
        "updated_at": {"$gte": since, "$lte": f"{until}T23:59:59.999999+00:00"},
        "archived": {"$ne": True},
    }
    cases = await db.trust_cases.find(flt, {"_id": 0}).sort("updated_at", -1).to_list(5000)

    # Headline stats
    total = len(cases)
    completed = sum(1 for c in cases if c.get("status") == "Completed")
    paid = sum(1 for c in cases if (c.get("payment") or {}).get("status") in ("paid", "verified"))
    collected_cents = sum(
        ((c.get("payment") or {}).get("amount_cents") or 0)
        for c in cases
        if (c.get("payment") or {}).get("status") in ("paid", "verified")
    )
    by_status: dict = {}
    by_path = {"new": 0, "review": 0}
    for c in cases:
        s = c.get("status") or "Unknown"
        by_status[s] = by_status.get(s, 0) + 1
        by_path[(c.get("intake_path") or "new")] = by_path.get(c.get("intake_path") or "new", 0) + 1

    # Build CSV bytes
    buf = io.StringIO()
    w = _csv.writer(buf)
    w.writerow([
        "case_id", "client_name", "client_email", "client_phone",
        "trust_name", "intake_path", "trust_type", "status",
        "amount_usd", "payment_status", "credit_repair_released",
        "credit_repair_released_at", "created_at", "updated_at",
    ])
    for c in cases:
        p = c.get("payment") or {}
        amt_cents = p.get("amount_cents")
        amt_usd = f"{amt_cents/100:.2f}" if amt_cents else ""
        w.writerow([
            c.get("id", ""), c.get("client_name", ""), c.get("client_email", ""),
            c.get("client_phone", ""), c.get("trust_name", ""),
            c.get("intake_path", "new"), c.get("trust_type", ""), c.get("status", ""),
            amt_usd, p.get("status", ""),
            "yes" if c.get("credit_repair_released") else "no",
            c.get("credit_repair_released_at", ""),
            c.get("created_at", ""), c.get("updated_at", ""),
        ])
    csv_bytes = buf.getvalue().encode("utf-8")

    # Compose email
    branding = await _branding_doc()
    biz = branding.get("business_name", "Trust Portal")
    accent = branding.get("accent_color", "#C5A880")
    primary = branding.get("primary_color", "#1C252E")
    month_label = datetime(year, month, 1).strftime("%B %Y")
    collected_usd = f"${collected_cents/100:,.2f}"
    by_status_rows = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#64748B;">{s}</td><td style="padding:4px 0;font-weight:600;">{n}</td></tr>'
        for s, n in sorted(by_status.items(), key=lambda x: -x[1])
    )
    inner = f"""
<p style="font-size:22px;margin:0 0 12px 0;font-family:Georgia,serif;">Monthly summary — {month_label}</p>
<p style="font-size:15px;color:#334155;margin:0 0 18px 0;">
    <b>{total}</b> cases · <b>{completed}</b> completed · <b>{paid}</b> paid · <b>{collected_usd}</b> collected
</p>
<p style="font-size:13px;color:#64748B;margin:0 0 6px 0;">Paths: <b>{by_path.get('new',0)}</b> new trust · <b>{by_path.get('review',0)}</b> existing review</p>
<table style="border-collapse:collapse;margin:8px 0 18px 0;font-size:13px;">{by_status_rows}</table>
<p style="font-size:13px;color:#64748B;">The full case list for {month_label} is attached as a CSV.</p>
"""
    html = _email_shell(biz, primary, accent, inner)
    subject = f"[{biz}] Monthly summary — {month_label} ({total} cases, {collected_usd})"
    fname = f"trust-cases-{period}.csv"

    if not ADMIN_NOTIFY_EMAIL:
        logger.warning("Monthly summary: ADMIN_NOTIFY_EMAIL not set — skipping send")
        return {"period": period, "skipped": "no_admin_email", "total": total}

    sent = False
    try:
        await send_email_notification_with_attachment(
            to_email=ADMIN_NOTIFY_EMAIL,
            subject=subject,
            html_body=html,
            attachment_name=fname,
            attachment_bytes=csv_bytes,
            content_type="text/csv",
        )
        sent = True
    except Exception as e:
        logger.error(f"Monthly summary email failed: {e}")

    record = {
        "period": period,
        "sent_at": now_iso() if sent else None,
        "total": total,
        "completed": completed,
        "paid": paid,
        "collected_cents": collected_cents,
        "by_status": by_status,
        "by_path": by_path,
    }
    await db.monthly_summaries.update_one(
        {"period": period},
        {"$set": record},
        upsert=True,
    )
    return record


async def _monthly_summary_scheduler():
    """Background task: every 6 hours, check if today is on/after the 1st and
    we haven't yet sent the previous month's summary. If so, send it.
    Idempotent via the unique `period` index."""
    # Small startup delay so we don't compete with index creation.
    await asyncio.sleep(60)
    while True:
        try:
            now = datetime.now(timezone.utc)
            prev_year, prev_month = _previous_month(now)
            period = f"{prev_year:04d}-{prev_month:02d}"
            existing = await db.monthly_summaries.find_one({"period": period}, {"_id": 0, "sent_at": 1})
            if not existing or not existing.get("sent_at"):
                # Only attempt on the 1st-5th of the month (window of forgiveness for downtime)
                if now.day <= 5:
                    logger.info(f"Monthly summary: dispatching {period}")
                    await _build_and_send_monthly_summary(prev_year, prev_month)
        except Exception as e:
            logger.error(f"Monthly summary scheduler tick failed: {e}")
        await asyncio.sleep(6 * 3600)  # every 6 hours


@app.on_event("shutdown")
async def shutdown():
    client.close()
