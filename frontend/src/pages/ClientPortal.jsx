import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { ArrowRight, ShieldCheck, Download, FilePen, AlertTriangle, Plus, Sparkles } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import StatusTracker from "@/components/StatusTracker";
import { toast } from "sonner";

export default function ClientPortal() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const { data } = await api.get("/trust-cases/mine");
      setCases(data);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  return (
    <Layout>
      <div className="mb-10">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Welcome{user?.name ? `, ${user.name.split(" ")[0]}` : ""}</p>
        <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Your Trust Portal</h1>
        <p className="text-[#64748B] mt-2 text-lg max-w-2xl">
          Complete your trust intake in a guided, section-by-section flow. All fields marked required must be finished to continue.
        </p>
      </div>

      {loading ? (
        <p className="text-[#64748B]">Loading…</p>
      ) : cases.length === 0 ? (
        <div>
          <h2 className="font-serif text-2xl text-navy mb-3">Begin a new trust intake</h2>
          <p className="text-[#64748B] mb-6 max-w-2xl">
            Choose the trust type and give it a formal name in the next step. Your trust name will appear on the
            EIN filing, the trust documents, and the final PDF.
          </p>
          <button
            onClick={() => navigate("/portal/new")}
            className="btn-primary inline-flex items-center"
            data-testid="portal-start-new-btn">
            Start a new trust <ArrowRight className="h-4 w-4 ml-1" />
          </button>
        </div>
      ) : (
        <div className="space-y-8">
          {cases.map((c) => (
            <div key={c.id} className="space-y-4" data-testid={`case-row-${c.id}`}>
              {(c.pending_items || []).length > 0 && (
                <div className="bg-amber-50 border border-amber-300 rounded-xl p-5" data-testid={`pending-banner-${c.id}`}>
                  <div className="flex items-start gap-3">
                    <AlertTriangle className="h-5 w-5 text-amber-800 mt-0.5 shrink-0" />
                    <div className="flex-1">
                      <p className="font-semibold text-amber-900">Action required — {(c.pending_items || []).length} item(s) still needed</p>
                      <ul className="mt-2 space-y-1 text-sm text-amber-900/90">
                        {(c.pending_items || []).map((p, i) => (
                          <li key={i} className="flex items-start gap-2">
                            <span className="mt-1 h-1.5 w-1.5 rounded-full bg-amber-700 shrink-0"></span>
                            <span className="flex-1">
                              <b>{p.label}</b>
                              {p.note && <span className="text-amber-800/80"> — {p.note}</span>}
                            </span>
                          </li>
                        ))}
                      </ul>
                      <div className="mt-3">
                        <Link to={`/intake/${c.id}?step=documents`} className="btn-primary text-sm inline-flex items-center" data-testid={`pending-upload-${c.id}`}>
                          Upload now <ArrowRight className="h-4 w-4 ml-1" />
                        </Link>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {c.payment?.invoice_id && c.payment.status !== "paid" && c.payment.status !== "paid_manual" && c.payment.public_url && (
                <div className="bg-bronze/10 border border-bronze/40 rounded-xl p-5 flex flex-col sm:flex-row items-start sm:items-center gap-3 justify-between" data-testid={`payment-banner-${c.id}`}>
                  <div>
                    <p className="font-semibold text-navy">
                      {c.payment.status === "ach_pending" ? "ACH payment pending — waiting for your bank to clear." :
                       "Invoice ready — please complete payment to unlock your final trust."}
                    </p>
                    <p className="text-sm text-[#334155]">
                      {c.payment.amount_cents ? `Amount: $${(c.payment.amount_cents/100).toLocaleString(undefined, {minimumFractionDigits: 2})}` : ""}
                      {c.payment.due_date ? ` · Due ${c.payment.due_date}` : ""}
                    </p>
                  </div>
                  {c.payment.status !== "ach_pending" && (
                    <a href={c.payment.public_url} target="_blank" rel="noreferrer" className="btn-accent text-sm shrink-0" data-testid={`pay-btn-${c.id}`}>
                      Pay securely with Square
                    </a>
                  )}
                </div>
              )}
              <StatusTracker status={c.status} />

              {/* Free Credit Review — visible only after admin manually releases */}
              {c.credit_repair_released && (
                <div className="rounded-xl border-2 border-bronze/40 bg-bronze/5 p-5 sm:p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4" data-testid={`credit-repair-block-${c.id}`}>
                  <div className="h-12 w-12 rounded-full bg-bronze/15 flex items-center justify-center shrink-0">
                    <Sparkles className="h-6 w-6 text-bronze" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-serif text-xl text-navy mb-1">Your complimentary credit review is ready</p>
                    <p className="text-sm text-[#334155]">
                      Click the button to launch your free credit review. The link is yours alone — it lives behind your secure portal login and was never sent by email or text.
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      try {
                        const { data } = await api.get(`/trust-cases/${c.id}/credit-repair-link`);
                        window.open(data.url, "_blank", "noopener,noreferrer");
                      } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
                    }}
                    className="btn-primary text-sm w-full sm:w-auto shrink-0"
                    data-testid={`start-credit-review-btn-${c.id}`}>
                    Start Your Free Credit Review <ArrowRight className="h-4 w-4 inline ml-1" />
                  </button>
                </div>
              )}

              <div className="bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-4 w-4 text-bronze shrink-0" />
                    <span className="text-xs uppercase tracking-wide text-[#64748B] font-semibold truncate">
                      {c.trust_type === "joint" ? "Joint Trust" : "Single Trust"} · Started {new Date(c.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <h3 className="font-serif text-xl text-navy break-words">{c.trust_name || `Trust Case #${c.id.slice(0, 8).toUpperCase()}`}</h3>
                  {c.trust_name && <p className="text-xs text-[#94A3B8] mt-0.5">Case #{c.id.slice(0, 8).toUpperCase()}</p>}
                  <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-sm text-[#64748B]">
                    <span>{c.grantors?.length || 0} grantor(s)</span>
                    <span className="hidden sm:inline">·</span>
                    <span>{c.beneficiaries?.length || 0} beneficiary(ies)</span>
                    <span className="hidden sm:inline">·</span>
                    <span>{c.assets?.length || 0} asset(s)</span>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:flex lg:items-center gap-2 lg:flex-nowrap">
                  {c.trust_draft && !c.trust_unlocked && (
                    <Link to={`/portal/trust-preview/${c.id}`} className="btn-primary text-sm w-full lg:w-auto" data-testid={`open-trust-preview-${c.id}`}>
                      <FilePen className="h-4 w-4 inline mr-1" /> Review Draft Trust
                    </Link>
                  )}
                  {c.trust_unlocked && (
                    <Link to={`/portal/trust-final/${c.id}`} className="btn-accent text-sm w-full lg:w-auto" data-testid={`open-trust-final-${c.id}`}>
                      <FilePen className="h-4 w-4 inline mr-1" /> Final Trust
                    </Link>
                  )}
                  <button
                    onClick={async () => {
                      try {
                        const res = await api.get(`/trust-cases/${c.id}/export.pdf`, { responseType: "blob" });
                        const url = URL.createObjectURL(res.data);
                        const a = document.createElement("a");
                        a.href = url; a.download = `trust-intake-${c.id.slice(0,8)}.pdf`; a.click();
                        URL.revokeObjectURL(url);
                      } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
                    }}
                    className="btn-secondary text-sm w-full lg:w-auto"
                    data-testid={`download-pdf-${c.id}`}>
                    <Download className="h-4 w-4 inline mr-1" /> PDF
                  </button>
                  <Link to={`/intake/${c.id}`} className="btn-accent text-sm w-full lg:w-auto sm:col-span-2 lg:col-span-1" data-testid={`continue-case-${c.id}`}>
                    {c.status === "Completed" ? "View" : "Continue Intake"}
                  </Link>
                </div>
              </div>
            </div>
          ))}
          <button
            onClick={() => cases[0] && navigate("/portal/new")}
            className="btn-secondary"
            data-testid="new-case-btn">
            <Plus className="h-4 w-4 inline mr-1" /> Start another trust
          </button>
        </div>
      )}
    </Layout>
  );
}
