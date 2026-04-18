import React, { useState } from "react";
import { Field, Txt, TA, SectionHeader, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Landmark, Home, Car, Shield, TrendingUp, Briefcase, Cloud } from "lucide-react";

const TYPES = [
  { v: "bank", l: "Bank Account", icon: Landmark },
  { v: "real_estate", l: "Real Estate", icon: Home },
  { v: "vehicle", l: "Vehicle", icon: Car },
  { v: "life_insurance", l: "Life Insurance", icon: Shield },
  { v: "investment", l: "Investment", icon: TrendingUp },
  { v: "business", l: "Business Interest", icon: Briefcase },
  { v: "digital", l: "Digital Asset", icon: Cloud },
];

function empty() {
  return { asset_type: "bank", institution_name: "", property_address: "",
    account_number: "", institution_address: "", estimated_value: null, notes: "" };
}

function Form({ caseId, initial, idx, reload, onCancel }) {
  const [a, setA] = useState(initial || empty());
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setA({ ...a, [k]: v });

  const save = async () => {
    if (a.asset_type === "real_estate") {
      if (!a.property_address) { toast.error("Property address is required for real estate."); return; }
    } else {
      if (!a.institution_name) { toast.error("Institution name is required."); return; }
    }
    setSaving(true);
    try {
      const payload = { ...a, estimated_value: a.estimated_value ? Number(a.estimated_value) : null };
      if (a.id) await api.put(`/trust-cases/${caseId}/assets/${a.id}`, payload);
      else await api.post(`/trust-cases/${caseId}/assets`, payload);
      toast.success("Asset saved");
      onCancel?.();
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-5 border border-bronze/40 bg-sand-200/30 rounded-lg p-5" data-testid={`asset-form-${idx}`}>
      <h4 className="font-serif text-xl text-navy">Asset {idx + 1}</h4>
      <Field id="a-type" label="Asset type" required>
        <select value={a.asset_type} onChange={(e) => set("asset_type", e.target.value)}
          className="w-full rounded-md border border-input bg-white px-3 py-2 text-base" data-testid="asset-type-select">
          {TYPES.map((t) => <option key={t.v} value={t.v}>{t.l}</option>)}
        </select>
      </Field>
      <div className="grid sm:grid-cols-2 gap-4">
        {a.asset_type === "real_estate" ? (
          <div className="sm:col-span-2">
            <Field id="a-paddr" label="Property address" required>
              <Txt id="a-paddr" value={a.property_address} onChange={(v) => set("property_address", v)} testId="asset-property-input" />
            </Field>
          </div>
        ) : (
          <>
            <Field id="a-inst" label="Institution / Issuer name" required>
              <Txt id="a-inst" value={a.institution_name} onChange={(v) => set("institution_name", v)} testId="asset-institution-input" />
            </Field>
            <Field id="a-acc" label="Account / policy number">
              <Txt id="a-acc" value={a.account_number} onChange={(v) => set("account_number", v)} testId="asset-account-input" />
            </Field>
            <Field id="a-iaddr" label="Institution address">
              <Txt id="a-iaddr" value={a.institution_address} onChange={(v) => set("institution_address", v)} testId="asset-institution-address-input" />
            </Field>
          </>
        )}
        <Field id="a-val" label="Estimated value (USD)">
          <Txt id="a-val" type="number" value={a.estimated_value ?? ""} onChange={(v) => set("estimated_value", v)} testId="asset-value-input" />
        </Field>
      </div>
      <Field id="a-notes" label="Notes">
        <TA id="a-notes" value={a.notes} onChange={(v) => set("notes", v)} testId="asset-notes-textarea" />
      </Field>
      <div className="flex gap-2">
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="asset-save-btn">
          {saving ? "Saving…" : "Save Asset"}
        </button>
        <button onClick={onCancel} className="btn-secondary" data-testid="asset-cancel-btn">Cancel</button>
      </div>
    </div>
  );
}

export default function AssetStep({ caseId, trustCase, reload }) {
  const [editing, setEditing] = useState(null);
  const list = trustCase.assets || [];

  const remove = async (id) => {
    if (!window.confirm("Remove this asset?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/assets/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const label = (v) => TYPES.find((t) => t.v === v)?.l || v;

  return (
    <div>
      <SectionHeader num={5} total={8} title="Trust Assets"
        subtitle="List the assets you'd like to place in the trust. Add at least one to continue." />

      <div className="space-y-4">
        {list.map((a, i) =>
          editing === i ? (
            <Form key={a.id} caseId={caseId} initial={a} idx={i} reload={reload} onCancel={() => setEditing(null)} />
          ) : (
            <div key={a.id} className="border border-[#E2E0DA] rounded-lg p-5 flex items-start justify-between" data-testid={`asset-card-${i}`}>
              <div>
                <p className="text-xs uppercase tracking-wide text-bronze font-semibold">{label(a.asset_type)}</p>
                <h4 className="font-serif text-lg text-navy">{a.asset_type === "real_estate" ? a.property_address : a.institution_name}</h4>
                <p className="text-sm text-[#64748B]">
                  {a.account_number && `Acct: ${a.account_number}`}
                  {a.estimated_value && ` · ~$${Number(a.estimated_value).toLocaleString()}`}
                </p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(i)} className="text-sm text-navy hover:text-bronze" data-testid={`asset-edit-${i}`}>Edit</button>
                <button onClick={() => remove(a.id)} className="text-red-600 hover:text-red-800" data-testid={`asset-remove-${i}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        )}
        {editing !== "new" && (
          <button onClick={() => setEditing("new")} className="btn-accent" data-testid="asset-add-btn">
            <Plus className="h-4 w-4 inline mr-1" /> Add Asset
          </button>
        )}
        {editing === "new" && (
          <Form caseId={caseId} idx={list.length} reload={reload} onCancel={() => setEditing(null)} />
        )}
      </div>

      {list.length === 0 && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="asset-warning">
          <strong>Required:</strong> Please add at least one asset to continue.
        </div>
      )}
    </div>
  );
}
