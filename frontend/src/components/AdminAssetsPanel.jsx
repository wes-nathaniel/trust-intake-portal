import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Pencil, ArrowRightLeft, AlertTriangle, Lock, Eye } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import AssetItemForm from "@/components/AssetItemForm";
import { bizNeedsMoreInfo } from "@/components/AssetItemForm";
import { KIND_LABEL, STATUS_LABEL, METHOD_OTHER, METHOD_UNSURE } from "@/lib/assetCopy";

const ACCT_KINDS = new Set(["bank", "investment", "life_insurance"]);
const TABS = [["summary", "Summary"], ["items", "Items"], ["schedule", "Schedule A"]];
const badge = "text-xs font-semibold px-2 py-1 rounded-full";

function NeedsMoreInfoBadge({ itemId }) {
  return (
    <span className={`${badge} bg-amber-100 text-amber-900 border border-amber-300`} data-testid={`needs-more-info-${itemId}`}>
      Needs more info
    </span>
  );
}

function EinReveal({ caseId, item }) {
  const [revealed, setRevealed] = useState("");
  const [revealing, setRevealing] = useState(false);
  const [show, setShow] = useState(false);
  if (item.kind !== "business") return null;
  const bi = item.business_info || {};

  const reveal = async () => {
    if (revealed) { setShow(true); return; }
    setRevealing(true);
    try {
      const { data } = await api.get(`/admin/trust-cases/${caseId}/asset-items/${item.id}/ein`);
      setRevealed(data.ein || "");
      setShow(true);
    } catch { toast.error("Could not load EIN."); }
    finally { setRevealing(false); }
  };

  if (!bi.has_ein) {
    return <span className={`${badge} bg-orange-100 text-orange-900 border border-orange-300`} data-testid={`ein-missing-badge-${item.id}`}>EIN not provided</span>;
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" data-testid={`ein-reveal-${item.id}`}>
      <Lock className="h-3 w-3 text-bronze" />
      {show && revealed ? (
        <>
          <span className="font-mono font-semibold">{revealed}</span>
          <button type="button" onClick={() => setShow(false)} className="underline text-[#64748B] min-h-[32px] px-1" data-testid={`ein-hide-${item.id}`}>Hide</button>
        </>
      ) : (
        <>
          <span className="text-navy">EIN ••••{bi.ein_last4}</span>
          <button type="button" onClick={reveal} disabled={revealing}
            className="underline text-bronze inline-flex items-center gap-0.5 min-h-[32px] px-1" data-testid={`ein-reveal-btn-${item.id}`}>
            <Eye className="h-3 w-3" />{revealing ? "Loading" : "Reveal"}
          </button>
        </>
      )}
    </span>
  );
}

function Badges({ f }) {
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {f.other && <span className={`${badge} bg-purple-100 text-purple-800`} data-testid="badge-other">Other</span>}
      {f.unsure && <span className={`${badge} bg-amber-100 text-amber-900`} data-testid="badge-unsure">I am not sure</span>}
      {f.review && <span className={`${badge} bg-red-100 text-red-800`} data-testid="badge-review">Wes will review this one</span>}
    </div>
  );
}

