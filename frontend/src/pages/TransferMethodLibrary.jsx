import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, CheckCircle2 } from "lucide-react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { US_STATES } from "@/lib/assetCopy";

const inp = "w-full border border-[#E2E0DA] rounded-md px-3 py-3 text-base bg-white";
const LIB_KINDS = [["house_land", "House or Land"], ["bank", "Bank Account"], ["investment", "Investment Account"], ["vehicle", "Vehicle"],
  ["business", "Business Ownership"], ["belongings", "Personal Belongings"], ["life_insurance", "Life Insurance Policy"], ["cash", "Cash"], ["other", "Other kinds"]];
const KL = Object.fromEntries(LIB_KINDS);

function RowForm({ row, onSave, onCancel }) {
  const [f, setF] = useState(row || { kind: "house_land", state: "", wording: "", status: "needs_check" });
  return (
    <div className="space-y-3 border rounded-lg p-3 bg-sand-200/20" data-testid="method-row-form">
      <select className={inp} value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} data-testid="method-kind">
        {LIB_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <select className={inp} value={f.state} onChange={(e) => setF({ ...f, state: e.target.value })} data-testid="method-state">
        <option value="">Pick a state</option><option value="ANY">Any state (generic)</option>
        {US_STATES.map((s) => <option key={s}>{s}</option>)}
      </select>
      <textarea className={inp} rows={3} value={f.wording} onChange={(e) => setF({ ...f, wording: e.target.value })} placeholder="Method wording" data-testid="method-wording" />
      <div className="flex gap-2">
        <button onClick={() => onSave(f)} className="btn-primary flex-1 min-h-[48px]" data-testid="method-save-btn">Save</button>
        <button onClick={onCancel} className="flex-1 min-h-[48px] border rounded-md">Cancel</button>
      </div>
    </div>
  );
}

export default function TransferMethodLibrary() {
  const [rows, setRows] = useState([]);
  const [fk, setFk] = useState("");
  const [fs, setFs] = useState("");
  const [editing, setEditing] = useState(null);

  const load = () => api.get("/admin/transfer-methods").then(({ data }) => setRows(data.rows || []));
  useEffect(() => { load(); }, []);

  const save = async (f, id) => {
    try {
      if (id) await api.patch(`/admin/transfer-methods/${id}`, f);
      else await api.post("/admin/transfer-methods", f);
      toast.success("Saved.");
      setEditing(null);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const shown = rows.filter((r) => (!fk || r.kind === fk) && (!fs || r.state === fs));

  return (
    <Layout>
      <div className="max-w-3xl mx-auto" data-testid="transfer-method-library">
        <h1 className="font-serif text-3xl text-navy mb-2">Transfer Method Library</h1>
        <p className="text-sm text-[#64748B] mb-4">Clients see these choices for their item kind and state. New rows start as "Needs attorney check."</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-4">
          <select className={inp} value={fk} onChange={(e) => setFk(e.target.value)} data-testid="filter-kind"><option value="">All kinds</option>{LIB_KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <select className={inp} value={fs} onChange={(e) => setFs(e.target.value)} data-testid="filter-state"><option value="">All states</option><option value="ANY">Any state</option>{US_STATES.map((s) => <option key={s}>{s}</option>)}</select>
          <button onClick={() => setEditing("new")} className="btn-primary col-span-2 sm:col-span-1 min-h-[48px] inline-flex items-center justify-center gap-1" data-testid="add-method-btn"><Plus className="h-4 w-4" /> Add row</button>
        </div>
        {editing === "new" && <RowForm onSave={(f) => save(f)} onCancel={() => setEditing(null)} />}
        <div className="space-y-3 mt-3">
          {shown.map((r) => editing === r.id ? (
            <RowForm key={r.id} row={r} onSave={(f) => save(f, r.id)} onCancel={() => setEditing(null)} />
          ) : (
            <div key={r.id} className="bg-white border rounded-lg p-4" data-testid={`method-row-${r.id}`}>
              <p className="text-sm text-[#64748B]">{KL[r.kind] || r.kind} · {r.state === "ANY" ? "Any state" : r.state}</p>
              <p className="text-base text-navy break-words my-1">{r.wording}</p>
              <span className={`text-xs font-semibold px-2 py-1 rounded-full ${r.status === "confirmed" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>
                {r.status === "confirmed" ? "Confirmed" : "Needs attorney check"}
              </span>
              <div className="flex gap-2 mt-3">
                <button onClick={() => setEditing(r.id)} className="flex-1 min-h-[44px] border rounded-md" data-testid={`method-edit-${r.id}`}>Edit</button>
                {r.status !== "confirmed" && (
                  <button onClick={() => save({ ...r, status: "confirmed" }, r.id)} className="flex-1 min-h-[44px] rounded-md bg-emerald-700 text-white inline-flex items-center justify-center gap-1" data-testid={`method-confirm-${r.id}`}><CheckCircle2 className="h-4 w-4" /> Mark Confirmed</button>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Layout>
  );
}
