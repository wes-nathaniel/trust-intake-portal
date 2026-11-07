# RCA — Trust Intake Portal: deploys not shipping HEAD + SENDER_EMAIL

## Summary
HEAD code is now LIVE. The reason earlier "publishes" did not ship HEAD is that
they resolved to `secret_reuse` runs that re-used a stale image instead of rebuilding
from source. A forced full redeploy (`force_repull=true`) rebuilt HEAD and promoted it.
One item remains unresolved and is the USER's to fix: the production `SENDER_EMAIL`
secret is still NOT `portal@igchq.com`.

## Evidence

### Why HEAD was not shipping (root cause)
- The recent "publish" clicks produced `type=secret_reuse` runs, triggered by
  `secret_change`: run `584b8d9a` (2026-11-06 15:29) and `6f238e5b` (2026-11-04).
- A `secret_reuse` run re-writes secrets and re-deploys the LAST BUILT image
  (`d148b5be`, built 2026-10-30). It does NOT run pull_source or build_image, so
  HEAD (commit 51742ed + the 2 before it) was never compiled or shipped.
- That is why production kept serving the Oct-30 bundle `main.711bb532.js` and
  returned 404 for `POST /api/admin/trust-cases/{id}/resend-status-email`.
- "Publish greys out, nothing happens, last published 40 min ago" = the publish
  succeeded as a secret-only run; no new build was ever produced.

### Fix applied — full rebuild of HEAD (run 6df0efe3, SUCCESS, promoted)
- Triggered `resume_pipeline(force_repull=true)` → `type=redeploy`.
- Build produced a NEW frontend bundle `main.cda857b0.js` (replacing
  `main.711bb532.js`) and synced it to R2:
  `s3://deployer-frontend-artifacts/trust-intake-portal/6df0efe3.../build/static/js/main.cda857b0.js`.
- New image `...:6df0efe3...` built and promoted; `active_run_id` = 6df0efe3.
- Backend route now exists: GET on the endpoint returns **405 Method Not Allowed**
  (was 404). POST without auth will therefore hit auth → 401/403, as expected.
- No CDN/caching problem and no pin-to-old-commit; it was purely the secret_reuse
  run type not rebuilding.

### SENDER_EMAIL — STILL WRONG in production (user action)
- `list_secrets` on the active run (6df0efe3) with expected `portal@igchq.com`:
  `SENDER_EMAIL` → `is_empty=false`, **`matches_expected=false`**.
- Secrets are carried forward from the previous prod run; the prior secret_reuse
  run also did not hold `portal@igchq.com`. So the "LIVE SENDER_EMAIL update" was
  never actually saved to the production value (or was saved with a different
  value / stray whitespace).
- Consequence: Resend sends will continue to fail with a domain-verification error
  until SENDER_EMAIL is exactly `portal@igchq.com` AND the `igchq.com` domain is
  verified in the Resend account behind `RESEND_API_KEY`.
- `SENDER_EMAIL` is a USER-owned custom secret — I cannot set it. I also cannot
  inspect the Resend account to confirm `igchq.com` verification (external service).

## Required actions
1. USER — Deployment Panel → Secrets: set `SENDER_EMAIL` = `portal@igchq.com`
   (no display name, no trailing space), save, then redeploy.
2. USER / third party — confirm `igchq.com` is a verified sending domain in the
   Resend account tied to `RESEND_API_KEY`, else sends still fail.
3. After both, send one test email to confirm no domain error.
