import React from "react";
import { Info } from "lucide-react";

/** Plain-English role definition helper block shown at the top of each role step. */
export default function RoleDefinition({ role, who_is, who_to_put, showIntro = true }) {
  return (
    <div className="mb-6 p-4 rounded-lg bg-sand-200/40 border border-[#E2E0DA]" data-testid={`role-definition-${role.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
      {showIntro && (
        <p className="text-[11px] uppercase tracking-[0.18em] text-bronze font-semibold mb-2 flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5" /> What this means
        </p>
      )}
      <p className="font-serif text-lg text-navy mb-2">{role}</p>
      <dl className="text-sm text-[#475569] space-y-1.5">
        <div>
          <dt className="font-semibold text-navy/80 inline">Who this is: </dt>
          <dd className="inline text-[#475569]">{who_is}</dd>
        </div>
        <div>
          <dt className="font-semibold text-navy/80 inline">Who to put here: </dt>
          <dd className="inline text-[#475569]">{who_to_put}</dd>
        </div>
      </dl>
    </div>
  );
}
