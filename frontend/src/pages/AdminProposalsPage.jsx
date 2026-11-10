import React, { useEffect, useState, useCallback } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { ArrowLeft, CheckCircle, XCircle, Clock, RefreshCw, Send, ChevronDown } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter
} from "@/components/ui/dialog";

const STATUS_COLOR = {
  pending: "bg-amber-50 text-amber-800 border-amber-200",
  approved: "bg-emerald-50 text-emerald-800 border-emerald-200",
  rejected: "bg-red-50 text-red-800 border-red-200",
};
const TYPE_LABEL = {
  field_change: "Field Change",
  client_message: "Client Message",
  admin_note: "Admin Note",
};

function SendConfirmDialog({ proposal, onConfirm, onClose }) {
  const [sending, setSending] = useState(false);
  const send = async () => {
    setSending(true);
    try {
      await api.post(`/admin/mcp/proposals/${proposal.id}/send-message`);
      toast.success("Message sent to client.");
      onConfirm();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      setSending(false);
    }
  };
  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Send this email now?</DialogTitle>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="bg-[#F6F4F0] border border-[#E2E0DA] rounded-lg p-3 space-y-2">
            <p><b>To:</b> {proposal.to_email}</p>
            <p><b>Subject:</b> {proposal.subject}</p>
          </div>
          <div className="bg-[#F6F4F0] border border-[#E2E0DA] rounded-lg p-3 whitespace-pre-wrap text-navy max-h-48 overflow-y-auto">
            {proposal.message}
          </div>
          {proposal.reason && (
            <p className="text-xs text-[#64748B] italic">Reason from Claude: {proposal.reason}</p>
          )}
        </div>
        <DialogFooter className="flex flex-col-reverse sm:flex-row gap-3 pt-2">
          <button type="button" onClick={onClose}
            className="btn-secondary min-h-[52px] flex-1 sm:flex-none sm:min-w-[160px]"
            data-testid="cancel-send-btn">
            Approve but don't send yet
          </button>
          <button type="button" onClick={send} disabled={sending}
            className="btn-primary min-h-[52px] flex-1 sm:flex-none sm:min-w-[160px] flex items-center justify-center gap-2"
            data-testid="confirm-send-btn">
            <Send className="h-4 w-4" />
            {sending ? "Sending…" : "Send this email"}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ProposalCard({ p, onAction }) {
  const [expanded, setExpanded] = useState(false);
  const [approving, setApproving] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [sendConfirm, setSendConfirm] = useState(null);

  const approve = async () => {
    setApproving(true);
    try {
      const { data } = await api.post(`/admin/mcp/proposals/${p.id}/approve`);
      if (data.requires_send_confirm) {
        setSendConfirm({ ...p, ...data });
      } else {
        toast.success("Approved and applied.");
        onAction();
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setApproving(false);
    }
  };

  const reject = async () => {
    if (!window.confirm("Reject this proposal?")) return;
    setRejecting(true);
    try {
      await api.post(`/admin/mcp/proposals/${p.id}/reject`);
      toast.success("Rejected.");
      onAction();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRejecting(false);
    }
  };

  const isPending = p.status === "pending";

  return (
    <div className={`border rounded-xl p-4 space-y-3 ${STATUS_COLOR[p.status] || "border-[#E2E0DA]"}`}
      data-testid={`proposal-card-${p.id?.slice(0, 8)}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="space-y-0.5 flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold uppercase tracking-wide">{TYPE_LABEL[p.type] || p.type}</span>
            <span className="text-xs font-mono bg-white/60 border border-current/20 rounded px-1.5 py-0.5">{p.status}</span>
          </div>
          <p className="font-semibold text-sm truncate">{p.case_name} · Case #{(p.case_id || "").slice(0, 8).toUpperCase()}</p>
          <p className="text-xs opacity-70">{new Date(p.created_at).toLocaleString()}</p>
        </div>
        <button type="button" onClick={() => setExpanded(!expanded)}
          className="shrink-0 min-h-[44px] min-w-[44px] flex items-center justify-center rounded-lg hover:bg-black/10"
          data-testid="expand-proposal-btn">
          <ChevronDown className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      </div>

      {/* Summary line */}
      {p.type === "field_change" && (
        <p className="text-sm"><b>{p.field_path}</b> → <span className="font-mono text-xs">{JSON.stringify(p.new_value)}</span></p>
      )}
      {p.type === "client_message" && (
        <p className="text-sm"><b>Subject:</b> {p.subject}</p>
      )}
      {p.type === "admin_note" && (
        <p className="text-sm line-clamp-2">{p.note}</p>
      )}

      {/* Expanded details */}
      {expanded && (
        <div className="bg-white/70 rounded-lg p-3 text-sm space-y-2 border border-current/20">
          {p.reason && <p><b>Reason from Claude:</b> {p.reason}</p>}
          {p.type === "client_message" && (
            <>
              <p><b>To:</b> {p.to_email}</p>
              <div className="bg-white border border-current/20 rounded p-2 whitespace-pre-wrap text-xs max-h-40 overflow-y-auto">{p.message}</div>
              {p.sent && <p className="text-xs text-emerald-700">Sent {p.sent_at ? new Date(p.sent_at).toLocaleString() : ""}</p>}
            </>
          )}
          {p.type === "field_change" && (
            <div className="text-xs font-mono break-all">
              <p><b>Field:</b> {p.field_path}</p>
              <p><b>New value:</b> {JSON.stringify(p.new_value)}</p>
            </div>
          )}
          {p.type === "admin_note" && (
            <div className="whitespace-pre-wrap text-xs">{p.note}</div>
          )}
        </div>
      )}

      {/* Action buttons — only for pending */}
      {isPending && (
        <div className="flex gap-4 pt-1">
          <button type="button" onClick={approve} disabled={approving || rejecting}
            className="btn-primary min-h-[52px] flex-1 flex items-center justify-center gap-2 text-sm"
            data-testid="approve-proposal-btn">
            <CheckCircle className="h-4 w-4" />
            {approving ? "Approving…" : "Approve"}
          </button>
          <div className="w-6" /> {/* visual space between buttons */}
          <button type="button" onClick={reject} disabled={approving || rejecting}
            className="min-h-[52px] flex-1 flex items-center justify-center gap-2 text-sm rounded-xl border border-red-300 text-red-700 hover:bg-red-50 font-semibold transition-colors"
            data-testid="reject-proposal-btn">
            <XCircle className="h-4 w-4" />
            {rejecting ? "Rejecting…" : "Reject"}
          </button>
        </div>
      )}

      {sendConfirm && (
        <SendConfirmDialog
          proposal={sendConfirm}
          onConfirm={() => { setSendConfirm(null); onAction(); }}
          onClose={() => { setSendConfirm(null); onAction(); }}
        />
      )}
    </div>
  );
}

export default function AdminProposalsPage() {
  const [proposals, setProposals] = useState([]);
  const [filter, setFilter] = useState("pending");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/mcp/proposals?status_filter=${filter}`);
      setProposals(data.proposals || []);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => { load(); }, [load]);

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to="/admin/mcp" className="text-[#64748B] hover:text-navy min-h-[44px] flex items-center" data-testid="back-btn">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="font-serif text-3xl text-navy">Claude Proposals</h1>
            <p className="text-sm text-[#64748B]">Review and approve suggestions from Claude</p>
          </div>
        </div>

        {/* Filter tabs */}
        <div className="flex border border-[#E2E0DA] rounded-lg overflow-hidden" role="tablist">
          {["pending", "approved", "rejected", "all"].map(f => (
            <button key={f} role="tab" aria-selected={filter === f}
              onClick={() => setFilter(f)}
              className={`flex-1 min-h-[44px] text-sm capitalize transition-colors ${filter === f ? "bg-navy text-white font-semibold" : "bg-white text-navy hover:bg-[#F6F4F0]"}`}
              data-testid={`filter-${f}`}>
              {f}
            </button>
          ))}
        </div>

        {/* Refresh */}
        <div className="flex justify-end">
          <button type="button" onClick={load} disabled={loading}
            className="text-sm text-[#64748B] flex items-center gap-1.5 min-h-[44px]"
            data-testid="refresh-btn">
            <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>

        {loading && <p className="text-sm text-[#64748B] text-center py-8">Loading…</p>}

        {!loading && proposals.length === 0 && (
          <div className="text-center py-12 text-[#64748B] space-y-2">
            <Clock className="h-8 w-8 mx-auto opacity-40" />
            <p className="text-sm">No {filter === "all" ? "" : filter} proposals right now.</p>
          </div>
        )}

        <div className="space-y-4">
          {proposals.map(p => (
            <ProposalCard key={p.id} p={p} onAction={load} />
          ))}
        </div>
      </div>
    </Layout>
  );
}
