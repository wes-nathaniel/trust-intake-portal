# Trust Intake & Client Portal — PRD

## Problem Statement
Full Trust Intake & Client Portal web app for Iron Gate Consulting: client-facing 8-step intake wizard, admin dashboard, secure page-by-page trust draft preview (watermarked, anti-copy/print), Square-powered payment workflow with ACH tracking, final trust unlock with notarization instructions, legal disclosures + acknowledgments, business asset SOS advisory, EIN admin-filing, branding, and messaging.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth (httpOnly cookies), bcrypt, brute-force lockout.
- **Frontend**: React (CRA + craco) + Tailwind + shadcn/ui. Cormorant Garamond + IBM Plex Sans.
- **3rd-party**: Resend (email), Emergent LLM key (AI Q&A — Claude Sonnet), Dropbox Sign (dormant), Square (invoices + webhooks — live production), Twilio SMS + **Twilio WhatsApp** (fan-out admin notifications, per-case outbound + inbound thread).
- **Trust preview**: pypdfium2 renders per-page PNGs at low DPI with tiled diagonal watermark.


## Changelog — 2026-07-16 (security audit + hardening + admin SSN reveal)
- ✅ **SSN encryption at rest (AES-256-GCM)** — new `/app/backend/crypto.py` module encrypts every SSN before it reaches Mongo (`enc:v1:<nonce_b64>:<ct_b64>` format). Key from new `SSN_ENCRYPTION_KEY` env (base64-urlsafe, 32 bytes). Legacy plaintext SSNs are passthrough-readable and encrypted lazily on next write.
- ✅ **SSN masking on every API response** — new `_response_case()` helper masks every grantor + EIN SSN to `XXX-XX-####` on every case response (`/trust-cases/mine`, `/trust-cases/{id}`, `/admin/trust-cases`, `add_grantor`, `update_grantor`). Plaintext SSN never travels over the wire outside the explicit reveal endpoint.
- ✅ **Admin SSN reveal + audit** — new `POST /api/admin/trust-cases/{case_id}/grantors/{grantor_id}/reveal-ssn` (admin-only). Returns full plaintext SSN. Every reveal is written to `ssn_reveal_log` collection (`admin_id`, `admin_email`, `case_id`, `grantor_id`, `grantor_name`, `ip`, `user_agent`, `at`). Client role always gets 403.
- ✅ **Idle session timeout** — `get_current_user` now enforces `IDLE_TIMEOUT_MINUTES` (default 60). `last_seen_at` refreshed on every authenticated request, on `/auth/login`, and on `/auth/refresh`. 401 with `"Session expired after 60 minutes of inactivity"` when exceeded.
- ✅ **Security headers middleware** — HSTS (`max-age=31536000; includeSubDomains; preload`), X-Content-Type-Options `nosniff`, X-Frame-Options `SAMEORIGIN`, Referrer-Policy `strict-origin-when-cross-origin`, Permissions-Policy locks down camera/mic/geo/payment.
- ✅ **Frontend admin `SSNReveal` component** — `/app/frontend/src/components/SSNReveal.jsx` shows masked by default, has a `Reveal SSN` button that fetches from the audited endpoint and auto-hides after 30s. Only rendered on admin pages.
- ✅ **Data-loss guard** — `update_grantor` preserves the existing ciphertext when the incoming SSN is masked (`XXX-XX-####`, our own display form) so client round-trips can't destroy the stored value. Defense-in-depth in `_encrypt_grantor_ssns` clears masked writes and logs a warning.
- 🔒 **Audit results at end of iteration**:
  1. SSN at-rest encryption: ✅ AES-256-GCM
  2. Password hashing: ✅ bcrypt gensalt() cost=12 (unchanged)
  3. Login rate limiting: ✅ 5 attempts → 15 min lockout (unchanged)
  4. Session inactivity: ✅ 60-min server-tracked idle timeout
  5. HTTPS: ✅ HSTS preload + cookie `secure=True`
  6. Admin SSN reveal: ✅ endpoint + audit log + frontend button
- Tests: `/app/backend/tests/test_iteration22_security.py` — **19/19 backend tests pass**, all critical bugs (SSN data-loss on masked-round-trip, idle-lock login recovery) resolved. Frontend admin reveal + client hidden verified via Playwright. Iterations 22 → 23.


## Changelog — 2026-07-16 (branding assets + email deliverability hardening)
- ✅ **Iron Gate branding assets** shipped as static frontend files:
  - `/app/frontend/public/favicon.png` (512×512, from IronGate Favicon ver.png)
  - `/app/frontend/public/apple-touch-icon.png` (180×180)
  - `/app/frontend/public/irongate-logo.png` (400×400, downscaled from IronGate Logo.png for email + header use)
  - `index.html` updated to load the PNG favicon + apple-touch-icon (old inline base64 shield removed)
  - `Login.jsx` renders the shield above "IGC Trust Portal" (`data-testid="login-logo"`)
- ✅ **Email deliverability upgrades** (code-side, complete):
  - `From` header now `Iron Gate Consulting <support@igcfirm.com>` (display name via new `SENDER_DISPLAY` env, default 'Iron Gate Consulting')
  - `Reply-To: support@igcfirm.com` on every send
  - Every email is now sent as **HTML + plain-text multipart** via a new `_html_to_text()` helper (Gmail penalizes HTML-only mail)
  - `List-Unsubscribe: <mailto:support@igcfirm.com?subject=Unsubscribe>` + `List-Unsubscribe-Post: One-Click` headers per RFC 8058
  - `_email_shell()` rewritten to include the Iron Gate shield PNG at the top of every email (absolute URL from `FRONTEND_URL`)
- 📄 **DNS setup guide** written to `/app/memory/EMAIL_DELIVERABILITY.md` — user must add the 4 Resend-provided DNS records (SPF, DKIM, DMARC, MX) at their domain registrar to complete deliverability. Code side is done.


## Changelog — 2026-07-15 (name rule + Iron Gate advisor rule for page-by-page explainer)
- ✅ **NAME RULE — intake first name is the only truth**. `_build_case_context` (server.py) now derives `client_first_name` from `grantors[0].first_name` (intake), falling back to first token of client_name. `_context_brief` writes an explicit `APPROVED_FIRST_NAME:` line, and both SYSTEM_PROMPT and user_prompt hammer the rule ("ignore any middle name from the PDF"). Verified: for a client 'Arlene Tamara Nathaniel' with intake first_name='Arlene', every page addresses her as 'Arlene', never 'Tamara' or 'Ms. Nathaniel'.
- ✅ **IRON GATE CONSULTING RULE — no outside counsel language**. New `IRON_GATE_ADVISOR_LINE` module constant with the exact copy: *"Your trust was carefully prepared through Iron Gate Consulting's military legal benefits program. If you have questions, contact your Iron Gate Consulting advisor directly."* Prompt now forbids all suggestions to consult attorneys / seek independent legal counsel / obtain a second opinion, and instructs the model to substitute the Iron Gate line at natural closings. Two-layer defense: `_scrub_attorney_advice()` regex post-processor replaces any residual attorney-advice sentence with the Iron Gate line (dedupes to a single line per page, preserves surrounding HTML tags).
- Tests: 8 new unit tests in `/app/backend/tests/test_page_explainer_scrubs.py` (7 attorney sentence variants + build_case_context.client_first_name derivation) plus 1 e2e in `/app/backend/tests/test_iteration21_e2e.py` (full regenerate cycle for Michael Thompson: 6/6 pages mention Michael, 0 attorney phrases, 0 jargon, Iron Gate line present). Full regression suite (test_page_explanations 7 + test_page_resume 3 + test_trust_draft_personalization 8 + iter21 12) = 30/30 pass. Iteration 21.


