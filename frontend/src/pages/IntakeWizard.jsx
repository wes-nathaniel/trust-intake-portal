import React, { useEffect, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import Layout from "@/components/Layout";
import NiaChat from "@/components/NiaChat";
import api, { formatApiError } from "@/lib/api";
import StatusTracker from "@/components/StatusTracker";
import MessageThread from "@/components/MessageThread";
import { toast } from "sonner";
import { CheckCircle2, Circle, Lock, ArrowLeft, ArrowRight, AlertTriangle } from "lucide-react";
import GrantorStep from "@/pages/intake/GrantorStep";
import TrusteeStep from "@/pages/intake/TrusteeStep";
import SuccessorStep from "@/pages/intake/SuccessorStep";
import BeneficiaryStep from "@/pages/intake/BeneficiaryStep";
import AssetStep from "@/pages/intake/AssetStep";
import EINStep from "@/pages/intake/EINStep";
import DocumentsStep from "@/pages/intake/DocumentsStep";
import ReviewStep from "@/pages/intake/ReviewStep";
import { isStepComplete } from "@/lib/intakeProgress";

const STEP_DEFS = [
  { key: "grantors", label: "Grantors", Component: GrantorStep },
  { key: "trustee", label: "Trustee", Component: TrusteeStep },
  { key: "successor", label: "Successor Trustees", Component: SuccessorStep },
  { key: "beneficiaries", label: "Beneficiaries", Component: BeneficiaryStep },
  { key: "assets", label: "Assets", Component: AssetStep },
  { key: "ein", label: "EIN Workflow", Component: EINStep },
  { key: "documents", label: "Documents", Component: DocumentsStep },
  { key: "review", label: "Review", Component: ReviewStep },
];

// "review" intake path = client already has a trust → minimal flow
const REVIEW_PATH_STEP_KEYS = new Set(["documents", "review"]);

function stepsForCase(trustCase) {
  const path = trustCase?.intake_path || "new";
  if (path === "review") return STEP_DEFS.filter((s) => REVIEW_PATH_STEP_KEYS.has(s.key));
  return STEP_DEFS;
}

export default function IntakeWizard() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [trustCase, setTrustCase] = useState(null);
  const [stepIdx, setStepIdx] = useState(0);

  const reload = async () => {
    try {
      const { data } = await api.get(`/trust-cases/${caseId}`);
      setTrustCase(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      navigate("/portal");
    }
  };

  useEffect(() => { reload(); /* eslint-disable-next-line */ }, [caseId]);

  // Deep-link: ?step=<key> jumps to that step (if unlocked)
  useEffect(() => {
    if (!trustCase) return;
    const qsStep = searchParams.get("step");
    if (!qsStep) return;
    const steps = stepsForCase(trustCase);
    const idx = steps.findIndex((s) => s.key === qsStep);
    if (idx >= 0 && idx !== stepIdx) setStepIdx(idx);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trustCase?.id, searchParams]);

  if (!trustCase) return (
    <Layout><p className="text-[#64748B]">Loading…</p></Layout>
  );

  const steps = stepsForCase(trustCase);
  const safeStepIdx = Math.min(stepIdx, steps.length - 1);
  const StepComp = steps[safeStepIdx].Component;
  const stepKey = steps[safeStepIdx].key;

  const gotoStep = (i) => {
    // Free navigation: any step can be opened; final submit still requires all steps (see ReviewStep)
    if (i < 0 || i >= steps.length) return;
    setStepIdx(i);
    setSearchParams({ step: steps[i].key }, { replace: true });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <Layout>
      <div className="mb-8 flex items-center gap-3">
        <button onClick={() => navigate("/portal")} className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1" data-testid="back-to-portal-btn">
          <ArrowLeft className="h-4 w-4" /> Back to portal
        </button>
        <span className="text-[#CBD5E1]">·</span>
        <span className="text-sm text-[#64748B]">
          {trustCase.trust_type === "joint" ? "Joint Trust" : "Single Trust"} · Case #{trustCase.id.slice(0, 8).toUpperCase()}
        </span>
      </div>

      <div className="mb-6">
        <StatusTracker status={trustCase.status} />
      </div>

      {(trustCase.pending_items || []).length > 0 && stepKey !== "documents" && (
        <div className="mb-6 bg-amber-50 border border-amber-300 rounded-xl p-4 flex flex-col sm:flex-row items-start gap-3" data-testid="wizard-pending-banner">
          <AlertTriangle className="h-5 w-5 text-amber-800 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-amber-900">Action required — {(trustCase.pending_items || []).length} document(s) still needed</p>
            <ul className="text-sm text-amber-900/90 mt-1 space-y-0.5">
              {(trustCase.pending_items || []).map((p, i) => (
                <li key={i}>• <b>{p.label}</b>{p.note && <span className="text-amber-800/80"> — {p.note}</span>}</li>
              ))}
            </ul>
          </div>
          <button onClick={() => gotoStep(steps.findIndex((s) => s.key === "documents"))}
            className="btn-primary text-sm shrink-0 w-full sm:w-auto" data-testid="wizard-jump-to-documents">
            Go to Documents
          </button>
        </div>
      )}

      <div className="grid lg:grid-cols-[280px_1fr] gap-4 lg:gap-8">
        {/* Step nav — vertical on lg+, horizontal scrollable strip on mobile */}
        <aside className="min-w-0 lg:space-y-1 lg:block" data-testid="intake-step-nav">
          <div className="lg:hidden -mx-3 px-3 mb-2 overflow-x-auto no-scrollbar">
            <div className="flex gap-2 min-w-max pb-2">
              {steps.map((s, i) => {
                const done = s.key === "review" ? false : isStepComplete(s.key, trustCase);
                const locked = false;
                const active = i === safeStepIdx;
                return (
                  <button key={s.key} onClick={() => gotoStep(i)} disabled={locked}
                    className={`shrink-0 px-3 py-2 rounded-md flex items-center gap-2 text-sm transition-colors min-h-[44px] ${
                      active ? "bg-navy text-white" : locked ? "text-[#CBD5E1] cursor-not-allowed bg-white border border-[#E2E0DA]" : "bg-white border border-[#E2E0DA] text-navy"
                    }`}
                    data-testid={`step-nav-mobile-${s.key}`}>
                    {locked ? <Lock className="h-4 w-4" /> : done ? <CheckCircle2 className="h-4 w-4 text-bronze" /> : <Circle className="h-4 w-4" />}
                    <span className="font-medium whitespace-nowrap">{i + 1}. {s.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="hidden lg:block lg:space-y-1">
            {steps.map((s, i) => {
              const done = s.key === "review" ? false : isStepComplete(s.key, trustCase);
              const locked = false;
              const active = i === safeStepIdx;
              return (
                <button key={s.key} onClick={() => gotoStep(i)} disabled={locked}
                  className={`w-full text-left px-4 py-3 rounded-md flex items-center gap-3 transition-colors ${
                    active ? "bg-navy text-white" : locked ? "text-[#CBD5E1] cursor-not-allowed" : "hover:bg-sand-200 text-navy"
                  }`}
                  data-testid={`step-nav-${s.key}`}>
                  {locked ? <Lock className="h-4 w-4" /> : done ? <CheckCircle2 className="h-4 w-4 text-bronze" /> : <Circle className="h-4 w-4" />}
                  <span className="text-sm font-medium">{s.label}</span>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Right content */}
        <div className="min-w-0 space-y-6 sm:space-y-8">
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6 lg:p-10">
            <StepComp trustCase={trustCase} caseId={caseId} reload={reload} />
          </div>

          <div className="flex items-center justify-between gap-3 pr-0 sm:pr-16 pb-16 sm:pb-0">
            <button onClick={() => gotoStep(safeStepIdx - 1)} disabled={safeStepIdx === 0}
              className="btn-secondary flex-1 sm:flex-none" data-testid="wizard-prev-btn">
              <ArrowLeft className="h-4 w-4 inline mr-1" /> Previous
            </button>
            {safeStepIdx < steps.length - 1 ? (
              <button onClick={() => gotoStep(safeStepIdx + 1)}
                className="btn-primary flex-1 sm:flex-none" data-testid="wizard-next-btn">
                Next <ArrowRight className="h-4 w-4 inline ml-1" />
              </button>
            ) : (
              <button onClick={() => navigate("/portal")} className="btn-primary flex-1 sm:flex-none" data-testid="wizard-done-btn">
                Back to Portal
              </button>
            )}
          </div>
        </div>
      </div>
      <NiaChat caseId={caseId} clientFirstName={(trustCase?.grantors?.[0]?.full_legal_name || "").split(" ")[0] || null} />
    </Layout>
  );
}
