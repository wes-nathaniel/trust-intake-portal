import React, { useState, useEffect } from "react";
import { Field, Txt, TA, AddressFields, SectionHeader, validateRequired } from "./_shared";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import RoleDefinition from "@/components/RoleDefinition";
import NotesQuestionsBox from "@/components/NotesQuestionsBox";

const REQ = ["full_legal_name", "relationship", "phone", "email"];

function emptyT() {
  return { full_legal_name: "", relationship: "", phone: "", email: "",
    address: { line1: "", line2: "", city: "", state: "", zip: "", country: "USA" }, notes: "" };
}

export default function TrusteeStep({ caseId, trustCase, reload }) {
  const existing = trustCase.trustees?.[0];
  const [t, setT] = useState(existing || emptyT());
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (existing) setT({ ...emptyT(), ...existing }); }, [existing?.id]);

  const set = (k, v) => setT({ ...t, [k]: v });
  const save = async () => {
    const missing = validateRequired(t, REQ);
    if (missing.length) { toast.error("Complete all required fields."); return; }
    setSaving(true);
    try {
      await api.put(`/trust-cases/${caseId}/trustee`, t);
      toast.success("Trustee saved");
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <div>
      <SectionHeader num={2} total={8} title="Trustee Information"
        subtitle="The trustee will manage the trust's assets. This is often one of the grantors." />

      <RoleDefinition
        role="Trustee"
        who_is="The person who manages the trust and follows your instructions."
        who_to_put="Someone you trust to handle money and property responsibly."
      />

      <div className="space-y-5" data-testid="trustee-form">
        <div className="grid sm:grid-cols-2 gap-4">
          <Field id="t-name" label="Full legal name" required>
            <Txt id="t-name" value={t.full_legal_name} onChange={(v) => set("full_legal_name", v)} testId="trustee-fullname-input" />
          </Field>
          <Field id="t-rel" label="Relationship to grantor" required>
            <Txt id="t-rel" value={t.relationship} onChange={(v) => set("relationship", v)} placeholder="Self, spouse, sibling, etc." testId="trustee-relationship-input" />
          </Field>
          <Field id="t-phone" label="Phone" required>
            <Txt id="t-phone" type="tel" value={t.phone} onChange={(v) => set("phone", v)} testId="trustee-phone-input" />
          </Field>
          <Field id="t-email" label="Email" required>
            <Txt id="t-email" type="email" value={t.email} onChange={(v) => set("email", v)} testId="trustee-email-input" />
          </Field>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Address (optional)</p>
          <AddressFields addr={t.address} onChange={(v) => set("address", v)} prefix="t-addr" />
        </div>
        <Field id="t-notes" label="Notes">
          <TA id="t-notes" value={t.notes} onChange={(v) => set("notes", v)} testId="trustee-notes-textarea" />
        </Field>
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="trustee-save-btn">
          {saving ? "Saving…" : "Save Trustee"}
        </button>
      </div>

      <NotesQuestionsBox caseId={caseId} section="trustee" />
    </div>
  );
}
