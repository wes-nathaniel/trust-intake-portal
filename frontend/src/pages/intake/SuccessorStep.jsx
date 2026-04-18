import React, { useState } from "react";
import { Field, Txt, TA, AddressFields, SectionHeader, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

const REQ = ["full_legal_name", "relationship", "phone", "email"];
const empty = () => ({ full_legal_name: "", relationship: "", phone: "", email: "",
  address: { line1: "", line2: "", city: "", state: "", zip: "", country: "USA" }, notes: "" });

function Form({ caseId, initial, onCancel, reload, idx }) {
  const [t, setT] = useState(initial || empty());
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setT({ ...t, [k]: v });
  const save = async () => {
    const missing = validateRequired(t, REQ);
    if (missing.length) { toast.error("Complete required fields."); return; }
    setSaving(true);
    try {
      if (t.id) await api.put(`/trust-cases/${caseId}/successor-trustees/${t.id}`, t);
      else await api.post(`/trust-cases/${caseId}/successor-trustees`, t);
      toast.success("Successor trustee saved");
      onCancel?.();
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-5 border border-bronze/40 bg-sand-200/30 rounded-lg p-5" data-testid={`successor-form-${idx}`}>
      <h4 className="font-serif text-xl text-navy">Successor Trustee {idx + 1}</h4>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field id="s-name" label="Full legal name" required>
          <Txt id="s-name" value={t.full_legal_name} onChange={(v) => set("full_legal_name", v)} testId="successor-fullname-input" />
        </Field>
        <Field id="s-rel" label="Relationship" required>
          <Txt id="s-rel" value={t.relationship} onChange={(v) => set("relationship", v)} testId="successor-relationship-input" />
        </Field>
        <Field id="s-phone" label="Phone" required>
          <Txt id="s-phone" type="tel" value={t.phone} onChange={(v) => set("phone", v)} testId="successor-phone-input" />
        </Field>
        <Field id="s-email" label="Email" required>
          <Txt id="s-email" type="email" value={t.email} onChange={(v) => set("email", v)} testId="successor-email-input" />
        </Field>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Address (optional)</p>
        <AddressFields addr={t.address} onChange={(v) => set("address", v)} prefix="s-addr" />
      </div>
      <Field id="s-notes" label="Notes">
        <TA id="s-notes" value={t.notes} onChange={(v) => set("notes", v)} testId="successor-notes-textarea" />
      </Field>
      <div className="flex gap-2">
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="successor-save-btn">
          {saving ? "Saving…" : "Save"}
        </button>
        <button onClick={onCancel} className="btn-secondary" data-testid="successor-cancel-btn">Cancel</button>
      </div>
    </div>
  );
}

export default function SuccessorStep({ caseId, trustCase, reload }) {
  const [editing, setEditing] = useState(null);
  const list = trustCase.successor_trustees || [];

  const remove = async (id) => {
    if (!window.confirm("Remove this successor trustee?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/successor-trustees/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <SectionHeader num={3} total={8} title="Successor Trustees"
        subtitle="At least one successor trustee is required. You may add up to 3, listed in order of succession." />
      <div className="space-y-4">
        {list.map((t, i) =>
          editing === i ? (
            <Form key={t.id} caseId={caseId} initial={t} idx={i} reload={reload} onCancel={() => setEditing(null)} />
          ) : (
            <div key={t.id} className="border border-[#E2E0DA] rounded-lg p-5 flex items-start justify-between" data-testid={`successor-card-${i}`}>
              <div>
                <p className="text-xs uppercase tracking-wide text-bronze font-semibold">Successor {i + 1}</p>
                <h4 className="font-serif text-xl text-navy">{t.full_legal_name}</h4>
                <p className="text-sm text-[#64748B]">{t.relationship} · {t.email} · {t.phone}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(i)} className="text-sm text-navy hover:text-bronze" data-testid={`successor-edit-${i}`}>Edit</button>
                <button onClick={() => remove(t.id)} className="text-red-600 hover:text-red-800" data-testid={`successor-remove-${i}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        )}
        {list.length < 3 && editing !== "new" && (
          <button onClick={() => setEditing("new")} className="btn-accent" data-testid="successor-add-btn">
            <Plus className="h-4 w-4 inline mr-1" /> Add Successor Trustee
          </button>
        )}
        {editing === "new" && (
          <Form caseId={caseId} idx={list.length} reload={reload} onCancel={() => setEditing(null)} />
        )}
      </div>
      {list.length === 0 && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="successor-warning">
          <strong>Required:</strong> Please add at least one successor trustee to continue.
        </div>
      )}
    </div>
  );
}
