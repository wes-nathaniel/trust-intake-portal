import React, { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { Sparkles, AlertCircle, Loader2 } from "lucide-react";

/**
 * Right-hand panel on the client trust preview page. Fetches the per-page
 * personalized plain-English explanations and renders the one matching the
 * PDF page the client is currently viewing on the LEFT — the two panels move
 * together as the client pages through the trust.
 *
 * Polls every 6s while the background job is still running so pages appear
 * as soon as the LLM finishes each batch.
 */
export default function TrustDraftExplanationPanel({ caseId, clientName, currentPage, totalPages }) {
  const [state, setState] = useState({ loading: true, byPage: {}, status: "pending", pagesDone: 0, pagesTotal: 0, error: null });
  const pollTimer = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const { data } = await api.get(`/trust-cases/${caseId}/trust-page-explanations`);
        if (cancelled) return;
        const map = {};
        (data.explanations || []).forEach((e) => { map[e.page] = e.text; });
        setState({
          loading: false,
          byPage: map,
          status: data.status || "idle",
          pagesDone: data.pages_done || 0,
          pagesTotal: data.pages_total || 0,
          error: data.error || null,
        });
        // Keep polling while the job is still running
        if (data.status === "pending") {
          pollTimer.current = setTimeout(load, 6000);
        }
      } catch (e) {
        if (cancelled) return;
        const detail = e.response?.data?.detail || "Unable to load your plain-English explanation.";
        setState((s) => ({ ...s, loading: false, error: detail, status: "error" }));
      }
    };
    load();
    return () => {
      cancelled = true;
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [caseId]);

  const first = (clientName || "").split(" ")[0] || "there";
  const html = state.byPage[currentPage];
  const jobRunning = state.status === "pending";

  return (
    <div
      className="bg-white rounded-xl border border-[#E2E0DA] overflow-hidden flex flex-col"
      style={{ minHeight: 500 }}
      data-testid="trust-draft-explanation-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 bg-sand-200/60 border-b border-[#E2E0DA]">
        <div className="text-xs tracking-wide uppercase text-bronze font-semibold flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5" /> Page {currentPage || "—"} — in plain English
        </div>
        <span className="text-[10px] font-semibold uppercase tracking-wide text-navy/70 bg-white px-2 py-0.5 rounded-full border border-[#E2E0DA]" data-testid="personalized-badge">
          Personalized for {first}
        </span>
      </div>

      {jobRunning && (
        <div className="px-4 py-2 bg-bronze/10 border-b border-bronze/30 text-[11px] text-bronze font-semibold flex items-center gap-2" data-testid="page-job-progress">
          <Loader2 className="h-3 w-3 animate-spin" />
          Writing plain-English notes… {state.pagesDone}
          {state.pagesTotal ? ` of ${state.pagesTotal}` : ""} page{state.pagesDone === 1 ? "" : "s"} ready
        </div>
      )}

      <div className="p-6 space-y-4 text-navy leading-relaxed overflow-y-auto flex-1" data-testid="trust-draft-explanation-body">
        {state.loading && (
          <div className="flex items-center gap-2 text-sm text-[#64748B]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading your personalized notes…
          </div>
        )}

        {!state.loading && state.status === "failed" && (
          <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-800" data-testid="explanation-empty">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold mb-1">Your plain-English notes couldn&apos;t be generated.</p>
              <p className="text-amber-700">{state.error || "Please contact your administrator to regenerate."}</p>
            </div>
          </div>
        )}

        {!state.loading && !html && (state.status === "pending" || state.status === "idle") && (
          <div className="flex items-start gap-3 p-4 bg-sand-200/40 border border-bronze/30 rounded-md text-sm text-navy" data-testid="explanation-page-pending">
            <Loader2 className="h-4 w-4 mt-0.5 shrink-0 animate-spin text-bronze" />
            <div>
              <p className="font-semibold mb-1">Page {currentPage} note is on the way.</p>
              <p className="text-[#64748B]">
                We&apos;re writing this page&apos;s plain-English walk-through just for you. It&apos;ll appear here in a few seconds.
              </p>
            </div>
          </div>
        )}

        {!state.loading && !html && state.status === "completed" && (
          <div className="text-sm text-[#64748B] italic" data-testid="explanation-page-missing">
            No plain-English note was generated for this page (may be blank or a signature page).
          </div>
        )}

        {html && (
          <div
            className="space-y-3 [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-2 [&_li]:mb-1 [&_strong]:text-navy [&_strong]:font-semibold"
            data-testid={`explanation-page-${currentPage}`}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        )}
      </div>

      {state.pagesTotal > 0 && (
        <div className="px-4 py-2 text-[10px] text-[#94A3B8] border-t border-[#E2E0DA] text-right">
          {totalPages ? `PDF page ${currentPage} of ${totalPages}` : ""} · notes ready for {state.pagesDone}/{state.pagesTotal} page{state.pagesTotal === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );
}
