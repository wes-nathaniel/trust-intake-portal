import React, { useState } from "react";
import { Field, Txt, TA, AddressFields, SectionHeader, maskSSN, displaySSN, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Trash2, Plus, Eye, EyeOff } from "lucide-react";

const REQ = ["full_legal_name", "date_of_birth", "ssn", "phone", "email", "marital_status", "citizenship",
             "address.line1", "address.city", "address.state", "address.zip"];

function emptyGrantor() {
  return {
    full_legal_name: "", middle_name: "", date_of_birth: "", ssn: "",
    phone: "", secondary_phone: "", email: "",
    address: { line1: "", line2: "", city: "", state: "", zip: "", country: "USA" },
    marital_status: "", citizenship: "", notes: "",
  };
}

function GrantorForm({ caseId, initial, reload, onCancel, grantorIndex }) {
  const [g, setG] = useState(initial || emptyGrantor());
  const [showSSN, setShowSSN] = useState(false);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setG({ ...g, [k]: v });

  const save = async () => {
    const missing = validateRequired(g, REQ);
    if (missing.length) { toast.error("Please complete all required fields before saving."); return; }
    setSaving(true);
    try {
      if (g.id) {
        await api.put(`/trust-cases/${caseId}/grantors/${g.id}`, g);
      } else {
        await api.post(`/trust-cases/${caseId}/grantors`, g);
      }
      toast.success("Grantor saved");
      onCancel?.();
      reload();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-5 border border-bronze/40 bg-sand-200/30 rounded-lg p-5" data-testid={`grantor-form-${grantorIndex}`}>
      <h4 className="font-serif text-xl text-navy">Grantor {grantorIndex + 1} Details</h4>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field id="gf-full" label="Full legal name" required>
          <Txt id="gf-full" value={g.full_legal_name} onChange={(v) => set("full_legal_name", v)} testId="grantor-fullname-input" />
        </Field>
        <Field id="gf-mid" label="Middle name">
          <Txt id="gf-mid" value={g.middle_name} onChange={(v) => set("middle_name", v)} testId="grantor-middlename-input" />
        </Field>
        <Field id="gf-dob" label="Date of birth" required>
          <Txt id="gf-dob" type="date" value={g.date_of_birth} onChange={(v) => set("date_of_birth", v)} testId="grantor-dob-input" />
        </Field>
        <Field id="gf-ssn" label="SSN" required hint="Masked for your security">
          <div className="relative">
            <Txt id="gf-ssn" type={showSSN ? "text" : "password"} value={g.ssn} onChange={(v) => set("ssn", maskSSN(v))} placeholder="XXX-XX-XXXX" testId="grantor-ssn-input" />
            <button type="button" onClick={() => setShowSSN(!showSSN)} className="absolute right-2 top-1/2 -translate-y-1/2 text-[#64748B] hover:text-navy" data-testid="grantor-ssn-toggle">
              {showSSN ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </Field>
        <Field id="gf-phone" label="Phone" required>
          <Txt id="gf-phone" type="tel" value={g.phone} onChange={(v) => set("phone", v)} testId="grantor-phone-input" />
        </Field>
        <Field id="gf-phone2" label="Secondary phone">
          <Txt id="gf-phone2" type="tel" value={g.secondary_phone} onChange={(v) => set("secondary_phone", v)} testId="grantor-phone2-input" />
        </Field>
        <Field id="gf-email" label="Email" required>
          <Txt id="gf-email" type="email" value={g.email} onChange={(v) => set("email", v)} testId="grantor-email-input" />
        </Field>
        <Field id="gf-marital" label="Marital status" required>
          <select className="w-full rounded-md border border-input bg-white px-3 py-2 text-base" value={g.marital_status}
            onChange={(e) => set("marital_status", e.target.value)} data-testid="grantor-marital-select">
            <option value="">Select…</option>
            <option value="single">Single</option>
            <option value="married">Married</option>
            <option value="partnered">Domestic Partnership</option>
            <option value="divorced">Divorced</option>
            <option value="widowed">Widowed</option>
          </select>
        </Field>
        <Field id="gf-citizen" label="Citizenship" required>
          <Txt id="gf-citizen" value={g.citizenship} onChange={(v) => set("citizenship", v)} placeholder="e.g., USA" testId="grantor-citizenship-input" />
        </Field>
      </div>

      <div>
        <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Residential Address <span className="text-red-500">*</span></p>
        <AddressFields addr={g.address} onChange={(v) => set("address", v)} prefix="g-addr" required />
      </div>

      <Field id="gf-notes" label="Notes">
        <TA id="gf-notes" value={g.notes} onChange={(v) => set("notes", v)} testId="grantor-notes-textarea" />
      </Field>

      <div className="flex gap-2">
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="grantor-save-btn">
          {saving ? "Saving…" : "Save Grantor"}
        </button>
        <button onClick={onCancel} className="btn-secondary" data-testid="grantor-cancel-btn">Cancel</button>
      </div>
    </div>
  );
}

export default function GrantorStep({ caseId, trustCase, reload }) {
  const [editing, setEditing] = useState(null); // null | index | "new"
  const grantors = trustCase.grantors || [];
  const max = trustCase.trust_type === "joint" ? 2 : 1;

  const remove = async (gid) => {
    if (!window.confirm("Remove this grantor?")) return;
    try {
      await api.delete(`/trust-cases/${caseId}/grantors/${gid}`);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <SectionHeader num={1} total={8} title="Grantor Information"
        subtitle={trustCase.trust_type === "joint" ? "Please provide details for both grantors (2 required for a joint trust)." : "Please provide grantor details."} />

      <div className="space-y-4">
        {grantors.map((g, i) =>
          editing === i ? (
            <GrantorForm key={g.id} caseId={caseId} initial={g} grantorIndex={i} reload={reload} onCancel={() => setEditing(null)} />
          ) : (
            <div key={g.id} className="border border-[#E2E0DA] rounded-lg p-5 flex items-start justify-between" data-testid={`grantor-card-${i}`}>
              <div>
                <p className="text-xs uppercase tracking-wide text-bronze font-semibold mb-1">Grantor {i + 1}</p>
                <h4 className="font-serif text-xl text-navy">{g.full_legal_name}</h4>
                <p className="text-sm text-[#64748B]">{g.email} · {g.phone}</p>
                <p className="text-sm text-[#64748B]">SSN: {displaySSN(g.ssn)}</p>
                <p className="text-sm text-[#64748B]">{g.address?.city}, {g.address?.state} {g.address?.zip}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(i)} className="text-sm text-navy hover:text-bronze" data-testid={`grantor-edit-${i}`}>Edit</button>
                <button onClick={() => remove(g.id)} className="text-red-600 hover:text-red-800" data-testid={`grantor-remove-${i}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </div>
          )
        )}

        {grantors.length < max && editing !== "new" && (
          <button onClick={() => setEditing("new")} className="btn-accent" data-testid="grantor-add-btn">
            <Plus className="h-4 w-4 inline mr-1" /> Add Grantor
          </button>
        )}
        {editing === "new" && (
          <GrantorForm caseId={caseId} grantorIndex={grantors.length} reload={reload} onCancel={() => setEditing(null)} />
        )}
      </div>

      {grantors.length < max && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-md text-sm text-amber-900" data-testid="grantor-warning">
          <strong>Required:</strong> Please add {max - grantors.length} more grantor{(max - grantors.length) > 1 ? "s" : ""} to continue.
        </div>
      )}
    </div>
  );
}
