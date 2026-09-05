import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import { DollarSign, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

const fmt = (c) => `$${((c || 0) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const STATUS_LABEL = {
  pending_approval: "Pending approval",
  approved: "Approved",
  denied: "Denied",
  paid: "Paid",
};

export default function AdminCommissionsPage() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  const load = async () => {
    setLoading(true);
    try {
      const q = filter === "all" ? "" : `?status=${filter}`;
      const { data } = await api.get(`/admin/commissions${q}`);
      setRows(data.commissions || []);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [filter]);

  const approve = async (c) => {
    if (!window.confirm(`Approve ${fmt(c.rep_cents)} to ${c.rep_name}${c.manager_id ? ` + ${fmt(c.manager_cents)} override to ${c.manager_name}` : ""}?`)) return;
    try {
      await api.post(`/admin/commissions/${c.id}/approve`, {});
      toast.success("Commission approved");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const deny = async (c) => {
    if (!window.confirm(`Deny commission for ${c.rep_name}? This voids the payout.`)) return;
    try {
      await api.post(`/admin/commissions/${c.id}/deny`, {});
      toast.success("Commission denied");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Layout>
      <h1 className="font-serif text-3xl text-navy mb-1 flex items-center gap-2">
        <DollarSign className="h-7 w-7 text-bronze" /> Commissions
      </h1>
      <p className="text-[#64748B] mb-6 max-w-2xl">
        Every payment through a referred client creates a commission on hold until you approve it here (or reply
        <span className="font-mono"> APPROVE CODE </span>on WhatsApp).
      </p>

      <div className="mb-4 flex flex-wrap gap-2">
        {["all", "pending_approval", "approved", "denied"].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`text-xs px-3 py-1.5 rounded-full border ${filter === f ? "bg-navy text-white border-navy" : "bg-white text-navy border-[#E2E0DA]"}`}
            data-testid={`commission-filter-${f}`}>
            {STATUS_LABEL[f] || "All"}
          </button>
        ))}
      </div>

      <div className="bg-white border border-[#E2E0DA] rounded-xl overflow-hidden" data-testid="commissions-table">
        {loading ? <p className="p-5 text-sm text-[#64748B]">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[#64748B] bg-[#FAF9F5]">
                  <th className="py-2 px-3">Client</th>
                  <th className="py-2 px-3">Product</th>
                  <th className="py-2 px-3">Rep</th>
                  <th className="py-2 px-3">Manager</th>
                  <th className="py-2 px-3">Rep $</th>
                  <th className="py-2 px-3">Mgr $</th>
                  <th className="py-2 px-3">Code</th>
                  <th className="py-2 px-3">Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="border-t border-[#E2E0DA]" data-testid={`commission-row-${c.id}`}>
                    <td className="py-2 px-3">
                      <div className="font-semibold text-navy">{c.client_name}</div>
                      <div className="text-[11px] text-[#94A3B8]">#{c.case_short}</div>
                    </td>
                    <td className="py-2 px-3">{c.product}</td>
                    <td className="py-2 px-3">{c.rep_name} <span className="text-[11px] text-[#94A3B8]">({c.rep_code})</span></td>
                    <td className="py-2 px-3">{c.manager_name || "—"}</td>
                    <td className="py-2 px-3 font-mono">{fmt(c.rep_cents)}</td>
                    <td className="py-2 px-3 font-mono">{c.manager_cents ? fmt(c.manager_cents) : "—"}</td>
                    <td className="py-2 px-3 font-mono text-bronze">{c.approval_code}</td>
                    <td className="py-2 px-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        c.status === "approved" ? "bg-green-100 text-green-800" :
                        c.status === "denied" ? "bg-red-100 text-red-800" :
                        "bg-amber-100 text-amber-800"
                      }`}>
                        {STATUS_LABEL[c.status] || c.status}
                      </span>
                    </td>
                    <td className="py-2 px-3">
                      {c.status === "pending_approval" && (
                        <div className="flex gap-1">
                          <button onClick={() => approve(c)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-green-600 text-white" data-testid={`approve-${c.id}`}>
                            <CheckCircle2 className="h-3 w-3" /> Approve
                          </button>
                          <button onClick={() => deny(c)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-red-600 text-white" data-testid={`deny-${c.id}`}>
                            <XCircle className="h-3 w-3" /> Deny
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan="9" className="py-6 text-center text-[#64748B]">No commissions yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
