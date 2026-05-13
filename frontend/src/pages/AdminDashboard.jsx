import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { Search, Users, FileClock, ArrowRight, UserPlus, Trash2, Archive, X, CheckSquare, Square, Download } from "lucide-react";
import { Input } from "@/components/ui/input";
import InviteClientDialog from "@/components/InviteClientDialog";
import DiagnosticsPanel from "@/components/DiagnosticsPanel";
import { toast } from "sonner";

const STATUSES = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review",
                  "Drafting Trust", "Ready for Client Review", "Ready for Payment", "Pending Payment Verification", "Payment Verified", "Completed"];

export default function AdminDashboard() {
  const [cases, setCases] = useState([]);
  const [stats, setStats] = useState(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);

  const toggleRow = (id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const toggleAllVisible = () => {
    setSelected((prev) => {
      const visibleIds = cases.map((c) => c.id);
      const allSelected = visibleIds.every((id) => prev.has(id));
      if (allSelected) {
        const next = new Set(prev);
        visibleIds.forEach((id) => next.delete(id));
        return next;
      }
      const next = new Set(prev);
      visibleIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const clearSelection = () => setSelected(new Set());

  const bulkArchive = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    if (!window.confirm(`Archive ${ids.length} case${ids.length === 1 ? "" : "s"}? You can restore them later.`)) return;
    setBulkBusy(true);
    try {
      const { data } = await api.post("/admin/trust-cases/bulk-archive", { case_ids: ids });
      toast.success(`Archived ${data.archived} case${data.archived === 1 ? "" : "s"}.`);
      clearSelection();
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBulkBusy(false); }
  };

  const bulkUnarchive = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    setBulkBusy(true);
    try {
      const { data } = await api.post("/admin/trust-cases/bulk-unarchive", { case_ids: ids });
      toast.success(`Restored ${data.restored} case${data.restored === 1 ? "" : "s"}.`);
      clearSelection();
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBulkBusy(false); }
  };

  const bulkDelete = async () => {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    const typed = window.prompt(
      `⚠️ Permanently DELETE ${ids.length} case${ids.length === 1 ? "" : "s"}?\n\n` +
      `This removes the cases, messages, documents, invites, and questions. This cannot be undone.\n\n` +
      `Type DELETE to confirm:`
    );
    if (typed !== "DELETE") { toast.message("Cancelled — nothing was deleted."); return; }
    const alsoUser = window.confirm(
      `Also delete client user accounts that have no other cases remaining?\n\nOK = delete client users too · Cancel = keep client accounts.`
    );
    setBulkBusy(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/bulk-delete?delete_user=${alsoUser}`, { case_ids: ids });
      const bits = [
        `Deleted ${data.deleted_cases} case${data.deleted_cases === 1 ? "" : "s"}`,
        data.storage_objects_deleted ? `${data.storage_objects_deleted} docs` : "",
        data.users_deleted ? `${data.users_deleted} user${data.users_deleted === 1 ? "" : "s"}` : "",
      ].filter(Boolean).join(" · ");
      toast.success(bits);
      clearSelection();
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBulkBusy(false); }
  };

  // Reset selection when filters change (selection might include cases no longer in view)
  useEffect(() => { clearSelection(); }, [status, includeArchived, q]);

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
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={async () => {
              try {
                const res = await api.get("/admin/trust-cases.csv", { responseType: "blob" });
                const url = URL.createObjectURL(res.data);
                const a = document.createElement("a");
                const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
                a.href = url; a.download = `trust-cases-${today}.csv`; a.click();
                URL.revokeObjectURL(url);
              } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
            }}
            className="btn-secondary"
            data-testid="admin-export-csv-btn">
            <Download className="h-4 w-4 inline mr-1" /> Export CSV
          </button>
          <button onClick={() => setInviteOpen(true)} className="btn-accent" data-testid="invite-client-btn">
            <UserPlus className="h-4 w-4 inline mr-1" /> Invite client
          </button>
        </div>
      </div>
      <InviteClientDialog open={inviteOpen} onOpenChange={setInviteOpen} onInvited={() => load()} />

      <DiagnosticsPanel />

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

      {selected.size > 0 && (
        <div
          className="sticky top-0 z-20 mb-4 bg-navy text-white rounded-xl p-4 shadow-lg flex flex-col sm:flex-row sm:items-center gap-3 justify-between"
          data-testid="bulk-action-bar">
          <div className="flex items-center gap-3">
            <span className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-bronze text-navy font-bold text-sm">
              {selected.size}
            </span>
            <div>
              <p className="font-semibold leading-tight">
                {selected.size} case{selected.size === 1 ? "" : "s"} selected
              </p>
              <button onClick={clearSelection} className="text-xs text-white/70 hover:text-bronze underline-offset-4 hover:underline" data-testid="bulk-clear-btn">
                Clear selection
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {includeArchived && (
              <button
                onClick={bulkUnarchive}
                disabled={bulkBusy}
                className="inline-flex items-center gap-1 px-4 py-2 rounded-md bg-white/10 hover:bg-white/20 text-white text-sm font-medium disabled:opacity-50"
                data-testid="bulk-unarchive-btn">
                Restore
              </button>
            )}
            <button
              onClick={bulkArchive}
              disabled={bulkBusy}
              className="inline-flex items-center gap-1 px-4 py-2 rounded-md bg-white/10 hover:bg-white/20 text-white text-sm font-medium disabled:opacity-50"
              data-testid="bulk-archive-btn">
              <Archive className="h-4 w-4" /> Archive selected
            </button>
            <button
              onClick={bulkDelete}
              disabled={bulkBusy}
              className="inline-flex items-center gap-1 px-4 py-2 rounded-md bg-red-600 hover:bg-red-700 text-white text-sm font-semibold disabled:opacity-50"
              data-testid="bulk-delete-btn">
              <Trash2 className="h-4 w-4" /> {bulkBusy ? "Working…" : "Delete permanently"}
            </button>
            <button
              onClick={clearSelection}
              className="inline-flex items-center gap-1 px-3 py-2 rounded-md text-white/70 hover:text-white text-sm"
              data-testid="bulk-close-btn"
              aria-label="Close">
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <p className="text-[#64748B]">Loading…</p>
      ) : cases.length === 0 ? (
        <p className="text-[#64748B]" data-testid="admin-empty">No cases match your filters.</p>
      ) : (
        <div className="bg-white border border-[#E2E0DA] rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-sand-200/60 text-xs uppercase tracking-wider text-[#64748B]">
              <tr>
                <th className="px-4 py-3 w-10">
                  <button
                    onClick={toggleAllVisible}
                    className="inline-flex items-center text-[#64748B] hover:text-navy"
                    title="Select / deselect all visible"
                    data-testid="bulk-select-all">
                    {cases.length > 0 && cases.every((c) => selected.has(c.id))
                      ? <CheckSquare className="h-4 w-4 text-bronze" />
                      : <Square className="h-4 w-4" />}
                  </button>
                </th>
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
                <tr key={c.id} className={`border-t border-[#E2E0DA] transition-colors ${selected.has(c.id) ? "bg-bronze/10" : "hover:bg-sand-200/30"}`} data-testid={`admin-case-row-${c.id}`}>
                  <td className="px-4 py-3 w-10 align-middle">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => toggleRow(c.id)}
                      className="h-4 w-4 rounded border-[#94A3B8] cursor-pointer accent-bronze"
                      onClick={(e) => e.stopPropagation()}
                      data-testid={`bulk-select-${c.id}`}
                    />
                  </td>
                  <td className="px-5 py-3">
                    <p className="font-medium text-navy">
                      {c.client_name || c.client_email}
                      {c.archived && <span className="ml-2 inline-block text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 uppercase tracking-wide" data-testid={`archived-badge-${c.id}`}>Archived</span>}
                    </p>
                    <p className="text-xs text-[#64748B]" data-testid={`client-email-${c.id}`}>{c.client_email}</p>
                    {c.client_phone && (
                      <p className="text-xs text-navy font-medium" data-testid={`client-phone-${c.id}`}>
                        <a href={`tel:${c.client_phone}`} className="hover:text-bronze">{c.client_phone}</a>
                      </p>
                    )}
                    {c.trust_name && <p className="text-xs text-[#94A3B8] truncate max-w-xs italic">{c.trust_name}</p>}
                  </td>
                  <td className="px-5 py-3 capitalize">
                    {(() => {
                      const isReview = (c.intake_path || "new") === "review";
                      const setCents = c.payment?.amount_cents;
                      const setLabel = setCents ? `$${(setCents / 100).toLocaleString(undefined, { minimumFractionDigits: setCents % 100 === 0 ? 0 : 2 })}` : null;
                      if (isReview) {
                        return (
                          <span className="inline-block text-[10px] bg-bronze/15 text-bronze px-2 py-1 rounded-full font-semibold whitespace-nowrap" data-testid={`path-badge-${c.id}`}>
                            Existing Trust{setLabel ? ` · ${setLabel}` : ""}
                          </span>
                        );
                      }
                      return (
                        <span className="inline-block text-[10px] bg-navy/10 text-navy px-2 py-1 rounded-full font-semibold whitespace-nowrap" data-testid={`path-badge-${c.id}`}>
                          {c.trust_type}{setLabel ? ` · ${setLabel}` : ""}
                        </span>
                      );
                    })()}
                  </td>
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
