# Trust Intake & Client Portal — PRD

## Problem Statement
Full Trust Intake & Client Portal web app with strict section-by-section (HARD STOP) validation, single/joint trust support, document uploads, EIN workflow, client↔admin messaging, status tracking, admin dashboard, and branding customization.

## Architecture
- **Backend**: FastAPI + MongoDB (motor). JWT auth (httpOnly cookies), bcrypt hashing, brute-force lockout using X-Forwarded-For. Emergent object storage for file uploads. Resend email notifications (mocked when key not set).
- **Frontend**: React (CRA + craco) + Tailwind + shadcn/ui. Cormorant Garamond + IBM Plex Sans. Deep Slate Navy / Warm Sand / Legacy Bronze palette.

## User Personas
- **Client (age 50+)**: completes intake wizard, uploads docs, messages the firm, tracks status.
- **Admin (estate attorney/paralegal)**: reviews cases, updates status, adds notes, uploads EIN letter, sends messages, customizes branding.

## Core Requirements (Done)
- Single/Joint Trust selector
- Grantor intake (1 or 2 grantors, required + optional fields, masked SSN)
- Trustee intake (required)
- Successor Trustees (up to 3, at least 1 required)
- Beneficiaries (primary + contingent, percentage)
- Assets (7 categories with category-specific required fields)
- EIN workflow with auth checkbox + masked SSN; admin can upload EIN letter; client can download
- Documents: ID + Proof of Address required; deeds, titles, statements, etc. optional
- Messaging per section + general thread
- 7-stage status tracker
- Admin dashboard: list, filters, search, status, notes, EIN request, messaging
- Branding (business name, colors, logo URL, header image URL)
- HARD STOP: step navigation locks future steps until prior required sections are complete

## Implementation Status (2026-02-18)
- ✅ Backend: auth, trust-cases CRUD, documents upload/download via Emergent storage, messaging, admin endpoints, branding
- ✅ Frontend: login/register, client portal, 8-step wizard with HARD STOP, admin dashboard + case detail, branding page
- ✅ Admin seeded: support@igcfirm.com / Wllorenzo03!
- ✅ Brute-force lockout via X-Forwarded-For

## Backlog (Next Phase)
- **P0**: Provide real Resend API key to enable email notifications (currently mocked/logged)
- **P1**: Email templates branded with firm colors
- **P1**: Server-side beneficiary percentage sum validation (must equal 100)
- **P1**: PDF export of completed intake for client records
- **P2**: Signed download URLs with expiry
- **P2**: 2FA for admin accounts
- **P2**: Multi-admin roles (paralegal vs attorney)
- **P2**: Industry-template clones (real estate intake, business formation intake)

## Endpoints Summary
See `/app/memory/test_credentials.md` and `/app/backend/server.py`.

## Updates — 2026-02-18 (later)
- ✅ Branded welcome email (HTML with navy/bronze palette) sent to client on case creation
- ✅ Admin notification email on new case
- ✅ Server-side beneficiary percentage validation (cannot exceed 100%)
- ✅ PDF export (reportlab) — branded summary with masked SSNs; endpoints: `GET /api/trust-cases/{id}/export.pdf`
- ✅ PDF auto-emailed to client (as attachment) when admin sets status to **Completed**
- ✅ Download buttons on Client Portal, Admin Case Detail, and the wizard Review step
- ✅ Resend API key configured

## Resend — Important Note
Resend returned: *"You can only send testing emails to your own email address (wes@igcfirm.com). To send emails to other recipients, please verify a domain at resend.com/domains, and change the `from` address to an email using this domain."*

This is a Resend account restriction, not a code bug. To go live:
1. Go to https://resend.com/domains → Add Domain → add `igcfirm.com` → add the DNS records shown
2. Wait a few minutes for DNS verification
3. Update `SENDER_EMAIL` in `/app/backend/.env` to something like `noreply@igcfirm.com`
4. `sudo supervisorctl restart backend`

## Updates — 2026-02-18 (Session 3 — build-to-completion)

### ✅ Shipped
- **Admin-initiated client invite** — `POST /api/admin/invite-client`, `GET /api/auth/invite-info`, `POST /api/auth/accept-invite`. Admin dashboard has "Invite client" button → dialog → branded magic-link email → `/accept-invite?token=…` page → set password → auto-login → land on intake wizard.
- **Progress-status emails** — every admin status change sends a branded email to the client with the new status and copy explaining what it means (incl. "Waiting on Documents", "In Review", "Drafting Trust", "Ready for Signing", "Completed").
- **Referral block** — the completion email now has "Your family deserves the same peace of mind" block with a unique referral link (`/register?ref=<case-prefix>`).
- **E-sign integration (code complete, key-gated)** — Dropbox Sign via `dropbox-sign` SDK. Endpoints: `POST /admin/trust-cases/{id}/send-for-signing`, `GET /admin/trust-cases/{id}/signature-status`, `GET /admin/trust-cases/{id}/download-signed`, `GET /trust-cases/{id}/download-signed` (client side). UI: "E-Signature" section on AdminCaseDetail with Send-for-Signing dialog, refresh, and download. Client portal shows "Signed Trust" download button when signed.
- **E-sign intentionally disabled** — `DROPBOX_SIGN_API_KEY` blank in `.env`; endpoints return 503 with clean setup message. Flip this by pasting a key and restarting backend.

### Testing
- Iteration 2: 39/39 backend tests pass. Brute-force lockout (iteration 1 issue) now passes. All new flows verified.

