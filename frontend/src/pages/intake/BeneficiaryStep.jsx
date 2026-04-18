import React, { useState } from "react";
import { Field, Txt, TA, AddressFields, SectionHeader, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2 } from "lucide-react";

const REQ = ["full_legal_name", "date_of_birth", "relationship", "percentage"];
const empty = () => ({
  full_legal_name: "", date_of_birth: "", relationship: "", percentage: 0,
  address: { line1: "", line2: "", city: "", state: "", zip: "", country: "USA" },
  phone: "", email: "", special_instructions: "",
  contingent_name: "", contingent_relationship: "", contingent_phone: "",
  notes: "",
});

function Form({ caseId, initial, idx, reload, onCancel }) {
  const [b, setB] = useState(initial || empty());
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setB({ ...b, [k]: v });
  const save = async () => {
    const missing = validateRequired(b, REQ.filter(k => k !== "percentage"));
    if (missing.length || b.percentage == null || b.percentage === "" || Number(b.percentage) <= 0) {
      toast.error("Complete required fields (name, DOB, relationship, percentage > 0).");
      return;
    }
    setSaving(true);
    try {
      const payload = { ...b, percentage: Number(b.percentage) };
      if (b.id) await api.put(`/trust-cases/${caseId}/beneficiaries/${b.id}`, payload);
      else await api.post(`/trust-cases/${caseId}/beneficiaries`, payload);
      toast.success("Beneficiary saved");
      onCancel?.();
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div className="space-y-5 border border-bronze/40 bg-sand-200/30 rounded-lg p-5" data-testid={`beneficiary-form-${idx}`}>
      <h4 className="font-serif text-xl text-navy">Primary Beneficiary {idx + 1}</h4>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field id="b-name" label="Full legal name" required>
          <Txt id="b-name" value={b.full_legal_name} onChange={(v) => set("full_legal_name", v)} testId="beneficiary-fullname-input" />
        </Field>
        <Field id="b-dob" label="Date of birth" required>
          <Txt id="b-dob" type="date" value={b.date_of_birth} onChange={(v) => set("date_of_birth", v)} testId="beneficiary-dob-input" />
        </Field>
        <Field id="b-rel" label="Relationship" required>
          <Txt id="b-rel" value={b.relationship} onChange={(v) => set("relationship", v)} testId="beneficiary-relationship-input" />
        </Field>
        <Field id="b-pct" label="Percentage / share (%)" required>
          <Txt id="b-pct" type="number" value={b.percentage} onChange={(v) => set("percentage", v)} testId="beneficiary-percentage-input" />
        </Field>
        <Field id="b-phone" label="Phone">
          <Txt id="b-phone" type="tel" value={b.phone} onChange={(v) => set("phone", v)} testId="beneficiary-phone-input" />
        </Field>
        <Field id="b-email" label="Email">
          <Txt id="b-email" type="email" value={b.email} onChange={(v) => set("email", v)} testId="beneficiary-email-input" />
        </Field>
      </div>
      <div>
        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Address (optional)</p>
        <AddressFields addr={b.address} onChange={(v) => set("address", v)} prefix="b-addr" />
      </div>
      <Field id="b-si" label="Special instructions">
        <TA id="b-si" value={b.special_instructions} onChange={(v) => set("special_instructions", v)} testId="beneficiary-special-textarea" />
      </Field>

      <div className="border-t border-dashed border-bronze/40 pt-5">
        <p className="text-xs uppercase tracking-wide text-bronze font-semibold mb-3">Contingent Beneficiary (optional)</p>
        <div className="grid sm:grid-cols-3 gap-4">
          <Field id="bc-name" label="Full name">
            <Txt id="bc-name" value={b.contingent_name} onChange={(v) => set("contingent_name", v)} testId="contingent-name-input" />
          </Field>
          <Field id="bc-rel" label="Relationship">
            <Txt id="bc-rel" value={b.contingent_relationship} onChange={(v) => set("contingent_relationship", v)} testId="contingent-relationship-input" />
          </Field>
          <Field id="bc-phone" label="Phone">
            <Txt id="bc-phone" type="tel" value={b.contingent_phone} onChange={(v) => set("contingent_phone", v)} testId="contingent-phone-input" />
          </Field>
        </div>
      </div>
      <Field id="b-notes" label="Notes">
        <TA id="b-notes" value={b.notes} onChange={(v) => set("notes", v)} testId="beneficiary-notes-textarea" />
      </Field>
      <div className="flex gap-2">
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="beneficiary-save-btn">
          {saving ? "Saving…" : "Save Beneficiary"}
        </button>
        <button onClick={onCancel} className="btn-secondary" data-testid="beneficiary-cancel-btn">Cancel</button>
      </div>
    </div>
  );
}

export default function BeneficiaryStep({ caseId, trustCase, reload }) {
  const [editing, setEditing] = useState(null);
  const list = trustCase.beneficiaries || [];
  const total = list.reduce((s, b) => s + (b.percentage || 0), 0);

  const remove = async (id) => {
    if (!window.confirm("Remove this beneficiary?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/beneficiaries/${id}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <SectionHeader num={4} total={8} title="Beneficiaries"
        subtitle="Add at least one primary beneficiary. Percentages should ideally sum to 100%." />
      <div className="space-y-4">
        {list.map((b, i) =>
          editing === i ? (
            <Form key={b.id} caseId={caseId} initial={b} idx={i} reload={reload} onCancel={() => setEditing(null)} />
          ) : (
            <div key={b.id} className="border border-[#E2E0DA] rounded-lg p-5 flex items-start justify-between" data-testid={`beneficiary-card-${i}`}>
              <div>
                <p className="text-xs uppercase tracking-wide text-bronze font-semibold">Beneficiary {i + 1}</p>
                <h4 className="font-serif text-xl text-navy">{b.full_legal_name}</h4>
                <p className="text-sm text-[#64748B]">{b.relationship} · {b.percentage}% · DOB {b.date_of_birth}</p>
                {b.contingent_name && <p className="text-xs text-[#64748B] mt-1">Contingent: {b.contingent_name}</p>}
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(i)} className="text-sm text-navy hover:text-bronze" data-testid={`beneficiary-edit-${i}`}>Edit</button>
                <button onClick={() => remove(b.id)} className="text-red-600 hover:text-red-800" data-testid={`beneficiary-remove-${i}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        )}

        {editing !== "new" && (
          <button onClick={() => setEditing("new")} className="btn-accent" data-testid="beneficiary-add-btn">
            <Plus className="h-4 w-4 inline mr-1" /> Add Beneficiary
          </button>
        )}
        {editing === "new" && (
          <Form caseId={caseId} idx={list.length} reload={reload} onCancel={() => setEditing(null)} />
        )}
      </div>
      <div className="mt-4 text-sm text-[#64748B]" data-testid="beneficiary-total">
        Total allocated: <span className={`font-semibold ${total === 100 ? "text-green-700" : "text-bronze"}`}>{total}%</span>
      </div>
      {list.length === 0 && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="beneficiary-warning">
          <strong>Required:</strong> Please add at least one primary beneficiary.
        </div>
      )}
    </div>
  );
}
