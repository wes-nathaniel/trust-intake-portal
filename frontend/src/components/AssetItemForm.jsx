import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Upload, AlertTriangle, Eye, Lock } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { KIND_OPTIONS, OTHER_KINDS, STATE_KINDS, EXAMPLES, US_STATES, METHOD_OTHER, METHOD_UNSURE, COPY, HELP } from "@/lib/assetCopy";

// Same pattern as backend RETIREMENT_RE
const RETIREMENT_RE = /\b(ira|401\s*\(?k\)?|403\s*\(?b\)?|457\s*\(?b\)?\s*(plan|account)?|roth\s+(ira|401|account)|sep\s+ira|simple\s+ira|pension(\s+(plan|account))?|retirement\s+(account|plan|savings|fund)|tsp\s+account|thrift\s+savings)\b/i;

// Kinds that need a full account / policy number
const ACCT_KINDS = new Set(["bank", "investment", "life_insurance"]);

export const BIZ_TYPE_OPTIONS = [
  ["llc",        "LLC (Limited Liability Company)"],
  ["s_corp",     "S Corporation"],
  ["corp",       "C Corporation"],
  ["partnership","Partnership"],
  ["sole_prop",  "Sole Proprietorship"],
  ["nonprofit",  "Non-Profit"],
  ["other",      "Other"],
  ["unsure",     "I am not sure"],
];

export function bizNeedsMoreInfo(item) {
  if (item.kind !== "business") return false;
  const bi = item.business_info || {};
  return !bi.legal_name?.trim() || !bi.biz_type?.trim() || !bi.state_formed?.trim() || !bi.ownership_pct?.trim();
}

const inp = "w-full border border-[#E2E0DA] rounded-md px-3 py-3 text-base bg-white focus:outline-none focus:ring-2 focus:ring-bronze/40";
const inpErr = "w-full border-2 border-red-400 rounded-md px-3 py-3 text-base bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-300";
const lab = "block text-base font-semibold text-navy mb-1";

function Help({ text, id }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(!open)}
        className="text-sm text-bronze underline ml-1 min-h-[44px] inline-flex items-center px-1"
        data-testid={`help-${id}`}>What does this mean?</button>
      {open && <p className="text-sm text-[#475569] bg-sand-200/40 rounded p-2 mt-1">{text}</p>}
    </>
  );
}

const blank = (state) => ({
  description: "", kind: "", other_kind: "", other_text: "",
  state, in_trust: "", not_done: true, date_delivered: "",
  method: "", method_other: "", attachment_doc_id: "", account_number: ""
});

const blankBi = () => ({
  legal_name: "", dba: "", biz_type: "", state_formed: "", date_formed: "",
  ownership_pct: "", ein: "", biz_description: "",
  biz_address_street: "", biz_address_city: "", biz_address_state: "", biz_address_zip: "",
});

// Field label map used in validation messages
const BIZ_REQUIRED_LABELS = {
  legal_name:    "Business name",
  biz_type:      "Type of business",
  state_formed:  "State it was formed in",
  ownership_pct: "Percent you own",
};

