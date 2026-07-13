# Trust Intake & Client Portal — PRD

## Problem Statement
Full Trust Intake & Client Portal web app for Iron Gate Consulting: client-facing 8-step intake wizard, admin dashboard, secure page-by-page trust draft preview (watermarked, anti-copy/print), Square-powered payment workflow with ACH tracking, final trust unlock with notarization instructions, legal disclosures + acknowledgments, business asset SOS advisory, EIN admin-filing, branding, and messaging.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth (httpOnly cookies), bcrypt, brute-force lockout.
- **Frontend**: React (CRA + craco) + Tailwind + shadcn/ui. Cormorant Garamond + IBM Plex Sans.
- **3rd-party**: Resend (email), Emergent LLM key (AI Q&A — Claude Sonnet), Dropbox Sign (dormant), Square (invoices + webhooks — live production), Twilio SMS + **Twilio WhatsApp** (fan-out admin notifications, per-case outbound + inbound thread).
- **Trust preview**: pypdfium2 renders per-page PNGs at low DPI with tiled diagonal watermark.

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
