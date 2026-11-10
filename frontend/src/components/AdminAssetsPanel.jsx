import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Download, Pencil, ArrowRightLeft, AlertTriangle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import AssetItemForm from "@/components/AssetItemForm";
import { KIND_LABEL, STATUS_LABEL, METHOD_OTHER, METHOD_UNSURE } from "@/lib/assetCopy";

const TABS = [["summary", "Summary"], ["items", "Items"], ["schedule", "Schedule A"]];
const badge = "text-xs font-semibold px-2 py-1 rounded-full";

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

function ScheduleA({ caseId, sa }) {
  const exportData = async (format) => {
    const { data } = await api.get(`/admin/trust-cases/${caseId}/schedule-a`, { params: { format }, responseType: format === "csv" ? "blob" : "json" });
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
      <div className="flex flex-col sm:flex-row gap-2">
        <button onClick={() => exportData("csv")} className="btn-primary min-h-[48px] inline-flex items-center justify-center gap-2" data-testid="export-schedule-csv"><Download className="h-4 w-4" /> Export Schedule A data (CSV)</button>
        <button onClick={() => exportData("json")} className="min-h-[48px] border rounded-md px-4 inline-flex items-center justify-center gap-2" data-testid="export-schedule-json"><Download className="h-4 w-4" /> JSON</button>
      </div>
    </div>
  );
}

export default function AdminAssetsPanel({ caseId }) {
  const [tab, setTab] = useState("summary");
  const [d, setD] = useState(null);
  const [editing, setEditing] = useState(null);
  const [togglingPart, setTogglingPart] = useState(null);

  const load = useCallback(async () => {
    try {
      const [items, summary, sa] = await Promise.all([
        api.get(`/trust-cases/${caseId}/asset-items`), api.get(`/admin/trust-cases/${caseId}/intake-summary`),
        api.get(`/admin/trust-cases/${caseId}/schedule-a`)]);
      setD({ items: items.data, summary: summary.data, sa: sa.data });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  }, [caseId]);
  useEffect(() => { load(); }, [load]);

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

      {/* Alert: items added after trust was signed — awaiting admin review */}
      {postCompletion.length > 0 && (
        <div className="mb-3 p-3 rounded-lg bg-blue-50 border border-blue-300 flex gap-2 items-start" data-testid="post-completion-alert">
          <AlertTriangle className="h-5 w-5 shrink-0 text-blue-700 mt-0.5" />
          <p className="text-sm text-blue-900">
            <strong>{postCompletion.length} item{postCompletion.length > 1 ? "s" : ""} added after the trust was signed.</strong> Review each one and set status to "Moved into trust" to include in Schedule A.
          </p>
        </div>
      )}

      {/* Alert: retirement items in list (should be empty, shown if old data slipped through) */}
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
      {tab === "summary" && <Summary s={d.summary} />}
      {tab === "schedule" && <ScheduleA caseId={caseId} sa={d.sa} />}
      {tab === "items" && (
        <div className="space-y-3" data-testid="admin-asset-items">
          {unreleased && (
            <div className="p-3 rounded-md bg-amber-50 border border-amber-300 text-sm flex flex-col sm:flex-row gap-2 sm:items-center justify-between">
              <span data-testid="asset-edits-held-note">Some edits are hidden from the client. Use the Release button at the bottom of the screen to show them.</span>
            </div>
          )}
          {items.length === 0 && <p className="text-sm text-[#94A3B8]">The client has not listed anything yet.</p>}
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
                  </div>
                  <p className="font-semibold text-navy break-words">{i.description}</p>
                  <p className="text-[#64748B]">{KIND_LABEL[i.kind]}{i.other_kind ? ` (${i.other_kind === "Something Else" ? i.other_text : i.other_kind})` : ""}{i.state ? `, ${i.state}` : ""}</p>
                  <p className="mt-1">Status: <b>{STATUS_LABEL[i.status]}</b>{i.date_delivered ? `, ${i.date_delivered}` : ""}</p>
                  {methodLabel(i) && <p className="break-words text-[#64748B]">Method: {methodLabel(i)}</p>}

                  {/* Part I/II toggle — only on items with moved or planned status */}
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
