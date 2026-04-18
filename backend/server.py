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
async def send_email_notification(to_email: str, subject: str, html_body: str):
    if not RESEND_API_KEY:
        logger.info(f"[email-mock] to={to_email} subject={subject}")
        return
    try:
        params = {"from": SENDER_EMAIL, "to": [to_email], "subject": subject, "html": html_body}
        await asyncio.to_thread(resend.Emails.send, params)
    except Exception as e:
        logger.error(f"Resend send failed: {e}")

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
    return case

@api_router.get("/trust-cases/mine")
async def my_cases(user: dict = Depends(get_current_user)):
    cases = await db.trust_cases.find({"client_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return cases

@api_router.get("/trust-cases/{case_id}")
async def get_case_endpoint(case_id: str, user: dict = Depends(get_current_user)):
    return await get_case(case_id, user)

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
@api_router.post("/trust-cases/{case_id}/beneficiaries")
async def add_beneficiary(case_id: str, b: Beneficiary, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    bens = case.get("beneficiaries", [])
    bens.append(b.model_dump())
    await update_case(case_id, {"beneficiaries": bens})
    return b.model_dump()

@api_router.put("/trust-cases/{case_id}/beneficiaries/{bid}")
async def update_beneficiary(case_id: str, bid: str, b: Beneficiary, user: dict = Depends(get_current_user)):
    case = await get_case(case_id, user)
    bens = case.get("beneficiaries", [])
    for i, x in enumerate(bens):
        if x["id"] == bid:
            data = b.model_dump(); data["id"] = bid; bens[i] = data
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
    return case

@api_router.put("/admin/trust-cases/{case_id}/status")
async def admin_update_status(case_id: str, body: StatusUpdate, admin: dict = Depends(require_admin)):
    if body.status not in STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    await update_case(case_id, {"status": body.status})
    return {"ok": True, "status": body.status}

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

@api_router.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_admin)):
    total = await db.trust_cases.count_documents({})
    by_status = {}
    for s in STATUSES:
        by_status[s] = await db.trust_cases.count_documents({"status": s})
    clients = await db.users.count_documents({"role": "client"})
    return {"total_cases": total, "total_clients": clients, "by_status": by_status}

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
