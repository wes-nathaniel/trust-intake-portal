import React from "react";
import { Link } from "react-router-dom";
import { Shield, Phone, Mail, MapPin, ScrollText, FileLock, Users, Building2 } from "lucide-react";

/*
  A2P 10DLC compliance landing page for Twilio brand + campaign registration.
  Single public route — no authentication, no portal chrome, no JS state.
*/

const BUSINESS = {
  legal_name: "IGC Firm — Iron Gate Consulting",
  dba: "Iron Gate Consulting",
  tagline: "Trust Structuring & Client Onboarding",
  technology_partner: "WAAAIR Technology LLC",
  email: "support@igcfirm.com",
  phone_e164: "+19545983681",
  phone_display: "(954) 598-3681",
  address_line_1: "Iron Gate Consulting",
  address_line_2: "Fort Lauderdale, Florida, USA",
  portal_url: "https://trust.igcfirm.com",
  site_url: "https://igcfirm.com",
  effective_date: "April 21, 2026",
};

const Section = ({ id, title, icon: Icon, children }) => (
  <section id={id} className="mb-12 scroll-mt-20">
    <div className="flex items-center gap-3 mb-3 border-b border-[#E2E0DA] pb-2">
      {Icon && <Icon className="h-5 w-5 text-bronze" />}
      <h2 className="font-serif text-2xl sm:text-3xl text-navy">{title}</h2>
    </div>
    <div className="text-[#334155] leading-relaxed space-y-3 text-sm sm:text-base">
      {children}
    </div>
  </section>
);

