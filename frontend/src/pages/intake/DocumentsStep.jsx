import React, { useState, useRef } from "react";
import { SectionHeader } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileText, Trash2, Download, CheckCircle2, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

const REQUIRED_DOC_TYPES = [
  { v: "government_id", l: "Government-issued ID", hint: "Driver's license, passport, or state ID." },
  { v: "proof_of_address", l: "Proof of Address", hint: "Utility bill, bank statement, or lease less than 60 days old." },
];

const OPTIONAL_DOC_TYPES = [
  { v: "existing_trust", l: "Existing Trust Document", hint: "If you have an existing trust you'd like to update." },
  { v: "bank_statement", l: "Bank Statement", hint: "Helpful if you want the trust to include bank accounts." },
  { v: "deed", l: "Deed", hint: "For real estate you'd like to place in the trust." },
  { v: "title", l: "Title", hint: "Vehicles or other titled assets." },
  { v: "insurance_policy", l: "Insurance Policy", hint: "Life insurance policies you'd like to fund to the trust." },
  { v: "business_document", l: "Business Document", hint: "Operating agreements, stock certificates, etc." },
  { v: "supporting_file", l: "Other Supporting File", hint: "Anything else you'd like to share with your trust team." },
];

function DocGroup({ caseId, docType, label, hint, required, requested, docs, reload, highlight }) {
  const [uploading, setUploading] = useState(false);
  const inputRef = useRef();

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    try {
      await api.post(`/trust-cases/${caseId}/documents`, form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${label} uploaded`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setUploading(false); if (inputRef.current) inputRef.current.value = ""; }
  };

  const download = async (d) => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = d.filename || "file";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this document?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/documents/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const hasDoc = docs.length > 0;
  const outlineClass =
    highlight ? "border-amber-400 bg-amber-50/30"
    : required && !hasDoc ? "border-red-200 bg-red-50/20"
    : hasDoc ? "border-green-200 bg-green-50/30"
    : "border-[#E2E0DA]";

  return (
    <div className={`rounded-lg p-5 border ${outlineClass}`} data-testid={`doc-group-${docType}`}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-navy flex items-center gap-2">
            {label}
            {required && <span className="text-[10px] uppercase tracking-wider bg-red-100 text-red-700 rounded-full px-2 py-0.5 font-semibold">Required</span>}
            {requested && <span className="text-[10px] uppercase tracking-wider bg-amber-100 text-amber-800 rounded-full px-2 py-0.5 font-semibold">Requested by your team</span>}
            {!required && !requested && <span className="text-[10px] uppercase tracking-wider text-[#94A3B8] font-semibold">Optional</span>}
            {hasDoc && <CheckCircle2 className="h-4 w-4 text-green-600" />}
          </p>
          {hint && <p className="text-xs text-[#64748B] mt-0.5">{hint}</p>}
        </div>
        <label className="btn-accent cursor-pointer text-sm inline-flex items-center shrink-0">
          <Upload className="h-4 w-4 inline mr-1" /> {uploading ? "Uploading…" : hasDoc ? "Replace" : "Upload"}
          <input ref={inputRef} type="file" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid={`doc-upload-${docType}`} />
        </label>
      </div>
      {docs.length > 0 && (
        <ul className="space-y-2">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between text-sm bg-white/60 rounded-md px-3 py-2 border border-[#E2E0DA]" data-testid={`doc-item-${d.id}`}>
              <span className="flex items-center gap-2 text-navy truncate">
                <FileText className="h-4 w-4 shrink-0" /> <span className="truncate">{d.filename}</span>
              </span>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => download(d)} className="text-navy hover:text-bronze" data-testid={`doc-download-${d.id}`}><Download className="h-4 w-4" /></button>
                <button onClick={() => remove(d.id)} className="text-red-600 hover:text-red-800" data-testid={`doc-remove-${d.id}`}><Trash2 className="h-4 w-4" /></button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function DocumentsStep({ caseId, trustCase, reload }) {
  const docs = (trustCase.documents || []).filter((d) => !d.is_deleted);
  const byType = (t) => docs.filter((d) => d.doc_type === t);
  const pending = trustCase.pending_items || [];
  const requestedTypes = new Set(pending.filter((p) => p.kind === "requested_doc").map((p) => p.doc_type));
  const [optionalOpen, setOptionalOpen] = useState(false);

  const hasId = byType("government_id").length > 0;
  const hasPoa = byType("proof_of_address").length > 0;

  // EIN letter is admin-uploaded; show it only if requested
  const adminRequested = pending.filter((p) => p.kind === "requested_doc");
  // Ensure ein_letter (admin-facing) also shows if requested
  const hasEinRequest = [...requestedTypes].includes("ein_letter");

  return (
    <div>
      <SectionHeader num={7} total={8} title="Document Uploads"
        subtitle="We only need two required documents. Everything else is optional — upload anything you think will help us draft your trust accurately." />

      {adminRequested.length > 0 && (
        <div className="mb-5 bg-amber-50 border border-amber-300 rounded-lg p-4" data-testid="doc-requested-banner">
          <p className="font-semibold text-amber-900 flex items-center gap-2">
            <AlertCircle className="h-4 w-4" /> Your trust team has requested:
          </p>
          <ul className="mt-1 text-sm text-amber-900/90 pl-6 list-disc">
            {adminRequested.map((r, i) => (
              <li key={i}><b>{r.label}</b>{r.note && <span className="text-amber-800/80"> — {r.note}</span>}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Required section */}
      <div className="mb-8">
        <h3 className="font-serif text-xl text-navy mb-3">Required</h3>
        <div className="space-y-3">
          {REQUIRED_DOC_TYPES.map((t) => (
            <DocGroup key={t.v} caseId={caseId} docType={t.v} label={t.l} hint={t.hint} required
              requested={requestedTypes.has(t.v)} highlight={requestedTypes.has(t.v)}
              docs={byType(t.v)} reload={reload} />
          ))}
          {hasEinRequest && (
            <DocGroup caseId={caseId} docType="ein_letter" label="EIN Letter"
              hint="Your trust team requested this document." requested highlight
              docs={byType("ein_letter")} reload={reload} />
          )}
        </div>
      </div>

      {/* Optional section (collapsed by default unless highlighted) */}
      <div className="mb-4">
        <button onClick={() => setOptionalOpen(!optionalOpen)}
          className="w-full text-left flex items-center justify-between py-3 border-t border-[#E2E0DA]"
          data-testid="doc-optional-toggle">
          <span className="font-serif text-xl text-navy">Optional uploads <span className="text-sm text-[#64748B] font-sans">({OPTIONAL_DOC_TYPES.length} categories)</span></span>
          {optionalOpen ? <ChevronUp className="h-5 w-5 text-[#64748B]" /> : <ChevronDown className="h-5 w-5 text-[#64748B]" />}
        </button>
        {optionalOpen && (
          <div className="space-y-3 mt-2">
            {OPTIONAL_DOC_TYPES.map((t) => (
              <DocGroup key={t.v} caseId={caseId} docType={t.v} label={t.l} hint={t.hint}
                requested={requestedTypes.has(t.v)} highlight={requestedTypes.has(t.v)}
                docs={byType(t.v)} reload={reload} />
            ))}
          </div>
        )}
      </div>

      {(!hasId || !hasPoa) && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="doc-warning">
          <strong>Required:</strong> Please upload both a Government-issued ID and Proof of Address to continue.
        </div>
      )}
    </div>
  );
}
