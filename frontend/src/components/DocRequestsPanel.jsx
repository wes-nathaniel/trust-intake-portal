import React, { useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, CheckCircle2, Clock, Send } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";

const COMMON = [
  { v: "government_id", l: "Government-issued ID" },
  { v: "proof_of_address", l: "Proof of Address" },
  { v: "ein_letter", l: "EIN Letter" },
  { v: "bank_statement", l: "Bank Statement" },
  { v: "deed", l: "Deed" },
  { v: "title", l: "Title" },
  { v: "insurance_policy", l: "Insurance Policy" },
  { v: "business_document", l: "Business Document" },
  { v: "existing_trust", l: "Existing Trust Document" },
  { v: "supporting_file", l: "Other Supporting File" },
];

export default function DocRequestsPanel({ caseId, requests, reload }) {
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ doc_type: "bank_statement", label: "", note: "" });
  const [loading, setLoading] = useState(false);

  const add = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post(`/admin/trust-cases/${caseId}/doc-requests`, {
        doc_type: form.doc_type,
        label: form.label || null,
        note: form.note || "",
      });
      toast.success("Request sent to client");
      setForm({ doc_type: "bank_statement", label: "", note: "" });
      setAdding(false);
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  const cancel = async (id) => {
    if (!window.confirm("Cancel this document request?")) return;
    try {
      await api.delete(`/admin/trust-cases/${caseId}/doc-requests/${id}`);
      toast.success("Request cancelled");
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const markFulfilled = async (id) => {
    try {
      await api.post(`/admin/trust-cases/${caseId}/doc-requests/${id}/mark-fulfilled`);
      toast.success("Marked as received");
      reload();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const open = (requests || []).filter((r) => !r.fulfilled && !r.cancelled);
  const closed = (requests || []).filter((r) => r.fulfilled || r.cancelled);

  return (
    <div data-testid="doc-requests-panel">
      {open.length === 0 ? (
        <p className="text-sm text-[#64748B] mb-3">No outstanding document requests.</p>
      ) : (
        <ul className="space-y-2 mb-3">
          {open.map((r) => (
            <li key={r.id} className="flex items-start justify-between bg-amber-50 border border-amber-200 rounded-md p-3 text-sm" data-testid={`doc-request-${r.id}`}>
              <div className="flex items-start gap-2 flex-1 min-w-0">
                <Clock className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
                <div className="min-w-0">
                  <p className="font-semibold text-amber-900">{r.label}</p>
                  {r.note && <p className="text-amber-800/80 text-xs mt-0.5">{r.note}</p>}
                  <p className="text-[11px] text-[#64748B] mt-0.5">Requested {new Date(r.created_at).toLocaleDateString()} by {r.requested_by_name}</p>
                </div>
              </div>
              <div className="flex gap-1 shrink-0">
                <button onClick={() => markFulfilled(r.id)} className="text-green-700 hover:text-green-900" title="Mark received" data-testid={`doc-request-fulfill-${r.id}`}>
                  <CheckCircle2 className="h-4 w-4" />
                </button>
                <button onClick={() => cancel(r.id)} className="text-red-600 hover:text-red-800" title="Cancel" data-testid={`doc-request-cancel-${r.id}`}>
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {!adding ? (
        <button onClick={() => setAdding(true)} className="btn-accent text-sm" data-testid="doc-request-add-btn">
          <Plus className="h-4 w-4 inline mr-1" /> Request a document
        </button>
      ) : (
        <form onSubmit={add} className="space-y-3 border border-[#E2E0DA] rounded-md p-4 bg-sand-200/30" data-testid="doc-request-form">
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Document type</Label>
            <select value={form.doc_type} onChange={(e) => setForm({ ...form, doc_type: e.target.value })}
              className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm" data-testid="doc-request-type-select">
              {COMMON.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Display name (optional)</Label>
            <Input value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })}
              placeholder="Override the default label shown to the client"
              className="mt-1 bg-white" data-testid="doc-request-label-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Note to client (optional)</Label>
            <Textarea value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })}
              placeholder='e.g. "Last 3 months of statements for the joint checking account."'
              className="mt-1 bg-white" data-testid="doc-request-note-input" />
          </div>
          <div className="flex gap-2">
            <button type="submit" disabled={loading} className="btn-primary text-sm" data-testid="doc-request-submit-btn">
              <Send className="h-4 w-4 inline mr-1" /> {loading ? "Sending…" : "Send request to client"}
            </button>
            <button type="button" onClick={() => setAdding(false)} className="btn-secondary text-sm">Cancel</button>
          </div>
        </form>
      )}

      {closed.length > 0 && (
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer text-[#64748B]">History ({closed.length})</summary>
          <ul className="mt-2 space-y-1">
            {closed.map((r) => (
              <li key={r.id} className="text-xs text-[#64748B] flex items-center gap-2">
                {r.fulfilled ? <CheckCircle2 className="h-3 w-3 text-green-600" /> : <Trash2 className="h-3 w-3 text-red-500" />}
                <span>{r.label}</span>
                <span className="text-[#94A3B8]">· {r.fulfilled ? `received ${new Date(r.fulfilled_at).toLocaleDateString()}` : `cancelled ${new Date(r.cancelled_at).toLocaleDateString()}`}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
