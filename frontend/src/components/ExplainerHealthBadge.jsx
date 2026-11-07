import React, { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, AlertTriangle, CheckCircle2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

// Admin-only health badge for the page-by-page AI explainer of the current trust draft.
export default function ExplainerHealthBadge({ caseId }) {
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const timer = useRef(null);

  const load = useCallback(async () => {
    clearTimeout(timer.current);
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/trust-page-explanations`);
      setS(data);
      if (data.status === "pending") timer.current = setTimeout(load, 10000);
    } catch { setS(null); }
  }, [caseId]);

  useEffect(() => { load(); return () => clearTimeout(timer.current); }, [load]);

  const regenFailed = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/trust-page-explanations/regenerate-failed`);
      toast.success(data.failed_pages?.length ? `Regenerating ${data.failed_pages.length} page(s), one at a time…` : "No failed pages.");
      setTimeout(load, 1500);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  if (!s || s.status === "idle") return null;
  const failed = s.failed_pages || [];
  const base = "mt-3 p-3 rounded-md border text-sm flex flex-wrap items-center justify-between gap-3";

  if (s.status === "pending") {
    return (
      <div className={`${base} bg-sand-200/40 border-bronze/30 text-navy`} data-testid="explainer-health-badge" data-status="pending">
        <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin text-bronze" />
          Explainer writing… {s.pages_done} / {s.pages_total || "?"} pages done</span>
      </div>
    );
  }
  if (s.status === "needs_attention" || s.status === "failed") {
    return (
      <div className={`${base} bg-red-50 border-red-300 text-red-800`} data-testid="explainer-health-badge" data-status={s.status}>
        <span className="inline-flex items-center gap-2 font-semibold"><AlertTriangle className="h-4 w-4" />
          {failed.length ? `${failed.length} page${failed.length === 1 ? "" : "s"} need attention (page ${failed.join(", ")})` : "Explainer failed. Please regenerate."}
        </span>
        <button onClick={regenFailed} disabled={busy} className="btn-primary text-sm inline-flex items-center gap-1 disabled:opacity-50" data-testid="regenerate-failed-pages-btn">
          <RefreshCw className="h-4 w-4" /> {busy ? "Starting…" : "Regenerate failed pages"}
        </button>
      </div>
    );
  }
  return (
    <div className={`${base} bg-emerald-50 border-emerald-300 text-emerald-900`} data-testid="explainer-health-badge" data-status="completed">
      <span className="inline-flex items-center gap-2"><CheckCircle2 className="h-4 w-4" /> Explainer complete, all {s.pages_total} pages written</span>
    </div>
  );
}
