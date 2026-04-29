"""
Sets up a fresh case ready for the Payment UI test:
- Registers a new client
- Creates a trust case
- Sets all acknowledgments (state_laws, notarization, disclosure, review_completed)
- Logs in as admin and uploads a trust draft PDF (so /portal/trust-preview renders)
Prints client_email|client_password|case_id on the last line.
"""
import io, os, sys, uuid, requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://trust-intake-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"


def make_pdf():
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    for i in range(2):
        c.setFont("Helvetica", 14)
        c.drawString(72, 720, f"IGC Payment-UI Test Trust — Page {i+1}")
        c.showPage()
    c.save()
    return buf.getvalue()


def main():
    # 1. Register client
    cs = requests.Session()
    email = f"paytest_{uuid.uuid4().hex[:8]}@example.com"
    password = "PayTest12345!"
    r = cs.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Pay Test"})
    assert r.status_code == 200, r.text

    # 2. Create case
    r = cs.post(f"{API}/trust-cases", json={"trust_type": "single", "trust_name": "TEST Payment Trust"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]

    # 3. Acknowledgments incl review_completed_ack so PaymentMethodPicker renders
    r = cs.put(f"{API}/trust-cases/{cid}/acknowledgments", json={
        "state_laws_ack": True,
        "notarization_ack": True,
        "disclosure_ack": True,
        "review_completed_ack": True,
    })
    assert r.status_code == 200, r.text

    # 4. Admin login + upload trust draft
    asn = requests.Session()
    r = asn.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    files = {"file": ("draft.pdf", io.BytesIO(make_pdf()), "application/pdf")}
    r = asn.post(f"{API}/admin/trust-cases/{cid}/trust-draft", files=files)
    assert r.status_code == 200, r.text

    print(f"RESULT|{email}|{password}|{cid}")


if __name__ == "__main__":
    main()