## Changelog — 2026-07-15 (resumable jobs + admin Regenerate + workers=2)
- ✅ **Uvicorn workers 1 → 2** in production. New `/app/backend/supervisord.conf` (deploy image) runs `uvicorn server:app --host 0.0.0.0 --port 8001 --workers 2` without `--reload`. Preview supervisord.conf is platform-managed and untouched. Rationale: prevent event-loop starvation on production (Emergent Support guidance after Cloudflare 524).
- ✅ **Resumable page-explain background job**. `page_explanation_jobs.start_page_explain_job` now accepts `resume_from_batch: int` and `prior_explanations: list`. Partial explanations are persisted to `case.trust_page_explanations` after EVERY batch (not only at end). On startup, `sweep_stuck_jobs_on_startup(db, update_case_fn, resume_fn)` calls the injected `resume_fn` (defined in `server.py` lifespan) which reloads the source PDF from object storage and re-fires the runner from the last completed batch. Falls back to `failed` only if the PDF can't be reloaded. `trust_page_explainer.explain_pages` now accepts `start_batch` and `prior` params and skips batches ≤ start_batch.
- ✅ **Admin-only Regenerate button** on the client trust preview page. `TrustDraftExplanationPanel.jsx` now imports `useAuth()`, shows a `Regenerate` pill in the top-right of the right panel when `user.role === 'admin'`. Clicking POSTs to `/api/admin/trust-cases/{id}/trust-page-explanations/regenerate` and re-starts polling. Client-role users NEVER see the button. Disabled state shows `Starting…` (during API call) or `Running…` (while jobRunning).
- Tests: 3 new pytest cases in `/app/backend/tests/test_page_resume.py` (resume branch fires, partial persistence during run, banned-jargon regression). All prior tests still pass. Iteration 20 — 100% backend + 100% frontend.


## Changelog — 2026-07-16 (auto page-by-page trust explainer + jargon scrub)
- ✅ **Removed "Import Trust Draft PDF" button** — page-by-page auto explainer replaces the manual import flow.
- ✅ **Auto-fires background job on every Trust Draft PDF upload** (`POST /api/admin/trust-cases/{id}/trust-draft`). Returns instantly (202-style) while `page_explanation_jobs.start_page_explain_job` generates plain-English notes per PDF page on a worker thread.
- ✅ New endpoint `GET /api/trust-cases/{id}/trust-page-explanations` → ordered `[{page, text}]` + job status/progress; `POST /api/admin/trust-cases/{id}/trust-page-explanations/regenerate` re-fires the job.
- ✅ **Client trust preview** renders the watermarked PDF on the LEFT and `TrustDraftExplanationPanel` on the RIGHT with polling (6s cadence). Panel content updates as the client pages through; shows "Writing plain-English notes… X of N pages ready" while the job runs.
- ✅ **Deep personalization**: each page's explanation cites Michael/Sarah/James (or the case's actual names), exact beneficiary %, real asset addresses/institutions.
- ✅ **Banned legal jargon scrub** — two layers: (1) `SYSTEM_PROMPT` + user_prompt in `/app/backend/trust_page_explainer.py` now forbid even QUOTING banned Latin/legal terms and provide plain-English substitutes; (2) `_scrub_jargon()` regex post-processor replaces any leaked term (quoted or unquoted): `per stirpes`→`by family branch`, `in terrorem`→`no-contest rule`, `settlor`→`the person creating this trust`, `corpus`→`the trust's property`, `spendthrift`→`creditor-protection safeguard`, `fiduciary`→`trusted manager`, plus `hereinafter`/`aforementioned` collapse.
- ✅ Startup sweep `page_explanation_jobs.sweep_stuck_jobs_on_startup` marks orphaned pending jobs as failed after a pod restart.
- Tests: 7/7 pytest in `/app/backend/tests/test_page_explanations.py` + Playwright frontend verification. Iteration 18 (found jargon leak) → Iteration 19 (verified fix, 0 leaks across 6 pages).

## Changelog — 2026-07-15 (personalized client trust preview)
- ✅ **FIX #1** — Client trust preview page (`/portal/trust-preview/{case_id}`) now renders **watermarked PDF on the LEFT and the personalized AI plain-English explanation on the RIGHT** as a single two-column grid (`data-testid="trust-preview-side-by-side"`) when the case has a trust_draft but no manually-created trust_sections. Legacy `TrustViewerTwoPanel` path preserved for cases that already have structured sections.
- ✅ **FIX #2** — Deeply personalized AI explanation. `doc_explainer.generate_explanation(...)` now accepts optional `case_context` and, when called from the "Import Trust Draft PDF" flow (or the regenerate flow on a trust-draft-source doc), emits 7 new personalized fields alongside the legacy 5:
  - `greeting` — Hi <first-name> opener
  - `grantor_intro` — powers, incapacity, death
  - `trustee_roles` — trustee + successor by name
  - `beneficiaries` — each by name, relationship, share%
  - `assets_plain` — assets described in plain English (addresses, institutions, account tails)
  - `trust_type_meaning` — what THIS trust type means for THIS grantor
  - `next_steps` — addressed by first name
- New `PERSONALIZED_SYSTEM_PROMPT` bans corporate/legalese jargon (settlor, corpus, per stirpes, in terrorem, spendthrift, hereinafter…) and defines legal terms inline in everyday words.
- New helper `_build_case_context(case)` in `server.py:2841` gathers client_name, trust_type, grantors, trustees, successors, beneficiaries, assets.
- New client-facing endpoint `GET /api/trust-cases/{case_id}/trust-draft-explanation` returns the ai_explanation from the source='trust_draft' admin_document; 404 with human-friendly detail when not yet generated.
- New `TrustDraftExplanationPanel.jsx` component fetches + renders the personalized panel with 7 sections (with graceful empty-state amber notice).
- Tests: 8/8 pytest in `/app/backend/tests/test_trust_draft_personalization.py` + full Playwright frontend verification. Iteration 17.

