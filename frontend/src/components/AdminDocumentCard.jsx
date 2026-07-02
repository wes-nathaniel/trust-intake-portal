import React from "react";
import { FileText, Download, Sparkles, StampIcon, Info } from "lucide-react";

/** Compact read-only card that shows a single admin-uploaded document
 *  and the AI-generated explanation directly under it. Used by BOTH
 *  the admin case detail page and the client portal. */
export default function AdminDocumentCard({ doc, caseId, apiBase, canDelete, onDelete, onRegenerate, regenerating, className = "" }) {
  const ai = doc.ai_explanation || {};
  const hasAi = !!(ai.what_is || ai.what_it_does || ai.why_it_matters || ai.notarization || ai.client_action);
  const download = () => {
    const url = `${apiBase}/trust-cases/${caseId}/admin-documents/${doc.id}/download`;
    window.open(url, "_blank", "noopener,noreferrer");
  };
  const kb = doc.size ? (doc.size / 1024).toFixed(0) : null;

  return (
    <div
      className={`border border-[#E2E0DA] rounded-xl bg-white overflow-hidden ${className}`}
      data-testid={`admin-doc-card-${doc.id}`}>
      <div className="flex items-start gap-3 p-4 border-b border-[#F1EFEA] bg-sand-200/30">
        <div className="shrink-0 mt-0.5 h-9 w-9 rounded-md bg-bronze/10 border border-bronze/30 flex items-center justify-center">
          <FileText className="h-4 w-4 text-bronze" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-serif text-lg text-navy break-words" data-testid={`admin-doc-label-${doc.id}`}>{doc.label}</p>
          <p className="text-xs text-[#64748B] truncate">{doc.filename}{kb ? ` · ${kb} KB` : ""}</p>
          <p className="text-[11px] text-[#94A3B8] mt-0.5">Uploaded {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString() : "—"}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={download}
            className="btn-secondary text-xs inline-flex items-center"
            data-testid={`admin-doc-download-${doc.id}`}>
            <Download className="h-3.5 w-3.5 mr-1" /> Download
          </button>
          {onRegenerate && (
            <button
              onClick={onRegenerate}
              disabled={regenerating}
              className="btn-secondary text-xs inline-flex items-center"
              title="Re-run the AI explainer for this document"
              data-testid={`admin-doc-regenerate-${doc.id}`}>
              <Sparkles className="h-3.5 w-3.5 mr-1" /> {regenerating ? "Regenerating…" : "Re-explain"}
            </button>
          )}
          {canDelete && (
            <button
              onClick={onDelete}
              className="text-red-600 hover:text-red-700 text-xs font-medium"
              data-testid={`admin-doc-delete-${doc.id}`}>
              Remove
            </button>
          )}
        </div>
      </div>

      <div className="p-4">
        <p className="text-[10px] uppercase tracking-wider font-bold text-bronze mb-2 inline-flex items-center gap-1">
          <Sparkles className="h-3 w-3" /> Plain-English explanation
        </p>
        {!hasAi ? (
          <p className="text-sm text-[#94A3B8] italic">
            {ai.error ? `Explanation unavailable (${ai.error}). ` : "The AI explanation is still being generated…"}
            {onRegenerate && ai.error ? "Click Re-explain to try again." : ""}
          </p>
        ) : (
          <div className="space-y-3 text-sm text-navy leading-relaxed">
            {ai.what_is && (
              <Row icon={<Info className="h-3.5 w-3.5 text-bronze" />} label="What it is">{ai.what_is}</Row>
            )}
            {ai.what_it_does && (
              <Row icon={<Info className="h-3.5 w-3.5 text-bronze" />} label="What it does">{ai.what_it_does}</Row>
            )}
            {ai.why_it_matters && (
              <Row icon={<Info className="h-3.5 w-3.5 text-bronze" />} label="Why it matters">{ai.why_it_matters}</Row>
            )}
            {ai.notarization && (
              <Row icon={<StampIcon className="h-3.5 w-3.5 text-bronze" />} label="Notarization">{ai.notarization}</Row>
            )}
            {ai.client_action && (
              <Row icon={<Info className="h-3.5 w-3.5 text-bronze" />} label="What you should do">{ai.client_action}</Row>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

const Row = ({ icon, label, children }) => (
  <div className="grid grid-cols-[130px_1fr] gap-2 items-start">
    <span className="text-[11px] uppercase tracking-wide text-[#64748B] font-semibold inline-flex items-center gap-1 pt-0.5">
      {icon}{label}
    </span>
    <p className="text-[13px] text-navy">{children}</p>
  </div>
);
