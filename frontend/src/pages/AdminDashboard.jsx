import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { Search, Users, FileClock, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

const STATUSES = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review",
                  "Drafting Trust", "Ready for Signing", "Completed"];

export default function AdminDashboard() {
  const [cases, setCases] = useState([]);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (q) params.q = q;
      if (status) params.status = status;
      const [{ data: cs }, { data: st }] = await Promise.all([
        api.get("/admin/trust-cases", { params }),
        api.get("/admin/stats"),
      ]);
      setCases(cs); setStats(st);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [status]);

  return (
    <Layout>
      <div className="mb-10">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Administrator</p>
        <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Admin Dashboard</h1>
        <p className="text-[#64748B] mt-2">Manage all trust intake cases, clients, documents and messages.</p>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10" data-testid="admin-stats">
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Total Cases</p>
            <p className="font-serif text-3xl text-navy mt-1">{stats.total_cases}</p>
          </div>
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Clients</p>
            <p className="font-serif text-3xl text-navy mt-1">{stats.total_clients}</p>
          </div>
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">In Review</p>
            <p className="font-serif text-3xl text-navy mt-1">{stats.by_status["In Review"] || 0}</p>
          </div>
          <div className="bg-white border border-[#E2E0DA] rounded-xl p-5">
            <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Completed</p>
            <p className="font-serif text-3xl text-navy mt-1">{stats.by_status["Completed"] || 0}</p>
          </div>
        </div>
      )}

      <div className="flex flex-col md:flex-row gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[#94A3B8]" />
          <Input placeholder="Search by client name or email…" value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()}
            className="pl-10 bg-white" data-testid="admin-search-input" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)}
          className="bg-white border border-input rounded-md px-3 py-2 text-sm" data-testid="admin-status-filter">
          <option value="">All statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={load} className="btn-primary" data-testid="admin-search-btn">Search</button>
      </div>

      {loading ? (
        <p className="text-[#64748B]">Loading…</p>
      ) : cases.length === 0 ? (
        <p className="text-[#64748B]" data-testid="admin-empty">No cases match your filters.</p>
      ) : (
        <div className="bg-white border border-[#E2E0DA] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-sand-200/60 text-xs uppercase tracking-wider text-[#64748B]">
              <tr>
                <th className="text-left px-5 py-3">Client</th>
                <th className="text-left px-5 py-3">Type</th>
                <th className="text-left px-5 py-3">Status</th>
                <th className="text-left px-5 py-3">Grantors</th>
                <th className="text-left px-5 py-3">Assets</th>
                <th className="text-left px-5 py-3">Updated</th>
                <th className="px-5 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id} className="border-t border-[#E2E0DA] hover:bg-sand-200/30 transition-colors" data-testid={`admin-case-row-${c.id}`}>
                  <td className="px-5 py-3">
                    <p className="font-medium text-navy">{c.client_name || c.client_email}</p>
                    <p className="text-xs text-[#64748B]">{c.client_email}</p>
                  </td>
                  <td className="px-5 py-3 capitalize">{c.trust_type}</td>
                  <td className="px-5 py-3">
                    <span className="inline-block text-xs bg-bronze/15 text-bronze px-2 py-1 rounded-full font-semibold">{c.status}</span>
                  </td>
                  <td className="px-5 py-3">{c.grantors?.length || 0}</td>
                  <td className="px-5 py-3">{c.assets?.length || 0}</td>
                  <td className="px-5 py-3 text-[#64748B]">{new Date(c.updated_at).toLocaleDateString()}</td>
                  <td className="px-5 py-3 text-right">
                    <Link to={`/admin/cases/${c.id}`} className="text-bronze hover:text-bronze-dark inline-flex items-center gap-1" data-testid={`admin-case-view-${c.id}`}>
                      View <ArrowRight className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Layout>
  );
}
