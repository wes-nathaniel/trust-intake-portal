import React, { useEffect, useState } from "react";
import api from "@/lib/api";
import { Sparkles, AlertCircle, Loader2 } from "lucide-react";

/**
 * Right-hand panel on the client trust preview page. Fetches the personalized
 * plain-English explanation stored on the case's imported "trust_draft" AI
 * document and renders it as a readable, warm walk-through. Falls back
 * gracefully when the explanation hasn't been generated yet.
 */
export default function TrustDraftExplanationPanel({ caseId, clientName }) {
  const [state, setState] = useState({ loading: true, data: null, error: null });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/trust-cases/${caseId}/trust-draft-explanation`);
        if (!cancelled) setState({ loading: false, data, error: null });
      } catch (e) {
        const detail = e.response?.data?.detail || "Unable to load your plain-English explanation.";
        if (!cancelled) setState({ loading: false, data: null, error: detail });
      }
    })();
    return () => { cancelled = true; };
  }, [caseId]);

  const first = (clientName || "").split(" ")[0] || "there";

  return (
    <div
      className="bg-white rounded-xl border border-[#E2E0DA] overflow-hidden flex flex-col"
      data-testid="trust-draft-explanation-panel"
    >
      <div className="flex items-center justify-between px-4 py-3 bg-sand-200/60 border-b border-[#E2E0DA]">
        <div className="text-xs tracking-wide uppercase text-bronze font-semibold flex items-center gap-2">
          <Sparkles className="h-3.5 w-3.5" /> Your trust — in plain English
        </div>
        {state.data?.personalized && (
          <span className="text-[10px] font-semibold uppercase tracking-wide text-navy/70 bg-white px-2 py-0.5 rounded-full border border-[#E2E0DA]" data-testid="personalized-badge">
            Personalized for {first}
          </span>
        )}
      </div>

      <div className="p-6 space-y-6 text-navy leading-relaxed overflow-y-auto" data-testid="trust-draft-explanation-body">
        {state.loading && (
          <div className="flex items-center gap-2 text-sm text-[#64748B]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading your personalized explanation…
          </div>
        )}

        {!state.loading && state.error && (
          <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-800" data-testid="explanation-empty">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <p className="font-semibold mb-1">Your plain-English walk-through is being prepared.</p>
              <p className="text-amber-700">
                Your administrator will generate this shortly. Refresh this page in a few minutes to see your trust explained just for you.
              </p>
            </div>
          </div>
        )}

        {!state.loading && state.data && <ExplanationBody ai={state.data.explanation || {}} />}
      </div>
    </div>
  );
}

function ExplanationBody({ ai }) {
  // Personalized (rich) view when the LLM was called with case context —
  // otherwise fall back to the legacy 5-field layout.
  const isPersonalized = ai.personalized || ai.greeting || ai.grantor_intro || ai.beneficiaries;

  if (isPersonalized) {
    return (
      <div className="space-y-6 [&_p]:mb-2 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:mb-2 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol]:mb-2 [&_li]:mb-1 [&_strong]:text-navy [&_strong]:font-semibold">
        {ai.greeting && (
          <div className="text-lg font-serif text-navy" dangerouslySetInnerHTML={{ __html: ai.greeting }} data-testid="expl-greeting" />
        )}
        <Section title="Your role as Grantor" html={ai.grantor_intro} testid="expl-grantor" />
        <Section title="Your trustees" html={ai.trustee_roles} testid="expl-trustees" />
        <Section title="Your beneficiaries" html={ai.beneficiaries} testid="expl-beneficiaries" />
        <Section title="What's going into your trust" html={ai.assets_plain} testid="expl-assets" />
        <Section title="What this type of trust means for you" html={ai.trust_type_meaning} testid="expl-trust-type" />
        <Section title="What happens next" html={ai.next_steps || ai.client_action} testid="expl-next-steps" />
        {ai.notarization && (
          <Section title="Notarization" html={ai.notarization.startsWith("<") ? ai.notarization : `<p>${ai.notarization}</p>`} testid="expl-notarization" />
        )}
      </div>
    );
  }

  // Legacy 5-field layout
  return (
    <div className="space-y-5 [&_p]:mb-2">
      <Section title="What this document is" html={legacyToHtml(ai.what_is)} testid="expl-legacy-what-is" />
      <Section title="What it does" html={legacyToHtml(ai.what_it_does)} testid="expl-legacy-what-it-does" />
      <Section title="Why it matters" html={legacyToHtml(ai.why_it_matters)} testid="expl-legacy-why" />
      <Section title="Notarization" html={legacyToHtml(ai.notarization)} testid="expl-legacy-notarization" />
      <Section title="What to do next" html={legacyToHtml(ai.client_action)} testid="expl-legacy-action" />
    </div>
  );
}

function Section({ title, html, testid }) {
  if (!html || !String(html).trim()) return null;
  return (
    <section data-testid={testid}>
      <h3 className="font-serif text-lg text-bronze mb-2">{title}</h3>
      <div dangerouslySetInnerHTML={{ __html: html }} />
    </section>
  );
}

function legacyToHtml(txt) {
  if (!txt) return "";
  if (String(txt).trim().startsWith("<")) return txt;
  return `<p>${String(txt).replace(/\n/g, "</p><p>")}</p>`;
}
