# Email Deliverability Setup — igcfirm.com

Client emails from `support@igcfirm.com` will land in **Spam** at Gmail / Outlook / Yahoo until the DNS records below are added. **You must add these once at your domain registrar.** The code side of deliverability is already done — proper `From` display name, `Reply-To`, HTML+text multipart, `List-Unsubscribe` header, and the branded logo header are all live.

## Step 1 — Verify `igcfirm.com` in Resend

1. Log in to https://resend.com/domains as the account that owns your API key `re_4T9ZwYa9…`.
2. Click **Add Domain** → enter `igcfirm.com`.
3. Resend shows a list of DNS records — copy them exactly. They look like this (values will be specific to your Resend account, not the placeholders below):

```
Record 1  MX     send.igcfirm.com                → feedback-smtp.us-east-1.amazonses.com  (priority 10)
Record 2  TXT    send.igcfirm.com                → "v=spf1 include:amazonses.com ~all"
Record 3  TXT    resend._domainkey.igcfirm.com   → p=MIGfMA0GCSq… (long DKIM public key)
Record 4  TXT    _dmarc.igcfirm.com              → "v=DMARC1; p=none;"
```

## Step 2 — Add the records at your DNS provider

Log in to whoever hosts DNS for `igcfirm.com` (GoDaddy / Cloudflare / Route 53 / Google Domains / etc.) and add all 4 records above.

**⚠️ Important:**
- If a **TXT record already exists at the root `@`** with `v=spf1 …` for another service (e.g., a mailbox provider), do NOT add a second SPF record. Instead, merge Resend's `include:amazonses.com` into the existing one. Only ONE SPF record per domain is allowed.
- For DMARC start with `p=none` (monitor mode). After a week of clean reports, tighten to `p=quarantine` and eventually `p=reject`.
- Cloudflare users: set the DNS records to **DNS only** (grey cloud), NOT **Proxied** (orange cloud).

## Step 3 — Verify in Resend

Wait 5-30 minutes for DNS propagation, then click **Verify** in the Resend dashboard for each record. All four should show **Verified** ✅. Send a test email to Gmail using Resend's UI to confirm it lands in the Inbox (check the raw headers — you should see `dkim=pass`, `spf=pass`, `dmarc=pass`).

## Step 4 — What the code already does (no action needed)

- ✅ `SENDER_EMAIL=support@igcfirm.com` (verified in `/app/backend/.env`)
- ✅ `From` header formatted as `Iron Gate Consulting <support@igcfirm.com>` (display name)
- ✅ `Reply-To: support@igcfirm.com`
- ✅ Every email is sent as **HTML + plain-text multipart** (Gmail penalizes HTML-only mail)
- ✅ `List-Unsubscribe` + `List-Unsubscribe-Post: One-Click` headers per RFC 8058
- ✅ Branded logo in email header (Iron Gate shield PNG at `/irongate-logo.png`)
- ✅ No spammy words in transactional subjects (no "FREE", no ALL CAPS, no "!!!")

## Optional — BIMI (brand logo in Gmail inbox)

Once DMARC is at `p=quarantine` or `p=reject`, you can add a BIMI record so Gmail displays the Iron Gate shield in the recipient's inbox next to the sender name. BIMI requires:

1. Your logo as an SVG P/S file (Tiny SVG format).
2. A **VMC certificate** from Entrust or DigiCert (paid; ~$1,500/year).
3. A DNS TXT record at `default._bimi.igcfirm.com`.

Not required for inbox delivery — just a visual upgrade. Skip unless you're doing brand-forward outreach.

## Verifying it worked

Send a test invite from the portal to a Gmail address you own, then in Gmail click the three-dot menu → **Show original**. You want to see:

```
SPF:     PASS with domain igcfirm.com
DKIM:    'PASS' with domain igcfirm.com
DMARC:   'PASS' with domain igcfirm.com
```

If any show FAIL, re-check the DNS records were added exactly as shown in Resend.
