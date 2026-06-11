import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import TrustViewerTwoPanel from "@/components/TrustViewerTwoPanel";
import { ArrowLeft, Eye } from "lucide-react";

/**
 * Admin-only preview of the client-facing two-panel Trust Viewer.
 * Uses the exact same component the client sees so admins can sanity-check
 * the saved trust_sections JSON (scroll sync, watermark, security blocking
 * all behave identically).
 */
export default function AdminTrustViewerPreview() {
  const { caseId } = useParams();
  const [c, setC] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get(`/admin/trust-cases/${caseId}`);
        if (!cancelled) setC(data);
      } catch (e) {
        const msg = formatApiError(e.response?.data?.detail) || "Could not load case.";
        if (!cancelled) setErr(msg);
        toast.error(msg);
      }
    })();
    return () => { cancelled = true; };
  }, [caseId]);

  if (err) {
    return (
      <div className="min-h-screen p-6 bg-sand">
        <p className="text-red-700">{err}</p>
        <Link to={`/admin/cases/${caseId}`} className="text-navy underline">Back to case</Link>
      </div>
    );
  }

  if (!c) {
    return <div className="min-h-screen p-6 bg-sand text-[#64748B]">Loading client preview…</div>;
  }

  const sections = c.trust_sections || [];

  return (
    <div className="min-h-screen bg-sand">
      {/* Admin-only banner (visually distinct so admin never confuses this with client view) */}
      <div className="bg-amber-100 border-b-2 border-amber-300 px-4 py-2 flex items-center justify-between text-sm gap-3 flex-wrap" data-testid="admin-preview-banner">
        <div className="flex items-center gap-2 text-amber-900">
          <Eye className="h-4 w-4" />
          <span><b>Admin preview</b> — this is exactly what the client sees. Scroll-sync, watermark, and print/copy blocking are all live.</span>
        </div>
        <Link to={`/admin/cases/${caseId}`} className="text-amber-900 font-semibold hover:text-amber-700 inline-flex items-center gap-1" data-testid="admin-preview-back">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to case
        </Link>
      </div>

      <div className="p-3 sm:p-6">
        {sections.length === 0 ? (
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-8 text-center text-[#64748B]" data-testid="admin-preview-empty">
            No trust sections saved yet. Add at least one article on the case detail page, save, then preview again.
          </div>
        ) : (
          <TrustViewerTwoPanel
            sections={sections}
            caseShortId={(c.id || "").slice(0, 8).toUpperCase()}
            clientName={c.client_name || c.client_email}
            trustName={c.trust_name}
          />
        )}
      </div>
    </div>
  );
}
