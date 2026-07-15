"""Iteration 20 — tests for resumability of the page-explain background job.

- Partial persistence: while status='pending', explanations list grows.
- Restart resume: sudo supervisorctl restart backend during a live job MUST
  either resume from batches_done (log 'page-explain sweep: RESUMED case ...')
  OR mark it failed with the 'Server restarted' message. In BOTH branches,
  previously-persisted explanations must still be present.
- Banned-jargon regression on the final 6 pages.
"""
import os
import time
import subprocess
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "support@igcfirm.com"
ADMIN_PASSWORD = "Wllorenzo03!"
CASE_ID = "8eb42bd3-5d43-43f2-b765-b98a144bd931"
BANNED = ["settlor", "per stirpes", "corpus", "in terrorem",
          "spendthrift", "hereinafter", "aforementioned", "fiduciary"]


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{BASE_URL}/api/auth/login",
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                  timeout=30)
    assert r.status_code == 200, r.text
    return sess


def _get(s):
    r = s.get(f"{BASE_URL}/api/trust-cases/{CASE_ID}/trust-page-explanations",
              timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _regen(s):
    r = s.post(
        f"{BASE_URL}/api/admin/trust-cases/{CASE_ID}"
        f"/trust-page-explanations/regenerate",
        timeout=30,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _wait_completed(s, deadline_sec=240):
    deadline = time.time() + deadline_sec
    last = None
    while time.time() < deadline:
        last = _get(s)
        if last["status"] == "completed" and len(last["explanations"]) >= 6:
            return last
        if last["status"] == "failed":
            return last
        time.sleep(5)
    return last


# ---- 1. Partial persistence while running ----
def test_partial_persistence_during_run(s):
    j = _regen(s)
    assert "task_id" in j
    # Poll every ~5s; look for a snapshot where 0 < len(explanations) < pages_total
    saw_partial = False
    saw_zero_then_more = False
    prev_len = None
    deadline = time.time() + 90
    while time.time() < deadline:
        data = _get(s)
        n = len(data.get("explanations") or [])
        pt = data.get("pages_total") or 0
        st = data.get("status")
        if prev_len is not None and n > prev_len:
            saw_zero_then_more = True
        prev_len = n
        if st == "pending" and pt and 0 < n < pt:
            saw_partial = True
            break
        if st == "completed":
            break
        time.sleep(4)
    # Either we caught a partial snapshot OR we saw the count grow between polls
    assert saw_partial or saw_zero_then_more, (
        f"never saw partial persistence — last n={prev_len}, last={data}"
    )


# ---- 2. Final run completes clean, 6 pages, no banned jargon ----
def test_final_completes_and_no_banned_jargon(s):
    final = _wait_completed(s, 240)
    assert final and final["status"] == "completed", f"did not complete: {final}"
    assert final["pages_total"] == 6, final
    assert len(final["explanations"]) == 6, final
    joined = "\n".join(e["text"] for e in final["explanations"]).lower()
    hits = [b for b in BANNED if b in joined]
    assert not hits, f"banned words leaked: {hits}"


# ---- 3. Restart mid-run: either resume or mark failed, but priors preserved ----
def test_restart_mid_run_preserves_priors(s):
    # Kick off a fresh regen
    _regen(s)
    # Wait so batch 1 has persisted but 2+3 not yet done
    time.sleep(12)
    before = _get(s)
    pages_before = len(before.get("explanations") or [])
    print(f"before restart: pages_done={pages_before} status={before['status']}")

    # Restart backend via supervisor (Popen — restart can be slow during load)
    proc = subprocess.Popen(["sudo", "supervisorctl", "restart", "backend"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
    # give it time to boot and run sweep
    time.sleep(10)
    # Re-login (cookies survive but session may drop)
    s2 = requests.Session()
    r = s2.post(f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=30)
    assert r.status_code == 200
    after = _get(s2)
    pages_after = len(after.get("explanations") or [])
    print(f"after restart: pages_done={pages_after} status={after['status']} "
          f"error={after.get('error')}")
    # Priors from before the restart must still be present
    assert pages_after >= pages_before, (
        f"lost persisted priors: before={pages_before} after={pages_after}"
    )
    # Either resumed to completion or marked failed with the specific message
    if after["status"] == "failed":
        assert "regenerate" in (after.get("error") or "").lower() or \
               "restart" in (after.get("error") or "").lower(), \
               f"unexpected failure msg: {after.get('error')}"
        print("BRANCH: marked failed after restart (resume path skipped)")
        return
    # else: expect eventual completion
    final = _wait_completed(s2, 240)
    assert final and final["status"] == "completed" and \
           len(final["explanations"]) == 6, f"did not complete after restart: {final}"
    print("BRANCH: RESUMED after restart and completed to 6 pages")
