import React, { useState } from "react";
import { ClipboardCheck, FileSearch, PenLine, Download, X } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const STEPS = [
  { icon: ClipboardCheck, title: "Complete your intake form", body: "Walk through a guided, section-by-section questionnaire to capture everything we need." },
  { icon: FileSearch,    title: "Review your trust draft",   body: "Read a side-by-side view of your trust — legal text on the left, plain English on the right." },
  { icon: PenLine,       title: "Sign and approve",          body: "Confirm the trust draft, pay the filing fee, and notarize the final document." },
  { icon: Download,      title: "Download your documents",   body: "Receive your final trust, EIN letter, and supporting files — all from your portal." },
];

/**
 * One-time "Take the Tour" card shown on the client portal after a first login.
 * Dismissing posts to /auth/dismiss-tour which sets has_seen_tour=true on the
 * user record, so the card never appears again on any device.
 *
 * Props:
 *  - onDismissed(): called after the server confirms the flag was flipped.
 */
export default function TourCard({ onDismissed }) {
  const [dismissing, setDismissing] = useState(false);

  const handleDismiss = async () => {
    setDismissing(true);
    try {
      await api.post("/auth/dismiss-tour");
      onDismissed && onDismissed();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      setDismissing(false);
    }
  };

  return (
    <div
      className="relative bg-white border-2 border-bronze/40 rounded-xl p-6 sm:p-7 mb-10 shadow-sm"
      data-testid="tour-card">
      <button
        type="button"
        onClick={handleDismiss}
        disabled={dismissing}
        className="absolute top-3 right-3 p-1.5 rounded-md text-[#94A3B8] hover:text-navy hover:bg-sand-200/60 disabled:opacity-50"
        aria-label="Dismiss tour"
        data-testid="tour-card-close-btn">
        <X className="h-4 w-4" />
      </button>

      <p className="text-[11px] uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Take the tour</p>
      <h3 className="font-serif text-2xl text-navy mb-1">Here&rsquo;s how this portal works</h3>
      <p className="text-sm text-[#64748B] mb-5 max-w-2xl">Four simple steps from start to finish.</p>

      <ol className="grid sm:grid-cols-2 gap-4">
        {STEPS.map((s, i) => {
          const Icon = s.icon;
          return (
            <li
              key={s.title}
              className="flex gap-3 items-start"
              data-testid={`tour-step-${i + 1}`}>
              <div className="shrink-0 mt-0.5 h-9 w-9 rounded-full bg-sand-200/70 border border-bronze/30 flex items-center justify-center">
                <Icon className="h-4 w-4 text-bronze" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-navy">
                  <span className="text-bronze mr-1.5">{i + 1}.</span>{s.title}
                </p>
                <p className="text-xs text-[#64748B] mt-0.5 leading-relaxed">{s.body}</p>
              </div>
            </li>
          );
        })}
      </ol>

      <div className="mt-6 flex items-center justify-between flex-wrap gap-3">
        <p className="text-xs text-[#94A3B8]">This card is shown once — you can dismiss it at any time.</p>
        <button
          type="button"
          onClick={handleDismiss}
          disabled={dismissing}
          className="btn-primary text-sm"
          data-testid="tour-card-dismiss-btn">
          {dismissing ? "Saving…" : "Got it — don't show again"}
        </button>
      </div>
    </div>
  );
}
