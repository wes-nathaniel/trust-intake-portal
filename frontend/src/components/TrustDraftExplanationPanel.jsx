import React, { useEffect, useRef, useState, useCallback } from "react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Sparkles, AlertCircle, Loader2, RefreshCw } from "lucide-react";

/**
 * Right-hand panel on the client trust preview page. Fetches the per-page
 * personalized plain-English explanations and renders the one matching the
 * PDF page the client is currently viewing on the LEFT — the two panels move
 * together as the client pages through the trust.
 *
 * Polls every 6s while the background job is still running so pages appear
 * as soon as the LLM finishes each batch.
 *
 * Admin-only: shows a "Regenerate" button so an admin viewing the client
 * preview can retry without re-uploading the PDF (e.g., if intake data was
 * updated after the initial upload).
 */
export default function TrustDraftExplanationPanel({ caseId, clientName, currentPage, totalPages }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [state, setState] = useState({ loading: true, byPage: {}, status: "pending", pagesDone: 0, pagesTotal: 0, error: null });
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState(null);
  const pollTimer = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/trust-page-explanations`);
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
      const detail = e.response?.data?.detail || "Unable to load your plain-English explanation.";
      setState((s) => ({ ...s, loading: false, error: detail, status: "error" }));
    }
  }, [caseId]);

  useEffect(() => {
    load();
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, [load]);

  const handleRegenerate = async () => {
    if (regenerating || !currentPage) return;
    setRegenerating(true);
    setRegenError(null);
    // Kick off single-page regenerate. Only the page currently being
    // viewed will be re-generated; all other pages are left alone.
    try {
      await api.post(`/admin/trust-cases/${caseId}/trust-page-explanations/${currentPage}/regenerate`);
    } catch (e) {
      const detail = e.response?.data?.detail || "Could not start regeneration. Please try again.";
      setRegenError(detail);
      setRegenerating(false);
      return;
    }
    // Optimistically clear the current page so the pending state shows
    setState((s) => ({ ...s, byPage: { ...s.byPage, [currentPage]: undefined } }));
    // Poll the single-page status endpoint every 3s until completed or failed.
    // Cap at ~3 min (60 polls) to avoid runaway loops on a bad case.
    let polls = 0;
    const MAX_POLLS = 60;
    const pollOnce = async () => {
      polls += 1;
      try {
        const { data } = await api.get(`/trust-cases/${caseId}/trust-page-explanations/${currentPage}/status`);
        if (data.status === "completed") {
          // Re-fetch the whole explanations blob so byPage picks up the fresh text
          await load();
          setRegenerating(false);
          return;
        }
        if (data.status === "failed") {
          setRegenError(data.error || "Regeneration failed. Please try again.");
          await load();
          setRegenerating(false);
          return;
        }
        if (polls >= MAX_POLLS) {
          setRegenError("Regeneration is taking longer than expected. Refresh in a moment to check.");
          setRegenerating(false);
          return;
        }
        setTimeout(pollOnce, 3000);
      } catch (e) {
        setRegenError(e.response?.data?.detail || "Lost connection while regenerating.");
        setRegenerating(false);
      }
    };
    setTimeout(pollOnce, 1500);
  };

  const first = (clientName || "").split(" ")[0] || "there";
  const html = state.byPage[currentPage];
  const jobRunning = state.status === "pending";

  return (
    <div
      className="bg-white rounded-xl border border-[#E2E0DA] overflow-hidden flex flex-col"
      style={{ minHeight: 500 }}
      data-testid="trust-draft-explanation-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 bg-sand-200/60 border-b border-[#E2E0DA] gap-2">
        <div className="text-xs tracking-wide uppercase text-bronze font-semibold flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5" /> Page {currentPage || "—"} — in plain English
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-navy/70 bg-white px-2 py-0.5 rounded-full border border-[#E2E0DA]" data-testid="personalized-badge">
            Personalized for {first}
          </span>
          {isAdmin && (
            <button
              type="button"
              onClick={handleRegenerate}
              disabled={regenerating || jobRunning}
              data-testid="regenerate-page-explanations-btn"
              className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-white bg-bronze hover:bg-bronze/90 disabled:opacity-50 disabled:cursor-not-allowed px-2.5 py-1 rounded-full transition-colors"
              title="Admin: regenerate plain-English notes for THIS page only (audited)"
            >
              {regenerating ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              {jobRunning ? "Running…" : regenerating ? "Starting…" : "Regenerate"}
            </button>
          )}
        </div>
      </div>

      {regenError && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-200 text-[11px] text-red-700 flex items-center gap-2" data-testid="regenerate-error">
          <AlertCircle className="h-3 w-3" /> {regenError}
        </div>
      )}

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
