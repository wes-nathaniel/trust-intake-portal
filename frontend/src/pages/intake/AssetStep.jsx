import React, { useState, useRef } from "react";
import { Field, Txt, TA, SectionHeader, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Landmark, Home, Car, Shield, TrendingUp, Briefcase, Cloud, Upload, FileText, Download, ListPlus, FileUp } from "lucide-react";
import NotesQuestionsBox from "@/components/NotesQuestionsBox";

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
  const [mode, setMode] = useState("documents"); // "documents" | "manual"
  const list = trustCase.assets || [];
  const allDocs = (trustCase.documents || []).filter(d => !d.is_deleted);
  const ASSET_DOC_TYPE_LABELS = {
    bank_statement: "Bank Statement",
    deed: "Deed",
    title: "Vehicle Title",
    insurance_policy: "Insurance Policy",
    business_document: "Business Document",
  };
  const assetDocs = allDocs.filter(d => ASSET_DOC_TYPE_LABELS[d.doc_type]);
  const hasAssets = list.length > 0 || assetDocs.length > 0;

  const uploadInput = useRef();
  const [uploadingType, setUploadingType] = useState("bank_statement");
  const [uploading, setUploading] = useState(false);

  const uploadAssetDoc = async (file) => {
    if (!file) return;
    setUploading(true);
    const form = new FormData();
    form.append("doc_type", uploadingType);
    form.append("file", file);
    try {
      await api.post(`/trust-cases/${caseId}/documents`, form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${ASSET_DOC_TYPE_LABELS[uploadingType]} uploaded`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setUploading(false); if (uploadInput.current) uploadInput.current.value = ""; }
  };

  const removeAssetDoc = async (id) => {
    if (!window.confirm("Remove this document?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/documents/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const downloadDoc = async (d) => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = d.filename || "file"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const remove = async (id) => {
    if (!window.confirm("Remove this asset?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/assets/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const label = (v) => TYPES.find((t) => t.v === v)?.l || v;

  // Business asset advisory — show when any business-type asset or business-document upload is present
  const hasBusinessAsset =
    list.some(a => a.asset_type === "business") ||
    allDocs.some(d => d.doc_type === "business_document");

  return (
    <div>
      <SectionHeader num={5} total={8} title="Trust Assets"
        subtitle="Tell us what you'd like to place in the trust. Easiest: upload statements, deeds, titles, etc. and our team will extract the details. You can also enter assets manually." />

      {hasBusinessAsset && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-300 rounded-md text-sm text-amber-900" data-testid="business-sos-advisory-asset">
          <p className="font-semibold mb-1">Secretary of State — Business Ownership Transfer</p>
          <p className="text-amber-900/90">
            If you are placing a business under your trust, most states require you to file a <b>Change of Ownership / Change of Responsible Party</b> form with the Secretary of State.
            This updates the business registration from your personal name to the trust name. Please contact your Secretary of State's office to complete this step.
          </p>
        </div>
      )}
      {/* Mode selector */}
      <div className="inline-flex bg-sand-200 rounded-lg p-1 mb-6" data-testid="asset-mode-toggle">
        <button onClick={() => setMode("documents")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${mode === "documents" ? "bg-white text-navy shadow-sm" : "text-[#64748B]"}`}
          data-testid="asset-mode-documents">
          <FileUp className="h-4 w-4 inline mr-1" /> Upload documents
        </button>
        <button onClick={() => setMode("manual")}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${mode === "manual" ? "bg-white text-navy shadow-sm" : "text-[#64748B]"}`}
          data-testid="asset-mode-manual">
          <ListPlus className="h-4 w-4 inline mr-1" /> Enter manually
        </button>
      </div>

      {mode === "documents" ? (
        <div className="space-y-4" data-testid="asset-docs-mode">
          <div className="border border-[#E2E0DA] rounded-lg p-5 bg-sand-200/30">
            <p className="font-serif text-lg text-navy mb-1">Upload an asset document</p>
            <p className="text-sm text-[#64748B] mb-4">Your trust team will review and add these assets to your case. Upload as many as you like.</p>
            <div className="flex flex-wrap items-center gap-3">
              <select value={uploadingType} onChange={(e) => setUploadingType(e.target.value)}
                className="rounded-md border border-input bg-white px-3 py-2 text-sm" data-testid="asset-doc-type-select">
                {Object.entries(ASSET_DOC_TYPE_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
              <label className="btn-accent cursor-pointer text-sm inline-flex items-center" data-testid="asset-doc-upload-label">
                <Upload className="h-4 w-4 inline mr-1" /> {uploading ? "Uploading…" : "Choose file"}
                <input ref={uploadInput} type="file" className="hidden" onChange={(e) => uploadAssetDoc(e.target.files?.[0])} data-testid="asset-doc-upload-input" />
              </label>
            </div>
          </div>

          {assetDocs.length > 0 && (
            <div>
              <h4 className="font-serif text-lg text-navy mb-2">Uploaded asset documents ({assetDocs.length})</h4>
              <ul className="space-y-2">
                {assetDocs.map((d) => (
                  <li key={d.id} className="flex items-center justify-between text-sm bg-white border border-[#E2E0DA] rounded-md px-3 py-2" data-testid={`asset-doc-item-${d.id}`}>
                    <span className="flex items-center gap-2 text-navy truncate">
                      <FileText className="h-4 w-4 shrink-0" />
                      <span className="truncate">{d.filename}</span>
                      <span className="text-xs text-[#64748B]">· {ASSET_DOC_TYPE_LABELS[d.doc_type]}</span>
                    </span>
                    <div className="flex gap-2 shrink-0">
                      <button onClick={() => downloadDoc(d)} className="text-navy hover:text-bronze"><Download className="h-4 w-4" /></button>
                      <button onClick={() => removeAssetDoc(d.id)} className="text-red-600 hover:text-red-800"><Trash2 className="h-4 w-4" /></button>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Manual-entered assets still visible so they don't disappear if switching modes */}
          {list.length > 0 && (
            <div className="mt-6">
              <h4 className="font-serif text-lg text-navy mb-2">Manually entered assets ({list.length})</h4>
              <ul className="space-y-2">
                {list.map((a) => (
                  <li key={a.id} className="flex items-center justify-between text-sm bg-white border border-[#E2E0DA] rounded-md px-3 py-2">
                    <span><b>{label(a.asset_type)}</b> · {a.institution_name || a.property_address}</span>
                    <button onClick={() => remove(a.id)} className="text-red-600 hover:text-red-800"><Trash2 className="h-4 w-4" /></button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4" data-testid="asset-manual-mode">
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
              <Plus className="h-4 w-4 inline mr-1" /> Add Asset manually
            </button>
          )}
          {editing === "new" && (
            <Form caseId={caseId} idx={list.length} reload={reload} onCancel={() => setEditing(null)} />
          )}
        </div>
      )}

      {!hasAssets && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="asset-warning">
          <strong>Required:</strong> Please add at least one asset (upload a document or enter manually) to continue.
        </div>
      )}

      <NotesQuestionsBox caseId={caseId} section="assets" />
    </div>
  );
}
