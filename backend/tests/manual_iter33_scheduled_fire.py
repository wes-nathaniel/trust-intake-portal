# Manual (slow ~4 min) check: scheduled release fires with the snapshot status, not the latest internal one.
import os, time, uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
a = requests.Session()
assert a.post(f"{API}/auth/login", json={"email": "support@igcfirm.com", "password": "Wllorenzo03!"}).status_code == 200
c = requests.Session()
email = f"test_sched_{uuid.uuid4().hex[:8]}@example.com"
c.post(f"{API}/auth/register", json={"email": email, "password": "Test12345!Aa", "name": "TEST Sched"})
cid = c.post(f"{API}/trust-cases", json={"trust_type": "single"}).json()["id"]
a.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "Ready for Payment"})
at = (datetime.now(ZoneInfo("America/New_York")) + timedelta(minutes=2, seconds=30)).strftime("%Y-%m-%dT%H:%M")
r = a.post(f"{API}/admin/trust-cases/{cid}/release", json={"mode": "schedule", "release_at": at, "send_email": False})
print("schedule", r.status_code, r.json().get("scheduled", {}).get("release_at_local"))
a.put(f"{API}/admin/trust-cases/{cid}/status", json={"status": "Completed"})
print("client before:", c.get(f"{API}/trust-cases/{cid}/status").json())
for i in range(16):
    time.sleep(20)
    p = a.get(f"{API}/admin/trust-cases/{cid}/release").json()
    if not p["scheduled_release"]:
        break
print("client after:", c.get(f"{API}/trust-cases/{cid}/status").json())
print("preview after:", {k: p[k] for k in ("internal_status", "client_status", "scheduled_release")}, p["history"][:1])
print("CASE", cid, email)
