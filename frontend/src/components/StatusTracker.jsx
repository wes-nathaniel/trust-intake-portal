import React from "react";
import { CheckCircle2, Circle } from "lucide-react";

const STEPS = [
  "Intake Started",
  "Intake In Progress",
  "Waiting on Documents",
  "In Review",
  "Drafting Trust",
  "Ready for Client Review",
  "Ready for Payment",
  "Pending Payment Verification",
  "Payment Verified",
  "Completed",
];

export default function StatusTracker({ status }) {
  const idx = STEPS.indexOf(status);
  const total = STEPS.length;
  const current = idx >= 0 ? idx + 1 : 0;
  const pct = idx >= 0 ? Math.round((current / total) * 100) : 0;

  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6 lg:p-8" data-testid="status-tracker">
      <div className="flex items-center justify-between gap-3 mb-3 sm:mb-4">
        <h3 className="font-serif text-xl sm:text-2xl text-navy">Case Status</h3>
        <span className="text-[10px] sm:text-xs uppercase tracking-wide bg-bronze/10 text-bronze px-2.5 sm:px-3 py-1 rounded-full font-semibold whitespace-nowrap">
          {status || "Not Started"}
        </span>
      </div>

      {/* ----- MOBILE: progress bar + step number ----- */}
      <div className="sm:hidden" data-testid="status-tracker-mobile">
        <div className="flex items-center justify-between text-xs text-[#64748B] mb-2">
          <span>Step {current} of {total}</span>
          <span>{pct}%</span>
        </div>
        <div className="h-2 bg-sand-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-bronze rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
            data-testid="status-tracker-progress-bar"
          />
        </div>
      </div>

      {/* ----- DESKTOP: full step row ----- */}
      <div className="hidden sm:flex sm:items-start" data-testid="status-tracker-desktop">
        {STEPS.map((s, i) => {
          const done = i <= idx;
          const active = i === idx;
          return (
            <div key={s} className="flex flex-col items-center flex-1 relative">
              <div className={`shrink-0 flex items-center justify-center h-8 w-8 rounded-full border-2 ${
                done ? "bg-bronze border-bronze text-white" : "bg-white border-[#E2E0DA] text-[#94A3B8]"
              } ${active ? "step-active" : ""}`} data-testid={`status-step-${i}`}>
                {done ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
              </div>
              <div className="mt-2 text-center px-1">
                <p className={`text-[11px] leading-tight ${done ? "text-navy font-semibold" : "text-[#94A3B8]"}`}>
                  {s}
                </p>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`absolute top-4 left-1/2 w-full h-0.5 ${
                  i < idx ? "bg-bronze" : "bg-[#E2E0DA]"
                }`} style={{ zIndex: -1 }} />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
