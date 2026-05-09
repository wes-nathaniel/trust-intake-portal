import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import { Users, User, ArrowRight, FileSearch, FilePlus, ScrollText } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Field, Txt } from "@/pages/intake/_shared";

export default function StartNew() {
  const navigate = useNavigate();
  const [hasExistingTrust, setHasExistingTrust] = useState(null); // null | true | false
  const [trustType, setTrustType] = useState("single");
  const [trustName, setTrustName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const create = async () => {
    if (hasExistingTrust === null) {
      toast.error("Please answer the question above to continue.");
      return;
    }
    const name = (trustName || "").trim();
    if (name.length < 3) {
      toast.error("Please enter the trust name.");
      return;
    }
    setSubmitting(true);
    try {
      const intake_path = hasExistingTrust ? "review" : "new";
      const payload = { intake_path, trust_name: name };
      // trust_type only meaningful for new path; default "single" for review
      payload.trust_type = hasExistingTrust ? "single" : trustType;
      const { data } = await api.post("/trust-cases", payload);
      navigate(`/intake/${data.id}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  return (
    <Layout>
      <h1 className="font-serif text-3xl sm:text-4xl text-navy mb-2">Start a new trust intake</h1>
      <p className="text-[#64748B] mb-8 max-w-2xl">
        First, tell us whether you already have a trust. We'll guide you through the right path.
      </p>

      <div className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-8 max-w-2xl">
        {/* ========== Step 1: Existing trust question ========== */}
        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">1. Tell us about your trust</p>
        <p className="font-serif text-xl sm:text-2xl text-navy mb-4">Do you currently have a living trust set up?</p>

        <div className="grid sm:grid-cols-2 gap-3 mb-2">
          <button
            type="button"
            onClick={() => setHasExistingTrust(false)}
            className={`text-left border rounded-xl p-4 sm:p-5 transition-all ${
              hasExistingTrust === false ? "border-bronze bg-bronze/5 ring-2 ring-bronze/30" : "border-[#E2E0DA] hover:border-bronze"
            }`}
            data-testid="has-existing-trust-no">
            <div className="h-10 w-10 rounded-full bg-sand-200 flex items-center justify-center mb-3">
              <FilePlus className="h-5 w-5 text-navy" />
            </div>
            <h3 className="font-serif text-xl text-navy">No</h3>
            <p className="text-sm text-[#64748B] mt-1">I want to create a new trust.</p>
          </button>
          <button
            type="button"
            onClick={() => setHasExistingTrust(true)}
            className={`text-left border rounded-xl p-4 sm:p-5 transition-all ${
              hasExistingTrust === true ? "border-bronze bg-bronze/5 ring-2 ring-bronze/30" : "border-[#E2E0DA] hover:border-bronze"
            }`}
            data-testid="has-existing-trust-yes">
            <div className="h-10 w-10 rounded-full bg-sand-200 flex items-center justify-center mb-3">
              <FileSearch className="h-5 w-5 text-navy" />
            </div>
            <h3 className="font-serif text-xl text-navy">Yes</h3>
            <p className="text-sm text-[#64748B] mt-1">I already have a trust I'd like reviewed.</p>
          </button>
        </div>

        {/* Path-specific note */}
        {hasExistingTrust === true && (
          <div className="mt-4 mb-2 rounded-lg border-2 border-bronze/40 bg-bronze/5 p-4" data-testid="review-path-note">
            <p className="font-serif text-lg text-navy mb-1">Existing Trust Review — $297</p>
            <p className="text-sm text-[#334155] leading-relaxed">
              Your existing trust will be reviewed by our legal team at no additional charge. Your <b>$297</b> covers
              enrollment in our free credit repair program, your 90-day cash settlement process, and your trust review.
            </p>
          </div>
        )}
        {hasExistingTrust === false && (
          <div className="mt-4 mb-2 rounded-lg border border-[#E2E0DA] bg-sand-200/40 p-4" data-testid="new-path-note">
            <p className="font-serif text-lg text-navy mb-1">New Trust Drafting — $997</p>
            <p className="text-sm text-[#334155] leading-relaxed">
              We'll guide you through an 8-step intake to draft your new trust. Final price <b>$997</b>, payable after
              you've reviewed and approved the draft.
            </p>
          </div>
        )}

        {/* ========== Step 2: Trust type (NEW path only) ========== */}
        {hasExistingTrust === false && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">2. Choose trust type</p>
            <div className="grid sm:grid-cols-2 gap-3 mb-6">
              <button
                type="button"
                onClick={() => setTrustType("single")}
                className={`text-left border rounded-xl p-4 sm:p-5 transition-all ${
                  trustType === "single" ? "border-bronze bg-bronze/5 ring-2 ring-bronze/30" : "border-[#E2E0DA] hover:border-bronze"
                }`}
                data-testid="new-trust-single">
                <div className="h-10 w-10 rounded-full bg-sand-200 flex items-center justify-center mb-3">
                  <User className="h-5 w-5 text-navy" />
                </div>
                <h3 className="font-serif text-xl text-navy">Single Trust</h3>
                <p className="text-sm text-[#64748B] mt-1">One grantor.</p>
              </button>
              <button
                type="button"
                onClick={() => setTrustType("joint")}
                className={`text-left border rounded-xl p-4 sm:p-5 transition-all ${
                  trustType === "joint" ? "border-bronze bg-bronze/5 ring-2 ring-bronze/30" : "border-[#E2E0DA] hover:border-bronze"
                }`}
                data-testid="new-trust-joint">
                <div className="h-10 w-10 rounded-full bg-sand-200 flex items-center justify-center mb-3">
                  <Users className="h-5 w-5 text-navy" />
                </div>
                <h3 className="font-serif text-xl text-navy">Joint Trust</h3>
                <p className="text-sm text-[#64748B] mt-1">Two grantors (spouses / partners).</p>
              </button>
            </div>
          </div>
        )}

        {/* ========== Step 3: Name your trust ========== */}
        {hasExistingTrust !== null && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">
              {hasExistingTrust ? "2." : "3."} Name your trust
            </p>
            <Field id="trust-name" label="Trust name" required
              hint={
                hasExistingTrust
                  ? "Use the exact name on your existing trust document so we can match the records."
                  : 'Examples: "The John A. Smith Living Trust", "The Smith Family Revocable Trust".'
              }>
              <Txt id="trust-name" value={trustName} onChange={setTrustName} placeholder="The Smith Family Revocable Trust" testId="trust-name-input" />
            </Field>
          </div>
        )}

        {/* ========== Submit ========== */}
        <div className="mt-8 flex items-center justify-end">
          <button
            onClick={create}
            disabled={submitting || hasExistingTrust === null}
            className="btn-primary w-full sm:w-auto"
            data-testid="start-new-submit">
            {submitting ? "Starting…" : (hasExistingTrust ? "Continue to upload" : "Start intake")}
            <ArrowRight className="h-4 w-4 ml-1" />
          </button>
        </div>
      </div>

      <div className="mt-6 max-w-2xl flex items-start gap-2 text-xs text-[#64748B]">
        <ScrollText className="h-4 w-4 shrink-0 mt-0.5" />
        <p>
          Both paths collect your contact information and route to your assigned agent. You can pause and return any time —
          progress is saved section by section.
        </p>
      </div>
    </Layout>
  );
}