function Summary({ s }) {
  return (
    <div className="space-y-4 text-sm" data-testid="intake-summary">
      <p><b>Client state (Grantor 1 address):</b> {s.client_state || "not entered yet"}</p>
      <div>
        <p className="font-semibold text-navy mb-1">What the client typed, exactly as written</p>
        {s.original_text.length === 0 ? <p className="text-[#94A3B8]">Nothing typed yet.</p> : s.original_text.map((t, i) => (
          <blockquote key={i} className="whitespace-pre-wrap break-words border-l-4 border-bronze/50 bg-sand-200/30 p-3 rounded mb-2" data-testid={`original-text-${i}`}>{t.text}</blockquote>
        ))}
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="border rounded-lg p-3"><p className="font-semibold mb-1">By kind ({s.total_items} items)</p>
          {Object.entries(s.by_kind).map(([k, v]) => <p key={k}>{k}: <b>{v.count}</b></p>)}</div>
        <div className="border rounded-lg p-3"><p className="font-semibold mb-1">By state</p>
          {Object.entries(s.by_state).map(([k, v]) => <p key={k}>{k}: <b>{v}</b></p>)}
          {s.states_with_property.length > 1 && <p className="text-red-700 font-semibold mt-1">Property in more than one state</p>}</div>
      </div>
      {s.has_business && <p className="text-navy font-semibold">Client owns a business.</p>}
      {s.unsure_items.length > 0 && <p><b>Unsure:</b> {s.unsure_items.join("; ")}</p>}
      {s.other_items.length > 0 && <p><b>Other:</b> {s.other_items.join("; ")}</p>}
      <div>
        <p className="font-semibold text-navy mb-1">Old Assets step entries (read only)</p>
        {s.legacy_assets.length === 0 ? <p className="text-[#94A3B8]">None.</p> : (
          <ul className="space-y-1" data-testid="legacy-assets">
            {s.legacy_assets.map((a) => (
              <li key={a.id} className="border rounded p-2 break-words">{a.asset_type}: {a.institution_name || a.property_address || "(no name)"}{a.estimated_value ? `, $${a.estimated_value}` : ""}{a.notes ? `. ${a.notes}` : ""}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function AccountNumberReveal({ caseId, item }) {
  const [revealed, setRevealed] = useState("");
  const [revealing, setRevealing] = useState(false);
  const [show, setShow] = useState(false);

  if (!ACCT_KINDS.has(item.kind)) return null;

  const reveal = async () => {
    if (revealed) { setShow(true); return; }
    setRevealing(true);
    try {
      const { data } = await api.get(`/admin/trust-cases/${caseId}/asset-items/${item.id}/account-number`);
      setRevealed(data.account_number || "");
      setShow(true);
    } catch { toast.error("Could not load account number."); }
    finally { setRevealing(false); }
  };

  if (!item.has_account_number) {
    return (
      <span className={`${badge} bg-orange-100 text-orange-900 border border-orange-300`} data-testid={`acct-missing-badge-${item.id}`}>
        Full account number needed
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 text-xs" data-testid={`acct-reveal-${item.id}`}>
      <Lock className="h-3 w-3 text-bronze" />
      {show && revealed ? (
        <>
          <span className="font-mono font-semibold">{revealed}</span>
          <button type="button" onClick={() => setShow(false)} className="underline text-[#64748B] min-h-[32px] px-1" data-testid={`acct-hide-${item.id}`}>Hide</button>
        </>
      ) : (
        <>
          <span className="text-navy">••••{item.account_number_last4}</span>
          <button type="button" onClick={reveal} disabled={revealing}
            className="underline text-bronze inline-flex items-center gap-0.5 min-h-[32px] px-1" data-testid={`acct-reveal-btn-${item.id}`}>
            <Eye className="h-3 w-3" />{revealing ? "Loading" : "Reveal"}
          </button>
        </>
      )}
    </span>
  );
}

function ScheduleA({ caseId, sa }) {
  const [includeAcctNums, setIncludeAcctNums] = useState(true);

  const exportData = async (format) => {
    const { data } = await api.get(`/admin/trust-cases/${caseId}/schedule-a`, {
      params: { format, include_account_numbers: includeAcctNums },
      responseType: format === "csv" ? "blob" : "json"
    });
    const blob = format === "csv" ? data : new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `schedule_a_${caseId.slice(0, 8)}.${format}`;
    a.click();
  };
  const Part = ({ title, rows }) => (
    <div className="mb-4">
      <p className="font-semibold text-navy mb-2">{title}</p>
      {rows.length === 0 ? <p className="text-sm text-[#94A3B8]">No items moved into the trust yet.</p> : rows.map((r) => (
        <div key={r.number} className="border rounded-lg p-3 mb-2 text-sm grid sm:grid-cols-[40px_2fr_1fr_2fr_1fr] gap-1 sm:gap-3" data-testid={`schedule-row-${r.number}`}>
          <b>{r.number}.</b>
          <span><span className="sm:hidden text-[#64748B]">Description: </span>{r.description_of_property}</span>
          <span><span className="sm:hidden text-[#64748B]">Date: </span>{r.date_delivered}</span>
          <span><span className="sm:hidden text-[#64748B]">Method: </span>{r.instrument_or_method_of_transfer}</span>
          <span className="text-[#94A3B8]"><span className="sm:hidden">Initials: </span>________</span>
        </div>
      ))}
    </div>
  );
  return (
    <div data-testid="schedule-a-preview">
      <p className="text-sm italic text-[#64748B] mb-3">This is a preview. Your trustee will sign and initial the final copy.</p>
      <Part title="Part I" rows={sa.part_i} />
      <Part title="Part II" rows={sa.part_ii} />
      <div className="border-t border-[#E2E0DA] pt-3 mt-2 space-y-3">
        <label className="flex items-center gap-2 cursor-pointer min-h-[44px]" data-testid="include-acct-nums-toggle">
          <input type="checkbox" className="h-5 w-5 accent-[#C5A880]" checked={includeAcctNums} onChange={(e) => setIncludeAcctNums(e.target.checked)} />
          <span className="text-sm font-semibold text-navy">Include full account numbers in export</span>
        </label>
        <p className="text-xs text-[#64748B]">When checked, the full account number appears in the Description column of the exported file. The preview above never shows them.</p>
        <div className="flex flex-col sm:flex-row gap-2">
          <button onClick={() => exportData("csv")} className="btn-primary min-h-[48px] inline-flex items-center justify-center gap-2" data-testid="export-schedule-csv"><Download className="h-4 w-4" /> Export Schedule A data (CSV)</button>
          <button onClick={() => exportData("json")} className="min-h-[48px] border rounded-md px-4 inline-flex items-center justify-center gap-2" data-testid="export-schedule-json"><Download className="h-4 w-4" /> JSON</button>
        </div>
      </div>
    </div>
  );
}

export default function AdminAssetsPanel({ caseId }) {
  const [tab, setTab] = useState("summary");
  const [d, setD] = useState(null);
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [togglingPart, setTogglingPart] = useState(null);
  const [alertEmail, setAlertEmail] = useState("");
  const [alertEmailSaving, setAlertEmailSaving] = useState(false);
  const [loginAlertEnabled, setLoginAlertEnabled] = useState(false);
  const [loginAlertSaving, setLoginAlertSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [items, summary, sa, notif] = await Promise.all([
        api.get(`/trust-cases/${caseId}/asset-items`),
        api.get(`/admin/trust-cases/${caseId}/intake-summary`),
        api.get(`/admin/trust-cases/${caseId}/schedule-a`),
        api.get("/admin/notification-settings"),
      ]);
      setD({ items: items.data, summary: summary.data, sa: sa.data });
      setAlertEmail(notif.data.admin_alert_email || "");
      setLoginAlertEnabled(!!notif.data.login_alert_enabled);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [caseId]);
  useEffect(() => { load(); }, [load]);

  const saveAlertEmail = async () => {
    setAlertEmailSaving(true);
    try {
      await api.patch("/admin/notification-settings", { admin_alert_email: alertEmail.trim() });
      toast.success("Alert email saved.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setAlertEmailSaving(false); }
  };

  const toggleLoginAlert = async (enabled) => {
    setLoginAlertSaving(true);
    try {
      await api.patch("/admin/notification-settings", { login_alert_enabled: enabled });
      setLoginAlertEnabled(enabled);
      toast.success(enabled ? "Login alerts turned on." : "Login alerts turned off.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoginAlertSaving(false); }
  };

  const togglePart = async (itemId, currentPart) => {
    const newPart = currentPart === "I" ? "II" : "I";
    setTogglingPart(itemId);
    try {
      await api.patch(`/admin/trust-cases/${caseId}/asset-items/${itemId}/part`, { part: newPart });
      toast.success(`Moved to Part ${newPart}`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setTogglingPart(null); }
  };

  if (!d) return null;
  const items = d.items.items || [];
  const unreleased = items.some((i) => i.has_unreleased_edits);
  const postCompletion = items.filter((i) => i.post_completion);
  const methodLabel = (i) => (i.method === METHOD_OTHER ? i.method_other : i.method === METHOD_UNSURE ? "I am not sure" : i.method) || "";

  return (
    <section className="mb-6 bg-white border border-[#E2E0DA] rounded-xl p-4 sm:p-5" data-testid="admin-assets-panel">
      <h2 className="font-serif text-xl text-navy mb-3">What the client owns</h2>

      {/* Alert: items added after trust was signed */}
      {postCompletion.length > 0 && (
        <div className="mb-3 p-3 rounded-lg bg-blue-50 border border-blue-300 flex gap-2 items-start" data-testid="post-completion-alert">
          <AlertTriangle className="h-5 w-5 shrink-0 text-blue-700 mt-0.5" />
          <p className="text-sm text-blue-900">
            <strong>{postCompletion.length} item{postCompletion.length > 1 ? "s" : ""} added after the trust was signed.</strong> Review each one and set status to "Moved into trust" to include in Schedule A.
          </p>
        </div>
      )}

      {/* Alert: retirement items in list */}
      {(d.summary.retirement_items_in_list || []).length > 0 && (
        <div className="mb-3 p-3 rounded-lg bg-red-50 border border-red-300 text-sm text-red-900" data-testid="retirement-items-alert">
          <strong>Retirement accounts detected in the item list (must be removed):</strong> {d.summary.retirement_items_in_list.join(", ")}
        </div>
      )}

      <div className="flex gap-1 mb-4 overflow-x-auto" role="tablist">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={`min-h-[44px] px-4 rounded-md text-sm font-semibold ${tab === k ? "bg-navy text-white" : "bg-sand-200/50 text-navy"}`} data-testid={`assets-tab-${k}`}>{l}</button>
        ))}
      </div>
      {tab === "summary" && (
        <div className="space-y-5">
          <Summary s={d.summary} />
          {/* Editable alert email */}
          <div className="border-t border-[#E2E0DA] pt-4 space-y-4">
            <div>
              <p className="text-sm font-semibold text-navy mb-1">Alert email for asset changes</p>
              <p className="text-xs text-[#64748B] mb-2">You receive an email here whenever a client adds, changes, or removes an asset.</p>
              <div className="flex gap-2">
                <input
                  type="email"
                  className="flex-1 border border-[#E2E0DA] rounded-md px-3 py-2 text-sm"
                  value={alertEmail}
                  onChange={(e) => setAlertEmail(e.target.value)}
                  placeholder="wes@igchq.com"
                  data-testid="alert-email-input"
                />
                <button
                  onClick={saveAlertEmail}
                  disabled={alertEmailSaving}
                  className="px-4 py-2 bg-navy text-white rounded-md text-sm font-semibold min-h-[44px] disabled:opacity-50"
                  data-testid="alert-email-save-btn"
              >
                {alertEmailSaving ? "Saving" : "Save"}
              </button>
            </div>

            {/* Login alert toggle */}
            <div className="pt-3 border-t border-[#E2E0DA]">
              <p className="text-sm font-semibold text-navy mb-1">Alert me when a client logs in</p>
              <p className="text-xs text-[#64748B] mb-2">Sends one email per client per hour to the alert email above. Default is off.</p>
              <label className="inline-flex items-center gap-3 cursor-pointer min-h-[44px]" data-testid="login-alert-toggle-label">
                <button
                  type="button"
                  role="switch"
                  aria-checked={loginAlertEnabled}
                  disabled={loginAlertSaving}
                  onClick={() => toggleLoginAlert(!loginAlertEnabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-bronze/40 disabled:opacity-50 ${loginAlertEnabled ? "bg-emerald-500" : "bg-[#CBD5E1]"}`}
                  data-testid="login-alert-toggle">
                  <span className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${loginAlertEnabled ? "translate-x-5" : "translate-x-0.5"}`} />
                </button>
                <span className="text-sm text-navy">{loginAlertEnabled ? "On" : "Off"}</span>
              </label>
            </div>
          </div>
        </div>
      </div>
      )}
      {tab === "schedule" && <ScheduleA caseId={caseId} sa={d.sa} />}
      {tab === "items" && (
        <div className="space-y-3" data-testid="admin-asset-items">
          {unreleased && (
            <div className="p-3 rounded-md bg-amber-50 border border-amber-300 text-sm flex flex-col sm:flex-row gap-2 sm:items-center justify-between">
              <span data-testid="asset-edits-held-note">Some edits are hidden from the client. Use the Release button at the bottom of the screen to show them.</span>
            </div>
          )}
          {/* Add item for client */}
          {adding ? (
            <AssetItemForm
              caseId={caseId}
              clientState={d.items.client_state}
              onSaved={() => { setAdding(false); load(); }}
              onCancel={() => setAdding(false)}
            />
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="w-full min-h-[48px] border-2 border-dashed border-navy/30 rounded-lg text-sm text-navy/70 hover:border-navy hover:text-navy font-semibold flex items-center justify-center gap-2"
              data-testid="admin-add-asset-btn"
            >
              + Add item for this client
            </button>
          )}
          {items.length === 0 && !adding && <p className="text-sm text-[#94A3B8]">The client has not listed anything yet.</p>}
          {items.map((i) => (
            <div key={i.id} className={`border rounded-lg p-3 text-sm ${i.post_completion ? "border-blue-300 bg-blue-50/40" : ""}`} data-testid={`admin-asset-${i.id}`}>
              {editing === i.id ? (
                <AssetItemForm caseId={caseId} clientState={d.items.client_state} item={i} onSaved={() => { setEditing(null); load(); }} onCancel={() => setEditing(null)} />
              ) : (
                <>
                  <div className="flex flex-wrap gap-1 mb-1">
                    {i.post_completion && (
                      <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-300" data-testid={`post-completion-badge-${i.id}`}>Added after signing</span>
                    )}
                    {i.has_unreleased_edits && <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-900">Edit not visible to client</span>}
                    {bizNeedsMoreInfo(i) && <NeedsMoreInfoBadge itemId={i.id} />}
                    <AccountNumberReveal caseId={caseId} item={i} />
                    <EinReveal caseId={caseId} item={i} />
                  </div>
                  <p className="font-semibold text-navy break-words">{i.description}</p>
                  <p className="text-[#64748B]">{KIND_LABEL[i.kind]}{i.other_kind ? ` (${i.other_kind === "Something Else" ? i.other_text : i.other_kind})` : ""}{i.state ? `, ${i.state}` : ""}</p>
                  {i.kind === "business" && i.business_info && (
                    <div className="text-xs text-[#64748B] mt-0.5 space-y-0.5" data-testid={`biz-info-summary-${i.id}`}>
                      {i.business_info.legal_name && <span className="mr-3">Name: {i.business_info.legal_name}</span>}
                      {i.business_info.biz_type && <span className="mr-3">Type: {i.business_info.biz_type}</span>}
                      {i.business_info.state_formed && <span className="mr-3">Formed in: {i.business_info.state_formed}</span>}
                      {i.business_info.ownership_pct && <span>Owned: {i.business_info.ownership_pct}%</span>}
                    </div>
                  )}
                  <p className="mt-1">Status: <b>{STATUS_LABEL[i.status]}</b>{i.date_delivered ? `, ${i.date_delivered}` : ""}</p>
                  {methodLabel(i) && <p className="break-words text-[#64748B]">Method: {methodLabel(i)}</p>}
                  <div className="flex flex-wrap gap-2 mt-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-sand-200 text-navy font-semibold" data-testid={`part-badge-${i.id}`}>
                      Schedule A: Part {i.part || "I"}
                    </span>
                    <button
                      onClick={() => togglePart(i.id, i.part || "I")}
                      disabled={togglingPart === i.id}
                      className="text-xs px-3 py-1 rounded-full border border-navy/40 text-navy inline-flex items-center gap-1 min-h-[32px] hover:bg-navy/5 disabled:opacity-50"
                      data-testid={`toggle-part-${i.id}`}
                    >
                      <ArrowRightLeft className="h-3 w-3" /> Move to Part {i.part === "II" ? "I" : "II"}
                    </button>
                  </div>
                  <Badges f={i.flags} />
                  <button onClick={() => setEditing(i.id)} className="mt-2 min-h-[44px] px-4 border rounded-md inline-flex items-center gap-1" data-testid={`admin-asset-edit-${i.id}`}><Pencil className="h-4 w-4" /> Edit</button>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