## Changelog — 2026-07-14 (production RCA — clean exit fix)
- 🔴 **ROOT CAUSE FOUND — production FastAPI process was cleanly exiting (exit 0) on every startup, causing infinite Kubernetes restart loops with zero request logs.** Culprit: an **`IndexOptionsConflict` (MongoDB error code 85)** on the `invites.expires_at` TTL index. When a previous deploy created it with different `expireAfterSeconds` options, every subsequent boot's `db.invites.create_index("expires_at", expireAfterSeconds=0)` raised inside `@app.on_event("startup")` — uvicorn treats an unhandled lifespan exception as a clean shutdown → exit 0 → K8s restart → infinite loop.
- ✅ **Fix**: `@app.on_event("startup")` in `/app/backend/server.py:4810` fully rewritten. Every step now individually try/except-wrapped:
  - Each `create_index` call in its own try/except loop (per-index isolation)
  - `sweep_stuck_jobs_on_startup` wrapped
  - Admin seed block wrapped, with nested try/except around `verify_password` for malformed bcrypt hashes AND `.get()` for missing `password_hash` field (both were also uncaught before)
  - `init_storage()` wrapped
  - `asyncio.create_task(_monthly_summary_scheduler())` wrapped
  - Two bracketing INFO logs: "Lifespan startup begin" / "Lifespan startup complete"
