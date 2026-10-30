"""Seed a TEST client + fully complete 'new' case (not submitted) for UI submit testing."""
import io, uuid, requests
BASE = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL")][0].rstrip("/")
API = f"{BASE}/api"
tag = uuid.uuid4().hex[:6]
email, pw = f"test_freenav_ui_{tag}@example.com", "Client12345!"
requests.post(f"{API}/auth/register", json={"email": email, "password": pw, "name": "TEST FreeNav UI"}, timeout=20)
c = requests.Session(); c.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
cid = c.post(f"{API}/trust-cases", json={"trust_type": "single", "trust_name": f"TEST_FREENAV_UI_{tag}", "intake_path": "new"}).json()["id"]
addr = {"line1": "1 Main St", "city": "Austin", "state": "TX", "zip": "78701"}
c.post(f"{API}/trust-cases/{cid}/grantors", json={"full_legal_name": "TEST Grantor", "date_of_birth": "1980-01-01", "ssn": "123-45-6789", "phone": "5125550100", "email": "tg@example.com", "address": addr, "marital_status": "single", "citizenship": "US"})
c.put(f"{API}/trust-cases/{cid}/trustee", json={"full_legal_name": "TEST Trustee", "relationship": "self", "phone": "5125550101", "email": "tt@example.com"})
c.post(f"{API}/trust-cases/{cid}/successor-trustees", json={"full_legal_name": "TEST Succ", "relationship": "sibling", "phone": "5125550102", "email": "ts@example.com"})
c.post(f"{API}/trust-cases/{cid}/beneficiaries", json={"full_legal_name": "TEST Ben", "date_of_birth": "2010-01-01", "relationship": "child", "percentage": 100})
c.put(f"{API}/trust-cases/{cid}/acknowledgments", json={"no_assets_ack": True})
c.put(f"{API}/trust-cases/{cid}/ein", json={"authorized": True})
PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
for dt in ("government_id", "proof_of_address"):
    c.post(f"{API}/trust-cases/{cid}/documents", data={"doc_type": dt}, files={"file": (f"{dt}.pdf", io.BytesIO(PDF), "application/pdf")}, timeout=30)
print(email, pw, cid, c.get(f"{API}/trust-cases/{cid}").json()["status"])
