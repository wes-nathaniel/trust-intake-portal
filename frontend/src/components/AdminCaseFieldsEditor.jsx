import React, { useState } from "react";
import { Pencil, Plus, Save, X, History } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

const PATHS = [
  { value: "new", label: "Brand New Trust (New Trust Drafting)" },
  { value: "review", label: "Existing Trust (Existing Trust Review)" },
];
const TYPES = [{ value: "single", label: "Single Trust" }, { value: "joint", label: "Joint Trust" }];
const ASSET_TYPES = ["bank", "real_estate", "vehicle", "life_insurance", "investment", "business", "digital"];
const PEOPLE = [
  { key: "grantors", label: "Grantor(s)" },
  { key: "trustees", label: "Trustee(s)" },
  { key: "successor_trustees", label: "Successor Trustee(s)" },
  { key: "beneficiaries", label: "Beneficiary(ies)" },
];
const inputCls = "w-full border border-[#E2E0DA] rounded-md px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-bronze/40";
const labelCls = "text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 block";

const initForm = (c) => ({
  intake_path: c.intake_path || "new",
  trust_type: c.trust_type || "single",
  trust_name: c.trust_name || "",
  ...Object.fromEntries(PEOPLE.map(({ key }) => [key, (c[key] || []).map((p) => ({ id: p.id, full_legal_name: p.full_legal_name || "" }))])),
  assets: (c.assets || []).map((a) => ({ id: a.id, asset_type: a.asset_type || "bank", institution_name: a.institution_name || "", estimated_value: a.estimated_value ?? "" })),
});

function NameList({ k, label, rows, setRows }) {
  const update = (i, v) => setRows(rows.map((r, j) => (j === i ? { ...r, full_legal_name: v } : r)));
  return (
    <div data-testid={`admin-edit-${k}`}>
      <label className={labelCls}>{label}</label>
      <div className="space-y-2">
        {rows.length === 0 && <p className="text-xs text-[#94A3B8]">None yet.</p>}
        {rows.map((r, i) => (
          <input key={r.id || `new-${i}`} className={inputCls} value={r.full_legal_name} placeholder="Full legal name"
            onChange={(e) => update(i, e.target.value)} data-testid={`admin-edit-${k}-name-${i}`} />
        ))}
      </div>
      <button type="button" onClick={() => setRows([...rows, { full_legal_name: "" }])}
        className="mt-2 text-xs text-bronze hover:text-navy inline-flex items-center gap-1" data-testid={`admin-edit-${k}-add-btn`}>
        <Plus className="h-3 w-3" /> Add
      </button>
    </div>
  );
}

function AssetList({ rows, setRows }) {
  const update = (i, patch) => setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <div data-testid="admin-edit-assets">
      <label className={labelCls}>Assets</label>
      <div className="space-y-2">
        {rows.length === 0 && <p className="text-xs text-[#94A3B8]">None yet.</p>}
        {rows.map((r, i) => (
          <div key={r.id || `new-${i}`} className="grid grid-cols-1 sm:grid-cols-[140px_1fr_120px] gap-2">
            <select className={inputCls} value={r.asset_type} onChange={(e) => update(i, { asset_type: e.target.value })}
              data-testid={`admin-edit-asset-type-${i}`}>
              {ASSET_TYPES.map((t) => <option key={t} value={t}>{t.replace("_", " ")}</option>)}
            </select>
            <input className={inputCls} value={r.institution_name} placeholder="Institution / description"
              onChange={(e) => update(i, { institution_name: e.target.value })} data-testid={`admin-edit-asset-name-${i}`} />
            <input className={inputCls} type="number" min="0" value={r.estimated_value} placeholder="Value $"
              onChange={(e) => update(i, { estimated_value: e.target.value })} data-testid={`admin-edit-asset-value-${i}`} />
          </div>
        ))}
      </div>
      <button type="button" onClick={() => setRows([...rows, { asset_type: "bank", institution_name: "", estimated_value: "" }])}
        className="mt-2 text-xs text-bronze hover:text-navy inline-flex items-center gap-1" data-testid="admin-edit-assets-add-btn">
        <Plus className="h-3 w-3" /> Add asset
      </button>
    </div>
  );
}

