import React, { useEffect, useRef, useState } from "react";
import { FileText, Download, Sparkles, StampIcon, Info, Upload, History, RotateCcw, ChevronDown, Scissors } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

/** Compact read-only card that shows a single admin-uploaded document
 *  and the AI-generated explanation directly under it. Used by BOTH
 *  the admin case detail page and the client portal. */
export default function AdminDocumentCard({ doc, caseId, apiBase, canDelete, onDelete, onRegenerate, regenerating, onReplace, replacing, onRestored, className = "" }) {
  const replaceInputRef = useRef(null);
  const [showVersions, setShowVersions] = useState(false);
  const [restoring, setRestoring] = useState(null);
  const [trimOpen, setTrimOpen] = useState(false);
  const [trimming, setTrimming] = useState(false);
  const ai = doc.ai_explanation || {};
  const hasAi = !!(ai.what_is || ai.what_it_does || ai.why_it_matters || ai.notarization || ai.client_action);
  const download = () => {
    const url = `${apiBase}/trust-cases/${caseId}/admin-documents/${doc.id}/download`;
    window.open(url, "_blank", "noopener,noreferrer");
  };
  const kb = doc.size ? (doc.size / 1024).toFixed(0) : null;

  // Version history is admin-only (surfaced via onRestored callback).
  const versions = Array.isArray(doc.versions) ? [...doc.versions] : [];
  versions.sort((a, b) => (b.archived_at || "").localeCompare(a.archived_at || ""));
  const shown = versions.slice(0, 5);
  const hasHistory = versions.length > 0 && !!onRestored;

  const restore = async (versionNum) => {
    if (!window.confirm(`Restore version ${versionNum}? The current file will be archived as a new version so you can undo this.`)) return;
    setRestoring(versionNum);
    try {
      await api.post(`/admin/trust-cases/${caseId}/admin-documents/${doc.id}/versions/${versionNum}/restore`);
      toast.success(`Restored version ${versionNum}.`);
      onRestored && onRestored();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRestoring(null);
    }
  };

  const trim = async (keep) => {
    const trimmedCount = Math.max(0, versions.length - keep);
    if (trimmedCount === 0) {
      toast.info("Nothing to trim.");
      setTrimOpen(false);
      return;
    }
    const label = keep === 0 ? "clear ALL history" : `keep only the newest ${keep} version(s)`;
    if (!window.confirm(`This will ${label} and permanently delete ${trimmedCount} older file(s) from storage. Continue?`)) return;
    setTrimming(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/admin-documents/${doc.id}/trim-history`, { keep });
      toast.success(`Trimmed history — kept ${data.kept}, removed ${data.removed}.`);
      setTrimOpen(false);
      onRestored && onRestored();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setTrimming(false);
    }
  };

  // Close the trim dropdown when clicking outside
  useEffect(() => {
    if (!trimOpen) return;
    const onDown = (e) => {
      const trigger = document.querySelector(`[data-testid="admin-doc-trim-toggle-${doc.id}"]`);
      const menu = document.querySelector(`[data-testid="admin-doc-trim-menu-${doc.id}"]`);
      if (trigger?.contains(e.target) || menu?.contains(e.target)) return;
      setTrimOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [trimOpen, doc.id]);

  return (
    <div
      className={`border border-[#E2E0DA] rounded-xl bg-white overflow-hidden ${className}`}
      data-testid={`admin-doc-card-${doc.id}`}>
      <div className="flex flex-col sm:flex-row items-start gap-3 p-4 border-b border-[#F1EFEA] bg-sand-200/30">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="shrink-0 mt-0.5 h-9 w-9 rounded-md bg-bronze/10 border border-bronze/30 flex items-center justify-center">
            <FileText className="h-4 w-4 text-bronze" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-serif text-lg text-navy break-words" data-testid={`admin-doc-label-${doc.id}`}>
              {doc.label}
              {typeof doc.version === "number" && doc.version > 1 && (
                <span className="ml-2 text-[10px] uppercase tracking-wider bg-bronze/10 text-bronze border border-bronze/30 px-1.5 py-0.5 rounded font-sans font-semibold align-middle">
                  v{doc.version}
                </span>
              )}
            </p>
            <p className="text-xs text-[#64748B] truncate">{doc.filename}{kb ? ` · ${kb} KB` : ""}</p>
            <p className="text-[11px] text-[#94A3B8] mt-0.5">Uploaded {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleString() : "—"}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap sm:shrink-0 w-full sm:w-auto">
          <button
            onClick={download}
            className="btn-secondary text-xs inline-flex items-center"
            data-testid={`admin-doc-download-${doc.id}`}>
            <Download className="h-3.5 w-3.5 mr-1" /> Download
          </button>
          {onReplace && (
            <>
              <input
                ref={replaceInputRef}
                type="file"
                accept=".pdf,.docx,.doc,.txt,.jpg,.jpeg,.png"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) onReplace(f);
                  if (replaceInputRef.current) replaceInputRef.current.value = "";
                }}
                data-testid={`admin-doc-replace-input-${doc.id}`}
              />
              <button
                onClick={() => replaceInputRef.current?.click()}
                disabled={replacing}
                className="btn-secondary text-xs inline-flex items-center"
                title="Upload a new version — replaces this file and regenerates the AI explanation"
                data-testid={`admin-doc-replace-${doc.id}`}>
                <Upload className="h-3.5 w-3.5 mr-1" /> {replacing ? "Replacing…" : "Replace"}
              </button>
            </>
          )}
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

      {hasHistory && (
        <div className="border-t border-[#F1EFEA] bg-sand-200/20" data-testid={`admin-doc-history-${doc.id}`}>
          <div className="flex items-center justify-between px-4 py-2.5 gap-2">
            <button
              type="button"
              onClick={() => setShowVersions((v) => !v)}
              className="flex-1 flex items-center justify-between gap-2 text-xs text-[#64748B] hover:text-navy text-left"
              aria-expanded={showVersions}
              data-testid={`admin-doc-history-toggle-${doc.id}`}>
              <span className="inline-flex items-center gap-1.5">
                <History className="h-3.5 w-3.5" />
                Version history · {versions.length} prior version{versions.length === 1 ? "" : "s"}
              </span>
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showVersions ? "rotate-180" : ""}`} />
            </button>
            {onRestored && versions.length > 0 && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setTrimOpen((v) => !v)}
                  disabled={trimming}
                  className="text-[11px] text-[#94A3B8] hover:text-red-600 inline-flex items-center gap-1 disabled:opacity-50"
                  title="Delete older versions from storage"
                  data-testid={`admin-doc-trim-toggle-${doc.id}`}>
                  <Scissors className="h-3 w-3" /> {trimming ? "Trimming…" : "Trim"}
                </button>
                {trimOpen && (
                  <div
                    className="absolute right-0 top-full mt-1 z-30 bg-white border border-[#E2E0DA] rounded-md shadow-lg py-1 w-52"
                    role="menu"
                    data-testid={`admin-doc-trim-menu-${doc.id}`}>
                    <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-[#94A3B8] border-b border-[#F1EFEA]">
                      Keep newest…
                    </div>
                    {[10, 5, 3, 1].map((n) => (
                      <button
                        key={n}
                        onClick={() => trim(n)}
                        disabled={trimming || versions.length <= n}
                        className="w-full text-left px-3 py-1.5 text-sm text-navy hover:bg-bronze/10 disabled:opacity-40 disabled:cursor-not-allowed"
                        data-testid={`admin-doc-trim-keep-${n}-${doc.id}`}>
                        Keep last {n} <span className="text-[10px] text-[#94A3B8]">({Math.max(0, versions.length - n)} to remove)</span>
                      </button>
                    ))}
                    <div className="border-t border-[#F1EFEA] my-1" />
                    <button
                      onClick={() => trim(0)}
                      disabled={trimming}
                      className="w-full text-left px-3 py-1.5 text-sm text-red-600 hover:bg-red-50 font-medium"
                      data-testid={`admin-doc-trim-clear-${doc.id}`}>
                      Clear all history ({versions.length})
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
          {showVersions && (
            <ul className="px-4 pb-4 space-y-2">
              {shown.map((v) => (
                <li
                  key={v.version}
                  className="flex items-center justify-between gap-3 bg-white border border-[#E2E0DA] rounded-md px-3 py-2"
                  data-testid={`admin-doc-version-${doc.id}-${v.version}`}>
                  <div className="min-w-0">
                    <p className="text-[13px] text-navy">
                      <span className="text-[10px] uppercase tracking-wider bg-[#F1EFEA] text-[#64748B] px-1.5 py-0.5 rounded font-semibold mr-2 align-middle">
                        v{v.version}
                      </span>
                      <span className="truncate">{v.filename || "(no filename)"}</span>
                    </p>
                    <p className="text-[11px] text-[#94A3B8] mt-0.5">
                      Uploaded {v.uploaded_at ? new Date(v.uploaded_at).toLocaleString() : "—"}
                      {v.archived_at && <span> · archived {new Date(v.archived_at).toLocaleString()}</span>}
                    </p>
                  </div>
                  <button
                    onClick={() => restore(v.version)}
                    disabled={restoring === v.version}
                    className="btn-secondary text-xs inline-flex items-center shrink-0"
                    title={`Make v${v.version} the current version`}
                    data-testid={`admin-doc-restore-${doc.id}-${v.version}`}>
                    <RotateCcw className="h-3.5 w-3.5 mr-1" />
                    {restoring === v.version ? "Restoring…" : "Restore"}
                  </button>
                </li>
              ))}
              {versions.length > 5 && (
                <li className="text-[11px] text-[#94A3B8] italic px-1">
                  Showing latest 5 of {versions.length} versions.
                </li>
              )}
            </ul>
          )}
        </div>
      )}
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
