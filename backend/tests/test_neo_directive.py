"""
NEO Directive backend tests — Stripe, Reps/Managers, Rep referral,
Commission engine, Nia AI assistant, WhatsApp APPROVE/DENY.
"""
import os
import uuid
import asyncio
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trust-intake-portal.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"

# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def client_session():
    s = requests.Session()
    email = f"neo_client_{uuid.uuid4().hex[:8]}@test.example"
    r = s.post(f"{API}/auth/register", json={
        "email": email, "password": "Client12345!", "name": "Neo Client"
    })
    assert r.status_code in (200, 201), f"client register failed: {r.status_code} {r.text}"
    # Some backends do auto-login; login just in case.
    s.post(f"{API}/auth/login", json={"email": email, "password": "Client12345!"})
    s.email = email
    return s


@pytest.fixture(scope="module")
def created_ids():
    return {"reps": [], "managers": [], "commissions": [], "cases": []}


# ---------------- Stripe health & catalog ----------------

class TestStripe:
    def test_stripe_health(self, admin_session):
        r = admin_session.get(f"{API}/admin/stripe/health")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("enabled") is True
        assert d.get("mode") == "test"
        assert (d.get("account_id") or "").startswith("acct_"), d

    def test_setup_catalog_idempotent(self, admin_session):
        r1 = admin_session.post(f"{API}/admin/stripe/setup-catalog")
        assert r1.status_code == 200, r1.text
        prices1 = r1.json().get("prices", {})
        assert "basic_living_trust" in prices1 and prices1["basic_living_trust"].startswith("price_")
        assert "private_trust" in prices1 and prices1["private_trust"].startswith("price_")
        # Idempotent
        r2 = admin_session.post(f"{API}/admin/stripe/setup-catalog")
        assert r2.status_code == 200
        prices2 = r2.json().get("prices", {})
        assert prices1["basic_living_trust"] == prices2["basic_living_trust"]
        assert prices1["private_trust"] == prices2["private_trust"]


# ---------------- Managers & Reps CRUD ----------------