function EditHistory({ edits }) {
  if (!edits?.length) return null;
  return (
    <div className="mt-5 border-t border-[#F1EFEA] pt-3" data-testid="admin-edit-history">
      <p className={`${labelCls} flex items-center gap-1`}><History className="h-3 w-3" /> Admin edit history</p>
      <ul className="text-xs text-[#64748B] space-y-1 max-h-40 overflow-auto">
        {[...edits].reverse().map((e) => (
          <li key={e.id}>
            <b className="text-navy">{new Date(e.at).toLocaleString()}</b> · {e.admin_email}:{" "}
            {e.changes.map((ch) => `${ch.field} → ${ch.to ?? ""}`).join("; ")}
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AdminCaseFieldsEditor({ c, onSaved }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(() => initForm(c));
  const [saving, setSaving] = useState(false);
  const set = (k) => (v) => setForm((f) => ({ ...f, [k]: v }));

  const start = () => { setForm(initForm(c)); setOpen(true); };
  const save = async () => {
    const payload = { intake_path: form.intake_path, trust_type: form.trust_type, trust_name: form.trust_name };
    PEOPLE.forEach(({ key }) => { payload[key] = form[key].filter((r) => r.full_legal_name.trim()); });
    payload.assets = form.assets.filter((a) => a.id || a.institution_name.trim())
      .map((a) => ({ ...a, estimated_value: a.estimated_value === "" ? null : Number(a.estimated_value) }));
    setSaving(true);
    try {
      const { data } = await api.patch(`/admin/trust-cases/${c.id}/fields`, payload);
      toast.success(data.changes ? `Saved ${data.changes} change${data.changes === 1 ? "" : "s"}.` : "No changes to save.");
      setOpen(false);
      await onSaved?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="mb-6 bg-white border border-[#E2E0DA] rounded-xl p-5" data-testid="admin-case-fields-editor">
      <div className="flex items-center justify-between gap-3">
        <h2 className="font-serif text-xl text-navy flex items-center gap-2"><Pencil className="h-4 w-4 text-bronze" /> Edit case details</h2>
        {!open && (
          <button type="button" onClick={start} className="btn-primary text-sm px-4 py-2" data-testid="admin-edit-case-open-btn">Edit</button>
        )}
      </div>
      {!open ? (
        <p className="text-sm text-[#64748B] mt-1">Fix the trust type, title and names without touching the client's documents or progress.</p>
      ) : (
        <div className="mt-4 space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className={labelCls}>Trust path</label>
              <select className={inputCls} value={form.intake_path} onChange={(e) => set("intake_path")(e.target.value)} data-testid="admin-edit-intake-path">
                {PATHS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Single / Joint</label>
              <select className={inputCls} value={form.trust_type} onChange={(e) => set("trust_type")(e.target.value)} data-testid="admin-edit-trust-type">
                {TYPES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Trust title / case name</label>
              <input className={inputCls} value={form.trust_name} onChange={(e) => set("trust_name")(e.target.value)} data-testid="admin-edit-trust-name" />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {PEOPLE.map(({ key, label }) => (
              <NameList key={key} k={key} label={label} rows={form[key]} setRows={set(key)} />
            ))}
          </div>
          <AssetList rows={form.assets} setRows={set("assets")} />
          <p className="text-xs text-[#94A3B8]">
            Names added here show up in the client's intake; they complete the remaining details (date of birth, SSN, contact info).
            Nothing is deleted, and documents and progress stay as they are. The client isn't notified.
          </p>
          <div className="flex gap-2 justify-end">
            <button type="button" onClick={() => setOpen(false)} className="px-4 py-2 text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1"
              data-testid="admin-edit-case-cancel-btn"><X className="h-4 w-4" /> Cancel</button>
            <button type="button" onClick={save} disabled={saving} className="btn-primary px-4 py-2 text-sm inline-flex items-center gap-1 disabled:opacity-50"
              data-testid="admin-edit-case-save-btn"><Save className="h-4 w-4" /> {saving ? "Saving…" : "Save changes"}</button>
          </div>
        </div>
      )}
      <EditHistory edits={c.admin_edits} />
    </section>
  );
}
