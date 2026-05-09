import React, { useState, useEffect } from "react";
import { SectionHeader, Field, Txt } from "./_shared";
import { CheckCircle2, ShieldCheck, Download, Scale, Building2, Stamp } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";

const LINE = ({ l, v }) => (
  <div className="flex justify-between border-b border-dashed border-[#E2E0DA] py-1.5 text-sm">
    <span className="text-[#64748B]">{l}</span>
    <span className="text-navy font-medium text-right">{v || "—"}</span>
  </div>
);

export default function ReviewStep({ trustCase, caseId, reload }) {
  const g = trustCase.grantors || [];
  const t = trustCase.trustees?.[0];
  const sct = trustCase.successor_trustees || [];
  const b = trustCase.beneficiaries || [];
  const a = trustCase.assets || [];
  const docs = (trustCase.documents || []).filter((d) => !d.is_deleted);

  const hasBusinessAsset =
    a.some(x => x.asset_type === "business") ||
    docs.some(d => d.doc_type === "business_document");

  const acks = trustCase.acknowledgments || {};
  const [disclosureAck, setDisclosureAck] = useState(!!acks.disclosure_ack);
  const [stateLawsAck, setStateLawsAck] = useState(!!acks.state_laws_ack);
  const [notarizationAck, setNotarizationAck] = useState(!!acks.notarization_ack);
  const [businessSosAck, setBusinessSosAck] = useState(!!acks.business_sos_ack);
  const [trustName, setTrustName] = useState(trustCase.trust_name || "");
  const [savingName, setSavingName] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setDisclosureAck(!!(trustCase.acknowledgments || {}).disclosure_ack);
    setStateLawsAck(!!(trustCase.acknowledgments || {}).state_laws_ack);
    setNotarizationAck(!!(trustCase.acknowledgments || {}).notarization_ack);
    setBusinessSosAck(!!(trustCase.acknowledgments || {}).business_sos_ack);
    setTrustName(trustCase.trust_name || "");
  }, [trustCase.id, trustCase.updated_at]);

  const saveTrustName = async () => {
    const name = (trustName || "").trim();
    if (name.length < 3) { toast.error("Please enter the trust name."); return; }
    setSavingName(true);
    try {
      await api.put(`/trust-cases/${caseId}/trust-name`, { trust_name: name });
      toast.success("Trust name saved.");
      reload?.();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSavingName(false); }
  };

  const saveAcks = async (overrides = {}) => {
    setSaving(true);
    try {
      const payload = {
        disclosure_ack: disclosureAck,
        state_laws_ack: stateLawsAck,
        notarization_ack: notarizationAck,
        business_sos_ack: businessSosAck,
        ...overrides,
      };
      await api.put(`/trust-cases/${caseId}/acknowledgments`, payload);
      reload?.();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const submitReviewCompleted = async () => {
    if (!disclosureAck || !stateLawsAck || !notarizationAck) {
      toast.error("Please acknowledge all required disclosures first.");
      return;
    }
    if (hasBusinessAsset && !businessSosAck) {
      toast.error("Please acknowledge the Secretary of State business advisory.");
      return;
    }
    if (!trustCase.trust_name) {
      toast.error("Please enter and save your trust name before completing review.");
      return;
    }
    await saveAcks({ review_completed_ack: true });
    toast.success("Thank you for reviewing your trust. Your agent will contact you shortly.");
  };

  const reviewCompleted = !!acks.review_completed_ack;
  const isReviewPath = (trustCase.intake_path || "new") === "review";

  return (
    <div>
      <SectionHeader num={isReviewPath ? 2 : 8} total={isReviewPath ? 2 : 8}
        title="Review & Submit"
        subtitle={isReviewPath
          ? "Confirm the trust name, acknowledge the legal disclosures below, then complete your review."
          : "Review all the information you've provided, then acknowledge the legal disclosures and complete your review."} />

      {/* ===== Existing Trust Review path: $297 callout ===== */}
      {isReviewPath && (
        <div className="rounded-xl border-2 border-bronze/40 bg-bronze/5 p-5 sm:p-6 mb-8" data-testid="review-path-amount-note">
          <div className="flex items-start gap-3">
            <ShieldCheck className="h-5 w-5 text-bronze shrink-0 mt-0.5" />
            <div>
              <p className="font-serif text-xl sm:text-2xl text-navy mb-1">Existing Trust Review — $297</p>
              <p className="text-sm sm:text-base text-[#334155] leading-relaxed">
                Your existing trust will be reviewed by our legal team at no additional charge.
                Your <b>$297</b> covers enrollment in our free credit repair program, your 90-day cash settlement
                process, and your trust review.
              </p>
            </div>
          </div>
        </div>
      )}

      <div className="bg-bronze/10 border border-bronze/30 rounded-lg p-4 mb-8 flex flex-col sm:flex-row items-start sm:items-center gap-3 justify-between" data-testid="review-complete-banner">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-bronze" />
          <div>
            <p className="font-semibold text-navy">{isReviewPath ? "Your existing trust is uploaded." : "All required intake sections are complete."}</p>
            <p className="text-sm text-[#64748B]">{isReviewPath ? "Acknowledge the legal disclosures below to complete your review." : "Please review the summary below and acknowledge the legal disclosures."}</p>
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <button
            onClick={async () => {
              try {
                const res = await api.get(`/trust-cases/${caseId || trustCase.id}/export.pdf`, { responseType: "blob" });
                const url = URL.createObjectURL(res.data);
                const a = document.createElement("a");
                a.href = url; a.download = `trust-intake-${(caseId || trustCase.id).slice(0,8)}.pdf`; a.click();
                URL.revokeObjectURL(url);
              } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
            }}
            className="btn-accent shrink-0"
            data-testid="review-download-pdf-btn">
            <Download className="h-4 w-4 inline mr-1" /> Intake PDF
          </button>
        </div>
      </div>

      {/* Trust name */}
      <section className="bg-white border border-[#E2E0DA] rounded-lg p-5 mb-6" data-testid="review-trust-name">
        <h3 className="font-serif text-2xl text-navy mb-3">Trust Name</h3>
        <p className="text-sm text-[#64748B] mb-3">
          This name will appear on the EIN filing, trust documents, and the final PDF. Make sure it matches how you want it recorded.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 sm:items-end">
          <div className="flex-1">
            <Field id="review-trust-name" label="Trust name" required>
              <Txt id="review-trust-name" value={trustName} onChange={setTrustName} testId="review-trust-name-input" />
            </Field>
          </div>
          <button onClick={saveTrustName} disabled={savingName} className="btn-primary" data-testid="review-save-trust-name-btn">
            {savingName ? "Saving…" : "Save trust name"}
          </button>
        </div>
      </section>

      <div className="space-y-6" data-testid="review-summary">
        {!isReviewPath && (
          <>
        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Grantors ({g.length})</h3>
          {g.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Grantor {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="DOB" v={x.date_of_birth} />
              <LINE l="Email" v={x.email} />
              <LINE l="Phone" v={x.phone} />
              <LINE l="Marital" v={x.marital_status} />
              <LINE l="Citizenship" v={x.citizenship} />
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Trustee</h3>
          <div className="bg-sand-200/40 rounded-md p-4">
            <LINE l="Name" v={t?.full_legal_name} />
            <LINE l="Relationship" v={t?.relationship} />
            <LINE l="Email" v={t?.email} />
            <LINE l="Phone" v={t?.phone} />
          </div>
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Successor Trustees ({sct.length})</h3>
          {sct.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Successor {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="Relationship" v={x.relationship} />
              <LINE l="Email" v={x.email} />
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Beneficiaries ({b.length})</h3>
          {b.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Beneficiary {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="Relationship" v={x.relationship} />
              <LINE l="Share" v={`${x.percentage}%`} />
              {x.contingent_name && <LINE l="Contingent" v={x.contingent_name} />}
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Assets ({a.length})</h3>
          {a.map((x) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <LINE l="Type" v={x.asset_type} />
              <LINE l="Institution/Property" v={x.institution_name || x.property_address} />
              {x.estimated_value && <LINE l="Est. value" v={`$${Number(x.estimated_value).toLocaleString()}`} />}
            </div>
          ))}
        </section>
          </>
        )}

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Documents ({docs.length})</h3>
          <ul className="bg-sand-200/40 rounded-md p-4 space-y-1 text-sm">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" /> {d.filename} <span className="text-[#64748B]">({d.doc_type})</span>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* ----- Legal Disclosures ----- */}
      <div className="mt-10">
        <h3 className="font-serif text-2xl text-navy mb-4 flex items-center gap-2">
          <Scale className="h-5 w-5 text-bronze" /> Legal Disclosures
        </h3>

        <div className="bg-white border border-[#E2E0DA] rounded-lg p-5 space-y-4" data-testid="review-disclosures">
          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md">
            This trust has been reviewed for accuracy and completeness through my military legal benefits.
            All documents are prepared using standardized trust templates that are commonly reviewed by military legal professionals.
            I am not an attorney and do not provide legal advice. Clients may seek independent legal counsel at any time.
          </div>

          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer" data-testid="ack-disclosure-label">
            <Checkbox checked={disclosureAck} onCheckedChange={(v) => { setDisclosureAck(!!v); saveAcks({ disclosure_ack: !!v }); }} className="mt-0.5" data-testid="ack-disclosure-checkbox" />
            <span className="text-sm text-navy">
              <b>I have read and understand this legal disclosure.</b> I acknowledge this service is not a substitute for legal advice.
            </span>
          </label>

          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md">
            <b>State-specific advisory.</b> Trust laws vary by state. Clients are responsible for ensuring the trust meets their personal legal needs and may seek independent legal counsel in their state at any time.
          </div>
          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer" data-testid="ack-state-laws-label">
            <Checkbox checked={stateLawsAck} onCheckedChange={(v) => { setStateLawsAck(!!v); saveAcks({ state_laws_ack: !!v }); }} className="mt-0.5" data-testid="ack-state-laws-checkbox" />
            <span className="text-sm text-navy"><b>I acknowledge that trust laws vary by state.</b></span>
          </label>

          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md flex items-start gap-2">
            <Stamp className="h-4 w-4 shrink-0 mt-0.5 text-bronze" />
            <span><b>Notarization required.</b> Your trust must be printed and notarized to become legally valid. Please sign in the presence of a notary public and retain the original notarized copy with your important records.</span>
          </div>
          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer" data-testid="ack-notarization-label">
            <Checkbox checked={notarizationAck} onCheckedChange={(v) => { setNotarizationAck(!!v); saveAcks({ notarization_ack: !!v }); }} className="mt-0.5" data-testid="ack-notarization-checkbox" />
            <span className="text-sm text-navy"><b>I understand my trust must be printed and notarized.</b></span>
          </label>

          {hasBusinessAsset && (
            <>
              <div className="text-sm text-[#334155] leading-relaxed p-4 bg-amber-50 border border-amber-300 rounded-md flex items-start gap-2">
                <Building2 className="h-4 w-4 shrink-0 mt-0.5 text-amber-800" />
                <span>
                  <b>Secretary of State — Business Ownership Transfer.</b> If you are placing a business under your trust, most states require you to file a Change of Ownership/Change of Responsible Party form with the Secretary of State. This updates the business registration from your personal name to the trust name. Please contact your Secretary of State's office to complete this step.
                </span>
              </div>
              <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer" data-testid="ack-business-sos-label">
                <Checkbox checked={businessSosAck} onCheckedChange={(v) => { setBusinessSosAck(!!v); saveAcks({ business_sos_ack: !!v }); }} className="mt-0.5" data-testid="ack-business-sos-checkbox" />
                <span className="text-sm text-navy"><b>I acknowledge I am responsible for filing the Change of Ownership with my Secretary of State.</b></span>
              </label>
            </>
          )}
        </div>
      </div>

      {/* ----- Complete Review / Post-review CTAs ----- */}
      {!reviewCompleted ? (
        <div className="mt-10" data-testid="review-completed-section">
          <button
            onClick={submitReviewCompleted}
            disabled={saving}
            className="w-full py-5 sm:py-6 rounded-xl text-white text-xl sm:text-2xl font-bold shadow-lg transition-all active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: "#28a745", minHeight: 64 }}
            data-testid="review-completed-btn">
            {saving ? "Submitting…" : "✓  Complete Review"}
          </button>
          <p className="mt-3 text-center text-xs text-[#64748B]">
            Pressing this button notifies your agent. They will review and send your next steps shortly.
          </p>
        </div>
      ) : (
        <div className="mt-10 rounded-xl bg-green-50 border border-green-300 p-6 sm:p-8 text-center" data-testid="review-completed-badge">
          <CheckCircle2 className="h-10 w-10 text-green-700 mx-auto mb-2" />
          <p className="font-serif text-2xl text-navy mb-1">Review complete</p>
          <p className="text-sm text-[#334155] max-w-lg mx-auto">
            Thank you — your agent has been notified. Next steps will be shown on your portal.
          </p>
          <div className="mt-5 flex flex-col sm:flex-row gap-3 justify-center">
            <a href="/portal" className="btn-primary inline-flex items-center justify-center gap-1" data-testid="review-back-to-portal">
              Back to portal
            </a>
          </div>
        </div>
      )}

      <p className="mt-8 text-center text-xs text-[#94A3B8]" data-testid="review-footer-brand">
        Prepared by <b>Iron Gate Consulting</b> · Reviewed through military legal benefits
      </p>
    </div>
  );
}
