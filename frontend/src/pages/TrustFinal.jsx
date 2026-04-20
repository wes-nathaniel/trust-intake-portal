import React, { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { ChevronLeft, Download, Printer, Stamp, CheckCircle2, AlertTriangle } from "lucide-react";

export default function TrustFinal() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [meta, setMeta] = useState(null);
  const [trustCase, setTrustCase] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [{ data: m }, { data: c }] = await Promise.all([
        api.get(`/trust-cases/${caseId}/trust-preview/meta`),
        api.get(`/trust-cases/${caseId}`),
      ]);
      setMeta(m);
      setTrustCase(c);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not load final trust.");
      navigate("/portal");
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [caseId]);

  const downloadFinal = async () => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/trust-final`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      const safe = (meta?.trust_name || `trust-${caseId.slice(0,8)}`).replace(/[^\w\s.-]/g, "_");
      a.href = url; a.download = `${safe}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const openPrint = async () => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/trust-final`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const w = window.open(url, "_blank");
      if (w) { w.onload = () => { try { w.print(); } catch (_) {} }; }
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  if (loading || !meta) return <Layout><p className="text-[#64748B]">Loading…</p></Layout>;

  if (!meta.unlocked) {
    return (
      <Layout>
        <Link to="/portal" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-4">
          <ChevronLeft className="h-4 w-4" /> Back to portal
        </Link>
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-6 flex items-start gap-3" data-testid="trust-final-locked">
          <AlertTriangle className="h-5 w-5 text-amber-800 mt-0.5" />
          <div>
            <p className="font-semibold text-amber-900">Your final trust is not unlocked yet.</p>
            <p className="text-sm text-amber-900/90">Your final trust will be available here after payment is received and cleared.</p>
            <div className="mt-3">
              <Link to={`/portal/trust-preview/${caseId}`} className="btn-accent text-sm">Open draft preview</Link>
            </div>
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <Link to="/portal" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-4" data-testid="final-back">
        <ChevronLeft className="h-4 w-4" /> Back to portal
      </Link>

      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Final Trust · Unlocked</p>
        <h1 className="font-serif text-3xl sm:text-4xl text-navy">{meta.trust_name || "Your Trust"}</h1>
        <p className="text-[#64748B] text-sm mt-1">Case #{caseId.slice(0, 8).toUpperCase()}</p>
      </div>

      <div className="bg-green-50 border border-green-200 rounded-xl p-5 flex items-start gap-3 mb-6" data-testid="final-unlocked-banner">
        <CheckCircle2 className="h-5 w-5 text-green-700 mt-0.5" />
        <div>
          <p className="font-semibold text-green-900">Payment received — your final trust is unlocked.</p>
          <p className="text-sm text-green-900/90">Download, print, and take to a notary to complete your trust.</p>
        </div>
      </div>

      <div className="bg-white border border-[#E2E0DA] rounded-xl p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4 justify-between">
        <div>
          <p className="font-serif text-xl text-navy">Final trust document</p>
          <p className="text-sm text-[#64748B]">No watermark · Ready to print and sign</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button onClick={downloadFinal} className="btn-accent" data-testid="final-download-btn">
            <Download className="h-4 w-4 inline mr-1" /> Download final PDF
          </button>
          <button onClick={openPrint} className="btn-secondary" data-testid="final-print-btn">
            <Printer className="h-4 w-4 inline mr-1" /> Open & print
          </button>
        </div>
      </div>

      <div className="mt-8 bg-navy text-white rounded-xl p-6 sm:p-8" data-testid="final-notarization-block">
        <div className="flex items-start gap-3">
          <Stamp className="h-6 w-6 text-bronze shrink-0 mt-1" />
          <div>
            <p className="font-serif text-2xl mb-2">Notarization instructions</p>
            <ul className="text-white/90 space-y-1 text-sm leading-relaxed list-disc pl-5">
              <li>Print the full trust document.</li>
              <li>Bring a valid government-issued photo ID with you.</li>
              <li>Sign the trust <b>only in the presence of a notary public</b>.</li>
              <li>Retain the original notarized trust with your important records.</li>
              <li>If you placed a business under your trust, file a <b>Change of Ownership</b> with your Secretary of State.</li>
            </ul>
          </div>
        </div>
      </div>

      <p className="mt-8 text-center text-xs text-[#94A3B8]">
        Prepared by <b>Iron Gate Consulting</b> · Reviewed through military legal benefits
      </p>
    </Layout>
  );
}
