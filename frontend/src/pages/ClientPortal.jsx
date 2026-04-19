import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { Users, User, Plus, ArrowRight, FileText, ShieldCheck, Download, FilePen, AlertTriangle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import StatusTracker from "@/components/StatusTracker";
import { toast } from "sonner";

export default function ClientPortal() {
  const { user, branding } = useAuth();
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

  const createCase = async (trust_type) => {
    try {
      const { data } = await api.post("/trust-cases", { trust_type });
      navigate(`/intake/${data.id}`);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

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
          <h2 className="font-serif text-2xl text-navy mb-6">Begin a new trust intake</h2>
          <div className="grid md:grid-cols-2 gap-6" data-testid="trust-type-selector">
            <button
              onClick={() => createCase("single")}
              className="group bg-white border border-[#E2E0DA] rounded-xl p-8 text-left hover:border-bronze hover:shadow-lg transition-all"
              data-testid="trust-type-single">
              <div className="h-12 w-12 rounded-full bg-sand-200 flex items-center justify-center mb-5 group-hover:bg-bronze/15">
                <User className="h-6 w-6 text-navy" />
              </div>
              <h3 className="font-serif text-2xl text-navy mb-2">Single Trust</h3>
              <p className="text-[#64748B] mb-4">An individual trust with a single grantor — for unmarried individuals or sole grantors.</p>
              <span className="inline-flex items-center text-bronze font-medium">
                Start intake <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
              </span>
            </button>
            <button
              onClick={() => createCase("joint")}
              className="group bg-white border border-[#E2E0DA] rounded-xl p-8 text-left hover:border-bronze hover:shadow-lg transition-all"
              data-testid="trust-type-joint">
              <div className="h-12 w-12 rounded-full bg-sand-200 flex items-center justify-center mb-5 group-hover:bg-bronze/15">
                <Users className="h-6 w-6 text-navy" />
              </div>
              <h3 className="font-serif text-2xl text-navy mb-2">Joint Trust</h3>
              <p className="text-[#64748B] mb-4">A trust with two grantors — for married couples or partners sharing estate planning.</p>
              <span className="inline-flex items-center text-bronze font-medium">
                Start intake <ArrowRight className="h-4 w-4 ml-1 group-hover:translate-x-1 transition-transform" />
              </span>
            </button>
          </div>
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
              <StatusTracker status={c.status} />
              <div className="bg-white border border-[#E2E0DA] rounded-xl p-6 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <ShieldCheck className="h-4 w-4 text-bronze" />
                    <span className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">
                      {c.trust_type === "joint" ? "Joint Trust" : "Single Trust"} · Started {new Date(c.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  <h3 className="font-serif text-xl text-navy">Trust Case #{c.id.slice(0, 8).toUpperCase()}</h3>
                  <div className="flex gap-4 mt-2 text-sm text-[#64748B]">
                    <span>{c.grantors?.length || 0} grantor(s)</span>
                    <span>·</span>
                    <span>{c.beneficiaries?.length || 0} beneficiary(ies)</span>
                    <span>·</span>
                    <span>{c.assets?.length || 0} asset(s)</span>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-wrap">
                  {c.esign?.status === "signed" && (
                    <button
                      onClick={async () => {
                        try {
                          const res = await api.get(`/trust-cases/${c.id}/download-signed`, { responseType: "blob" });
                          const url = URL.createObjectURL(res.data);
                          const a = document.createElement("a");
                          a.href = url; a.download = `signed-trust-${c.id.slice(0,8)}.pdf`; a.click();
                          URL.revokeObjectURL(url);
                        } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
                      }}
                      className="btn-accent text-sm"
                      data-testid={`download-signed-${c.id}`}>
                      <FilePen className="h-4 w-4 inline mr-1" /> Signed Trust
                    </button>
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
                    className="btn-secondary text-sm"
                    data-testid={`download-pdf-${c.id}`}>
                    <Download className="h-4 w-4 inline mr-1" /> PDF
                  </button>
                  <Link to={`/intake/${c.id}`} className="btn-accent" data-testid={`continue-case-${c.id}`}>
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