export default function AssetItemForm({ caseId, clientState, item, onSaved, onCancel }) {
  const [f, setF] = useState(() => ({ ...blank(clientState), ...(item || {}), account_number: "" }));
  const [bi, setBi] = useState(() => item?.business_info ? { ...blankBi(), ...item.business_info, ein: "" } : blankBi());
  const [missingBiz, setMissingBiz] = useState([]); // list of field keys missing
  const [methods, setMethods] = useState([]);
  const [saving, setSaving] = useState(false);

  // Account number reveal state
  const [showAcctInput, setShowAcctInput] = useState(!item?.has_account_number);
  const [revealedNumber, setRevealedNumber] = useState("");
  const [revealing, setRevealing] = useState(false);
  const [showRevealed, setShowRevealed] = useState(false);

  // EIN reveal state (business items)
  const [showEinInput, setShowEinInput] = useState(!item?.business_info?.has_ein);
  const [revealedEin, setRevealedEin] = useState("");
  const [revealingEin, setRevealingEin] = useState(false);
  const [showRevealedEin, setShowRevealedEin] = useState(false);

  // Refs for scrolling to first missing business field
  const legalNameRef  = useRef(null);
  const bizTypeRef    = useRef(null);
  const stateFormedRef = useRef(null);
  const ownershipRef  = useRef(null);
  const bizValidRef   = useRef(null);

  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const setBiField = (k, v) => { setBi((x) => ({ ...x, [k]: v })); setMissingBiz((m) => m.filter((f) => f !== k)); };
  const showState = STATE_KINDS.has(f.kind);
  const unsureAny = f.kind === "unsure" || f.in_trust === "unsure" || f.method === METHOD_UNSURE;
  const isRetirement = RETIREMENT_RE.test(f.description);
  const needsAcct = ACCT_KINDS.has(f.kind);
  const isBusiness = f.kind === "business";

  useEffect(() => {
    if (!f.kind || f.not_done) return;
    api.get("/transfer-methods", { params: { kind: f.kind, state: showState ? f.state : clientState } })
      .then(({ data }) => setMethods(data.methods || [])).catch(() => setMethods([]));
  }, [f.kind, f.state, f.not_done, showState, clientState]);

  // When kind changes away from ACCT_KINDS, reset account number UI
  useEffect(() => {
    if (!needsAcct) {
      setShowAcctInput(false);
      setRevealedNumber("");
      setF(x => ({ ...x, account_number: "" }));
    }
  }, [f.kind, needsAcct]);

  // When kind changes away from business, clear missing flags
  useEffect(() => {
    if (!isBusiness) setMissingBiz([]);
  }, [f.kind, isBusiness]);

  const revealNumber = async () => {
    if (!item?.id) return;
    setRevealing(true);
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/asset-items/${item.id}/account-number`);
      setRevealedNumber(data.account_number || "");
      setShowRevealed(true);
    } catch {
      toast.error("Could not load your account number. Please try again.");
    } finally {
      setRevealing(false);
    }
  };

  const revealEin = async () => {
    if (!item?.id) return;
    setRevealingEin(true);
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/asset-items/${item.id}/ein`);
      setRevealedEin(data.ein || "");
      setShowRevealedEin(true);
    } catch {
      toast.error("Could not load the EIN. Please try again.");
    } finally {
      setRevealingEin(false);
    }
  };

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

  const validateBusiness = () => {
    const missing = ["legal_name", "biz_type", "state_formed", "ownership_pct"].filter(k => !bi[k]?.trim());
    setMissingBiz(missing);
    if (missing.length > 0) {
      // Scroll to validation message
      if (bizValidRef.current) bizValidRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
      return false;
    }
    return true;
  };

  const save = async (e) => {
    e.preventDefault();
    if (isBusiness && !validateBusiness()) return;
    // Client-side guard: account number required when marking as moved for ACCT_KINDS
    if (needsAcct && !f.not_done && !f.account_number && !item?.has_account_number) {
      toast.error("Please add the full account number before marking this item as moved into the trust.");
      return;
    }
    setSaving(true);
    try {
      const payload = { ...f };
      if (isBusiness) payload.business_info = { ...bi };
      if (item?.id) await api.put(`/trust-cases/${caseId}/asset-items/${item.id}`, payload);
      else await api.post(`/trust-cases/${caseId}/asset-items`, payload);
      toast.success("Saved.");
      onSaved?.();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const fieldClass = (key) => missingBiz.includes(key) ? inpErr : inp;

  return (
    <form onSubmit={save} className="space-y-5 bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-6" data-testid="asset-item-form">
      <div>
        <label className={lab}>What is it? Describe it so a stranger could find it. *</label>
        <Help text={HELP.what} id="what" />
        <input className={inp} value={f.description} onChange={(e) => set("description", e.target.value)} required
          placeholder={EXAMPLES[f.kind] || "House at 12 Oak Street, in my city"} data-testid="asset-description" />
        <p className="text-sm text-amber-800 mt-1">{COPY.noNumbers}</p>
        {isRetirement && (
          <div className="flex gap-2 items-start bg-amber-50 border border-amber-300 rounded-lg p-3 mt-2" data-testid="retirement-warning">
            <AlertTriangle className="h-5 w-5 shrink-0 text-amber-700 mt-0.5" />
            <p className="text-sm text-amber-900">
              Retirement accounts (IRA, 401k, 403b, 457b, pension, and similar) stay in your name and cannot go into your trust. We will talk with you about them separately. Please do not add this here.
            </p>
          </div>
        )}
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

      {/* ---- Business Information section (only for kind === "business") ---- */}
      {isBusiness && (
        <div className="rounded-xl border border-navy/20 bg-[#F8F7F4] p-4 space-y-4" data-testid="business-info-section">
          <p className="text-base font-semibold text-navy">Business information</p>

          {/* Validation message */}
          {missingBiz.length > 0 && (
            <div ref={bizValidRef} className="rounded-lg bg-amber-50 border border-amber-300 p-3" data-testid="biz-validation-msg">
              <p className="text-sm text-amber-900 font-medium">
                Please fill in these fields to continue: {missingBiz.map(k => BIZ_REQUIRED_LABELS[k]).join(", ")}.
              </p>
            </div>
          )}

          {/* Business legal name (required) */}
          <div>
            <label className={lab}>Business legal name *</label>
            <input
              ref={legalNameRef}
              className={fieldClass("legal_name")}
              value={bi.legal_name}
              onChange={(e) => setBiField("legal_name", e.target.value)}
              placeholder="Smith Consulting LLC"
              data-testid="biz-legal-name"
            />
          </div>

          {/* Type of business (required — "I am not sure" is a valid answer) */}
          <div>
            <label className={lab}>Type of business *</label>
            <select
              ref={bizTypeRef}
              className={fieldClass("biz_type")}
              value={bi.biz_type}
              onChange={(e) => setBiField("biz_type", e.target.value)}
              data-testid="biz-type"
            >
              <option value="">Pick one</option>
              {BIZ_TYPE_OPTIONS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </div>

          {/* State formed (required) */}
          <div>
            <label className={lab}>State where it was formed *</label>
            <select
              ref={stateFormedRef}
              className={fieldClass("state_formed")}
              value={bi.state_formed}
              onChange={(e) => setBiField("state_formed", e.target.value)}
              data-testid="biz-state-formed"
            >
              <option value="">Pick a state</option>
              {US_STATES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>

          {/* Percent owned (required) */}
          <div>
            <label className={lab}>Percent you own *</label>
            <input
              ref={ownershipRef}
              className={fieldClass("ownership_pct")}
              value={bi.ownership_pct}
              onChange={(e) => setBiField("ownership_pct", e.target.value)}
              placeholder="50"
              inputMode="decimal"
              data-testid="biz-ownership-pct"
            />
            <p className="text-sm text-[#64748B] mt-1">Just the number, for example: 100, 50, 33.3</p>
          </div>

          {/* DBA (optional) */}
          <div>
            <label className={lab}>Doing business as (DBA) <span className="font-normal text-[#94A3B8]">optional</span></label>
            <input className={inp} value={bi.dba} onChange={(e) => setBiField("dba", e.target.value)}
              placeholder="If the business uses a different name" data-testid="biz-dba" />
          </div>

          {/* Date formed (optional) */}
          <div>
            <label className={lab}>Date formed <span className="font-normal text-[#94A3B8]">optional</span></label>
            <input type="date" className={inp} value={bi.date_formed} onChange={(e) => setBiField("date_formed", e.target.value)} data-testid="biz-date-formed" />
          </div>

          {/* EIN — protected, same pattern as account number */}
          <div className="rounded-lg border border-[#E2E0DA] bg-white p-3 space-y-2" data-testid="biz-ein-section">
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-bronze shrink-0" />
              <label className={`${lab} mb-0`}>EIN (Employer Identification Number) <span className="font-normal text-[#94A3B8]">optional</span></label>
            </div>
            <p className="text-sm text-[#475569]">Type it only here, not in the description. It is protected the same way as a Social Security number.</p>

            {/* Existing EIN — masked view */}
            {item?.business_info?.has_ein && !showEinInput && (
              <div className="space-y-2">
                {showRevealedEin ? (
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-base bg-white border border-[#E2E0DA] rounded-md px-3 py-2 select-all" data-testid="biz-ein-revealed">
                      {revealedEin}
                    </span>
                    <button type="button" onClick={() => { setShowRevealedEin(false); setRevealedEin(""); }}
                      className="text-sm text-[#64748B] underline min-h-[44px] px-2" data-testid="biz-ein-hide-btn">Hide</button>
                    <button type="button" onClick={() => { setShowEinInput(true); setShowRevealedEin(false); setRevealedEin(""); }}
                      className="text-sm text-bronze underline min-h-[44px] px-2" data-testid="biz-ein-change-btn">Change</button>
                  </div>
                ) : (
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="text-base text-navy font-medium" data-testid="biz-ein-last4">
                      EIN ending in {item.business_info.ein_last4}
                    </span>
                    <button type="button" onClick={revealEin} disabled={revealingEin}
                      className="inline-flex items-center gap-1 text-sm text-bronze underline min-h-[44px] px-2" data-testid="biz-ein-show-btn">
                      <Eye className="h-4 w-4" /> {revealingEin ? "Loading" : "Show"}
                    </button>
                    <button type="button" onClick={() => setShowEinInput(true)}
                      className="text-sm text-[#64748B] underline min-h-[44px] px-2" data-testid="biz-ein-change-btn">Change</button>
                  </div>
                )}
              </div>
            )}

            {/* EIN input — when no existing EIN or when user taps Change */}
            {(!item?.business_info?.has_ein || showEinInput) && (
              <div className="space-y-1">
                <input
                  className={inp}
                  value={bi.ein}
                  onChange={(e) => setBiField("ein", e.target.value)}
                  placeholder="XX-XXXXXXX"
                  autoComplete="off"
                  inputMode="numeric"
                  data-testid="biz-ein-input"
                />
                {item?.business_info?.has_ein && (
                  <button type="button" onClick={() => { setShowEinInput(false); setBiField("ein", ""); }}
                    className="text-sm text-[#64748B] underline min-h-[44px] px-1" data-testid="biz-ein-cancel-change-btn">
                    Keep existing EIN
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Full account number — only for bank, investment, life_insurance */}
      {needsAcct && (
        <div className="rounded-xl border border-[#E2E0DA] bg-[#FAFAF8] p-4 space-y-2" data-testid="account-number-section">
          <div className="flex items-center gap-2">
            <Lock className="h-4 w-4 text-bronze shrink-0" />
            <label className={`${lab} mb-0`}>Full account number (optional now)</label>
          </div>
          <p className="text-sm text-[#475569]">
            This lets us identify your account exactly on your trust papers. Type it only in this box, not in the description. It is protected.
          </p>
          {item?.has_account_number && !showAcctInput && (
            <div className="space-y-2">
              {showRevealed ? (
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-base bg-white border border-[#E2E0DA] rounded-md px-3 py-2 select-all" data-testid="account-number-revealed">
                    {revealedNumber}
                  </span>
                  <button type="button" onClick={() => { setShowRevealed(false); setRevealedNumber(""); }}
                    className="text-sm text-[#64748B] underline min-h-[44px] px-2" data-testid="account-number-hide-btn">Hide</button>
                  <button type="button" onClick={() => { setShowAcctInput(true); setShowRevealed(false); setRevealedNumber(""); }}
                    className="text-sm text-bronze underline min-h-[44px] px-2" data-testid="account-number-change-btn">Change</button>
                </div>
              ) : (
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-base text-navy font-medium" data-testid="account-number-last4">
                    Account ending in {item.account_number_last4}
                  </span>
                  <button type="button" onClick={revealNumber} disabled={revealing}
                    className="inline-flex items-center gap-1 text-sm text-bronze underline min-h-[44px] px-2" data-testid="account-number-show-btn">
                    <Eye className="h-4 w-4" /> {revealing ? "Loading" : "Show"}
                  </button>
                  <button type="button" onClick={() => setShowAcctInput(true)}
                    className="text-sm text-[#64748B] underline min-h-[44px] px-2" data-testid="account-number-change-btn">Change</button>
                </div>
              )}
            </div>
          )}
          {(!item?.has_account_number || showAcctInput) && (
            <div className="space-y-1">
              <input
                className={inp}
                value={f.account_number}
                onChange={(e) => set("account_number", e.target.value)}
                placeholder={f.kind === "life_insurance" ? "Policy number" : "Account number"}
                autoComplete="off"
                data-testid="account-number-input"
              />
              {item?.has_account_number && (
                <button type="button" onClick={() => { setShowAcctInput(false); set("account_number", ""); }}
                  className="text-sm text-[#64748B] underline min-h-[44px] px-1" data-testid="account-number-cancel-change-btn">
                  Keep existing number
                </button>
              )}
            </div>
          )}
        </div>
      )}

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
          <label key={v} className="flex items-center gap-3 py-3 text-base cursor-pointer min-h-[52px]">
            <input type="radio" name="in_trust" className="h-5 w-5 shrink-0 accent-[#C5A880]" checked={f.in_trust === v} onChange={() => set("in_trust", v)} data-testid={`asset-in-trust-${v}`} /> {l}
          </label>
        ))}
      </fieldset>
      <div>
        <label className={lab}>What day did you move it into the trust?</label><Help text={HELP.date} id="date" />
        <label className="flex items-center gap-3 py-3 text-base cursor-pointer min-h-[52px]">
          <input type="checkbox" className="h-5 w-5 shrink-0 accent-[#C5A880]" checked={f.not_done} onChange={(e) => set("not_done", e.target.checked)} data-testid="asset-not-done" />
          I have not done this yet.
        </label>
        {!f.not_done && (
          <>
            {needsAcct && !f.account_number && !item?.has_account_number && (
              <div className="flex gap-2 items-start bg-amber-50 border border-amber-300 rounded-lg p-3 mb-3" data-testid="acct-required-warning">
                <AlertTriangle className="h-5 w-5 shrink-0 text-amber-700 mt-0.5" />
                <p className="text-sm text-amber-900">Please add the full account number above before marking this item as moved into the trust.</p>
              </div>
            )}
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

      {/* File upload — hidden for business items */}
      {!isBusiness && (
        <div>
          <label className={lab}>Have a copy of the paperwork? Upload it here.</label>
          <label className="inline-flex items-center gap-2 px-4 py-3 rounded-md border border-bronze/50 text-bronze cursor-pointer min-h-[48px]">
            <Upload className="h-5 w-5" /> {f.attachment_doc_id ? "Uploaded. Tap to change." : "Upload a PDF or photo"}
            <input type="file" accept="application/pdf,image/*" className="hidden" onChange={(e) => upload(e.target.files?.[0])} data-testid="asset-attachment" />
          </label>
          <p className="text-sm text-[#64748B] mt-1">Not required.</p>
        </div>
      )}

      {unsureAny && <p className="text-base text-emerald-800 bg-emerald-50 rounded p-3" data-testid="asset-unsure-msg">{COPY.unsure}</p>}
      <p className="text-sm text-[#64748B]">{COPY.initials}</p>
      <p className="text-xs text-[#94A3B8]">{COPY.infoOnly}</p>
      <div className="flex flex-col sm:flex-row gap-3 sticky bottom-0 bg-white pt-2">
        <button type="submit" disabled={saving || isRetirement} className="btn-primary w-full sm:w-auto min-h-[52px] text-base disabled:opacity-50" data-testid="asset-save-btn">
          {saving ? "Saving" : "Save this item"}
        </button>
        {onCancel && <button type="button" onClick={onCancel} className="min-h-[52px] px-6 text-base text-[#64748B] border border-[#E2E0DA] rounded-xl" data-testid="asset-cancel-btn">Cancel</button>}
      </div>
    </form>
  );
}
