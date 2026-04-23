import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { Search, Users, FileClock, ArrowRight, UserPlus, Trash2, Archive } from "lucide-react";
import { Input } from "@/components/ui/input";
import InviteClientDialog from "@/components/InviteClientDialog";
import { toast } from "sonner";

const STATUSES = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review",
                  "Drafting Trust", "Ready for Payment", "Completed"];

export default function AdminDashboard() {
  const [cases, setCases] = useState([]);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (q) params.q = q;
      if (status) params.status = status;
      if (includeArchived) params.include_archived = true;
      const [{ data: cs }, { data: st }] = await Promise.all([
        api.get("/admin/trust-cases", { params }),
        api.get("/admin/stats"),
      ]);
      setCases(cs); setStats(st);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status, includeArchived]);

  const quickArchive = async (id, label, e) => {
    e.preventDefault(); e.stopPropagation();
    if (!window.confirm(`Archive case for ${label}? You can restore it later.`)) return;
    try { await api.post(`/admin/trust-cases/${id}/archive`); toast.success("Archived."); await load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const quickDelete = async (id, label, e) => {
    e.preventDefault(); e.stopPropagation();
    const confirm1 = window.prompt(`⚠️ DELETE case for ${label} permanently?\n\nThis removes the case, messages, documents, and invites. Type DELETE to confirm:`);
    if (confirm1 !== "DELETE") { toast.message("Cancelled."); return; }
    try { await api.delete(`/admin/trust-cases/${id}`); toast.success("Case deleted."); await load(); }
    catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  return (
    <Layout>
      <div className="mb-10 flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Administrator</p>
          <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Admin Dashboard</h1>
          <p className="text-[#64748B] mt-2">Manage all trust intake cases, clients, documents and messages.</p>
        </div>
        <button onClick={() => setInviteOpen(true)} className="btn-accent" data-testid="invite-client-btn">
          <UserPlus className="h-4 w-4 inline mr-1" /> Invite client
        </button>
      </div>
      <InviteClientDialog open={inviteOpen} onOpenChange={setInviteOpen} onInvited={() => load()} />

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
        <label className="inline-flex items-center gap-2 text-sm text-[#64748B] cursor-pointer select-none" data-testid="include-archived-toggle">
          <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} />
          Show archived
        </label>
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
                    <p className="font-medium text-navy">
                      {c.client_name || c.client_email}
                      {c.archived && <span className="ml-2 inline-block text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 uppercase tracking-wide" data-testid={`archived-badge-${c.id}`}>Archived</span>}
                    </p>
                    <p className="text-xs text-[#64748B]">{c.client_email}</p>
                    {c.trust_name && <p className="text-xs text-[#94A3B8] truncate max-w-xs italic">{c.trust_name}</p>}
                  </td>
                  <td className="px-5 py-3 capitalize">{c.trust_type}</td>
                  <td className="px-5 py-3">
                    <span className="inline-block text-xs bg-bronze/15 text-bronze px-2 py-1 rounded-full font-semibold">{c.status}</span>
                  </td>
                  <td className="px-5 py-3">{c.grantors?.length || 0}</td>
                  <td className="px-5 py-3">{c.assets?.length || 0}</td>
                  <td className="px-5 py-3 text-[#64748B]">{new Date(c.updated_at).toLocaleDateString()}</td>
                  <td className="px-5 py-3 text-right whitespace-nowrap">
                    <div className="inline-flex items-center gap-1">
                      <button
                        onClick={(e) => quickArchive(c.id, c.client_name || c.client_email, e)}
                        className="p-1.5 rounded hover:bg-amber-50 text-[#64748B] hover:text-amber-700 transition-colors"
                        title="Archive"
                        data-testid={`admin-case-archive-${c.id}`}>
                        <Archive className="h-4 w-4" />
                      </button>
                      <button
                        onClick={(e) => quickDelete(c.id, c.client_name || c.client_email, e)}
                        className="p-1.5 rounded hover:bg-red-50 text-[#64748B] hover:text-red-700 transition-colors"
                        title="Delete permanently"
                        data-testid={`admin-case-delete-${c.id}`}>
                        <Trash2 className="h-4 w-4" />
                      </button>
                      <Link to={`/admin/cases/${c.id}`} className="ml-1 text-bronze hover:text-bronze-dark inline-flex items-center gap-1" data-testid={`admin-case-view-${c.id}`}>
                        View <ArrowRight className="h-4 w-4" />
                      </Link>
                    </div>
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
