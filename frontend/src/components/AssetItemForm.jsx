import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Upload } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { KIND_OPTIONS, OTHER_KINDS, STATE_KINDS, EXAMPLES, US_STATES, METHOD_OTHER, METHOD_UNSURE, COPY, HELP } from "@/lib/assetCopy";

const inp = "w-full border border-[#E2E0DA] rounded-md px-3 py-3 text-base bg-white focus:outline-none focus:ring-2 focus:ring-bronze/40";
const lab = "block text-base font-semibold text-navy mb-1";

function Help({ text, id }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(!open)} className="text-sm text-bronze underline ml-1" data-testid={`help-${id}`}>What does this mean?</button>
      {open && <p className="text-sm text-[#475569] bg-sand-200/40 rounded p-2 mt-1">{text}</p>}
    </>
  );
}

const blank = (state) => ({ description: "", kind: "", other_kind: "", other_text: "", state, in_trust: "", not_done: true,
  date_delivered: "", method: "", method_other: "", attachment_doc_id: "" });

export default function AssetItemForm({ caseId, clientState, item, onSaved, onCancel }) {
  const [f, setF] = useState(() => ({ ...blank(clientState), ...(item || {}) }));
  const [methods, setMethods] = useState([]);
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const showState = STATE_KINDS.has(f.kind);
  const unsureAny = f.kind === "unsure" || f.in_trust === "unsure" || f.method === METHOD_UNSURE;

  useEffect(() => {
    if (!f.kind || f.not_done) return;
    api.get("/transfer-methods", { params: { kind: f.kind, state: showState ? f.state : clientState } })
      .then(({ data }) => setMethods(data.methods || [])).catch(() => setMethods([]));
  }, [f.kind, f.state, f.not_done, showState, clientState]);

  const upload = async (file) => {
    if (!file) return;
    const form = new FormData();
    form.append("doc_type", "supporting_file");
    form.append("file", file);
    try {
      const { data } = await api.post(`/trust-cases/${caseId}/documents`, form, { headers: { "Content-Type": "multipart/form-data" } });
      set("attachment_doc_id", data.id || data.document?.id || "");
      toast.success("Your paperwork was uploaded.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (item?.id) await api.put(`/trust-cases/${caseId}/asset-items/${item.id}`, f);
      else await api.post(`/trust-cases/${caseId}/asset-items`, f);
      toast.success("Saved.");
      onSaved?.();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <form onSubmit={save} className="space-y-5 bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6" data-testid="asset-item-form">
      <div>
        <label className={lab}>What is it? Describe it so a stranger could find it. *</label>
        <Help text={HELP.what} id="what" />
        <input className={inp} value={f.description} onChange={(e) => set("description", e.target.value)} required
          placeholder={EXAMPLES[f.kind] || "House at 12 Oak Street, in my city"} data-testid="asset-description" />
        <p className="text-sm text-amber-800 mt-1">{COPY.noNumbers}</p>
      </div>
      <div>
        <label className={lab}>What kind of item is this? *</label><Help text={HELP.kind} id="kind" />
        <select className={inp} value={f.kind} onChange={(e) => set("kind", e.target.value)} required data-testid="asset-kind">
          <option value="">Pick one</option>
          {KIND_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
        </select>
        {f.kind === "other" && (
          <div className="mt-3">
            <label className={lab}>Tell us what it is *</label>
            <select className={inp} value={f.other_kind} onChange={(e) => set("other_kind", e.target.value)} required data-testid="asset-other-kind">
              <option value="">Pick one</option>
              {OTHER_KINDS.map((o) => <option key={o}>{o}</option>)}
            </select>
            {f.other_kind === "Something Else" && (
              <input className={`${inp} mt-2`} value={f.other_text} onChange={(e) => set("other_text", e.target.value)} required
                placeholder="Please type what it is in your own words." data-testid="asset-other-text" />
            )}
          </div>
        )}
      </div>
      {showState && (
        <div>
          <label className={lab}>What state is it in? *</label><Help text={HELP.state(clientState)} id="state" />
          <select className={inp} value={f.state} onChange={(e) => set("state", e.target.value)} required data-testid="asset-state">
            <option value="">Pick a state</option>
            {US_STATES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
      )}
      <fieldset>
        <legend className={lab}>Do you want to put this in your trust?</legend><Help text={HELP.inTrust} id="in-trust" />
        {[["yes", "Yes, I want it in the trust."], ["unsure", "I am not sure yet. Please help me."]].map(([v, l]) => (
          <label key={v} className="flex items-center gap-3 py-2 text-base cursor-pointer">
            <input type="radio" name="in_trust" className="h-5 w-5" checked={f.in_trust === v} onChange={() => set("in_trust", v)} data-testid={`asset-in-trust-${v}`} /> {l}
          </label>
        ))}
      </fieldset>
      <div>
        <label className={lab}>What day did you move it into the trust?</label><Help text={HELP.date} id="date" />
        <label className="flex items-center gap-3 py-2 text-base cursor-pointer">
          <input type="checkbox" className="h-5 w-5" checked={f.not_done} onChange={(e) => set("not_done", e.target.checked)} data-testid="asset-not-done" />
          I have not done this yet.
        </label>
        {!f.not_done && (
          <>
            <input type="date" className={inp} value={f.date_delivered} onChange={(e) => set("date_delivered", e.target.value)} required data-testid="asset-date" />
            <p className="text-sm text-[#64748B] mt-1">{HELP.date}</p>
            <label className={`${lab} mt-4`}>What paper did you sign, or what form did you fill out, to move it into the trust? *</label>
            <Help text={HELP.method} id="method" />
            <select className={inp} value={f.method} onChange={(e) => set("method", e.target.value)} required data-testid="asset-method">
              <option value="">Pick one</option>
              {methods.map((m) => <option key={m.wording} value={m.wording}>{m.wording}</option>)}
              <option value={METHOD_OTHER}>Other</option>
              <option value={METHOD_UNSURE}>I am not sure.</option>
            </select>
            <p className="text-sm text-[#64748B] mt-1">This is the paperwork that makes it official.</p>
            {f.method === METHOD_OTHER && (
              <input className={`${inp} mt-2`} value={f.method_other} onChange={(e) => set("method_other", e.target.value)} required
                placeholder="Tell us what paper or form you used." data-testid="asset-method-other" />
            )}
          </>
        )}
      </div>
      <div>
        <label className={lab}>Have a copy of the paperwork? Upload it here.</label>
        <label className="inline-flex items-center gap-2 px-4 py-3 rounded-md border border-bronze/50 text-bronze cursor-pointer min-h-[48px]">
          <Upload className="h-5 w-5" /> {f.attachment_doc_id ? "Uploaded. Tap to change." : "Upload a PDF or photo"}
          <input type="file" accept="application/pdf,image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="asset-attachment" />
        </label>
        <p className="text-sm text-[#64748B] mt-1">Not required.</p>
      </div>
      {unsureAny && <p className="text-base text-emerald-800 bg-emerald-50 rounded p-3" data-testid="asset-unsure-msg">{COPY.unsure}</p>}
      <p className="text-sm text-[#64748B]">{COPY.initials}</p>
      <p className="text-xs text-[#94A3B8]">{COPY.infoOnly}</p>
      <div className="flex flex-col sm:flex-row gap-3 sticky bottom-0 bg-white pt-2">
        <button type="submit" disabled={saving} className="btn-primary w-full sm:w-auto min-h-[52px] text-base disabled:opacity-50" data-testid="asset-save-btn">
          {saving ? "Saving" : "Save this item"}
        </button>
        {onCancel && <button type="button" onClick={onCancel} className="min-h-[52px] px-4 text-base text-[#64748B]" data-testid="asset-cancel-btn">Cancel</button>}
      </div>
    </form>
  );
}
