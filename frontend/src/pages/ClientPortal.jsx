import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import NiaChat from "@/components/NiaChat";
import api, { formatApiError } from "@/lib/api";
import { ArrowRight, ShieldCheck, Download, FilePen, AlertTriangle, Plus, KeyRound, Package } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import StatusTracker from "@/components/StatusTracker";
import TourCard from "@/components/TourCard";
import AdminDocumentCard from "@/components/AdminDocumentCard";
import ClientDocumentsPanel from "@/components/ClientDocumentsPanel";
import PaymentCard from "@/components/PaymentCard";
import { toast } from "sonner";

export default function ClientPortal() {
  const { user, markTourSeen } = useAuth();
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
      {user && user.has_seen_tour === false && (
        <TourCard onDismissed={markTourSeen} />
      )}
      <div className="mb-10">
        {user?.is_first_login ? (
          <>
            <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2" data-testid="welcome-first-login">Welcome to Iron Gate Trust Services.</p>
            <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Your Trust Portal</h1>
            <p className="text-[#64748B] mt-2 text-lg max-w-2xl">
              We&rsquo;re glad you&rsquo;re here. Complete your trust intake in a guided, section-by-section flow. All fields marked required must be finished to continue.
            </p>
          </>
        ) : (
          <>
            <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2" data-testid="welcome-returning">
              Welcome Back{user?.first_name ? `, ${user.first_name}` : (user?.name ? `, ${user.name.split(" ")[0]}` : "")}
            </p>
            <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Your Trust Portal</h1>
            <p className="text-[#64748B] mt-2 text-lg max-w-2xl">
              Complete your trust intake in a guided, section-by-section flow. All fields marked required must be finished to continue.
            </p>
          </>
        )}
        <Link to="/account#password" className="mt-3 inline-flex items-center gap-1.5 text-sm text-bronze hover:text-navy underline underline-offset-4"
          data-testid="portal-change-password-link">
          <KeyRound className="h-4 w-4" /> Change password
        </Link>
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

              {/* Payment card — shown when admin sends a payment link or Zelle is set up */}
              {(c.payment?.stripe_client_secret || c.payment?.link_sent_at || c.payment?.status === "received_zelle") && (
                <div className="bg-white border border-[#E2E0DA] rounded-xl p-5" data-testid={`payment-card-wrapper-${c.id}`}>
                  <PaymentCard caseId={c.id} />
                </div>
              )}
              <StatusTracker status={c.status} />

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
                    <Link to={`/intake/${c.id}?step=assets`} className="text-bronze underline underline-offset-2 hover:text-navy" data-testid={`asset-count-link-${c.id}`}>
                      {c.assets?.length || 0} asset(s)
                    </Link>
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
                  {/* Add / View Assets — always visible on every case at every status */}
                  <Link
                    to={`/intake/${c.id}?step=assets`}
                    className="btn-accent text-sm w-full lg:w-auto sm:col-span-2 lg:col-span-1 inline-flex items-center justify-center gap-1"
                    data-testid={`add-view-assets-${c.id}`}>
                    <Package className="h-4 w-4" /> Add / View Assets
                  </Link>
                  {/* Continue Intake — only for early-stage cases still filling out the form */}
                  {(c.status === "Intake Started" || c.status === "Intake In Progress") && (
                    <Link to={`/intake/${c.id}`} className="btn-secondary text-sm w-full lg:w-auto" data-testid={`continue-case-${c.id}`}>
                      Continue Intake
                    </Link>
                  )}
                </div>
              </div>

              {/* Client's own uploaded documents — download + delete */}
              <ClientDocumentsPanel
                caseId={c.id}
                docs={c.documents || []}
                onChanged={load}
              />

              {/* AI-explained documents from the trust team (Operating Agreement, EIN letter, etc.) */}
              {(c.admin_documents || []).length > 0 && (
                <div className="bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6" data-testid={`client-admin-docs-${c.id}`}>
                  <p className="text-[10px] uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Documents from your team</p>
                  <h3 className="font-serif text-xl text-navy mb-1">Recent uploads</h3>
                  <p className="text-xs text-[#64748B] mb-4">Each document includes a plain-English explanation prepared by our AI assistant. Download links live in your secure portal.</p>
                  <div className="space-y-4">
                    {(c.admin_documents || []).map((d) => (
                      <AdminDocumentCard
                        key={d.id}
                        doc={d}
                        caseId={c.id}
                        apiBase={api.defaults.baseURL || ""}
                      />
                    ))}
                  </div>
                </div>
              )}
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
      <NiaChat clientFirstName={user?.first_name || (user?.name || "").split(" ")[0]} />
    </Layout>
  );
}
