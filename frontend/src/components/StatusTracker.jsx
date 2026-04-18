import React from "react";
import { CheckCircle2, Circle } from "lucide-react";

const STEPS = [
  "Intake Started",
  "Intake In Progress",
  "Waiting on Documents",
  "In Review",
  "Drafting Trust",
  "Ready for Signing",
  "Completed",
];

export default function StatusTracker({ status }) {
  const idx = STEPS.indexOf(status);
  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl p-6 sm:p-8" data-testid="status-tracker">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-serif text-2xl text-navy">Case Status</h3>
        <span className="text-xs uppercase tracking-wide bg-bronze/10 text-bronze px-3 py-1 rounded-full font-semibold">
          {status || "Not Started"}
        </span>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-start gap-3 sm:gap-0">
        {STEPS.map((s, i) => {
          const done = i <= idx;
          const active = i === idx;
          return (
            <div key={s} className="flex sm:flex-col items-start sm:items-center flex-1 relative">
              <div className={`shrink-0 flex items-center justify-center h-8 w-8 rounded-full border-2 ${
                done ? "bg-bronze border-bronze text-white" : "bg-white border-[#E2E0DA] text-[#94A3B8]"
              } ${active ? "step-active" : ""}`} data-testid={`status-step-${i}`}>
                {done ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
              </div>
              <div className="ml-3 sm:ml-0 sm:mt-2 sm:text-center">
                <p className={`text-xs sm:text-[11px] leading-tight ${done ? "text-navy font-semibold" : "text-[#94A3B8]"}`}>
                  {s}
                </p>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`hidden sm:block absolute top-4 left-1/2 w-full h-0.5 ${
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
