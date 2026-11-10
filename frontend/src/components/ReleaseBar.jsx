import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Send, CalendarClock, AlertTriangle, ChevronDown, History, XCircle, Mail, MailX } from "lucide-react";
import ReleaseDialog from "@/components/ReleaseDialog";

function ScheduledNotice({ s, changes, onCancel, onUpdate }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mb-2 text-sm" data-testid="release-scheduled-notice">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="w-full min-h-[44px] flex items-center gap-1.5 text-left text-navy" data-testid="release-scheduled-toggle">
        <CalendarClock className="h-4 w-4 text-bronze shrink-0" />
        <span className="flex-1">Scheduled: <b data-testid="release-scheduled-time">{s.release_at_local}</b> ({s.send_email ? "with email" : "no email"})</span>
        {changes.length > 0 && <span className="inline-flex items-center gap-1 text-amber-800 font-semibold" data-testid="release-changed-warning"><AlertTriangle className="h-4 w-4" /> Changed since scheduled</span>}
        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="pb-1" data-testid="release-scheduled-details">
          <p className="text-[#64748B]">Will show status <b>{s.snapshot.status}</b>{s.snapshot.draft_held ? " and the trust draft" : ""}.</p>
          {changes.length > 0 && (
            <div className="mt-2 p-2 rounded-md bg-amber-50 border border-amber-300 text-amber-900">
              <ul className="list-disc ml-5">{changes.map((c) => <li key={c}>{c}</li>)}</ul>
              <p className="text-xs mt-1">Only what you scheduled will go out, unless you update it.</p>
            </div>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {changes.length > 0 && <button type="button" onClick={onUpdate} className="btn-primary min-h-[44px] text-sm" data-testid="release-update-scheduled-btn">Update scheduled release</button>}
            <button type="button" onClick={onCancel} className="btn-secondary min-h-[44px] text-sm" data-testid="release-cancel-scheduled-btn">Cancel scheduled release</button>
          </div>
        </div>
      )}
    </div>
  );
}

const MODE_LABELS = { now: "Released now", schedule: "Scheduled release", silent: "Released (no email)" };

function ReleaseLog({ history }) {
  const [open, setOpen] = useState(false);
  if (!history || history.length === 0) return null;
  return (
    <div className="mb-2 border-t border-[#E2E0DA] pt-2" data-testid="release-log">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="w-full min-h-[44px] flex items-center gap-1.5 text-left text-sm text-[#64748B]" data-testid="release-log-toggle">
        <History className="h-4 w-4 shrink-0" />
        <span className="flex-1 font-semibold">Release log ({history.length})</span>
        <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul className="mt-1 space-y-1.5" data-testid="release-log-list">
          {history.map((e, i) => {
            const sent = e.emailed;
            const requested = e.email_requested;
            return (
              <li key={e.id || i} className="flex flex-col gap-0.5 text-xs rounded-md bg-[#F6F4F0] px-3 py-2" data-testid={`release-log-entry-${i}`}>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {sent
                    ? <Mail className="h-3.5 w-3.5 text-green-600 shrink-0" />
                    : requested
                      ? <XCircle className="h-3.5 w-3.5 text-red-500 shrink-0" title="Email failed to send" />
                      : <MailX className="h-3.5 w-3.5 text-[#94A3B8] shrink-0" />}
                  <span className="font-semibold text-navy">{MODE_LABELS[e.mode] || e.mode}</span>
                  <span className="text-[#94A3B8]">·</span>
                  <span className="text-[#64748B]">Status: <b className="text-navy">{e.status}</b></span>
                  {e.draft_released && <span className="ml-1 text-green-700">· draft released</span>}
                  {e.assets_released > 0 && <span className="ml-1 text-green-700">· {e.assets_released} asset(s) released</span>}
                </div>
                <div className="flex items-center gap-1.5 text-[#94A3B8] flex-wrap">
                  <span>{new Date(e.at).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" })}</span>
                  <span>·</span>
                  <span>by {e.by}</span>
                  {sent && e.subject && <><span>·</span><span className="italic truncate max-w-[180px]" title={e.subject}>"{e.subject}"</span></>}
                  {requested && !sent && <><span>·</span><span className="text-red-500 font-semibold">Email failed</span></>}
                  {!requested && e.mode !== "silent" && <><span>·</span><span>No email</span></>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
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
    <div className="sticky bottom-0 z-30 -mx-3 sm:mx-0 mt-6 bg-white/95 backdrop-blur-xl border-t sm:border border-[#E2E0DA] sm:rounded-xl shadow-[0_-6px_20px_rgba(28,37,46,0.08)] px-4 py-3" data-testid="release-bar">
      <ReleaseLog history={p.history} />
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
