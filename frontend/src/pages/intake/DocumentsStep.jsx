import React, { useState, useRef } from "react";
import { SectionHeader } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileText, Trash2, Download, CheckCircle2 } from "lucide-react";

const DOC_TYPES = [
  { v: "government_id", l: "Government-issued ID", required: true },
  { v: "proof_of_address", l: "Proof of Address", required: true },
  { v: "existing_trust", l: "Existing Trust Document", required: false },
  { v: "bank_statement", l: "Bank Statement", required: false },
  { v: "deed", l: "Deed", required: false },
  { v: "title", l: "Title", required: false },
  { v: "insurance_policy", l: "Insurance Policy", required: false },
  { v: "business_document", l: "Business Document", required: false },
  { v: "supporting_file", l: "Other Supporting File", required: false },
];

function DocGroup({ caseId, docType, label, required, docs, reload }) {
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

  return (
    <div className="border border-[#E2E0DA] rounded-lg p-5" data-testid={`doc-group-${docType}`}>
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-2">
            {label} {required && <span className="text-red-500">*</span>}
            {required && hasDoc && <CheckCircle2 className="h-4 w-4 text-green-600" />}
          </p>
        </div>
        <label className="btn-accent cursor-pointer text-sm inline-flex items-center">
          <Upload className="h-4 w-4 inline mr-1" /> {uploading ? "Uploading…" : "Upload"}
          <input ref={inputRef} type="file" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid={`doc-upload-${docType}`} />
        </label>
      </div>
      {docs.length === 0 ? (
        <p className="text-sm text-[#64748B]">No files yet.</p>
      ) : (
        <ul className="space-y-2">
          {docs.map((d) => (
            <li key={d.id} className="flex items-center justify-between text-sm bg-sand-200/40 rounded-md px-3 py-2" data-testid={`doc-item-${d.id}`}>
              <span className="flex items-center gap-2 text-navy truncate">
                <FileText className="h-4 w-4 shrink-0" /> <span className="truncate">{d.filename}</span>
              </span>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => download(d)} className="text-navy hover:text-bronze" data-testid={`doc-download-${d.id}`}>
                  <Download className="h-4 w-4" />
                </button>
                <button onClick={() => remove(d.id)} className="text-red-600 hover:text-red-800" data-testid={`doc-remove-${d.id}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
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

  const hasId = byType("government_id").length > 0;
  const hasPoa = byType("proof_of_address").length > 0;

  return (
    <div>
      <SectionHeader num={7} total={8} title="Document Uploads"
        subtitle="Please upload the required documents. Optional uploads help us draft your trust more accurately." />

      <div className="space-y-4">
        {DOC_TYPES.map((t) => (
          <DocGroup key={t.v} caseId={caseId} docType={t.v} label={t.l} required={t.required} docs={byType(t.v)} reload={reload} />
        ))}
      </div>

      {(!hasId || !hasPoa) && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="doc-warning">
          <strong>Required:</strong> Please upload both a Government-issued ID and Proof of Address to continue.
        </div>
      )}
    </div>
  );
}
