import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Send, CalendarClock, AlertTriangle } from "lucide-react";
import ReleaseDialog from "@/components/ReleaseDialog";

function ScheduledNotice({ s, changes, onCancel, onUpdate }) {
  return (
    <div className="mb-2 text-sm" data-testid="release-scheduled-notice">
      <p className="flex items-center gap-1.5 text-navy"><CalendarClock className="h-4 w-4 text-bronze shrink-0" />
        Scheduled: <b data-testid="release-scheduled-time">{s.release_at_local}</b> ({s.send_email ? "with email" : "no email"}), status {s.snapshot.status}
      </p>
      {changes.length > 0 && (
        <div className="mt-2 p-2 rounded-md bg-amber-50 border border-amber-300 text-amber-900" data-testid="release-changed-warning">
          <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-4 w-4" /> Changed since scheduled</p>
          <ul className="list-disc ml-5">{changes.map((c) => <li key={c}>{c}</li>)}</ul>
          <p className="text-xs mt-1">Only what you scheduled will go out, unless you update it.</p>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {changes.length > 0 && <button type="button" onClick={onUpdate} className="btn-accent min-h-[44px] text-sm" data-testid="release-update-scheduled-btn">Update scheduled release</button>}
        <button type="button" onClick={onCancel} className="btn-secondary min-h-[44px] text-sm" data-testid="release-cancel-scheduled-btn">Cancel scheduled release</button>
      </div>
    </div>
  );
}

// Sticky bar: the ONLY way a client sees new status/drafts or gets a status email.
export default function ReleaseBar({ caseId, reloadKey, onReleased }) {
  const [p, setP] = useState(null);
  const [open, setOpen] = useState(false);
  const load = async () => {
    try { const { data } = await api.get(`/admin/trust-cases/${caseId}/release`); setP(data); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [caseId, reloadKey]);
  if (!p) return null;

  const act = async (fn, msg) => {
    try { await fn(); toast.success(msg); await load(); onReleased(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const pending = p.internal_status !== p.client_status || p.draft_held || p.asset_edits_held > 0;
  const s = p.scheduled_release;
  return (
    <div className="sticky bottom-0 z-30 -mx-4 sm:mx-0 mt-6 bg-white/95 backdrop-blur-xl border-t sm:border border-[#E2E0DA] sm:rounded-xl shadow-[0_-6px_20px_rgba(28,37,46,0.08)] px-4 py-3" data-testid="release-bar">
      {s && <ScheduledNotice s={s} changes={p.changed_since_scheduled}
        onCancel={() => act(() => api.delete(`/admin/trust-cases/${caseId}/release/scheduled`), "Scheduled release cancelled.")}
        onUpdate={() => act(() => api.post(`/admin/trust-cases/${caseId}/release/scheduled/update`), "Scheduled release now uses the latest version.")} />}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:justify-between">
        <p className="text-sm text-navy" data-testid="release-bar-status">
          Client sees: <b data-testid="release-client-status">{p.client_status}</b>
          <span className="text-[#64748B]"> · Yours: <span data-testid="release-internal-status">{p.internal_status}</span></span>
          {pending && <span className="ml-1 text-amber-700" data-testid="release-pending-note"> · not released yet{p.draft_held ? " (draft held)" : ""}{p.asset_edits_held ? ` (${p.asset_edits_held} asset edit)` : ""}</span>}
        </p>
        <button type="button" onClick={() => setOpen(true)} className="btn-primary min-h-[48px] w-full sm:w-auto inline-flex items-center justify-center gap-2" data-testid="release-to-client-btn">
          <Send className="h-4 w-4" /> Release to client for review
        </button>
      </div>
      {open && <ReleaseDialog open={open} onOpenChange={setOpen} caseId={caseId} preview={p} onDone={() => { load(); onReleased(); }} />}
    </div>
  );
}
