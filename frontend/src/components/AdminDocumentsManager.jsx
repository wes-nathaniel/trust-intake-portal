import React, { useState, useRef } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FolderPlus } from "lucide-react";
import AdminDocumentCard from "@/components/AdminDocumentCard";

/**
 * Admin-only manager for the "AI Document Explainer" feature.
 * Lists all admin-uploaded documents for a case, lets admin upload new ones
 * (with a custom label), regenerate the AI explanation, and remove docs.
 * Client-side download link uses the axios base URL so cookies flow correctly.
 */
export default function AdminDocumentsManager({ caseId, docs, onChanged, className = "" }) {
  const [label, setLabel] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [regenerating, setRegenerating] = useState({});
  const [replacing, setReplacing] = useState({});
  const fileRef = useRef(null);

  const apiBase = api.defaults.baseURL || "";

  const upload = async () => {
    if (!file) { toast.error("Choose a file first."); return; }
    if (!label.trim()) { toast.error("Type a label for this document."); return; }
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("label", label.trim());
      fd.append("file", file);
      await api.post(`/admin/trust-cases/${caseId}/admin-documents`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Uploaded "${label.trim()}" — AI explanation generated. Client notified by email.`);
      setLabel("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setUploading(false);
    }
  };

  const regen = async (docId) => {
    setRegenerating((m) => ({ ...m, [docId]: true }));
    try {
      await api.post(`/admin/trust-cases/${caseId}/admin-documents/${docId}/regenerate`);
      toast.success("AI explanation regenerated.");
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRegenerating((m) => ({ ...m, [docId]: false }));
    }
  };

  const remove = async (docId, docLabel) => {
    if (!window.confirm(`Remove "${docLabel}"? The client will no longer be able to see it or its explanation.`)) return;
    try {
      await api.delete(`/admin/trust-cases/${caseId}/admin-documents/${docId}`);
      toast.success("Document removed.");
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  const replace = async (docId, file) => {
    if (!file) return;
    setReplacing((m) => ({ ...m, [docId]: true }));
    try {
      const fd = new FormData();
      fd.append("file", file);
      await api.put(`/admin/trust-cases/${caseId}/admin-documents/${docId}`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document replaced — AI explanation regenerated. Client notified.");
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setReplacing((m) => ({ ...m, [docId]: false }));
    }
  };

  return (
    <section className={`bg-white border border-[#E2E0DA] rounded-xl p-6 ${className}`} data-testid="admin-documents-manager">
      <div className="flex items-start justify-between gap-3 mb-4 flex-wrap">
        <div>
          <h3 className="font-serif text-2xl text-navy">Client Documents (AI Explainer)</h3>
          <p className="text-xs text-[#64748B] mt-1 max-w-2xl">
            Upload any legal or supporting document (Operating Agreement, EIN letter, Membership Ledger, Schedule A, funding instructions, etc.).
            The AI will generate a short plain-English explanation shown to the client under the file. Separate from the Trust Draft.
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-dashed border-bronze/40 bg-sand-200/30 p-4 mb-5" data-testid="admin-doc-upload-form">
        <p className="text-[10px] uppercase tracking-wide font-bold text-bronze mb-2 inline-flex items-center gap-1">
          <FolderPlus className="h-3 w-3" /> Upload a new document
        </p>
        <div className="grid md:grid-cols-[1fr_auto_auto] gap-2 items-center">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder='Label (e.g., "Operating Agreement", "EIN Confirmation Letter")'
            className="w-full text-sm bg-white border border-input rounded-md px-3 py-2"
            maxLength={160}
            data-testid="admin-doc-label-input"
          />
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="text-xs"
            data-testid="admin-doc-file-input"
          />
          <button
            onClick={upload}
            disabled={uploading || !file || !label.trim()}
            className="btn-primary text-sm inline-flex items-center whitespace-nowrap"
            data-testid="admin-doc-upload-btn">
            <Upload className="h-4 w-4 mr-1" /> {uploading ? "Uploading & explaining…" : "Upload & explain"}
          </button>
        </div>
        <p className="text-[11px] text-[#94A3B8] mt-2">
          Accepted: PDF, DOCX, DOC, TXT, JPG, PNG · Max 25 MB. The AI runs immediately after upload; take ~5–15s.
        </p>
      </div>

      {(!docs || docs.length === 0) ? (
        <p className="text-sm text-[#64748B] italic">No client documents uploaded yet.</p>
      ) : (
        <div className="space-y-4" data-testid="admin-doc-list">
          {docs.map((d) => (
            <AdminDocumentCard
              key={d.id}
              doc={d}
              caseId={caseId}
              apiBase={apiBase}
              canDelete
              onDelete={() => remove(d.id, d.label)}
              onRegenerate={() => regen(d.id)}
              regenerating={!!regenerating[d.id]}
              onReplace={(file) => replace(d.id, file)}
              replacing={!!replacing[d.id]}
            />
          ))}
        </div>
      )}
    </section>
  );
}
