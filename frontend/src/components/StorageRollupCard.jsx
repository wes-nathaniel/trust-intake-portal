import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { HardDrive, AlertCircle, ChevronDown, ArrowRight } from "lucide-react";

/** Dashboard-level storage rollup for the AI Document Explainer. Aggregates
 *  usage across ALL non-archived cases and lists the top storage-heavy accounts
 *  so the admin can plan trim sweeps without opening each case individually. */
export default function StorageRollupCard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [showTop, setShowTop] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get("/admin/storage-rollup");
        if (!cancelled) setData(data);
      } catch (e) {
        if (!cancelled) setError("Could not load storage rollup.");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const fmt = (n) => {
    if (!n) return "0 KB";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
    if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  };

  if (error) return null;
  if (!data) {
    return (
      <div className="bg-white border border-[#E2E0DA] rounded-xl p-5 mb-6 text-sm text-[#94A3B8]" data-testid="storage-rollup-card">
        Loading storage usage…
      </div>
    );
  }
  if (data.total_bytes === 0) return null; // Nothing to show yet.

  const heavy = data.heavy_case_count > 0;

  return (
    <div
      className={`rounded-xl p-5 mb-6 border ${heavy ? "border-amber-300 bg-amber-50" : "border-[#E2E0DA] bg-white"}`}
      data-testid="storage-rollup-card">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3 min-w-0">
          {heavy ? (
            <AlertCircle className="h-5 w-5 text-amber-700 shrink-0" />
          ) : (
            <HardDrive className="h-5 w-5 text-bronze shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.2em] text-bronze font-semibold mb-0.5">Storage Usage</p>
            <p className="text-sm text-navy" data-testid="storage-rollup-summary">
              <b>{fmt(data.total_bytes)}</b> total across{" "}
              <b>{data.cases_with_docs}</b> case{data.cases_with_docs === 1 ? "" : "s"}
            </p>
            <p className="text-xs text-[#64748B] mt-1">
              <span title="Documents uploaded by admin + their AI explanations + archived versions">
                🤖 AI Explainer <b className="text-navy">{fmt(data.ai_bytes)}</b>
                <span className="text-[#94A3B8]"> ({data.doc_count} docs · {data.version_count} archived)</span>
              </span>
              <span className="text-[#94A3B8]"> · </span>
              <span title="Files clients uploaded (IDs, bills, existing trust, etc.)">
                📄 Client uploads <b className="text-navy">{fmt(data.client_bytes)}</b>
                <span className="text-[#94A3B8]"> ({data.client_doc_count})</span>
              </span>
              <span className="text-[#94A3B8]"> · </span>
              <span title="Trust Draft PDFs uploaded by admin">
                📜 Trust drafts <b className="text-navy">{fmt(data.draft_bytes)}</b>
                <span className="text-[#94A3B8]"> ({data.draft_count})</span>
              </span>
            </p>
            {heavy && (
              <p className="text-xs text-amber-800 mt-1">
                <b>{data.heavy_case_count}</b> case{data.heavy_case_count === 1 ? "" : "s"} over {fmt(data.heavy_threshold_bytes)} — expand below and trim.
              </p>
            )}
          </div>
        </div>
        {data.top_cases.length > 0 && (
          <button
            type="button"
            onClick={() => setShowTop((v) => !v)}
            className="text-xs text-[#64748B] hover:text-navy inline-flex items-center gap-1 shrink-0"
            aria-expanded={showTop}
            data-testid="storage-rollup-toggle">
            {showTop ? "Hide top" : "Show top storage-heavy cases"}
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showTop ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>

      {showTop && data.top_cases.length > 0 && (
        <div className="mt-4 bg-white rounded-md border border-[#E2E0DA] overflow-hidden" data-testid="storage-rollup-top">
          <table className="w-full text-xs">
            <thead className="bg-sand-200/40 text-[#64748B] uppercase tracking-wide">
              <tr>
                <th className="text-left px-3 py-1.5 font-semibold">Client</th>
                <th className="text-right px-3 py-1.5 font-semibold" title="AI Explainer">🤖 AI</th>
                <th className="text-right px-3 py-1.5 font-semibold" title="Client uploads">📄 Client</th>
                <th className="text-right px-3 py-1.5 font-semibold" title="Trust draft PDF">📜 Draft</th>
                <th className="text-right px-3 py-1.5 font-semibold">Total</th>
                <th className="px-3 py-1.5" />
              </tr>
            </thead>
            <tbody>
              {data.top_cases.map((c) => {
                const isHeavy = c.total_bytes >= data.heavy_threshold_bytes;
                return (
                  <tr key={c.case_id} className="border-t border-[#F1EFEA]" data-testid={`storage-row-${c.case_id}`}>
                    <td className="px-3 py-1.5 min-w-0">
                      <span className="text-navy font-medium truncate">{c.client_name || c.client_email || "(unknown)"}</span>
                      {c.trust_name && <span className="text-[#94A3B8]"> · {c.trust_name}</span>}
                    </td>
                    <td className="px-3 py-1.5 text-right text-navy">{c.ai_bytes ? fmt(c.ai_bytes) : "—"}</td>
                    <td className="px-3 py-1.5 text-right text-navy">{c.client_bytes ? fmt(c.client_bytes) : "—"}</td>
                    <td className="px-3 py-1.5 text-right text-navy">{c.trust_draft_bytes ? fmt(c.trust_draft_bytes) : "—"}</td>
                    <td className={`px-3 py-1.5 text-right font-semibold ${isHeavy ? "text-amber-800" : "text-navy"}`}>{fmt(c.total_bytes)}</td>
                    <td className="px-3 py-1.5 text-right">
                      <Link
                        to={`/admin/cases/${c.case_id}`}
                        className="inline-flex items-center gap-0.5 text-[#64748B] hover:text-bronze"
                        data-testid={`storage-open-${c.case_id}`}>
                        Open <ArrowRight className="h-3 w-3" />
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
