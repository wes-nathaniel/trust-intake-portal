import React from "react";
import { SectionHeader } from "./_shared";
import { CheckCircle2, ShieldCheck, Download } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const LINE = ({ l, v }) => (
  <div className="flex justify-between border-b border-dashed border-[#E2E0DA] py-1.5 text-sm">
    <span className="text-[#64748B]">{l}</span>
    <span className="text-navy font-medium text-right">{v || "—"}</span>
  </div>
);

export default function ReviewStep({ trustCase, caseId }) {
  const g = trustCase.grantors || [];
  const t = trustCase.trustees?.[0];
  const sct = trustCase.successor_trustees || [];
  const b = trustCase.beneficiaries || [];
  const a = trustCase.assets || [];
  const docs = (trustCase.documents || []).filter((d) => !d.is_deleted);

  return (
    <div>
      <SectionHeader num={8} total={8} title="Review & Submit"
        subtitle="Review all the information you've provided. Your case is now with our team." />

      <div className="bg-bronze/10 border border-bronze/30 rounded-lg p-4 mb-8 flex flex-col sm:flex-row items-start sm:items-center gap-3 justify-between" data-testid="review-complete-banner">
        <div className="flex items-center gap-3">
          <ShieldCheck className="h-5 w-5 text-bronze" />
          <div>
            <p className="font-semibold text-navy">All required sections are complete.</p>
            <p className="text-sm text-[#64748B]">Our team will contact you shortly. You can continue to upload documents and message us anytime.</p>
          </div>
        </div>
        <button
          onClick={async () => {
            try {
              const res = await api.get(`/trust-cases/${caseId || trustCase.id}/export.pdf`, { responseType: "blob" });
              const url = URL.createObjectURL(res.data);
              const a = document.createElement("a");
              a.href = url; a.download = `trust-intake-${(caseId || trustCase.id).slice(0,8)}.pdf`; a.click();
              URL.revokeObjectURL(url);
            } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
          }}
          className="btn-accent shrink-0"
          data-testid="review-download-pdf-btn">
          <Download className="h-4 w-4 inline mr-1" /> Download Summary PDF
        </button>
      </div>

      <div className="space-y-6" data-testid="review-summary">
        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Grantors ({g.length})</h3>
          {g.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Grantor {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="DOB" v={x.date_of_birth} />
              <LINE l="Email" v={x.email} />
              <LINE l="Phone" v={x.phone} />
              <LINE l="Marital" v={x.marital_status} />
              <LINE l="Citizenship" v={x.citizenship} />
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Trustee</h3>
          <div className="bg-sand-200/40 rounded-md p-4">
            <LINE l="Name" v={t?.full_legal_name} />
            <LINE l="Relationship" v={t?.relationship} />
            <LINE l="Email" v={t?.email} />
            <LINE l="Phone" v={t?.phone} />
          </div>
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Successor Trustees ({sct.length})</h3>
          {sct.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Successor {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="Relationship" v={x.relationship} />
              <LINE l="Email" v={x.email} />
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Beneficiaries ({b.length})</h3>
          {b.map((x, i) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <p className="text-xs uppercase text-bronze font-semibold">Beneficiary {i + 1}</p>
              <LINE l="Name" v={x.full_legal_name} />
              <LINE l="Relationship" v={x.relationship} />
              <LINE l="Share" v={`${x.percentage}%`} />
              {x.contingent_name && <LINE l="Contingent" v={x.contingent_name} />}
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Assets ({a.length})</h3>
          {a.map((x) => (
            <div key={x.id} className="bg-sand-200/40 rounded-md p-4 mb-2">
              <LINE l="Type" v={x.asset_type} />
              <LINE l="Institution/Property" v={x.institution_name || x.property_address} />
              {x.estimated_value && <LINE l="Est. value" v={`$${Number(x.estimated_value).toLocaleString()}`} />}
            </div>
          ))}
        </section>

        <section>
          <h3 className="font-serif text-2xl text-navy mb-3">Documents ({docs.length})</h3>
          <ul className="bg-sand-200/40 rounded-md p-4 space-y-1 text-sm">
            {docs.map((d) => (
              <li key={d.id} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-green-600" /> {d.filename} <span className="text-[#64748B]">({d.doc_type})</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
