import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Pencil, Plus, Trash2, Sparkles, Info, Lock } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import AssetItemForm from "@/components/AssetItemForm";
import { BIZ_TYPE_OPTIONS, bizNeedsMoreInfo } from "@/components/AssetItemForm";
import { COPY, KIND_OPTIONS, KIND_LABEL, STATUS_LABEL, OTHER_KINDS, US_STATES } from "@/lib/assetCopy";

const ACCT_KINDS = new Set(["bank", "investment", "life_insurance"]);
const big = "w-full min-h-[56px] rounded-xl border-2 text-base font-semibold flex items-center justify-center gap-2 px-4";
const minInp = "w-full border border-[#E2E0DA] rounded-md px-3 py-2 text-base bg-white focus:outline-none focus:ring-2 focus:ring-bronze/40";

function NeedsMoreInfoBadge() {
  return (
    <span className="inline-block text-xs font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300" data-testid="needs-more-info-badge">
      Needs more info
    </span>
  );
}

function JustTypeIt({ caseId, onDone }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState(null);
  const [leftOut, setLeftOut] = useState([]);

  const organize = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/trust-cases/${caseId}/asset-items/organize`, { text });
      setFound(data.items || []);
      setLeftOut(data.retirement_left_out || []);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };
  const edit = (i, patch) => setFound(found.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  const editBi = (i, biPatch) => setFound(found.map((x, j) => j === i ? { ...x, business_info: { ...(x.business_info || {}), ...biPatch } } : x));

  const confirm = async () => {
    // Validate business items before saving
    for (const it of found) {
      if (it.kind === "business") {
        const bi = it.business_info || {};
        const missing = [];
        if (!bi.legal_name?.trim()) missing.push("Business name");
        if (!bi.biz_type?.trim()) missing.push("Type of business");
        if (!bi.state_formed?.trim()) missing.push("State it was formed in");
        if (!bi.ownership_pct?.trim()) missing.push("Percent you own");
        if (missing.length > 0) {
          toast.error(`Please fill in these fields to continue: ${missing.join(", ")}.`);
          return;
        }
      }
    }
    setBusy(true);
    try {
      await api.post(`/trust-cases/${caseId}/asset-items/confirm`, { text, items: found });
      toast.success("Saved.");
      onDone();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4 bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6" data-testid="just-type-it">
      <label className="block text-base font-semibold text-navy">{COPY.typeLabel}</label>
      <textarea rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={COPY.typeExample}
        className="w-full border border-[#E2E0DA] rounded-md p-3 text-base" data-testid="just-type-text" />
      <p className="text-sm text-[#64748B]">Tip: tap the microphone on your phone keyboard to talk instead of type.</p>
      <p className="text-sm text-amber-800">{COPY.noNumbers}</p>
      {!found && (
        <button type="button" onClick={organize} disabled={busy || text.trim().length < 3} className="btn-primary w-full min-h-[52px] text-base disabled:opacity-50" data-testid="organize-btn">
          <Sparkles className="h-5 w-5 inline mr-1" /> {busy ? "Working on it" : "Help me organize this"}
        </button>
      )}
      {found && (
        <div className="space-y-3" data-testid="organized-list">
          <p className="font-semibold text-navy">We found {found.length} item{found.length === 1 ? "" : "s"}. Please check each one and fix anything that is wrong.</p>
          {leftOut.length > 0 && (
            <p className="text-sm bg-sand-200/50 rounded p-3" data-testid="retirement-left-out">Retirement accounts stay in your name, so we left this one off. We will talk with you about it. ({leftOut.join(", ")})</p>
          )}
          {found.map((it, i) => (
            <div key={i} className="border border-[#E2E0DA] rounded-lg p-3 space-y-2" data-testid={`organized-item-${i}`}>
              <input className="w-full border rounded px-3 py-2 text-base" value={it.description} onChange={(e) => edit(i, { description: e.target.value })} />
              <select className="w-full border rounded px-3 py-2 text-base" value={it.kind} onChange={(e) => edit(i, { kind: e.target.value, other_kind: e.target.value === "other" ? "Something Else" : "", other_text: e.target.value === "other" ? it.description : "" })}>
                {KIND_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
              {it.kind === "other" && (
                <select className="w-full border rounded px-3 py-2 text-base" value={it.other_kind || "Something Else"} onChange={(e) => edit(i, { other_kind: e.target.value })}>
                  {OTHER_KINDS.map((o) => <option key={o}>{o}</option>)}
                </select>
              )}
              {/* Business mini-form for required fields */}
              {it.kind === "business" && (
                <div className="space-y-2 mt-2 p-3 bg-[#F8F7F4] rounded-lg border border-navy/10" data-testid={`organized-biz-fields-${i}`}>
                  <p className="text-sm font-semibold text-navy">Business details (required)</p>
                  <input className={minInp} placeholder="Business legal name *"
                    value={it.business_info?.legal_name || ""}
                    onChange={(e) => editBi(i, { legal_name: e.target.value })}
                    data-testid={`org-biz-name-${i}`} />
                  <select className={minInp}
                    value={it.business_info?.biz_type || ""}
                    onChange={(e) => editBi(i, { biz_type: e.target.value })}
                    data-testid={`org-biz-type-${i}`}>
                    <option value="">Type of business *</option>
                    {BIZ_TYPE_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                  </select>
                  <select className={minInp}
                    value={it.business_info?.state_formed || ""}
                    onChange={(e) => editBi(i, { state_formed: e.target.value })}
                    data-testid={`org-biz-state-${i}`}>
                    <option value="">State it was formed in *</option>
                    {US_STATES.map((s) => <option key={s}>{s}</option>)}
                  </select>
                  <input className={minInp} placeholder="Percent you own (e.g. 50) *"
                    value={it.business_info?.ownership_pct || ""}
                    onChange={(e) => editBi(i, { ownership_pct: e.target.value })}
                    inputMode="decimal"
                    data-testid={`org-biz-pct-${i}`} />
                </div>
              )}
              <button type="button" onClick={() => setFound(found.filter((_, j) => j !== i))} className="text-sm text-red-700 underline min-h-[40px]">Remove this one</button>
            </div>
          ))}
          <p className="text-sm text-[#64748B]">If a house, land, or vehicle is in a different state than your home, tap Edit after saving to change it.</p>
          <button type="button" onClick={confirm} disabled={busy || !found.length} className="btn-primary w-full min-h-[56px] text-base sticky bottom-2 disabled:opacity-50" data-testid="looks-right-btn">
            {busy ? "Saving" : "Looks right"}
          </button>
        </div>
      )}
    </div>
  );
}

export default function OwnStep({ caseId, reload }) {
  const [data, setData] = useState(null);
  const [mode, setMode] = useState(null);
  const [editing, setEditing] = useState(null);

  const load = useCallback(async () => {
    const { data } = await api.get(`/trust-cases/${caseId}/asset-items`);
    setData(data);
  }, [caseId]);
  useEffect(() => { load(); }, [load]);

  const done = async () => { setMode(null); setEditing(null); await load(); reload?.(); };
  const remove = async (it) => {
    if (!window.confirm(`Remove "${it.description}"?`)) return;
    await api.delete(`/trust-cases/${caseId}/asset-items/${it.id}`);
    done();
  };
  if (!data) return <p>Loading</p>;
  const items = data.items || [];
  const legacy = data.legacy_assets || [];

  return (
    <div className="space-y-5" data-testid="own-step">
      <h2 className="font-serif text-2xl sm:text-3xl text-navy">Tell us what you own</h2>
      <p className="text-base text-[#334155]">{COPY.intro}</p>
      <p className="text-base bg-sand-200/50 border border-bronze/30 rounded-lg p-3 flex gap-2" data-testid="retirement-note"><Info className="h-5 w-5 shrink-0 text-bronze" />{COPY.retirement}</p>

      {items.length > 0 && (
        <ul className="space-y-3" data-testid="asset-items-list">
          {items.map((it) => (
            <li key={it.id} className="bg-white border border-[#E2E0DA] rounded-xl p-4" data-testid={`asset-item-${it.id}`}>
              {editing === it.id ? (
                <AssetItemForm caseId={caseId} clientState={data.client_state} item={it} onSaved={done} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <p className="text-base font-semibold text-navy break-words">{it.description}</p>
                  <p className="text-sm text-[#64748B]">{KIND_LABEL[it.kind] || it.kind}{it.state ? `, ${it.state}` : ""}</p>
                  {/* Account number summary — only for bank, investment, life_insurance */}
                  {ACCT_KINDS.has(it.kind) && (
                    <p className="text-sm text-[#475569] flex items-center gap-1 mt-0.5" data-testid={`item-acct-hint-${it.id}`}>
                      <Lock className="h-3.5 w-3.5 shrink-0 text-bronze" />
                      {it.has_account_number
                        ? <>Account ending in <span className="font-semibold">{it.account_number_last4}</span> (tap Edit to view or change)</>
                        : <span className="text-amber-700">No account number saved yet. Tap Edit to add it.</span>}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className={`inline-block text-sm px-3 py-1 rounded-full ${it.status === "moved" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-900"}`}>{STATUS_LABEL[it.status]}</span>
                    {bizNeedsMoreInfo(it) && <NeedsMoreInfoBadge />}
                    {it.post_completion && (
                      <span className="inline-block text-xs px-3 py-1 rounded-full bg-blue-50 text-blue-800 border border-blue-200" data-testid={`pending-review-${it.id}`}>Pending team review</span>
                    )}
                  </div>
                  <div className="flex gap-3 mt-3">
                    <button onClick={() => setEditing(it.id)} className="flex-1 min-h-[48px] border rounded-lg inline-flex items-center justify-center gap-1" data-testid={`asset-edit-${it.id}`}><Pencil className="h-4 w-4" /> Edit</button>
                    <button onClick={() => remove(it)} className="flex-1 min-h-[48px] border rounded-lg inline-flex items-center justify-center gap-1 text-red-700" data-testid={`asset-remove-${it.id}`}><Trash2 className="h-4 w-4" /> Remove</button>
                  </div>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      {items.length > 0 && <p className="text-lg font-semibold text-emerald-800" data-testid="great-job">Great job. You listed {items.length} item{items.length === 1 ? "" : "s"}.</p>}

      {/* Legacy assets (read-only) */}
      {legacy.length > 0 && (
        <div className="bg-[#F6F4F0] border border-[#E2E0DA] rounded-xl p-4 space-y-2" data-testid="legacy-assets">
          <p className="text-sm font-semibold text-[#64748B]">Items from your earlier intake (read-only)</p>
          <ul className="space-y-1">
            {legacy.map((a, i) => (
              <li key={i} className="text-sm text-navy">{typeof a === "string" ? a : a.description}</li>
            ))}
          </ul>
        </div>
      )}

      {mode === "type" && <JustTypeIt caseId={caseId} onDone={done} />}
      {mode === "form" && <AssetItemForm caseId={caseId} clientState={data.client_state} onSaved={done} onCancel={() => setMode(null)} />}
      {!mode && (
        <div className="grid sm:grid-cols-2 gap-3">
          <button onClick={() => setMode("type")} className={`${big} border-bronze text-navy`} data-testid="mode-type-btn"><Sparkles className="h-5 w-5" /> Just type it</button>
          <button onClick={() => setMode("form")} className={`${big} border-navy text-navy`} data-testid="mode-form-btn"><Plus className="h-5 w-5" /> {items.length ? "Add another item" : "Add one item at a time"}</button>
        </div>
      )}
      <p className="text-sm text-[#64748B]">{COPY.initials}</p>
      <p className="text-xs text-[#94A3B8]">{COPY.infoOnly}</p>
    </div>
  );
}
