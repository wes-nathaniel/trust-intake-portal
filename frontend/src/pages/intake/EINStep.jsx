import React, { useState } from "react";
import { Field, Txt, SectionHeader } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { Download, FileCheck, ShieldCheck } from "lucide-react";
import NotesQuestionsBox from "@/components/NotesQuestionsBox";

export default function EINStep({ caseId, trustCase, reload }) {
  const existing = trustCase.ein;
  const [trustName, setTrustName] = useState(trustCase.trust_name || "");
  const [authorized, setAuthorized] = useState(existing?.authorized || false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!authorized) { toast.error("Please authorize our firm to file your EIN."); return; }
    const cleanName = (trustName || "").trim();
    if (cleanName.length < 3) { toast.error("Please enter the trust name (e.g., 'The Smith Family Revocable Trust')."); return; }
    setSaving(true);
    try {
      if (cleanName !== (trustCase.trust_name || "")) {
        await api.put(`/trust-cases/${caseId}/trust-name`, { trust_name: cleanName });
      }
      await api.put(`/trust-cases/${caseId}/ein`, { authorized: true });
      toast.success("Authorization saved. Our firm will obtain the EIN for your trust.");
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const download = async (doc) => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/documents/${doc.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = doc.filename || "ein-letter.pdf";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <SectionHeader num={6} total={8} title="EIN Workflow"
        subtitle="Our company will obtain the EIN (Employer Identification Number) for your trust on your behalf." />

      <div className="space-y-5" data-testid="ein-form">
        <div className="p-4 bg-sand-200/50 border border-[#E2E0DA] rounded-md text-sm text-navy leading-relaxed">
          <p className="font-semibold mb-1 flex items-center gap-2"><ShieldCheck className="h-4 w-4 text-bronze" /> Admin-filed EIN</p>
          <p className="text-[#334155]">
            Our company will obtain the EIN for your trust. You do <b>not</b> need to file anything with the IRS yourself.
            Once the EIN letter (IRS CP-575) arrives, our team will upload it here and you can download it anytime.
          </p>
        </div>

        <Field id="ein-trust-name" label="Trust name (as it will appear on the EIN application)" required
          hint="This is the formal name used on IRS forms, trust documents, and your final PDF.">
          <Txt id="ein-trust-name" value={trustName} onChange={setTrustName}
            placeholder="The Smith Family Revocable Trust" testId="ein-trust-name-input" />
        </Field>

        <label className="flex items-start gap-3 p-4 border border-[#E2E0DA] rounded-md cursor-pointer bg-sand-200/30" data-testid="ein-auth-label">
          <Checkbox checked={authorized} onCheckedChange={(v) => setAuthorized(!!v)} className="mt-0.5" data-testid="ein-auth-checkbox" />
          <div className="text-sm text-navy">
            <p className="font-semibold">I authorize our firm to obtain the EIN for my trust.</p>
            <p className="text-[#64748B]">
              I authorize Iron Gate Consulting to file Form SS-4 with the IRS on behalf of my trust using the trust name
              above. I understand the EIN letter will be uploaded to my case once received.
            </p>
          </div>
        </label>

        {existing?.authorized && (
          <div className="p-4 bg-green-50 border border-green-200 rounded-md text-sm text-green-900" data-testid="ein-saved-info">
            <FileCheck className="h-4 w-4 inline mr-1" /> EIN authorization on file · Firm will file with IRS
            {trustCase.ein_requested && <div className="mt-1">Admin status: <strong>EIN Requested with IRS</strong></div>}
          </div>
        )}

        {trustCase.ein_letter && (
          <div className="flex items-center justify-between p-4 bg-bronze/10 border border-bronze/40 rounded-md" data-testid="ein-letter-box">
            <div>
              <p className="text-xs uppercase tracking-wide text-bronze font-semibold">EIN Letter Available</p>
              <p className="text-sm text-navy">{trustCase.ein_letter.filename}</p>
              <p className="text-xs text-[#64748B]">Uploaded by your trust team</p>
            </div>
            <button onClick={() => download(trustCase.ein_letter)} className="btn-accent" data-testid="ein-letter-download">
              <Download className="h-4 w-4 inline mr-1" /> Download
            </button>
          </div>
        )}

        <button onClick={save} disabled={saving} className="btn-primary" data-testid="ein-save-btn">
          {saving ? "Saving…" : "Authorize & Save"}
        </button>
      </div>

      <NotesQuestionsBox caseId={caseId} section="ein" />
    </div>
  );
}
