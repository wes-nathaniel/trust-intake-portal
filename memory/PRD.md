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