- **Reproduced locally**: forced the exact IndexOptionsConflict on `invites.expires_at` (expireAfterSeconds=999 vs code's 0), restarted backend. Old code: crash + clean exit. New code: WARNING log "Index create skipped on invites(expires_at): ...IndexOptionsConflict..." + startup completes + login responds in 0.5s.
- **Also verified**: no `sys.exit`, `os._exit`, `SystemExit`, or `signal` handlers anywhere in the backend (Support's other suspects, cleared).
- Tests: 5/5 new pytest cases in `/app/backend/tests/test_startup_guards.py` (index conflict, malformed bcrypt, missing password_hash, missing admin doc, clean startup). Iteration 16.

## Changelog — 2026-07-14 (unified explainer enrichment)
- ✅ **Explainer enrichment now merges 9 educational sections into the SAME scroll flow** as the extracted article explanations — no second page, no separate scroll area, one continuous client experience.
- New `/app/backend/trust_enrichment.py`: single Claude Sonnet 4.5 call after `trust_extractor.extract_trust_sections()` produces 9 sections in canonical order (Grantor Overview, Trustee Overview, Successor Trustee Overview, Incapacity Procedures, Death Procedures, Asset Protection Basics, Distribution Logic, Trust Fundamentals, and "What happens if…" scenarios). Every section personalized to the actual grantor/trustee/beneficiary names when present in the extracted articles.
- Hardcoded `_FALLBACK` template guarantees all 9 sections always render even if the LLM call fails or times out.
- Wired into `extract_jobs._runner()` — enrichment runs after extraction, results are appended to `trust_sections_draft[]` so the full 6+9=15 pattern flows through the existing publish-draft workflow untouched.
- `TrustViewerTwoPanel.jsx` updated to detect `kind==="educational"` and render:
  - LEFT: gold-tinted "Client Education" card with eyebrow, title, and italic guidance note
  - RIGHT: distinctive "📘 <Title> — Plain English" label + full HTML content
  - Both in the SAME two-column scroll (existing sync logic works unchanged)
- Tests: 5/5 new pytest in `/app/backend/tests/test_trust_enrichment.py` (fallback, timeout, live LLM, E2E) + frontend Playwright confirms single-scroll rendering. Iteration 14.

## Changelog — 2026-07-14 (post-Support hotfix pass)
- ✅ **Event loop no longer blocks on PDF text extraction.** `trust_extractor._extract_pdf_text()` (sync pypdfium2 call) now runs via `await asyncio.to_thread(...)`, so a large PDF can't freeze the FastAPI worker.
- ✅ **`GET /trust-sections/extract-status` wrapped in try/except.** Any unexpected exception now returns `{status:"error", error, sections_count:0}` with HTTP 200 so the frontend poll can't crash on a bad server response. Genuine 404 is preserved.
- ✅ **Stuck-job watchdog** — `extract_jobs.mark_failed_if_stuck()` flips a pending job to `failed` when the last progress (or start) timestamp is older than 300 seconds. Fires from inside `extract-status` on every poll, so orphaned jobs don't hang forever. `progress_cb` now stamps `last_progress_at` on each batch.
- ✅ **Startup sweep** — new `extract_jobs.sweep_stuck_jobs_on_startup()` runs during FastAPI startup and marks every `trust_extract_job` still in `pending` with no `finished_at` as `failed` with error "Server restarted while extraction was in progress. Please re-run auto-extract." This clears the ghost jobs left behind after a pod restart.
- Tests: 21/21 across `/app/backend/tests/test_watchdog_and_sweep.py` (new, 8 cases) + `/app/backend/tests/test_auto_extract_bg.py` (regression). Iteration 13.

## Changelog — 2026-07-14 (per Emergent Support / Wes Nathaniel)
- ✅ **CRITICAL FIX — Auto Generate from PDF was timing out through Cloudflare** because the sync LLM call outran the request timeout. Refactored to the exact pattern Support recommended:
  - `POST /api/admin/trust-cases/{id}/trust-sections/auto-extract` now returns **HTTP 202** with a `task_id` in **~0.5s** (was blocking 30-90s). The heavy work runs as an asyncio background task via new `/app/backend/extract_jobs.py` (in-memory task registry + case-doc mirror so restarts don't lose state).
  - New `GET /api/admin/trust-cases/{id}/trust-sections/extract-status` — poll every 6s until `status='completed'` or `'failed'`. Returns `{task_id, status, sections_count, batches_done, batches_total, error}`.
  - `/app/backend/trust_extractor.py` rewritten to chunk: heading-based `_split_into_articles()` splits the PDF into blocks; batches of 3 sections per LLM call; **each call wrapped in `asyncio.wait_for(..., timeout=85s)`** so a hung Claude call can't freeze the extractor.
  - Inline path (auto-extract on trust_draft upload) also switched to the background task, and the trust-ready email fire-off is now `asyncio.create_task(...)` so uploads return in <3s (was ~30s).
  - Frontend `TrustSectionsEditor.autoExtract()` rewritten to fire → poll `/extract-status` every 6s → toast on completion (or failure). Button label: "AI is reading the PDF (up to 90s)…". Max polling window 4 minutes; job continues after that if still running.
  - Tests: 4/4 targeted pytest cases + regression suite pass (`/app/backend/tests/test_auto_extract_bg.py`). Iterations 11 + 12.

## Changelog — 2026-07-13 (later)
- ✅ **Bug fix — AI Explainer had no PDF to read.** Two additive endpoints ship together:
  - `POST /api/admin/trust-cases/{id}/admin-documents/from-trust-draft` — one-click import of the existing trust draft PDF into the AI Document Explainer. Reuses the same storage object (no duplicate bytes). Runs Claude and stores structured plain-English explanation. Idempotent (`source='trust_draft'` + `source_storage_path` guard).
  - `DELETE /api/admin/trust-cases/{id}/trust-draft` — fully removes a wrongly-uploaded trust draft. Clears `trust_sections` + `trust_sections_draft` (they were derived from that PDF). Any imported explainer card is preserved but flagged `source_orphaned=true`.
  - UI: red-tinted "Delete draft" button in the Trust Draft section (data-testid `trust-draft-delete-btn`), "Import Trust Draft PDF" accent button in the AI Explainer panel (data-testid `admin-doc-import-trust-draft-btn`), only rendered when a draft exists.
  - Tests: 14 backend pytest cases + 7 frontend Playwright checkpoints, all pass (see `/app/backend/tests/test_trust_draft_explainer.py`).

## Changelog — 2026-07-13
- ✅ **Login header** updated from "Welcome back" → "IGC Trust Portal" (sub-header retained). Verified via screenshot.
- ✅ **WhatsApp integration (Twilio)** — reuses existing Twilio credentials.
  - New `/app/backend/whatsapp.py` (`send_whatsapp`, `send_admin_whatsapp`) + `/app/backend/notify.py` (fan-out helper that pushes admin notifications to both SMS and WhatsApp).
  - All 12 existing `sms.send_admin_sms(...)` call sites now use `notify.notify_admin(...)` — every event that used to only text the admin (new call requested, review completed, payment cleared, etc.) now also pings WhatsApp.
  - New endpoints:
    - `GET /api/admin/whatsapp/status` — reports whether the sender is fully configured.
    - `POST /api/admin/trust-cases/{id}/send-whatsapp` — admin outbound to a client, appended to the case's `whatsapp_thread[]`.
    - `GET /api/admin/trust-cases/{id}/whatsapp-thread` — full outbound/inbound history for a case.
    - `POST /api/webhooks/twilio/whatsapp-inbound` — Twilio-facing webhook that captures client replies. If the `From` matches an existing case (`client_phone` or grantor phone), the message is stored on that case; otherwise it lands in `whatsapp_inbox`. Admin is pinged either way.
  - New env vars in `backend/.env`: `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886` (Twilio Sandbox default), `ADMIN_WHATSAPP_NUMBER=+19545983681`, `WHATSAPP_NOTIFY_ADMIN=true`.
  - Admin UI: new `WhatsAppPanel` component on every case detail page — status badge (Live / Sandbox / disabled), to-number override, message compose, and threaded outbound+inbound history.
- ✅ **WhatsApp Inbox** (`/admin/whatsapp-inbox`, `AdminWhatsAppInbox.jsx`) — grouped view of unmatched inbound senders. Endpoints: `GET /api/admin/whatsapp/inbox`, `POST /api/admin/whatsapp/inbox/attach` (moves entire thread onto a case and saves the sender's phone for future auto-routing), `POST /api/admin/whatsapp/inbox/archive`. New nav link "WhatsApp" for admins. Verified end-to-end via 18 backend pytest cases + Playwright flow.
- ✅ **Intake WhatsApp opt-in** — Grantor step now shows a green-bordered opt-in card once a grantor with a phone is on the case. `POST /api/trust-cases/{id}/whatsapp-opt-in {opt_in, phone?}` toggles `whatsapp_opt_in` and — on first-time opt-in only — fires a personalized welcome message ("Hi {name} — thanks for starting your trust with IGC Trust Portal. You'll get case updates on this channel…"). Idempotent via `whatsapp_welcomed_at`.
- ✅ **Admin command shortcuts via WhatsApp** — messages from `ADMIN_WHATSAPP_NUMBER` are routed to `whatsapp_commands.handle_admin_command` and never touch the inbox. Recognized commands (all persisted to `whatsapp_admin_log`):
  - `/help` — list of commands
  - `/whoami` — sanity check
  - `/cases [status]` — list up to 10 cases (default: active)
  - `/case <short-id> info` — status, email, trust type, last 3 notes
  - `/case <short-id> status <new-status>` — flips status (fires the normal `_notify_status_change` pipeline including client email)
  - `/case <short-id> note <text>` — appends admin note with `author='WhatsApp Admin'`
  Short-id is the first 8 chars of the case UUID (case-insensitive). Fuzzy status matching (spaces/case ignored). Invalid inputs reply gracefully.

## Changelog — 2026-02-11 (cont'd)
- ✅ **New canonical `trust_sections[]` schema** per client spec: `{article_number, article_title, article_text, explainer_text, id}`. Legacy `{title, trust_html, explainer_html}` fields kept in DB (self-healing normalize() on save) so old records continue to render without migration. Extractor prompt updated to emit both. Viewer + editor read canonical first, legacy fallback. Verified end-to-end: 6-section Hartwell trust extracted with article_number values ["Preamble","I","II","III","IV","V"], client-side viewer renders "Article I — Declaration of Trust" etc. with verbatim legal text on left and clause-by-clause plain-English on right (defines "Grantor", "Trustee", "Schedule A", "'IN TRUST'" inline). Scroll-sync + click-to-jump intact.
- ✅ **Auto-extract trust sections from uploaded PDF** — new `/app/backend/trust_extractor.py` runs Claude Sonnet 4.5 on the extracted PDF text and returns a structured list of Articles (`title`, verbatim `trust_html`, plain-English `explainer_html`). Integrated into `POST /admin/trust-cases/{id}/trust-draft`: on upload, if `trust_sections` is empty, auto-populates it (never overwrites manual work). New `POST /admin/trust-cases/{id}/trust-sections/auto-extract` endpoint lets admin re-run extraction on cases where the PDF is already uploaded. Frontend: "Auto-generate from PDF" button in the empty state of `TrustSectionsEditor` (only shown when a trust draft is present). Verified end-to-end: 6-article Hartwell trust PDF → 6 correctly parsed sections including Preamble, ~7-second total time, client-facing two-panel viewer renders immediately with scroll-sync intact.
- ✅ **Expanded storage rollup** covers all three storage sources (AI Explainer + Client uploads + Trust Draft PDFs). Backend returns per-source totals (`ai_bytes`, `client_bytes`, `draft_bytes`) + a per-case breakdown. Frontend header now reads `"X MB total across N cases"` with a 3-column breakdown row. Top-10 table shows an AI · Client · Draft split per case.
- ✅ **Dashboard-level storage rollup** — new `GET /admin/storage-rollup` endpoint aggregates AI Explainer usage across ALL non-archived cases. Returns totals + top-10 storage-heavy cases. New `StorageRollupCard.jsx` component renders on `AdminDashboard` between the stat cards and the search bar. Auto-hides when no docs; auto-switches to amber warning when any case exceeds 100 MB. Expandable table lists top cases with an "Open →" deep link to each case's admin page.
- ✅ **Storage-usage indicator** at the top of the AI Explainer section on the admin case page. Live-derived from the docs prop (no extra API call). Format: "N documents · X KB total · V archived versions (Y KB)". Auto-switches to amber warning when the archived-versions total exceeds 100 MB with a hint to use Trim. Auto-hides for cases with zero uploads.
- ✅ **Trim version history** — new `POST /admin/trust-cases/{id}/admin-documents/{doc_id}/trim-history` endpoint. Body: `{keep: N}` where N ∈ [0, 100]. Keeps newest N versions, permanently deletes older ones from object storage. Frontend: **Trim** dropdown in the version history header with quick options (Keep last 10 / 5 / 3 / 1 + Clear all). Each option shows a live "N to remove" preview so admins know exactly what will happen. Confirmation dialog before deletion. Verified E2E: [4,3,2,1] → keep 3 → [4,3,2] → keep 1 → [4] → clear → []; boundary check `keep=-1` returns HTTP 400.
- ✅ **Version history + Restore** for AI Explainer docs. Replace no longer deletes old storage — it archives to a `versions[]` array on the doc (each entry keeps storage_path, filename, size, uploaded_at, ai_explanation, archived_at). New endpoints: `GET /admin/trust-cases/{id}/admin-documents/{doc_id}/versions` and `POST .../versions/{n}/restore`. Restore is reversible — the current state is archived as a new version each time. Delete now cleans up all versioned storage objects too. `AdminDocumentCard` shows a `vN` badge next to the label and a collapsible "Version history" row (latest 5 shown, Restore button on each).
- ✅ **Replace Document** in AI Explainer — new `PUT /api/admin/trust-cases/{id}/admin-documents/{doc_id}` endpoint replaces the file IN PLACE (same doc_id, deletes old storage, regenerates AI explanation, notifies client). New Replace button on `AdminDocumentCard` opens a file picker; no duplicate created. Verified E2E: same doc_id preserved, new content picked up by Claude, storage path rotated.
- ✅ **AdminDocumentsManager layout fix** — was rendering inside a 2-col grid causing label to wrap character-by-character; added `lg:col-span-2` so it spans full width.
- ✅ **Delete flows for documents** — three separate paths, all verified end-to-end:
  1. Admin can now Remove client-uploaded documents (ID, proof of address, bank statements, etc.) from the "Documents (N)" section on `AdminCaseDetail` — previously only Download existed.
  2. New `ClientDocumentsPanel` on `ClientPortal` ("Files you've sent us") shows every file the client has uploaded across intake steps with per-item Download + Delete. Admin-uploaded files (EIN letter, trust draft) render read-only with a "From your team" tag.
  3. Admin delete on the AI Document Explainer (`AdminDocumentsManager`) already worked in preview — was a redeploy gap on production.
- ✅ **AI Document Explainer** — new admin-uploads-any-document feature with Claude Sonnet 4.5 auto-generated plain-English explanations.
  - Backend: `/app/backend/doc_explainer.py` (text extraction for PDF/DOCX/TXT + LLM call via Emergent LLM Key). New endpoints on `server.py`: `POST /admin/trust-cases/{id}/admin-documents` (upload + label + AI), `POST .../regenerate`, `DELETE .../admin-documents/{doc_id}`, `GET /trust-cases/{id}/admin-documents/{doc_id}/download` (owner or admin).
  - Storage: new `admin_documents[]` field on trust_cases doc (fully independent of `trust_draft` / `trust_sections` / `documents`). Fields: id, label, storage_path, filename, content_type, size, uploaded_by, uploaded_at, ai_explanation{what_is, what_it_does, why_it_matters, notarization, client_action, generated_at, error}.
  - Frontend: `AdminDocumentsManager.jsx` (upload + list + regenerate + delete) on AdminCaseDetail. `AdminDocumentCard.jsx` (shared read-only card) rendered on both admin page and ClientPortal ("Documents from your team" section) — client sees Download only.
  - Notification: email to client on every upload; MOCKED as best-effort (never blocks upload).
  - Accepted: PDF, DOCX, DOC, TXT, JPG, PNG · max 25 MB. Re-upload/regenerate always regenerates the AI explanation.
  - Dependencies added: `python-docx==1.2.0`, `lxml==6.1.1` (added via pip install + pip freeze into requirements.txt).
- ✅ **"Last 5 logins" mini-table** on admin case page. New `GET /api/admin/trust-cases/{id}/login-activity?limit=N` endpoint returns recent rows from `login_activity` for the case's client. "Last login" line is now a toggle that lazy-loads a 4-column table (Kind / When / IP / User agent). Verified end-to-end via Playwright.
- ✅ **Login/logout activity logging** — `login_activity` collection persists every login/logout (kind, ts, ip, user_agent, email, name, role). `last_login_at` / `last_logout_at` mirrored onto user record. Admin case detail (`GET /api/admin/trust-cases/{id}`) now returns `client_last_login_at` + `client_last_logout_at`, surfaced in `AdminCaseDetail.jsx` under the client header. Each client login/logout sends a notification email to `ADMIN_NOTIFY_EMAIL` (= support@igcfirm.com) with the client's name, case number, time, IP, and UA. Admin sessions are NOT emailed. Best-effort: failures logged, never raised.
- ✅ **Removed admin-driven auto status-advance** — `PUT /admin/trust-cases/{id}/trust-sections` and `POST /admin/trust-cases/{id}/trust-draft` no longer flip status to "Ready for Client Review". Admin must manually move the status via the dropdown. The green "Client marked review as completed. Ready for payment." banner remains correctly gated to `review_completed_ack` which is only ever set by the client clicking Complete Review in `ReviewStep.jsx` or `TrustPreview.jsx`. Toast on trust-sections save updated to "Move the status to 'Ready for Client Review' when ready."
- ✅ **Templates library** in WYSIWYG editor — 6 boilerplate clauses (Revocation, Successor Trustee, Spendthrift, No Contest, Powers of Trustee, Distribution to Beneficiaries) defined in `/app/frontend/src/lib/trustTemplates.js`. Each has both a legal `trust_html` and plain-English `explain_html`. Dropdown in `RichTextEditor` inserts at cursor position via saved Range + `execCommand('insertHTML')`. Verified 12/12 PASS by testing_agent.
- ✅ **Welcome greeting** — new `has_logged_in_before` flag on user records. `public_user()` now returns `first_name` and `is_first_login`. `/auth/register`, `/auth/login`, `/auth/accept-invite` all build the response BEFORE flipping the flag. ClientPortal shows `Welcome to Iron Gate Trust Services.` on first login, then `Welcome Back, {first_name}` on every subsequent login.
- ✅ **"Take the Tour" card** — one-time onboarding card with 4 steps (Complete intake → Review draft → Sign & approve → Download docs). Shown on ClientPortal when `!user.has_seen_tour`. `POST /api/auth/dismiss-tour` sets the flag server-side; dismiss persists across reload and devices. Verified end-to-end via Playwright. — 6 boilerplate clauses (Revocation, Successor Trustee, Spendthrift, No Contest, Powers of Trustee, Distribution to Beneficiaries) defined in `/app/frontend/src/lib/trustTemplates.js`. Each has both a legal `trust_html` and plain-English `explain_html`. Dropdown in `RichTextEditor` inserts at cursor position via saved Range + `execCommand('insertHTML')`. Verified 12/12 PASS by testing_agent.
- ✅ **Welcome greeting** — new `has_logged_in_before` flag on user records. `public_user()` now returns `first_name` and `is_first_login`. `/auth/register`, `/auth/login`, `/auth/accept-invite` all build the response BEFORE flipping the flag, so the very first login shows `is_first_login: true`. ClientPortal shows `Welcome to Iron Gate Trust Services.` on first login, then `Welcome Back, {first_name}` on every subsequent login. Verified end-to-end via Playwright.

## Changelog — 2026-02-11
- ✅ Two-Panel Trust Viewer (TrustViewerTwoPanel.jsx) replaces PDF preview — legal text left, plain-English explainer right, with watermark + anti-screenshot/right-click block.
- ✅ Admin TrustSectionsEditor (WYSIWYG) — RichTextEditor with Bold/Italic/**Underline**/Subheading/Quote/Bulleted list/Numbered list/Link/Undo/Redo.
- ✅ Inline per-article Preview toggle + Duplicate article + Remove article buttons (verified by testing_agent_v3_fork — 13/14 PASS).
- ✅ "Preview as Client" admin button → AdminTrustViewerPreview reuses TrustViewerTwoPanel.
- ✅ Fixed compile-blocking invalid eslint-disable comment in TrustSectionsEditor.jsx.
- ✅ Added Underline toolbar button to RichTextEditor.jsx.
- ✅ Fixed nested-button warning in DiagnosticsPanel.jsx (outer toggle now div[role=button]).

## Core Requirements — ✅ Done
- 8-step intake wizard with HARD STOP validation
- Trust Name required field on case creation
- Admin-only EIN filing (client only authorizes — no SSN required)
- Admin EIN letter upload (RBAC enforced — clients get 403)
- Asset intake (manual or document-upload mode)
- Business Asset advisory (Secretary of State filing notice) on Asset step, Review step, Trust preview, emails, and PDF
- Legal disclosures + checkboxes: (1) military-legal disclosure, (2) state-laws-vary, (3) notarization required, (4) business-SOS (conditional)
- Review Completed button — notifies admin when client is satisfied
- Schedule Zoom Meeting button — uses https://us06web.zoom.us/j/7194164805?pwd=OTkyQlQ2QXNwWm5xeTBjbDkxWklJUT09
- **Secure draft trust preview**:
  - Admin uploads draft PDF → converted to watermarked low-res PNGs per page
  - Client views page-by-page with anti-copy / anti-print / anti-screenshot deterrents (dim on blur, disable Ctrl+P/S/C/U, disable right-click/drag, cache-control no-store, X-Frame-Options, overlay watermark, visibility-change dim)
  - Watermark: "IGC — SAMPLE ONLY — NOT VALID UNTIL PAID" (diagonal, tiled)
- **Square payment integration (PRODUCTION)**:
  - Admin creates invoice with amount + due date → Square sends hosted payment link via email
  - Invoice + Payment webhooks (`/api/webhooks/square`) update payment.status: invoice_sent → ach_pending → paid
  - Distinguishes CARD vs BANK_ACCOUNT (ACH) payments
  - Manual override: "Mark payment received"
  - Optional auto-unlock via `SQUARE_AUTO_UNLOCK_ON_PAID=true`
  - Signature verification when `SQUARE_WEBHOOK_SIGNATURE_KEY` is set
- **Unlock Final Trust** — admin action that:
  - Flips `trust_unlocked=true`, status=Completed
  - Enables clean-PDF download + print via `/api/trust-cases/{id}/trust-final`
  - Sends notarization instruction email
- **Admin status flow**: Intake Started → Intake In Progress → Waiting on Documents → In Review → Drafting Trust → **Ready for Review** → **Payment Pending** → Ready for Signing → Completed
- **Send Review Reminder** admin action
- **Document upload by client** triggers admin email notification
- Branding footer: "Prepared by Iron Gate Consulting · Reviewed through military legal benefits" on portal, emails, PDF cover, PDF footer on every page

## Prior Work (earlier sessions)
- JWT auth, admin seeding, brute-force lockout
- Client invites / magic links / resend invite
- Resend email: welcome, status-change, completion (with PDF + referral block)
- PDF generator with SSN masking, disclosures, business advisory, acknowledgments
- Branded messaging: section threads + general thread + admin "Client Questions" page
- AI assistant Q&A with confidence gating + admin escalation
- Doc-requests workflow (required/optional/requested labels, pending-items)
- Admin notifications bell, pending-invite banner

## Implementation Status (2026-04-20, Session 7 — Iron Gate Full Package)

### ✅ Shipped
- Trust Name on all flows (create + update + EIN step + Review + PDF + emails)
- Admin-only EIN (client only authorizes)
- Acknowledgments API + persisted on case
- Secure draft preview (`trust_preview.py`) — page-by-page PNG with watermark, low DPI
- Anti-copy / anti-print / dim-on-blur / disabled shortcuts on `/portal/trust-preview/:id`
- Unlock Final Trust action + `/portal/trust-final/:id` clean download
- Square integration (`square_service.py`): `create_invoice` + `get_invoice` + `cancel_invoice` + `get_payment` + `verify_webhook_signature`
- Admin UI: "Create Square invoice", "Refresh status", "Mark payment received (manual)"
- Client UI: payment banner on portal + preview with Square pay link
- `/api/webhooks/square` handling invoice.* and payment.* and refund.* events; idempotent via `square_events` collection
- Schedule Zoom Meeting button on Review + Trust Preview
- Document-upload admin notification email
- Send Review Reminder admin action
- Two new statuses: "Ready for Review", "Payment Pending"
- Footer + PDF + email templates now include "Prepared by Iron Gate Consulting · Reviewed through military legal benefits" + multi-paragraph legal disclaimer

### Testing
- Iteration 5: **90/90 backend tests pass** (55 regression + 35 new Phase 1-5 coverage). Minor low-priority items logged (422 vs 400 on amount validation; webhook signature enforcement policy; filename-extension PDF check). No critical or blocker issues.

### Environment Variables (new)
- `SQUARE_APPLICATION_ID`, `SQUARE_ACCESS_TOKEN`, `SQUARE_LOCATION_ID` — set (production)
- `SQUARE_ENVIRONMENT=production`
- `SQUARE_WEBHOOK_SIGNATURE_KEY` — **blank; user will set after registering webhook in Square Dashboard**
- `SQUARE_AUTO_UNLOCK_ON_PAID=false` — flip to `true` if they want automatic unlock when payment clears

### User next steps (required to activate payment)
1. Register webhook URL in Square Dashboard → Developer → Webhooks:
   - URL: `https://trust-intake-portal.preview.emergentagent.com/api/webhooks/square`
   - Events: `invoice.created`, `invoice.updated`, `invoice.payment_made`, `invoice.scheduled_charge_failed`, `payment.created`, `payment.updated`, `refund.created`, `refund.updated`
2. Copy the **Signature Key** Square generates
3. Paste into `/app/backend/.env` as `SQUARE_WEBHOOK_SIGNATURE_KEY="<key>"` and restart backend
4. (Optional) set `SQUARE_AUTO_UNLOCK_ON_PAID=true` for hands-free unlock after ACH clears

## Implementation Status (2026-05-13, Session 10 — Admin workflow polish + Credit Repair gate)

### ✅ Shipped (this session)
- **Phone captured at intake start + visible to admin**:
  - StartNew: new **required phone field** ("Best phone number to reach you") collected before case creation; persisted as `case.client_phone`
  - Admin Dashboard list: phone shows under email (clickable `tel:` link)
  - Admin Case Detail header: phone shows alongside email (clickable `tel:` link)
- **Status auto-advance during intake** (forward-only; admin-managed statuses never auto-touched):
  - Intake Started → Intake In Progress on first data write (grantor/trustee/etc.)
  - → Waiting on Documents once required uploads land (gov ID + proof of address; review path also requires existing trust)
  - → In Review when client clicks **Complete Review** on the intake wizard (was previously "Drafting Trust" — now follows the user's flow: admin manually moves to Drafting Trust after review)
- **Centralized status-change notifications** (`_notify_status_change`):
  - Admin email to `ADMIN_NOTIFY_EMAIL` (defaults to `support@igcfirm.com`) for **every** status change — including auto-advances
  - Client email for client-visible statuses (preserves existing dedicated emails for Pending/Verified/Payment-claimed)
  - Subject format: `[Trust Portal] {status} — {client name}`; includes client phone in body for fast call-back
- **Completed → automated message + admin SMS** (exact spec wording): "Congratulations — your trust is complete. A member of our team will call you within 10 minutes. Please log back into your portal to access your complimentary credit review." Admin SMS sent in parallel so the 10-min promise can be honored.
- **Payment-claimed admin alert** (already in place — verified):
  - Admin email to `ADMIN_NOTIFY_EMAIL` with case link
  - Admin SMS to `ADMIN_PHONE_NUMBER` (954-598-3681)
- **Secure credit-repair release** (admin-gated, portal-only):
  - `POST /api/admin/trust-cases/{id}/release-credit-repair` (and `/revoke-credit-repair`) — admin-only
  - `GET /api/trust-cases/{id}/credit-repair-link` — returns the Zoho URL with `?FirstName=...&LastName=...` prefilled, ONLY if `credit_repair_released=true` AND caller owns the case (403 otherwise)
  - Admin Case Detail: "Release Credit Repair" button appears once case is Payment Verified / Completed
  - Client Portal: "Start Your Free Credit Review" button appears ONLY after admin release; opens the Zoho URL in a new tab on click. The link is **never sent by email or SMS**
- **Backwards-compatible**: All new fields default sanely; existing cases without `client_phone` simply omit the phone row.
- **E2E preview verification**: all backend paths green (register → create-with-phone → grantor → auto-advance to "Intake In Progress" → docs upload → auto-advance to "Waiting on Documents" → review-complete → auto-advance to "In Review"; credit-repair 403 before release → 200 after; URL prefilled with split first/last name).

## Implementation Status (2026-05-09, Session 9 — Existing-Trust Review Path)

### ✅ Shipped (this session)
- **Two-path intake**: client now answers *"Do you currently have a living trust set up?"* at the top of `StartNew`:
  - **NO** → existing 8-step wizard, `intake_path: "new"`, suggested $997
  - **YES** → simplified 2-step wizard (Documents + Review), `intake_path: "review"`, suggested $297
- **Backend**:
  - Added `IntakePath` literal + `INTAKE_PATH_PRICE_CENTS = {"new": 99700, "review": 29700}`
  - `TrustCaseCreate` now accepts `intake_path` (default `"new"`)
  - Case stores `intake_path` and `payment.suggested_amount_cents` on creation
  - Welcome email subject/label adapts to "Existing Trust Review" for review-path cases
  - Backwards-compatible: existing API consumers without `intake_path` still default to `"new"`
- **Frontend**:
  - `StartNew.jsx` rebuilt with Yes/No at top; conditional path-specific notes; trust-type selector hidden on YES path
  - `IntakeWizard.jsx` filters steps by `intake_path` (review path = `documents + review` only); deep-link `?step=` and step-completion logic respect the filtered list
  - `DocumentsStep.jsx` adapts on review path — promoted "Upload Your Existing Trust Documents" section at top with `existing_trust` required, optional uploads section hidden, header rebranded
  - `ReviewStep.jsx` adapts — hides Grantors/Trustees/Successors/Beneficiaries/Assets summary blocks; shows a prominent **$297 callout with the exact spec wording** ("Your existing trust will be reviewed by our legal team at no additional charge. Your $297 covers enrollment in our free credit repair program, your 90-day cash settlement process, and your trust review.") at the top
  - `isStepComplete("documents")` requires `existing_trust` upload on review path
  - Admin: `setAmountOnly` `window.prompt` is **pre-filled with $297 / $997** based on path; admin can override
  - Path badge ("EXISTING TRUST REVIEW · $297" / "NEW TRUST · $997") visible on Admin Case Detail header and as a column on the Admin Dashboard list
- **E2E verified on preview**:
  - POST /api/trust-cases with `intake_path=review` → suggested 29700 ✓
  - POST /api/trust-cases with `intake_path=new` (joint) → suggested 99700 ✓
  - POST /api/trust-cases with no path → defaults to `new`, 99700 ✓ (backwards compat)
  - StartNew Yes → wizard shows ONLY "Documents" + "Review" steps ✓
  - DocumentsStep header reads "Upload Your Existing Trust Documents" ✓
  - Required warning correctly demands existing trust + ID + proof of address ✓

## Implementation Status (2026-05-08, Session 9 — Mobile Responsiveness)

### ✅ Shipped (this session)
- **Mobile responsive overhaul** for the entire client intake flow (verified at 360×740 and 390×844):
  - **Layout header**: smaller logo + brand name, hidden subtitle on <sm, icon-only sign-out, no horizontal overflow
  - **StatusTracker**: switched to a compact mobile mode (current step + progress bar + percentage); preserved full step row at sm+
  - **IntakeWizard**: converted vertical step sidebar to a horizontal scrollable strip on mobile (numbered, with check/lock icons), full-width Prev/Next nav buttons, reduced card padding
  - **ClientPortal**: action buttons stacked full-width on mobile, status-meta line wraps gracefully, case header column on mobile, row on lg+
  - **Pending banner**: stacks vertically on mobile with full-width "Go to Documents" button
  - **Global CSS**: all `.btn-*` get `min-height: 44px` (Apple/Google touch target), all inputs/textareas/selects forced to `font-size: 16px` (prevents iOS Safari zoom-on-focus), hidden horizontal page scroll, no-scrollbar utility for step strips
- **Verified via Playwright at 360×740 and 390×844** that:
  - Header, status tracker, intake wizard, grantor form, trust preview viewer, and pre-review section all render cleanly with no horizontal overflow
  - Tap targets meet WCAG / iOS guidelines (≥44px)
  - Form fields don't trigger Safari zoom

## Implementation Status (2026-05-07, Session 9 — Forgot Password + Diagnostics + Workflow Refinement)

### ✅ Shipped (this session)
- **Forgot Password / Password Reset frontend pages** (backend was already in place):
  - `/forgot-password` — email entry form, generic success message (no enumeration leak)
  - `/reset-password?token=XXX` — new password + confirm with strength rules (≥8 chars, letter, number, match)
  - "Forgot your password?" link added to `/login`
  - Branded reset email via existing `_email_shell`/`_cta` (subject: "Reset your {biz} password", 1-hour expiry, plain-link fallback)
- **Production diagnostics endpoint + panel**:
  - `GET /api/admin/diagnostics` (admin-only, 401 for unauth) — returns `all_ready`, plus per-integration ready/error state for Square, Twilio, Resend, Emergent LLM, Auth. Never leaks secrets — only booleans + non-sensitive Square location id.
  - `DiagnosticsPanel.jsx` mounted at top of Admin Dashboard. Collapsible, color-coded green/amber, with one-click "re-check".
- **Workflow refinement (per user spec)**:
  - New status added: **"Ready for Client Review"** (between "Drafting Trust" and "Ready for Payment"). Wired into `STATUSES`, `StatusTracker`, both admin status dropdowns, and status-change email copy.
  - Client clicks **Complete Review** in **intake step 8** → status flips to **"Drafting Trust"** (NOT auto-advancing further), admin notified
  - Admin uploads trust draft → status flips to **"Ready for Client Review"** (was previously "Drafting Trust")
  - Client clicks **Complete Review** on the **drafted-trust preview** → status STAYS at "Ready for Client Review", admin notified to manually advance to "Ready for Payment"
  - Admin can manually push status backwards anytime via the existing dropdown
  - **New "Need to speak with an agent?" pre-review CTA** on `TrustPreview.jsx`. Opens a modal with name + callback phone + optional note. POSTs to new `POST /api/trust-cases/{id}/callback-request` endpoint → emails + SMSs admin with client's name, callback number, and note. **No phone number is publicly displayed.**
- **E2E curl validation** (preview pod, all green):
  - register → forgot → reset → login-with-new-pw ✓ ; old pw 401 ✓ ; token reuse 400 ✓ ; non-existent email 200 (no leak) ✓
  - diagnostics 200 (admin) / 401 (unauth) ✓ ; all integrations green ✓
  - intake review-complete: status `Intake Started` → `Drafting Trust` ✓
  - trust-draft review-complete: status stays `Ready for Client Review` ✓
  - admin upload draft: status → `Ready for Client Review` ✓
  - callback-request: stored on case, admin email + SMS triggered ✓

## Implementation Status (2026-04-29, Session 8 — Custom Payment Step)

### ✅ Shipped (this session)
- **Custom multi-option Payment Step** (`PaymentMethodPicker.jsx`) replacing single-Square button:
  - Zelle option: opens modal with phone (954-598-3681), name (Wesley Nathaniel), exact amount + copy buttons
  - Cash App option: opens https://cash.app/$WNate1971 in new tab
  - Square option: opens existing `payment.public_url` (disabled if no Square invoice)
  - Big green "I Made My Payment" button → flips `payment.status='pending_verification'` + `case.status='Pending Payment Verification'`
- **Admin Set Amount-only flow** — `PUT /api/admin/trust-cases/{id}/payment-amount` for non-Square clients (no invoice generated)
- **Admin Verify Payment flow** — `POST /api/admin/trust-cases/{id}/payment-verify` flips `payment.status='verified'` + `case.status='Payment Verified'`, emails+SMSs client
- New statuses added: "Drafting Trust", "Ready for Payment", "Pending Payment Verification", "Payment Verified"
- Removed: Dropbox Sign / e-signature block (entire section deleted from UI)
- Bulk archive + bulk delete in admin dashboard (with storage cleanup)
- A2P Compliance landing page (`/company`, `/privacy`, `/terms`)
- Twilio SMS triggers wired to status changes + payment events
- Self-healing Square `LOCATION_ID` lookup at runtime (bypasses production env-var typo)
- Emergent badge removal via `MutationObserver` in `index.html`

### Testing — Session 8
- Iteration 6: **9/9 frontend scenarios passed** end-to-end on Payment Step + Admin Verification flow
- Backend smoke-tested via curl in iteration 5 (no regressions)
- DB-confirmed: case.status correctly advances to "Payment Verified" after admin verify

## Backlog
- P0 (Blocked, awaiting Emergent Support): Production env-var access for `TWILIO_*` and `SQUARE_WEBHOOK_SIGNATURE_KEY`
- P1: Refactor `server.py` (~3000 lines) into FastAPI APIRouter modules under `/app/backend/routes/` (auth, admin, cases, webhooks, payment)
- P2: PDF post-processor (reportlab) to rearrange Notary/Trustee blocks on uploaded trust PDFs (alternative: user updates Word template)
- P2: Dropbox Sign e-sign activation (pending user-provided key)
- P3: Server-side magic-byte check on trust-draft uploads
- P3: Cache rendered preview PNGs (currently re-rendered on every page request)
- P3: Replace `window.prompt`-based admin amount/verify dialogs with shadcn `Dialog`

## Endpoints Summary (new in Session 7)
- `POST /api/trust-cases` — now accepts `trust_name`
- `PUT /api/trust-cases/{id}/trust-name`
- `PUT /api/trust-cases/{id}/acknowledgments`
- `POST /api/admin/trust-cases/{id}/trust-draft` (admin uploads PDF)
- `GET /api/trust-cases/{id}/trust-preview/meta`
- `GET /api/trust-cases/{id}/trust-preview/page/{n}.png`
- `GET /api/admin/trust-cases/{id}/trust-draft/raw`
- `POST /api/admin/trust-cases/{id}/unlock-final`
- `GET /api/trust-cases/{id}/trust-final`
- `POST /api/admin/trust-cases/{id}/send-review-reminder`
- `POST /api/admin/trust-cases/{id}/invoice`
- `GET  /api/admin/trust-cases/{id}/invoice`
- `POST /api/admin/trust-cases/{id}/mark-payment-received`
- `GET  /api/trust-cases/{id}/payment-status`
- `GET  /api/admin/square/health`
- `POST /api/webhooks/square`

## Credentials
See `/app/memory/test_credentials.md` — admin: support@igcfirm.com / Wllorenzo03!
