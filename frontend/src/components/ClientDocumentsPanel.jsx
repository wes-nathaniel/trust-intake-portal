import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { FileText, Download, Trash2, Upload as UploadIcon } from "lucide-react";

const DOC_TYPE_LABELS = {
  government_id: "Government-issued ID",
  proof_of_address: "Proof of Address",
  existing_trust: "Existing Trust Document",
  bank_statement: "Bank Statement",
  deed: "Deed",
  title: "Title",
  insurance_policy: "Insurance Policy",
  business_document: "Business Document",
  supporting_file: "Supporting File",
  ein_letter: "EIN Confirmation Letter (from your team)",
  trust_draft: "Trust Draft",
};

/** Client-facing panel that lists everything the client has uploaded to a case
 *  (IDs, bills, existing trust, asset supporting docs) with per-item Download
 *  and Remove buttons. Uses the existing DELETE /trust-cases/{id}/documents/{doc_id}
 *  endpoint (soft-delete via is_deleted). Files uploaded by admin (ein_letter,
 *  trust_draft) are shown read-only — client can view but not delete them.
 */
export default function ClientDocumentsPanel({ caseId, docs, onChanged }) {
  const [busy, setBusy] = useState({});

  const clientDocs = (docs || []).filter((d) => !d.is_deleted);

  const download = async (d) => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = d.filename || "file"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete "${d.filename}"? You can re-upload the correct file afterward.`)) return;
    setBusy((b) => ({ ...b, [d.id]: true }));
    try {
      await api.delete(`/trust-cases/${caseId}/documents/${d.id}`);
      toast.success("File removed.");
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setBusy((b) => ({ ...b, [d.id]: false }));
    }
  };

  if (clientDocs.length === 0) return null;

  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6" data-testid={`client-uploads-panel-${caseId}`}>
      <p className="text-[10px] uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Your uploads</p>
      <h3 className="font-serif text-xl text-navy mb-1">Files you&rsquo;ve sent us</h3>
      <p className="text-xs text-[#64748B] mb-4">
        Uploaded the wrong file? Click the trash icon to remove it, then re-upload the correct one from the intake wizard.
      </p>
      <ul className="space-y-2">
        {clientDocs.map((d) => {
          const isAdminUpload = d.uploaded_by_role === "admin" || d.doc_type === "ein_letter" || d.doc_type === "trust_draft";
          const kb = d.size ? (d.size / 1024).toFixed(0) : null;
          return (
            <li
              key={d.id}
              className="flex items-center justify-between bg-sand-200/30 rounded-md px-3 py-2 gap-3"
              data-testid={`client-upload-item-${d.id}`}>
              <div className="flex items-center gap-2 min-w-0">
                <FileText className="h-4 w-4 shrink-0 text-bronze" />
                <div className="min-w-0">
                  <p className="text-sm text-navy truncate">
                    {d.filename}
                    {kb && <span className="text-[11px] text-[#94A3B8] ml-2">({kb} KB)</span>}
                  </p>
                  <p className="text-[11px] text-[#64748B]">
                    {DOC_TYPE_LABELS[d.doc_type] || d.doc_type}
                    {d.uploaded_at && <span> · {new Date(d.uploaded_at).toLocaleDateString()}</span>}
                    {isAdminUpload && <span className="ml-2 text-bronze font-medium">· From your team</span>}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button
                  onClick={() => download(d)}
                  className="text-navy hover:text-bronze"
                  title="Download"
                  data-testid={`client-upload-download-${d.id}`}>
                  <Download className="h-4 w-4" />
                </button>
                {!isAdminUpload && (
                  <button
                    onClick={() => remove(d)}
                    disabled={!!busy[d.id]}
                    className="text-red-600 hover:text-red-700 disabled:opacity-50"
                    title="Delete this upload"
                    data-testid={`client-upload-remove-${d.id}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
      <p className="text-[11px] text-[#94A3B8] mt-3 inline-flex items-center gap-1">
        <UploadIcon className="h-3 w-3" /> To add a new file, use the <b>Continue Intake</b> button above.
      </p>
    </div>
  );
}
