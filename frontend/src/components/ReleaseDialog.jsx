import React, { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Send, CalendarClock, EyeOff } from "lucide-react";

const MODES = [
  { id: "now", icon: Send, label: "Release now", hint: "The client sees it now and gets the email below." },
  { id: "schedule", icon: CalendarClock, label: "Schedule release", hint: "Pick a day and time (New York time)." },
  { id: "silent", icon: EyeOff, label: "Release without email", hint: "The client sees it now. No email is sent." },
];

function ModePicker({ mode, setMode }) {
  return (
    <div className="grid gap-2" role="radiogroup">
      {MODES.map(({ id, icon: Icon, label, hint }) => (
        <button key={id} type="button" role="radio" aria-checked={mode === id} onClick={() => setMode(id)}
          className={`min-h-[56px] w-full text-left rounded-lg border px-4 py-3 flex items-start gap-3 transition-colors ${mode === id ? "border-navy bg-navy/5 ring-1 ring-navy" : "border-[#E2E0DA] bg-white hover:bg-sand-200/30"}`}
          data-testid={`release-mode-${id}`}>
          <Icon className="h-5 w-5 mt-0.5 shrink-0 text-bronze" />
          <span><span className="block font-semibold text-navy">{label}</span><span className="block text-sm text-[#64748B]">{hint}</span></span>
        </button>
      ))}
    </div>
  );
}

function EmailEditor({ to, subject, setSubject, message, setMessage }) {
  return (
    <div className="space-y-2" data-testid="release-email-editor">
      <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Email to {to}. This exact text is sent. Edit it if you like.</p>
      <input value={subject} onChange={(e) => setSubject(e.target.value)} maxLength={200}
        className="w-full min-h-[44px] border border-input rounded-md px-3 text-base" data-testid="release-email-subject" aria-label="Email subject" />
      <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={9} maxLength={5000}
        className="text-base" data-testid="release-email-message" aria-label="Email message" />
      <p className="text-xs text-[#64748B]">An "Open your portal" button is added under the message.</p>
    </div>
  );
}

export default function ReleaseDialog({ open, onOpenChange, caseId, preview, onDone }) {
  const [mode, setMode] = useState("now");
  const [subject, setSubject] = useState(preview.subject);
  const [message, setMessage] = useState(preview.message);
  const [day, setDay] = useState("");
  const [time, setTime] = useState("09:00");
  const [busy, setBusy] = useState(false);
  const [schedEmail, setSchedEmail] = useState(true);
  const withEmail = mode === "now" || (mode === "schedule" && schedEmail);

  const submit = async () => {
    if (mode === "schedule" && !day) { toast.error("Pick a day for the release."); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/release`, {
        mode, subject, message, send_email: withEmail, release_at: mode === "schedule" ? `${day}T${time}` : "",
      });
      if (mode === "schedule") toast.success(`Scheduled for ${data.scheduled.release_at_local}.`);
      else if (mode === "silent") toast.success("Released. No email was sent.");
      else if (data.release.emailed) toast.success(`Released and emailed to ${preview.client_email}.`);
      else toast.warning("Released, but the email could not be sent. Check Resend.");
      onOpenChange(false);
      onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  const cta = { now: "Release and send email", schedule: "Schedule release", silent: "Release without email" }[mode];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[calc(100vw-1rem)] max-w-xl max-h-[92vh] overflow-y-auto p-4 sm:p-6" data-testid="release-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl text-navy">Release to client for review</DialogTitle>
          <DialogDescription data-testid="release-dialog-summary">
            The client will see status <b>{preview.internal_status}</b>
            {preview.draft_held ? ", the trust draft and its explainer" : ""}
            {preview.asset_edits_held ? `, and ${preview.asset_edits_held} asset edit(s)` : ""}.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <ModePicker mode={mode} setMode={setMode} />
          {mode === "schedule" && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2" data-testid="release-schedule-fields">
              <label className="text-sm text-navy">Day
                <input type="date" value={day} onChange={(e) => setDay(e.target.value)}
                  className="mt-1 w-full min-h-[44px] border border-input rounded-md px-3 text-base" data-testid="release-schedule-date" />
              </label>
              <label className="text-sm text-navy">Time (New York)
                <input type="time" value={time} onChange={(e) => setTime(e.target.value)}
                  className="mt-1 w-full min-h-[44px] border border-input rounded-md px-3 text-base" data-testid="release-schedule-time" />
              </label>
              <label className="sm:col-span-2 min-h-[44px] flex items-center gap-3 text-sm text-navy cursor-pointer">
                <input type="checkbox" checked={schedEmail} onChange={(e) => setSchedEmail(e.target.checked)}
                  className="h-5 w-5 accent-[#1C252E]" data-testid="release-schedule-send-email" />
                Send the email when it releases
              </label>
            </div>
          )}
          {withEmail && <EmailEditor to={preview.client_email} subject={subject} setSubject={setSubject} message={message} setMessage={setMessage} />}
          <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end">
            <button type="button" onClick={() => onOpenChange(false)} className="btn-secondary min-h-[44px]" data-testid="release-cancel-btn">Cancel</button>
            <button type="button" onClick={submit} disabled={busy} className="btn-primary min-h-[44px] disabled:opacity-50" data-testid="release-confirm-btn">
              {busy ? "Working…" : cta}
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
