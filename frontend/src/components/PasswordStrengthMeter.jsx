import React from "react";
import { passwordScore, passwordTips, STRENGTH_LABELS, MIN_GOOD_SCORE } from "@/lib/passwordStrength";

const COLORS = ["bg-[#E2E0DA]", "bg-red-500", "bg-amber-500", "bg-emerald-500", "bg-emerald-700"];
const TEXT = ["text-[#94A3B8]", "text-red-700", "text-amber-700", "text-emerald-700", "text-emerald-800"];

export default function PasswordStrengthMeter({ password, testId = "password-strength" }) {
  if (!password) return null;
  const score = passwordScore(password);
  const tips = score < MIN_GOOD_SCORE ? passwordTips(password) : [];
  return (
    <div className="mt-2" data-testid={testId}>
      <div className="flex gap-1" aria-hidden="true">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={`h-1.5 flex-1 rounded-full transition-colors duration-300 ${i <= score ? COLORS[score] : "bg-[#E2E0DA]"}`} />
        ))}
      </div>
      <p className={`text-xs mt-1 font-semibold ${TEXT[score]}`} data-testid={`${testId}-label`} data-score={score}>
        {STRENGTH_LABELS[score]}
        {score < MIN_GOOD_SCORE && <span className="font-normal text-[#64748B]"> — needs to be at least “Good”</span>}
      </p>
      {tips.length > 0 && (
        <ul className="text-xs text-[#64748B] list-disc list-inside mt-1 space-y-0.5" data-testid={`${testId}-tips`}>
          {tips.map((t) => <li key={t}>{t}</li>)}
        </ul>
      )}
    </div>
  );
}