class TestManagersReps:
    def test_manager_crud(self, admin_session, created_ids):
        # Create
        email = f"mgr_{uuid.uuid4().hex[:6]}@test.example"
        r = admin_session.post(f"{API}/admin/managers", json={
            "name": "Test Mgr", "email": email, "phone": "5551110000"
        })
        assert r.status_code == 200, r.text
        m = r.json()["manager"]
        assert m["email"] == email
        created_ids["managers"].append(m["id"])
        # List
        rl = admin_session.get(f"{API}/admin/managers")
        assert rl.status_code == 200
        assert any(x["id"] == m["id"] for x in rl.json()["managers"])
        # Update
        ru = admin_session.put(f"{API}/admin/managers/{m['id']}", json={
            "name": "Test Mgr Updated", "email": email, "phone": "5551110001"
        })
        assert ru.status_code == 200
        assert ru.json()["manager"]["name"] == "Test Mgr Updated"

    def test_rep_crud_and_duplicate(self, admin_session, created_ids):
        code = f"TESTREP{uuid.uuid4().hex[:4].upper()}"
        r = admin_session.post(f"{API}/admin/reps", json={
            "name": "Alice Test", "email": f"rep_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code.lower(),  # deliberately lowercase to check auto-upper
            "phone": "5552220000"
        })
        assert r.status_code == 200, r.text
        rep = r.json()["rep"]
        assert rep["rep_code"] == code
        created_ids["reps"].append(rep["id"])

        # Duplicate rep_code
        dup = admin_session.post(f"{API}/admin/reps", json={
            "name": "Dup", "email": f"dup_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code,
        })
        assert dup.status_code == 409, dup.text

        # Update
        upd = admin_session.put(f"{API}/admin/reps/{rep['id']}", json={
            "name": "Alice Renamed", "email": rep["email"],
            "rep_code": code, "phone": "5559990000"
        })
        assert upd.status_code == 200
        assert upd.json()["rep"]["name"] == "Alice Renamed"

    def test_rep_resolve_public(self, admin_session, created_ids):
        # create fresh rep
        code = f"RESOLV{uuid.uuid4().hex[:4].upper()}"
        r = admin_session.post(f"{API}/admin/reps", json={
            "name": "Resolve Rep", "email": f"rr_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code
        })
        assert r.status_code == 200
        created_ids["reps"].append(r.json()["rep"]["id"])
        # public resolve (no auth)
        s = requests.Session()
        got = s.get(f"{API}/reps/resolve/{code.lower()}")  # test case-insensitive
        assert got.status_code == 200, got.text
        j = got.json()
        assert j["rep_code"] == code
        assert j["rep_name"] == "Resolve Rep"
        # 404
        miss = s.get(f"{API}/reps/resolve/NOPE_{uuid.uuid4().hex[:4]}")
        assert miss.status_code == 404

    def test_delete_manager_unassigns_reps(self, admin_session, created_ids):
        # create manager
        me = f"mgrdel_{uuid.uuid4().hex[:6]}@test.example"
        m = admin_session.post(f"{API}/admin/managers", json={
            "name": "Del Mgr", "email": me
        }).json()["manager"]
        # create rep pointing to it
        code = f"DELREP{uuid.uuid4().hex[:4].upper()}"
        rep = admin_session.post(f"{API}/admin/reps", json={
            "name": "Del Rep", "email": f"delrep_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code, "manager_id": m["id"]
        }).json()["rep"]
        created_ids["reps"].append(rep["id"])
        # delete manager
        d = admin_session.delete(f"{API}/admin/managers/{m['id']}")
        assert d.status_code == 200
        # verify rep unassigned via list
        reps_list = admin_session.get(f"{API}/admin/reps").json()["reps"]
        for r in reps_list:
            if r["id"] == rep["id"]:
                assert r.get("manager_id") in (None, "")
                break


# ---------------- Trust case with rep_code ----------------

class TestCaseWithRep:
    def test_create_case_with_rep(self, admin_session, client_session, created_ids):
        code = f"CASE{uuid.uuid4().hex[:5].upper()}"
        r = admin_session.post(f"{API}/admin/reps", json={
            "name": "Case Rep", "email": f"cr_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code
        })
        assert r.status_code == 200
        rep_id = r.json()["rep"]["id"]
        created_ids["reps"].append(rep_id)

        rc = client_session.post(f"{API}/trust-cases", json={
            "rep_code": code, "trust_type": "single", "intake_path": "new",
            "trust_name": "TEST Rep Case", "client_phone": "5551234567"
        })
        assert rc.status_code == 200, rc.text
        case = rc.json()
        cid = case.get("id") or case.get("case", {}).get("id")
        assert cid
        # Fetch case via admin to verify persistence
        got = admin_session.get(f"{API}/admin/trust-cases/{cid}")
        # some builds expose under /admin/trust-cases, some under /trust-cases
        if got.status_code == 404:
            got = client_session.get(f"{API}/trust-cases/{cid}")
        assert got.status_code == 200, got.text
        gj = got.json()
        assert gj.get("rep_code") == code, gj
        assert gj.get("referral") and gj["referral"]["rep_code"] == code
        created_ids["cases"].append(cid)


# ---------------- Stripe checkout ----------------

