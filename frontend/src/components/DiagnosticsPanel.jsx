import React, { useState, useEffect, useCallback } from "react";
import api, { formatApiError } from "@/lib/api";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw, Activity, ChevronDown } from "lucide-react";
import { toast } from "sonner";

const Row = ({ label, ok, value, warn, hint }) => (
  <div className="flex items-start justify-between py-2 border-b border-[#F1EFEA] last:border-0" data-testid={`diag-row-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
    <div className="min-w-0 pr-3">
      <p className="text-sm text-navy">{label}</p>
      {hint && <p className="text-xs text-[#64748B] mt-0.5">{hint}</p>}
    </div>
    <div className="flex items-center gap-2 shrink-0">
      {value && <span className="font-mono text-xs text-[#64748B] truncate max-w-[180px]">{value}</span>}
      {warn ? (
        <AlertTriangle className="h-4 w-4 text-amber-600" />
      ) : ok ? (
        <CheckCircle2 className="h-4 w-4 text-green-600" />
      ) : (
        <XCircle className="h-4 w-4 text-red-600" />
      )}
    </div>
  </div>
);

export default function DiagnosticsPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: d } = await api.get("/admin/diagnostics");
      setData(d);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (!data) {
    return (
      <div className="bg-white border border-[#E2E0DA] rounded-xl p-5 mb-10" data-testid="diagnostics-panel-loading">
        <div className="flex items-center gap-2 text-[#64748B]"><Activity className="h-4 w-4 animate-pulse" /> Loading production diagnostics…</div>
      </div>
    );
  }

  const allReady = data.all_ready;
  const sq = data.square || {};
  const tw = data.twilio || {};

  return (
    <div
      className={`rounded-xl border-2 mb-10 overflow-hidden transition-colors ${
        allReady ? "bg-green-50 border-green-300" : "bg-amber-50 border-amber-300"
      }`}
      data-testid="diagnostics-panel">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left"
        data-testid="diagnostics-toggle-btn">
        <div className="flex items-center gap-2 min-w-0">
          {allReady
            ? <CheckCircle2 className="h-5 w-5 text-green-700 shrink-0" />
            : <AlertTriangle className="h-5 w-5 text-amber-700 shrink-0" />}
          <p className="font-serif text-lg text-navy truncate">
            {allReady ? "Production integrations: all systems go" : "Production integrations: needs attention"}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); load(); }}
            className="text-xs text-navy hover:text-bronze inline-flex items-center gap-1"
            data-testid="diagnostics-refresh-btn"
            title="Re-check">
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> {loading ? "checking…" : "re-check"}
          </button>
          <ChevronDown className={`h-4 w-4 text-navy transition-transform ${open ? "rotate-180" : ""}`} />
        </div>
      </button>

      {open && (
        <div className="px-5 pb-5">
          <div className="bg-white rounded-lg border border-[#E2E0DA] p-4 mb-3">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Square (Payments)</p>
            <Row
              label="Square enabled"
              ok={sq.ready}
              value={sq.environment}
              hint={sq.error ? `Error: ${sq.error}` : undefined}
            />
            <Row
              label="Location resolved"
              ok={!!sq.location_resolved}
              value={sq.location_resolved}
              warn={sq.location_id_typo}
              hint={sq.location_id_typo ? "Typo in SQUARE_LOCATION_ID — running on auto-resolved fallback. Fix env var." : undefined}
            />
            <Row
              label="Webhook signature key set"
              ok={sq.webhook_signed}
              hint={!sq.webhook_signed ? "Set SQUARE_WEBHOOK_SIGNATURE_KEY to enable signed webhooks." : undefined}
            />
          </div>

          <div className="bg-white rounded-lg border border-[#E2E0DA] p-4 mb-3">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Twilio (SMS)</p>
            <Row
              label="Twilio configured"
              ok={tw.ready}
              hint={!tw.ready ? "Set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER." : undefined}
            />
            <Row
              label="Admin phone number set"
              ok={tw.admin_phone_set}
              hint={!tw.admin_phone_set ? "Set ADMIN_PHONE_NUMBER to receive case-event SMS." : undefined}
            />
          </div>

          <div className="bg-white rounded-lg border border-[#E2E0DA] p-4 mb-3">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Email & AI</p>
            <Row label="Resend (email)" ok={data.email?.resend_ready} hint={!data.email?.resend_ready ? "Set RESEND_API_KEY." : undefined} />
            <Row label="Emergent LLM (AI assistant)" ok={data.ai?.emergent_llm_ready} hint={!data.ai?.emergent_llm_ready ? "Set EMERGENT_LLM_KEY." : undefined} />
          </div>

          <div className="bg-white rounded-lg border border-[#E2E0DA] p-4">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Auth</p>
            <Row label="JWT secret set" ok={data.auth?.jwt_secret_set} />
            <Row label="Admin user(s) seeded" ok={(data.auth?.admin_count ?? 0) >= 1} value={String(data.auth?.admin_count ?? 0)} />
            <Row label="Frontend URL" ok={!!data.frontend_url} value={data.frontend_url} />
          </div>

          {!allReady && (
            <p className="text-xs text-[#64748B] mt-3">
              After setting missing env-vars in your Emergent Deployment Settings panel, redeploy and click <b>re-check</b>.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
