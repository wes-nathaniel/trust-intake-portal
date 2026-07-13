import React, { useState, useRef, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FolderPlus, HardDrive, AlertCircle, FileDown } from "lucide-react";
import AdminDocumentCard from "@/components/AdminDocumentCard";

/**
 * Admin-only manager for the "AI Document Explainer" feature.
 * Lists all admin-uploaded documents for a case, lets admin upload new ones
 * (with a custom label), regenerate the AI explanation, and remove docs.
 * Client-side download link uses the axios base URL so cookies flow correctly.
 */
export default function AdminDocumentsManager({ caseId, docs, hasTrustDraft = false, onChanged, className = "" }) {
  const [label, setLabel] = useState("");
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [importingDraft, setImportingDraft] = useState(false);
  const [regenerating, setRegenerating] = useState({});
  const [replacing, setReplacing] = useState({});
  const fileRef = useRef(null);

  const apiBase = api.defaults.baseURL || "";

  // Live storage-usage stats (client-side derived — no extra API call needed
  // since the docs prop already carries size + versions[].size).
  const stats = useMemo(() => {
    const list = docs || [];
    let currentBytes = 0, versionBytes = 0, versionCount = 0;
    for (const d of list) {
      currentBytes += Number(d.size || 0);
      for (const v of (d.versions || [])) {
        versionBytes += Number(v.size || 0);
        versionCount += 1;
      }
    }
    const totalBytes = currentBytes + versionBytes;
    return {
      docCount: list.length,
      currentBytes, versionBytes, totalBytes, versionCount,
    };
  }, [docs]);

  const formatBytes = (n) => {
    if (!n) return "0 KB";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  // Soft threshold: warn when archived versions exceed 100 MB — the trim-history
  // control is the intended remediation.
  const ARCHIVE_WARN_BYTES = 100 * 1024 * 1024;
  const archiveOver = stats.versionBytes >= ARCHIVE_WARN_BYTES;

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

  const importFromTrustDraft = async () => {
    setImportingDraft(true);
    try {
      const { data } = await api.post(
        `/admin/trust-cases/${caseId}/admin-documents/from-trust-draft`
      );
      if (data.already_imported) {
        toast.info("Trust draft is already imported into the explainer.");
      } else {
        toast.success("Trust draft imported — AI explanation generated.");
      }
      onChanged && onChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setImportingDraft(false);
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

      {stats.docCount > 0 && (
        <div
          className={`mb-4 flex items-center justify-between gap-3 flex-wrap rounded-lg border px-4 py-2.5 ${archiveOver ? "border-amber-300 bg-amber-50" : "border-[#E2E0DA] bg-sand-200/30"}`}
          data-testid="admin-docs-storage-indicator">
          <div className="flex items-center gap-2 min-w-0 text-xs">
            {archiveOver ? (
              <AlertCircle className="h-3.5 w-3.5 text-amber-700 shrink-0" />
            ) : (
              <HardDrive className="h-3.5 w-3.5 text-bronze shrink-0" />
            )}
            <span className="text-navy" data-testid="admin-docs-storage-summary">
              <b>{stats.docCount}</b> document{stats.docCount === 1 ? "" : "s"}
              <span className="text-[#94A3B8]"> · </span>
              <b>{formatBytes(stats.totalBytes)}</b> total
              <span className="text-[#94A3B8]"> · </span>
              <b>{stats.versionCount}</b> archived version{stats.versionCount === 1 ? "" : "s"}
              {stats.versionCount > 0 && (
                <span className="text-[#94A3B8]"> ({formatBytes(stats.versionBytes)})</span>
              )}
            </span>
          </div>
          {archiveOver && (
            <span className="text-[11px] text-amber-800 font-medium">
              Archive over {formatBytes(ARCHIVE_WARN_BYTES)} — consider using the <b>Trim</b> button on individual documents.
            </span>
          )}
        </div>
      )}

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

        {hasTrustDraft && (
          <div className="mt-3 pt-3 border-t border-bronze/30 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-[#64748B]">
              <b>Shortcut:</b> The uploaded Trust Draft PDF can be imported here so the AI can explain it — no re-upload needed.
            </p>
            <button
              onClick={importFromTrustDraft}
              disabled={importingDraft}
              className="btn-accent text-sm inline-flex items-center whitespace-nowrap"
              data-testid="admin-doc-import-trust-draft-btn">
              <FileDown className="h-4 w-4 mr-1" /> {importingDraft ? "Importing…" : "Import Trust Draft PDF"}
            </button>
          </div>
        )}
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
              onRestored={() => onChanged && onChanged()}
            />
          ))}
        </div>
      )}
    </section>
  );
}