class TestStripeCheckout:
    def test_admin_cannot_start_checkout(self, admin_session, created_ids):
        # need a case that the admin has access to; use one from prior fixture.
        if not created_ids["cases"]:
            pytest.skip("no case available")
        cid = created_ids["cases"][0]
        r = admin_session.post(f"{API}/trust-cases/{cid}/stripe/checkout", json={
            "lookup_key": "basic_living_trust",
            "origin_url": "https://example.com"
        })
        assert r.status_code == 400, r.text

    def test_client_checkout_session(self, client_session, created_ids):
        if not created_ids["cases"]:
            pytest.skip("no case available")
        cid = created_ids["cases"][0]
        r = client_session.post(f"{API}/trust-cases/{cid}/stripe/checkout", json={
            "lookup_key": "basic_living_trust",
            "origin_url": "https://example.com"
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://")
        assert d.get("session_id", "").startswith("cs_")
        created_ids["checkout_session_id"] = d["session_id"]

    def test_payment_status_poll(self, client_session, created_ids):
        sid = created_ids.get("checkout_session_id")
        if not sid:
            pytest.skip("no session")
        r = requests.get(f"{API}/payments/status/{sid}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "status" in d and "payment_status" in d


# ---------------- Commission split (calls internal helper via direct DB) ----------------

class TestCommissionEngine:
    """We simulate a paid Stripe payment by injecting a payment_transactions
    doc + a case with a given rep, then calling the server helper via the
    async event loop.
    """

    @pytest.mark.parametrize("lookup_key,has_manager,exp_rep,exp_mgr", [
        ("basic_living_trust", False, 50000, 0),
        ("basic_living_trust", True, 45000, 5000),
        ("private_trust", False, 80000, 0),
        ("private_trust", True, 72000, 8000),
    ])
    def test_split(self, admin_session, lookup_key, has_manager, exp_rep, exp_mgr):
        # Create rep (+ optional manager)
        mgr_id = None
        if has_manager:
            m = admin_session.post(f"{API}/admin/managers", json={
                "name": "Split Mgr", "email": f"sm_{uuid.uuid4().hex[:6]}@test.example"
            }).json()["manager"]
            mgr_id = m["id"]
        code = f"SPL{uuid.uuid4().hex[:5].upper()}"
        rep = admin_session.post(f"{API}/admin/reps", json={
            "name": "Split Rep", "email": f"sr_{uuid.uuid4().hex[:6]}@test.example",
            "rep_code": code, "manager_id": mgr_id
        }).json()["rep"]

        # Create client + case with this rep
        cs = requests.Session()
        email = f"sc_{uuid.uuid4().hex[:6]}@test.example"
        cs.post(f"{API}/auth/register", json={"email": email, "password": "Client12345!", "name": "SC"})
        cs.post(f"{API}/auth/login", json={"email": email, "password": "Client12345!"})
        cj = cs.post(f"{API}/trust-cases", json={
            "rep_code": code, "trust_type": "single", "intake_path": "new",
            "trust_name": "TEST split", "client_phone": "5550000000"
        }).json()
        cid = cj["id"]

        # Kick off checkout to create the payment_transactions row
        chk = cs.post(f"{API}/trust-cases/{cid}/stripe/checkout", json={
            "lookup_key": lookup_key, "origin_url": "https://example.com"
        })
        assert chk.status_code == 200, chk.text
        sid = chk.json()["session_id"]

        # Force apply-paid via internal helper by calling server code directly
        import sys, importlib
        sys.path.insert(0, "/app/backend")
        # Load backend .env so MONGO_URL is available
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        server = importlib.import_module("server")

        async def _run():
            from motor.motor_asyncio import AsyncIOMotorClient
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            new_db = client[os.environ["DB_NAME"]]
            # rebind db globally so helper uses this loop's client
            server.db = new_db
            # Post-refactor: routers read state.db from routes._neo_state
            from routes._neo_state import state as _neo_state
            _neo_state.db = new_db
            import commissions as cm
            import notify as _n
            # silence WhatsApp
            _n.notify_admin = lambda *a, **k: None
            await new_db.payment_transactions.update_one(
                {"session_id": sid},
                {"$set": {"status": "completed", "payment_status": "paid"}},
            )
            await server._stripe_apply_paid(sid)
            comm = await new_db.commissions.find_one(
                {"case_id": cid, "lookup_key": lookup_key}, {"_id": 0}
            )
            client.close()
            return comm

        comm = asyncio.run(_run())

        assert comm is not None, f"commission not created for {lookup_key} has_manager={has_manager}"
        assert comm["rep_cents"] == exp_rep, comm
        assert comm["manager_cents"] == exp_mgr, comm
        assert comm["status"] == "pending_approval"
        assert len(comm["approval_code"]) >= 4 and comm["approval_code"].isupper()

        # Save for approve/deny tests
        if lookup_key == "basic_living_trust" and not has_manager:
            TestCommissionEngine._basic_solo = comm
        elif lookup_key == "private_trust" and has_manager:
            TestCommissionEngine._private_mgr = comm

    def test_approve_via_api(self, admin_session):
        c = getattr(self, "_basic_solo", None)
        if not c:
            pytest.skip("no commission")
        r = admin_session.post(f"{API}/admin/commissions/{c['id']}/approve", json={})
        assert r.status_code == 200, r.text
        assert r.json()["commission"]["status"] == "approved"

    def test_deny_via_api(self, admin_session):
        c = getattr(self, "_private_mgr", None)
        if not c:
            pytest.skip("no commission")
        r = admin_session.post(f"{API}/admin/commissions/{c['id']}/deny", json={})
        assert r.status_code == 200, r.text
        assert r.json()["commission"]["status"] == "denied"

    def test_whatsapp_approve_command(self):
        """Approve via WhatsApp handler directly (creates fresh commission)."""
        import sys, importlib
        sys.path.insert(0, "/app/backend")
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
        server = importlib.import_module("server")
        wc = importlib.import_module("whatsapp_commands")

        async def _run():
            from motor.motor_asyncio import AsyncIOMotorClient
            client = AsyncIOMotorClient(os.environ["MONGO_URL"])
            new_db = client[os.environ["DB_NAME"]]
            server.db = new_db
            # Post-refactor: routers read state.db from routes._neo_state
            from routes._neo_state import state as _neo_state
            _neo_state.db = new_db
            # Re-wire whatsapp_commands to point at our approve/deny closures
            wc.configure(
                db=new_db, statuses=[], now_iso=server.now_iso,
                update_status=lambda *a, **k: None,
                append_note=lambda *a, **k: None,
                approve_commission=server._wa_approve_commission,
                deny_commission=server._wa_deny_commission,
            )
            pending = await new_db.commissions.find_one({"status": "pending_approval"}, {"_id": 0})
            if not pending:
                client.close()
                return None
            reply = await wc.handle_admin_command(
                f"APPROVE {pending['approval_code']}",
                "+19545983681", "support@igcfirm.com"
            )
            after = await new_db.commissions.find_one({"id": pending["id"]}, {"_id": 0})
            client.close()
            return reply, after

        res = asyncio.run(_run())
        if res is None:
            pytest.skip("no pending commission")
        reply, after = res
        assert "APPROVED" in reply.upper() or "already" in reply.lower(), reply
        assert after["status"] == "approved", after


# ---------------- Nia AI Assistant ----------------

class TestNia:
    def test_chat_basic(self):
        sid = f"nia_test_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/nia/chat", json={
            "message": "What is a successor trustee?",
            "session_id": sid
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("reply") and len(d["reply"]) > 5, d
        assert d.get("urgent") is False
        # History
        h = requests.get(f"{API}/nia/history/{sid}")
        assert h.status_code == 200
        turns = h.json()["turns"]
        assert len(turns) >= 2
        assert turns[0]["role"] == "user"
        assert turns[1]["role"] == "assistant"

    @pytest.mark.parametrize("msg", [
        "I want a refund now",
        "This is a scam, I'll file a lawsuit",
        "I want to speak to a human",
        "please connect me with an attorney",
    ])
    def test_urgent_flag(self, msg):
        sid = f"nia_urg_{uuid.uuid4().hex[:8]}"
        r = requests.post(f"{API}/nia/chat", json={
            "message": msg, "session_id": sid
        })
        assert r.status_code == 200, r.text
        assert r.json()["urgent"] is True, r.json()
