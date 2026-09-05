import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import { Users, Trash2, Plus, Copy, Save, X } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

const EMPTY_REP = { name: "", email: "", rep_code: "", phone: "", manager_id: "", active: true };
const EMPTY_MGR = { name: "", email: "", phone: "", active: true };

export default function AdminRepsPage() {
  const [reps, setReps] = useState([]);
  const [managers, setManagers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingRep, setEditingRep] = useState(null);       // full object with id
  const [editingMgr, setEditingMgr] = useState(null);
  const [newRep, setNewRep] = useState(EMPTY_REP);
  const [newMgr, setNewMgr] = useState(EMPTY_MGR);
  const [showNewRep, setShowNewRep] = useState(false);
  const [showNewMgr, setShowNewMgr] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [r, m] = await Promise.all([
        api.get("/admin/reps"),
        api.get("/admin/managers"),
      ]);
      setReps(r.data.reps || []);
      setManagers(m.data.managers || []);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const managerById = (id) => managers.find((m) => m.id === id);

  const saveNewRep = async () => {
    try {
      await api.post("/admin/reps", { ...newRep, manager_id: newRep.manager_id || null });
      toast.success("Rep created");
      setShowNewRep(false);
      setNewRep(EMPTY_REP);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const saveEditRep = async () => {
    try {
      await api.put(`/admin/reps/${editingRep.id}`, {
        name: editingRep.name,
        email: editingRep.email,
        rep_code: editingRep.rep_code,
        phone: editingRep.phone || "",
        manager_id: editingRep.manager_id || null,
        active: !!editingRep.active,
      });
      toast.success("Rep updated");
      setEditingRep(null);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const removeRep = async (r) => {
    if (!window.confirm(`Delete rep ${r.name} (${r.rep_code})?`)) return;
    try { await api.delete(`/admin/reps/${r.id}`); toast.success("Rep deleted"); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const saveNewMgr = async () => {
    try {
      await api.post("/admin/managers", newMgr);
      toast.success("Manager created");
      setShowNewMgr(false);
      setNewMgr(EMPTY_MGR);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const saveEditMgr = async () => {
    try {
      await api.put(`/admin/managers/${editingMgr.id}`, {
        name: editingMgr.name,
        email: editingMgr.email,
        phone: editingMgr.phone || "",
        active: !!editingMgr.active,
      });
      toast.success("Manager updated");
      setEditingMgr(null);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const removeMgr = async (m) => {
    if (!window.confirm(`Delete manager ${m.name}? Reps under them will be unassigned.`)) return;
    try { await api.delete(`/admin/managers/${m.id}`); toast.success("Manager deleted"); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const copyLink = (code) => {
    const link = `${window.location.origin}/register?ref=${encodeURIComponent(code)}`;
    navigator.clipboard.writeText(link).then(
      () => toast.success("Referral link copied"),
      () => toast.error("Copy failed — long-press to copy")
    );
  };

  const inputCls = "w-full rounded-md border border-[#E2E0DA] px-3 py-2 text-sm outline-none focus:border-bronze";

  return (
    <Layout>
      <h1 className="font-serif text-3xl text-navy mb-1 flex items-center gap-2">
        <Users className="h-7 w-7 text-bronze" /> Reps & Managers
      </h1>
      <p className="text-[#64748B] mb-6 max-w-2xl">
        Every rep gets a unique code. Clients arriving via <code>?ref=CODE</code> are automatically credited on payment.
      </p>

      {/* ============ Managers ============ */}
      <div className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6 mb-8" data-testid="managers-section">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-2xl text-navy">Managers</h2>
          <button onClick={() => setShowNewMgr(true)} className="btn-primary text-sm px-3 py-2 inline-flex items-center gap-1" data-testid="add-manager-btn">
            <Plus className="h-4 w-4" /> Add manager
          </button>
        </div>

        {showNewMgr && (
          <div className="mb-4 rounded-lg border border-bronze/40 bg-bronze/5 p-4 grid gap-2 sm:grid-cols-4">
            <input className={inputCls} placeholder="Name" value={newMgr.name} onChange={(e) => setNewMgr({ ...newMgr, name: e.target.value })} data-testid="new-mgr-name" />
            <input className={inputCls} placeholder="Email" value={newMgr.email} onChange={(e) => setNewMgr({ ...newMgr, email: e.target.value })} data-testid="new-mgr-email" />
            <input className={inputCls} placeholder="Phone (+E164)" value={newMgr.phone} onChange={(e) => setNewMgr({ ...newMgr, phone: e.target.value })} data-testid="new-mgr-phone" />
            <div className="flex items-center gap-2">
              <button onClick={saveNewMgr} className="btn-primary text-sm px-3 py-2" data-testid="save-new-mgr-btn">Save</button>
              <button onClick={() => { setShowNewMgr(false); setNewMgr(EMPTY_MGR); }} className="text-sm px-3 py-2 border rounded">Cancel</button>
            </div>
          </div>
        )}

        {loading ? <p className="text-sm text-[#64748B]">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[#64748B] border-b">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Phone</th>
                  <th className="py-2 pr-3">Active</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {managers.map((m) => (
                  <tr key={m.id} className="border-b last:border-0" data-testid={`mgr-row-${m.id}`}>
                    {editingMgr?.id === m.id ? (
                      <>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingMgr.name} onChange={(e) => setEditingMgr({ ...editingMgr, name: e.target.value })} /></td>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingMgr.email} onChange={(e) => setEditingMgr({ ...editingMgr, email: e.target.value })} /></td>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingMgr.phone || ""} onChange={(e) => setEditingMgr({ ...editingMgr, phone: e.target.value })} /></td>
                        <td className="py-2 pr-3"><input type="checkbox" checked={!!editingMgr.active} onChange={(e) => setEditingMgr({ ...editingMgr, active: e.target.checked })} /></td>
                        <td className="py-2 pr-3 flex gap-1">
                          <button onClick={saveEditMgr} className="text-navy" title="Save"><Save className="h-4 w-4" /></button>
                          <button onClick={() => setEditingMgr(null)} className="text-[#64748B]" title="Cancel"><X className="h-4 w-4" /></button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="py-2 pr-3 font-semibold text-navy">{m.name}</td>
                        <td className="py-2 pr-3">{m.email}</td>
                        <td className="py-2 pr-3">{m.phone || "—"}</td>
                        <td className="py-2 pr-3">{m.active ? "✓" : "—"}</td>
                        <td className="py-2 pr-3 flex gap-1">
                          <button onClick={() => setEditingMgr({ ...m })} className="text-xs px-2 py-1 border rounded" data-testid={`edit-mgr-${m.id}`}>Edit</button>
                          <button onClick={() => removeMgr(m)} className="text-red-600" title="Delete" data-testid={`delete-mgr-${m.id}`}><Trash2 className="h-4 w-4" /></button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
                {managers.length === 0 && (
                  <tr><td colSpan="5" className="py-4 text-center text-[#64748B]">No managers yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* ============ Reps ============ */}
      <div className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6" data-testid="reps-section">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-2xl text-navy">Reps</h2>
          <button onClick={() => setShowNewRep(true)} className="btn-primary text-sm px-3 py-2 inline-flex items-center gap-1" data-testid="add-rep-btn">
            <Plus className="h-4 w-4" /> Add rep
          </button>
        </div>

        {showNewRep && (
          <div className="mb-4 rounded-lg border border-bronze/40 bg-bronze/5 p-4 grid gap-2 sm:grid-cols-6">
            <input className={inputCls} placeholder="Name" value={newRep.name} onChange={(e) => setNewRep({ ...newRep, name: e.target.value })} data-testid="new-rep-name" />
            <input className={inputCls} placeholder="Email" value={newRep.email} onChange={(e) => setNewRep({ ...newRep, email: e.target.value })} data-testid="new-rep-email" />
            <input className={inputCls} placeholder="Rep code (e.g. ALEX01)" value={newRep.rep_code} onChange={(e) => setNewRep({ ...newRep, rep_code: e.target.value.toUpperCase() })} data-testid="new-rep-code" />
            <input className={inputCls} placeholder="Phone" value={newRep.phone} onChange={(e) => setNewRep({ ...newRep, phone: e.target.value })} data-testid="new-rep-phone" />
            <select className={inputCls} value={newRep.manager_id || ""} onChange={(e) => setNewRep({ ...newRep, manager_id: e.target.value })} data-testid="new-rep-manager">
              <option value="">No manager</option>
              {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
            </select>
            <div className="flex items-center gap-2">
              <button onClick={saveNewRep} className="btn-primary text-sm px-3 py-2" data-testid="save-new-rep-btn">Save</button>
              <button onClick={() => { setShowNewRep(false); setNewRep(EMPTY_REP); }} className="text-sm px-3 py-2 border rounded">Cancel</button>
            </div>
          </div>
        )}

        {loading ? <p className="text-sm text-[#64748B]">Loading…</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-[#64748B] border-b">
                  <th className="py-2 pr-3">Name</th>
                  <th className="py-2 pr-3">Code</th>
                  <th className="py-2 pr-3">Email</th>
                  <th className="py-2 pr-3">Phone</th>
                  <th className="py-2 pr-3">Manager</th>
                  <th className="py-2 pr-3">Active</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {reps.map((r) => (
                  <tr key={r.id} className="border-b last:border-0" data-testid={`rep-row-${r.id}`}>
                    {editingRep?.id === r.id ? (
                      <>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingRep.name} onChange={(e) => setEditingRep({ ...editingRep, name: e.target.value })} /></td>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingRep.rep_code} onChange={(e) => setEditingRep({ ...editingRep, rep_code: e.target.value.toUpperCase() })} /></td>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingRep.email} onChange={(e) => setEditingRep({ ...editingRep, email: e.target.value })} /></td>
                        <td className="py-2 pr-3"><input className={inputCls} value={editingRep.phone || ""} onChange={(e) => setEditingRep({ ...editingRep, phone: e.target.value })} /></td>
                        <td className="py-2 pr-3">
                          <select className={inputCls} value={editingRep.manager_id || ""} onChange={(e) => setEditingRep({ ...editingRep, manager_id: e.target.value })}>
                            <option value="">No manager</option>
                            {managers.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                          </select>
                        </td>
                        <td className="py-2 pr-3"><input type="checkbox" checked={!!editingRep.active} onChange={(e) => setEditingRep({ ...editingRep, active: e.target.checked })} /></td>
                        <td className="py-2 pr-3 flex gap-1">
                          <button onClick={saveEditRep} className="text-navy" title="Save"><Save className="h-4 w-4" /></button>
                          <button onClick={() => setEditingRep(null)} className="text-[#64748B]" title="Cancel"><X className="h-4 w-4" /></button>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="py-2 pr-3 font-semibold text-navy">{r.name}</td>
                        <td className="py-2 pr-3 font-mono text-bronze">{r.rep_code}</td>
                        <td className="py-2 pr-3">{r.email}</td>
                        <td className="py-2 pr-3">{r.phone || "—"}</td>
                        <td className="py-2 pr-3">{managerById(r.manager_id)?.name || <span className="text-[#94A3B8]">—</span>}</td>
                        <td className="py-2 pr-3">{r.active ? "✓" : "—"}</td>
                        <td className="py-2 pr-3 flex gap-1">
                          <button onClick={() => copyLink(r.rep_code)} className="text-navy" title="Copy referral link" data-testid={`copy-ref-${r.id}`}>
                            <Copy className="h-4 w-4" />
                          </button>
                          <button onClick={() => setEditingRep({ ...r })} className="text-xs px-2 py-1 border rounded" data-testid={`edit-rep-${r.id}`}>Edit</button>
                          <button onClick={() => removeRep(r)} className="text-red-600" title="Delete" data-testid={`delete-rep-${r.id}`}><Trash2 className="h-4 w-4" /></button>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
                {reps.length === 0 && (
                  <tr><td colSpan="7" className="py-4 text-center text-[#64748B]">No reps yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </Layout>
  );
}
