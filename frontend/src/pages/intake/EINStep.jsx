import React, { useState } from "react";
import { Field, Txt, SectionHeader, maskSSN, displaySSN } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { Eye, EyeOff, Download, FileCheck } from "lucide-react";

export default function EINStep({ caseId, trustCase, reload }) {
  const existing = trustCase.ein;
  const [ssn, setSsn] = useState(existing?.ssn || "");
  const [authorized, setAuthorized] = useState(existing?.authorized || false);
  const [show, setShow] = useState(false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!ssn) { toast.error("SSN is required."); return; }
    if (!authorized) { toast.error("Please authorize EIN filing."); return; }
    setSaving(true);
    try {
      await api.put(`/trust-cases/${caseId}/ein`, { ssn, authorized });
      toast.success("EIN information saved");
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
        subtitle="We'll file for your trust's Employer Identification Number (EIN) with the IRS." />

      <div className="space-y-5" data-testid="ein-form">
        <Field id="ein-ssn" label="SSN (grantor)" required hint="Masked for your security">
          <div className="relative">
            <Txt id="ein-ssn" type={show ? "text" : "password"} value={ssn} onChange={(v) => setSsn(maskSSN(v))} placeholder="XXX-XX-XXXX" testId="ein-ssn-input" />
            <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 text-[#64748B]" data-testid="ein-ssn-toggle">
              {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </Field>

        <label className="flex items-start gap-3 p-4 border border-[#E2E0DA] rounded-md cursor-pointer bg-sand-200/30" data-testid="ein-auth-label">
          <Checkbox checked={authorized} onCheckedChange={(v) => setAuthorized(!!v)} className="mt-0.5" data-testid="ein-auth-checkbox" />
          <div className="text-sm text-navy">
            <p className="font-semibold">I authorize EIN filing for my trust.</p>
            <p className="text-[#64748B]">By checking this box, I authorize the firm to apply for an EIN on behalf of my trust and to use the SSN provided for identification purposes.</p>
          </div>
        </label>

        {existing?.ssn && (
          <div className="p-4 bg-green-50 border border-green-200 rounded-md text-sm text-green-900" data-testid="ein-saved-info">
            <FileCheck className="h-4 w-4 inline mr-1" /> EIN info on file · SSN: {displaySSN(existing.ssn)} · Authorized: {existing.authorized ? "Yes" : "No"}
            {trustCase.ein_requested && <div className="mt-1">Admin status: <strong>EIN Requested</strong></div>}
          </div>
        )}

        {trustCase.ein_letter && (
          <div className="flex items-center justify-between p-4 bg-bronze/10 border border-bronze/40 rounded-md" data-testid="ein-letter-box">
            <div>
              <p className="text-xs uppercase tracking-wide text-bronze font-semibold">EIN Letter Available</p>
              <p className="text-sm text-navy">{trustCase.ein_letter.filename}</p>
            </div>
            <button onClick={() => download(trustCase.ein_letter)} className="btn-accent" data-testid="ein-letter-download">
              <Download className="h-4 w-4 inline mr-1" /> Download
            </button>
          </div>
        )}

        <button onClick={save} disabled={saving} className="btn-primary" data-testid="ein-save-btn">
          {saving ? "Saving…" : "Save EIN Info"}
        </button>
      </div>
    </div>
  );
}