### To activate e-sign later
1. Get key from https://sign.dropbox.com → Settings → API → Generate key
2. Set `DROPBOX_SIGN_API_KEY="..."` in `/app/backend/.env`
3. `sudo supervisorctl restart backend`
4. Flip test mode to production when ready with `DROPBOX_SIGN_TEST_MODE="false"`

## Updates — 2026-02-19 (Session 4)
### ✅ Admin inbox + Resend invite
- **Admin notifications bell** — new `GET /api/admin/notifications` returns unread messages grouped by case (limit 50, 30s polling). Layout header shows a bell icon with red unread-count badge + popover listing groups (client name/email, trust type/status, latest message preview, time-ago). Click a group → navigates to admin case detail; messages become read on load.
- **Pending-invite banner + Resend invite** — `admin_get_case` now returns `pending_invite: {email, expires_at, created_at}` when the case was invited but the client hasn't accepted. AdminCaseDetail shows an amber "Invitation pending acceptance" banner with a one-click "Resend invite" button → `POST /api/admin/trust-cases/{id}/resend-invite` invalidates old tokens, creates a new one, resends the branded invite email.

## Updates — 2026-02-19 (Session 5 — workflow alignment)
### ✅ Fixed issues raised by user
- **Status ≠ reality** → `pending_items` now computed server-side (required-doc-missing + open admin requests) and attached to every case read (client & admin). Admin case detail shows a "Client-facing outstanding items" summary right under the status selector.
- **Generic 'Waiting on Documents' email** → `_status_change_email_html` now accepts `pending_items`; when status is set to "Waiting on Documents", the email lists **exactly which documents are still needed** (label + optional note) in a yellow callout and the CTA deep-links to `/intake/{id}?step=documents`.
- **Email link looping back to Step 1** → `IntakeWizard` now reads `useSearchParams('step')` and jumps straight to the requested step (respects HARD STOP; if prior steps aren't complete it remains at the earliest incomplete step by design).
- **Optional uploads looked required** → `DocumentsStep` rewritten with clear "Required" and collapsible "Optional uploads" sections; each upload shows a colored tag (Required / Optional / Requested by your team) and a green check when filled.
- **Admin had no way to request specific docs** → new `POST /api/admin/trust-cases/{id}/doc-requests`, `DELETE …/doc-requests/{req_id}`, `POST …/mark-fulfilled`. Auto-fulfill when client uploads a matching `doc_type`. New admin UI component `DocRequestsPanel` with type dropdown, optional custom label, note to client, per-row "mark received" and "cancel". Creating a request sends a branded "Document requested" email to the client.
- **Assets should be document-based** → `AssetStep` redesigned with a mode toggle:
  - **Upload documents** (default): select type (Bank Statement / Deed / Title / Insurance Policy / Business Document), upload; admin reviews and extracts. Step-complete when any such doc exists.
  - **Enter manually**: original form preserved.
  - `isStepComplete('assets')` now true if (manual asset list ≥ 1) OR (at least one asset-category doc uploaded).
- **Client portal "Action required" card** → top of each case row with `pending_items.length`, bullet list (label + note), and a primary "Upload now" button that deep-links to Documents step.

### Testing
- iteration_3: **47/47 backend tests pass** (39 regression + 8 new for doc-requests/pending-items). One critical runtime issue (missing `AlertTriangle` import) caught and auto-fixed by testing agent.

### Endpoints added
- `POST /api/admin/trust-cases/{id}/doc-requests`
- `DELETE /api/admin/trust-cases/{id}/doc-requests/{req_id}`
- `POST /api/admin/trust-cases/{id}/doc-requests/{req_id}/mark-fulfilled`
- Case GETs now include `pending_items: [{kind, doc_type, label, note, step}]`


## Updates — 2026-02-20 (Session 6 — AI assistant + Notes/Questions)
### ✅ Shipped
- **Notes/Questions box per section** — `NotesQuestionsBox` added to Grantors, Trustee, Successor, Beneficiaries, Assets, Documents. Client types → AI answers inline if confident, otherwise escalates. Past questions/answers/admin replies render as an inline thread.
- **AI assistant** — `ai_assistant.py` uses Claude Sonnet 4.5 via Emergent LLM key + `emergentintegrations`. System prompt contains plain-English role definitions and scope rules; outputs `CONFIDENCE: CONFIDENT/NOT_CONFIDENT` prefix which backend parses. One retry with 0.6s backoff on transient LLM errors.
- **Plain-English role definitions** — `RoleDefinition` helper blocks with "What this means / Who this is / Who to put here" rendered on each role step.
- **SMS (key-gated)** — `sms.py` with Twilio SDK; blank env vars currently. When a question is escalated: `send_admin_sms()` attempts SMS (no-op + `[sms-mock]` log if disabled), then **email fallback** to admin via Resend with the question + admin reply link.
- **Admin "Client Questions" page** — `/admin/questions` with 4 count cards (Needs reply / AI answered / Replied / All), per-question cards showing AI response + reply textarea. Reply emails the client, flips status to `admin_replied`. Nav link added.

### Testing
- Iteration 4: **55/55 backend tests pass** (47 regression + 8 new `TestQuestionsAndAI`). No critical or frontend issues. Minor: LLM budget-exceeded transient handled by retry + graceful escalation.

### Environment
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`, `ADMIN_PHONE_NUMBER` present in `.env` but blank. Fill them in + restart backend to enable real SMS; email fallback stays in place.