export default function Company() {
  return (
    <div className="min-h-screen bg-[#F6F4F0] text-[#1C252E]" data-testid="company-landing-page">
      {/* Header */}
      <header className="bg-navy text-white">
        <div className="max-w-4xl mx-auto px-6 py-12 sm:py-16">
          <div className="flex items-center gap-2 text-bronze text-[11px] tracking-[0.3em] uppercase mb-4">
            <Shield className="h-4 w-4" />
            Secure Trust Intake Services
          </div>
          <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl leading-tight" data-testid="page-heading">
            IGC Firm — Trust Structuring &amp; Client Onboarding
          </h1>
          <p className="mt-3 text-white/75 text-sm sm:text-base" data-testid="page-subheading">
            Powered by {BUSINESS.technology_partner}
          </p>
          <div className="mt-6 flex flex-wrap gap-4 text-sm text-white/80">
            <a href={`mailto:${BUSINESS.email}`} className="inline-flex items-center gap-1 hover:text-bronze">
              <Mail className="h-4 w-4" /> {BUSINESS.email}
            </a>
            <a href={`tel:${BUSINESS.phone_e164}`} className="inline-flex items-center gap-1 hover:text-bronze">
              <Phone className="h-4 w-4" /> {BUSINESS.phone_display}
            </a>
            <Link to="/login" className="inline-flex items-center gap-1 hover:text-bronze underline-offset-4 hover:underline">
              Client login →
            </Link>
          </div>
        </div>
      </header>

      {/* Body */}
      <main className="max-w-4xl mx-auto px-6 py-12 sm:py-16">

        <Section id="about" title="About IGC Firm" icon={Building2}>
          <p>
            <b>IGC Firm</b> (operating as <b>Iron Gate Consulting</b>) helps individuals and families build, organize, and complete
            living and revocable trust structures. We provide guided <b>trust structuring</b>, <b>client onboarding</b>, and <b>asset intake</b>
            services through a secure web portal, using standardized trust templates that are commonly reviewed by military legal professionals.
          </p>
          <p>
            Our platform walks clients through a step-by-step intake for grantors, trustees, successor trustees,
            beneficiaries, and trust assets; collects and verifies supporting documents; coordinates EIN filings;
            and produces a final, notarization-ready trust document. Clients communicate with our team through the
            portal and through SMS notifications they opt into when they begin their case.
          </p>
          <p className="text-[#64748B]">
            We are not a law firm and do not provide legal advice. Clients may seek independent legal counsel in their
            state at any time.
          </p>
        </Section>

        <Section id="services" title="What we do" icon={Users}>
          <ul className="list-disc pl-6 space-y-2">
            <li><b>Trust structuring</b> — guided intake for single and joint living trusts with strict, section-by-section validation.</li>
            <li><b>Client onboarding</b> — invitation-based onboarding with a secure, branded client portal.</li>
            <li><b>Asset intake</b> — accepts bank accounts, real estate, vehicles, business interests, insurance policies, and supporting documents.</li>
            <li><b>EIN coordination</b> — we file the Employer Identification Number with the IRS on behalf of the trust.</li>
            <li><b>Document review</b> — page-by-page secure draft trust review, followed by final unlocked download after payment.</li>
            <li><b>Status notifications</b> — transactional email and (opt-in) SMS updates about a client's case.</li>
          </ul>
        </Section>

        <Section id="contact" title="Contact information" icon={Phone}>
          <div className="grid sm:grid-cols-2 gap-4">
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA]">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1">Business name</p>
              <p className="font-semibold">{BUSINESS.legal_name}</p>
            </div>
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA]">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1">Technology partner</p>
              <p className="font-semibold">{BUSINESS.technology_partner}</p>
            </div>
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA]">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> Email</p>
              <a href={`mailto:${BUSINESS.email}`} className="font-semibold text-navy hover:text-bronze break-all">{BUSINESS.email}</a>
            </div>
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA]">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 flex items-center gap-1"><Phone className="h-3.5 w-3.5" /> Phone</p>
              <a href={`tel:${BUSINESS.phone_e164}`} className="font-semibold text-navy hover:text-bronze">{BUSINESS.phone_display}</a>
            </div>
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA] sm:col-span-2">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> Business location</p>
              <p className="font-semibold">{BUSINESS.address_line_1}</p>
              <p className="text-[#64748B]">{BUSINESS.address_line_2}</p>
            </div>
            <div className="p-4 rounded-lg bg-white border border-[#E2E0DA] sm:col-span-2">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1">Client portal</p>
              <a href={BUSINESS.portal_url} className="font-semibold text-navy hover:text-bronze">{BUSINESS.portal_url}</a>
            </div>
          </div>
          <p className="text-xs text-[#64748B] mt-3">
            Text messages to {BUSINESS.phone_display} are not monitored. For fastest support, please email {BUSINESS.email} or sign in to the client portal.
          </p>
        </Section>

        {/* SMS Terms & Opt-in Disclosure (required by A2P 10DLC) */}
        <Section id="sms" title="SMS Terms &amp; Opt-in Disclosure" icon={Phone}>
          <p>
            IGC Firm uses SMS text messaging only to send transactional service updates to its internal staff and to clients
            who have affirmatively opted in through the client portal.
          </p>
          <ul className="list-disc pl-6 space-y-2">
            <li><b>Opt-in.</b> Clients opt in when they register for an IGC Firm client account and when they click
              <i> "Complete Review"</i> or <i>"Schedule a Call"</i> inside the portal. A checkbox on the registration screen
              and the action of pressing either button constitutes the client's consent to receive SMS messages related to their case.</li>
            <li><b>Message frequency.</b> Message frequency varies. Typical volume is 1–5 messages per case milestone
              (status updates, payment confirmation, scheduled callback acknowledgment).</li>
            <li><b>Message &amp; data rates.</b> Standard message and data rates may apply.</li>
            <li><b>STOP &amp; HELP.</b> Reply <b>STOP</b> to any message to opt out of future SMS at any time. Reply <b>HELP</b>
              for help. You may also email {BUSINESS.email} to opt out manually.</li>
            <li><b>Carriers.</b> Supported on all major U.S. carriers. Carriers are not liable for delayed or undelivered messages.</li>
            <li><b>No sharing.</b> We do not share SMS opt-in data or phone numbers with third parties or affiliates for marketing purposes. See our <a href="#privacy" className="underline">Privacy Policy</a> for details.</li>
          </ul>
          <p className="text-xs text-[#64748B]">
            Examples of messages you may receive: <i>"IGC: your trust is ready for review."</i> &middot;
            <i> "IGC: payment received, your final trust will unlock shortly."</i> &middot;
            <i> "IGC: a team member will call you from a 954 number within 10 minutes."</i>
          </p>
        </Section>

        {/* Privacy Policy */}
        <Section id="privacy" title="Privacy Policy" icon={FileLock}>
          <p className="text-xs text-[#64748B]">Effective date: {BUSINESS.effective_date}</p>

          <h3 className="font-serif text-xl text-navy mt-4">1. Who we are</h3>
          <p>{BUSINESS.legal_name} ("IGC Firm," "we," "us," or "our") operates the client portal at {BUSINESS.portal_url}. This
            Privacy Policy explains how we collect, use, and share information when you use our services.</p>

          <h3 className="font-serif text-xl text-navy mt-4">2. Information we collect</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li><b>Account information:</b> name, email, phone number, and password (hashed).</li>
            <li><b>Trust intake information:</b> legal names, dates of birth, marital status, citizenship, addresses, phone numbers, Social Security numbers of grantors (encrypted at rest and masked in all outputs), beneficiary details, asset details, and uploaded supporting documents.</li>
            <li><b>Payment information:</b> processed by our payment processor (Square). We do not store card numbers or bank account numbers. We retain invoice identifiers and payment status.</li>
            <li><b>Usage &amp; device data:</b> IP address, browser/device metadata, session cookies, and basic logs (only as needed for security and service operation).</li>
            <li><b>SMS data:</b> phone numbers, opt-in timestamps, opt-out events, and messages we send.</li>
          </ul>

          <h3 className="font-serif text-xl text-navy mt-4">3. How we use information</h3>
          <ul className="list-disc pl-6 space-y-1">
            <li>To deliver, maintain, and improve our trust intake services.</li>
            <li>To generate trust documents, coordinate EIN filings, and process payments.</li>
            <li>To send transactional emails and SMS status updates relating to your case.</li>
            <li>To comply with legal obligations, prevent fraud, and enforce our Terms of Service.</li>
          </ul>

          <h3 className="font-serif text-xl text-navy mt-4">4. How we share information</h3>
          <p>
            We do <b>not</b> sell your personal information. We only share information with vetted service providers who
            act on our behalf and are contractually required to protect it, including:
          </p>
          <ul className="list-disc pl-6 space-y-1">
            <li><b>Square</b> — payment processing (invoices, payments, webhooks).</li>
            <li><b>Twilio</b> — SMS delivery.</li>
            <li><b>Resend</b> — transactional email delivery.</li>
            <li><b>Cloud hosting &amp; storage providers</b> — secure storage of uploaded documents and databases.</li>
            <li><b>Legal/compliance recipients</b> — where required by law or to protect the rights, safety, or property of IGC Firm or our clients.</li>
          </ul>
          <p>
            <b>SMS opt-in consent is not shared with any third party for marketing.</b> Opt-in data is used solely to operate our SMS notification service.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">5. Data retention</h3>
          <p>
            We retain client case information for as long as your account is active and for any period required by
            applicable record-retention laws (typically seven years). You may request deletion at any time; some data
            may be retained in backups or as required by law.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">6. Security</h3>
          <p>
            We use industry-standard technical and organizational measures to protect information, including encryption
            in transit (TLS) and at rest, password hashing, brute-force lockout, role-based access controls, and audit
            logs. No system is 100% secure — please notify us immediately if you suspect unauthorized access.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">7. Your rights</h3>
          <p>
            Subject to applicable law, you may request: (a) access to your personal information; (b) correction of
            inaccuracies; (c) deletion; (d) portability; and (e) to object to or restrict processing. To exercise any
            right, email {BUSINESS.email}. We will verify your identity before acting on your request.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">8. Children</h3>
          <p>Our services are not directed to children under 16 and we do not knowingly collect their information.</p>

          <h3 className="font-serif text-xl text-navy mt-4">9. Changes</h3>
          <p>
            We may update this Privacy Policy from time to time. Material changes will be notified by email or an in-app
            notice. Continued use after the effective date constitutes acceptance.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">10. Contact</h3>
          <p>
            For any privacy question or request, email <a className="underline" href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> or write to {BUSINESS.address_line_1}, {BUSINESS.address_line_2}.
          </p>
        </Section>

        {/* Terms of Service */}
        <Section id="terms" title="Terms of Service" icon={ScrollText}>
          <p className="text-xs text-[#64748B]">Effective date: {BUSINESS.effective_date}</p>

          <h3 className="font-serif text-xl text-navy mt-4">1. Acceptance of terms</h3>
          <p>
            By using the IGC Firm client portal at {BUSINESS.portal_url} (the "Services"), you agree to these Terms of
            Service ("Terms"). If you do not agree, do not use the Services.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">2. Nature of services &amp; no legal advice</h3>
          <p>
            IGC Firm provides trust structuring, client onboarding, asset intake, document coordination, and payment
            services. <b>IGC Firm is not a law firm and does not provide legal advice.</b> All documents are prepared
            using standardized trust templates commonly reviewed by military legal professionals. Trust laws vary by
            state and you may seek independent legal counsel at any time.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">3. Accounts &amp; accuracy</h3>
          <p>
            You agree to provide accurate, complete information, to keep your account credentials secure, and to notify
            us of unauthorized access. You are responsible for all activity on your account.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">4. Fees, payment &amp; refunds</h3>
          <p>
            Fees are quoted by IGC Firm per case and charged through our payment processor (Square). ACH payments may
            take 3–5 business days to clear. Your final trust document is unlocked only after your payment has cleared
            or our staff has manually confirmed receipt. Refund requests are evaluated case-by-case and honored only
            where documents have not yet been delivered in unlocked form.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">5. SMS communications</h3>
          <p>
            When you opt in, you consent to receive transactional SMS messages from IGC Firm regarding your case (status
            updates, callback confirmations, payment confirmations). Message frequency varies; standard message and
            data rates may apply. Reply <b>STOP</b> to opt out at any time.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">6. Acceptable use</h3>
          <p>You agree not to: (a) use the Services for any unlawful purpose; (b) attempt to access or interfere with
            any data that is not yours; (c) reverse engineer, resell, or exploit any part of the Services; (d) upload
            malicious code; (e) misrepresent your identity.</p>

          <h3 className="font-serif text-xl text-navy mt-4">7. Intellectual property</h3>
          <p>
            IGC Firm owns the portal, document templates, and all related intellectual property. We grant you a limited,
            non-transferable license to use the Services solely for the intended purpose. Trust documents generated for
            you are yours to keep and use upon payment.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">8. Draft preview restrictions</h3>
          <p>
            Draft trust documents displayed in the portal are watermarked, low-resolution previews. You may not
            attempt to copy, extract, print, circumvent watermarks on, or redistribute draft previews. Final documents
            are delivered in clean form only after payment.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">9. Third-party services</h3>
          <p>
            The Services integrate with third parties (Square for payments, Twilio for SMS, Resend for email, among
            others). Your use of those services is subject to their terms; IGC Firm is not responsible for third-party
            outages or errors.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">10. Disclaimers</h3>
          <p>
            The Services are provided "as is" and "as available," without warranties of any kind, express or implied,
            including merchantability, fitness for a particular purpose, non-infringement, or uninterrupted operation.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">11. Limitation of liability</h3>
          <p>
            To the maximum extent permitted by law, IGC Firm and {BUSINESS.technology_partner} will not be liable for any
            indirect, incidental, special, consequential, or punitive damages, or any loss of profits or revenues. Our
            aggregate liability for any claim arising from the Services will not exceed the amount paid by you to IGC
            Firm in the twelve (12) months preceding the claim.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">12. Indemnification</h3>
          <p>
            You agree to indemnify and hold harmless IGC Firm, {BUSINESS.technology_partner}, and their officers,
            employees, and agents from any claim arising out of your use of the Services or your violation of these Terms.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">13. Termination</h3>
          <p>
            You may stop using the Services at any time. We may suspend or terminate your account for violations of
            these Terms, for non-payment, or for any abuse. Upon termination, certain provisions survive (fees owed,
            disclaimers, IP, limitations of liability).
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">14. Governing law &amp; venue</h3>
          <p>
            These Terms are governed by the laws of the State of Florida, without regard to conflict-of-law principles.
            The exclusive venue for any dispute is the state or federal courts located in Broward County, Florida.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">15. Changes</h3>
          <p>
            We may update these Terms from time to time. The effective date at the top reflects the latest version.
            Continued use after the effective date constitutes acceptance.
          </p>

          <h3 className="font-serif text-xl text-navy mt-4">16. Contact</h3>
          <p>
            Questions? Email <a className="underline" href={`mailto:${BUSINESS.email}`}>{BUSINESS.email}</a> or write to {BUSINESS.address_line_1}, {BUSINESS.address_line_2}.
          </p>
        </Section>
      </main>

      {/* Footer */}
      <footer className="border-t border-[#E2E0DA] bg-white">
        <div className="max-w-4xl mx-auto px-6 py-8 text-center text-xs text-[#64748B] space-y-1">
          <p data-testid="footer-waair">Powered by <b>{BUSINESS.technology_partner}</b></p>
          <p>&copy; {new Date().getFullYear()} {BUSINESS.legal_name}. All rights reserved.</p>
          <p className="text-[#94A3B8]">
            <a href="#privacy" className="hover:text-navy">Privacy Policy</a>{" · "}
            <a href="#terms" className="hover:text-navy">Terms of Service</a>{" · "}
            <a href="#sms" className="hover:text-navy">SMS Terms</a>{" · "}
            <a href={`mailto:${BUSINESS.email}`} className="hover:text-navy">Contact</a>
          </p>
        </div>
      </footer>
    </div>
  );
}
