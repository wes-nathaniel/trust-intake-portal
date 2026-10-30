# Seed a TEST client with a trust case for password-feature UI testing
import os, time, requests
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
email = f"test_pwui_{int(time.time())}@igchq-test.com"
s = requests.Session()
r = s.post(f"{BASE}/api/auth/register", json={"email": email, "password": "InitPass123", "name": "TEST PwUI Client"})
print("register", r.status_code, r.text[:200])
r = s.post(f"{BASE}/api/trust-cases", json={"intake_path": "new", "trust_name": "TEST PwUI Trust", "client_phone": "5555551234", "trust_type": "single"})
print("case", r.status_code, r.text[:300])
print("EMAIL", email, "CASE", r.json().get("id"))
