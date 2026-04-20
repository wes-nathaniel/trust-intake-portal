import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import { Users, User, ArrowRight } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Field, Txt } from "@/pages/intake/_shared";

export default function StartNew() {
  const navigate = useNavigate();
  const [trustType, setTrustType] = useState("single");
  const [trustName, setTrustName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const create = async () => {
    const name = (trustName || "").trim();
    if (name.length < 3) {
      toast.error("Please enter the trust name (e.g., “The John A. Smith Living Trust”).");
      return;
    }
    setSubmitting(true);
    try {
      const { data } = await api.post("/trust-cases", { trust_type: trustType, trust_name: name });
      navigate(`/intake/${data.id}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSubmitting(false); }
  };

  return (
    <Layout>
      <h1 className="font-serif text-4xl text-navy mb-2">Start a new trust intake</h1>
      <p className="text-[#64748B] mb-8 max-w-2xl">
        Choose the kind of trust and name it. The trust name will be used on the EIN filing and on every trust document.
      </p>

      <div className="bg-white border border-[#E2E0DA] rounded-xl p-6 sm:p-8 max-w-2xl">
        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">1. Choose trust type</p>
        <div className="grid md:grid-cols-2 gap-4 mb-8">
          <button
            type="button"
            onClick={() => setTrustType("single")}
            className={`text-left border rounded-xl p-5 transition-all ${
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
            className={`text-left border rounded-xl p-5 transition-all ${
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

        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">2. Name your trust</p>
        <Field id="trust-name" label="Trust name" required
          hint='Examples: "The John A. Smith Living Trust", "The Smith Family Revocable Trust", "The Carter Legacy Trust".'>
          <Txt id="trust-name" value={trustName} onChange={setTrustName} placeholder="The Smith Family Revocable Trust" testId="trust-name-input" />
        </Field>

        <div className="mt-8 flex items-center justify-end">
          <button onClick={create} disabled={submitting} className="btn-primary" data-testid="start-new-submit">
            {submitting ? "Starting…" : "Start intake"} <ArrowRight className="h-4 w-4 inline ml-1" />
          </button>
        </div>
      </div>
    </Layout>
  );
}
