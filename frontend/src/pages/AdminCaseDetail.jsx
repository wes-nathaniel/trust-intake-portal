import React, { useEffect, useState, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import StatusTracker from "@/components/StatusTracker";
import MessageThread from "@/components/MessageThread";
import { toast } from "sonner";
import { ArrowLeft, Upload, Download, FileText, StickyNote, Download as DL, RefreshCw, MailPlus, Clock, Lock, Unlock, BellRing, ExternalLink, Trash2 } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { displaySSN } from "@/pages/intake/_shared";
import DocRequestsPanel from "@/components/DocRequestsPanel";

const STATUSES = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review",
                  "Drafting Trust", "Ready for Payment", "Pending Payment Verification", "Payment Verified", "Completed"];

function Section({ title, children }) {
  return (
    <section className="bg-white border border-[#E2E0DA] rounded-xl p-6">
      <h3 className="font-serif text-2xl text-navy mb-4">{title}</h3>
      {children}
    </section>
  );
}

const KV = ({ k, v }) => (
  <div className="grid grid-cols-[160px_1fr] gap-2 text-sm py-1 border-b border-dashed border-[#E2E0DA]">
    <span className="text-[#64748B] uppercase text-xs tracking-wide font-semibold">{k}</span>
    <span className="text-navy break-words">{v || "—"}</span>
  </div>
);

export default function AdminCaseDetail() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [c, setC] = useState(null);
  const [note, setNote] = useState("");
  const einInputRef = useRef();
  const [uploadingEin, setUploadingEin] = useState(false);
  const [resending, setResending] = useState(false);

  const trustDraftInputRef = useRef();
  const [uploadingTrust, setUploadingTrust] = useState(false);

  const [invoiceOpen, setInvoiceOpen] = useState(false);
  const [invoiceAmount, setInvoiceAmount] = useState("");
  const [invoiceDesc, setInvoiceDesc] = useState("");
  const [invoiceDue, setInvoiceDue] = useState(14);
  const [invoiceSending, setInvoiceSending] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/admin/trust-cases/${caseId}`);
      setC(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [caseId]);

  if (!c) return <Layout><p>Loading…</p></Layout>;

  const setStatus = async (s) => {
    try {
      await api.put(`/admin/trust-cases/${caseId}/status`, { status: s });
      toast.success(`Status → ${s}`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const requestEIN = async () => {
    try {
      await api.post(`/admin/trust-cases/${caseId}/ein-request`);
      toast.success("EIN marked as requested");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const uploadEinLetter = async (file) => {
    if (!file) return;
    setUploadingEin(true);
    const form = new FormData();
    form.append("doc_type", "ein_letter");
    form.append("file", file);
    try {
      await api.post(`/trust-cases/${caseId}/documents`, form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("EIN letter uploaded");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setUploadingEin(false); if (einInputRef.current) einInputRef.current.value = ""; }
  };

  const addNote = async () => {
    if (!note.trim()) return;
    try {
      await api.post(`/admin/trust-cases/${caseId}/notes`, { note });
      setNote("");
      toast.success("Note added");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const download = async (d) => {
    try {
      const res = await api.get(`/trust-cases/${caseId}/documents/${d.id}/download`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = d.filename || "file"; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const resendInvite = async () => {
    setResending(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/resend-invite`);
      toast.success(`Invitation resent to ${data.sent_to}`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setResending(false); }
  };

  const uploadTrustDraft = async (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Only PDF files are accepted for trust drafts.");
      return;
    }
    setUploadingTrust(true);
    const form = new FormData();
    form.append("file", file);
    try {
      await api.post(`/admin/trust-cases/${caseId}/trust-draft`, form, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Trust draft uploaded. Client has been notified.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setUploadingTrust(false); if (trustDraftInputRef.current) trustDraftInputRef.current.value = ""; }
  };

  const unlockFinal = async () => {
    if (!window.confirm("Unlock final trust for this client? This removes watermarks, enables download/print, and emails the client.")) return;
    try {
      await api.post(`/admin/trust-cases/${caseId}/unlock-final`);
      toast.success("Final trust unlocked.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const sendReviewReminder = async () => {
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/send-review-reminder`);
      toast.success(`Reminder sent to ${data.sent_to}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const downloadDraftRaw = async () => {
    try {
      const res = await api.get(`/admin/trust-cases/${caseId}/trust-draft/raw`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url; a.download = `draft-trust-${caseId.slice(0,8)}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const createInvoice = async () => {
    const cents = Math.round(parseFloat(invoiceAmount || "0") * 100);
    if (!(cents > 0)) { toast.error("Enter an amount greater than $0.00"); return; }
    setInvoiceSending(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/invoice`, {
        amount_cents: cents,
        description: invoiceDesc || undefined,
        due_in_days: Number(invoiceDue) || 14,
      });
      toast.success(`Invoice sent to ${c.client_email}`);
      if (data.public_url) window.open(data.public_url, "_blank");
      setInvoiceOpen(false);
      setInvoiceAmount(""); setInvoiceDesc("");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setInvoiceSending(false); }
  };

  const refreshInvoice = async () => {
    try {
      await api.get(`/admin/trust-cases/${caseId}/invoice`);
      toast.success("Invoice status refreshed from Square");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const setAmountOnly = async () => {
    const dollars = window.prompt("Set payment amount (USD) — for Zelle / Cash App / manual workflows. Enter a number like 750 or 1250.50:");
    if (dollars === null) return;
    const n = parseFloat(dollars);
    if (!(n > 0)) { toast.error("Enter a number greater than 0."); return; }
    try {
      await api.put(`/admin/trust-cases/${caseId}/payment-amount`, { amount_cents: Math.round(n * 100) });
      toast.success(`Amount set: $${n.toFixed(2)}. Status: Ready for Payment.`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const verifyPayment = async () => {
    const amtStr = window.prompt(
      "Verify and approve client's claimed payment.\n\n" +
      "Optionally enter the FINAL amount (USD) to lock it in (or leave blank to keep current). " +
      "This will also email the client and advance their status to 'Payment Verified'.",
      ""
    );
    if (amtStr === null) return;
    const body = {};
    const n = parseFloat(amtStr || "");
    if (n > 0) body.amount_cents = Math.round(n * 100);
    try {
      await api.post(`/admin/trust-cases/${caseId}/payment-verify`, body);
      toast.success("Payment verified. Client has been notified.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const markPaymentReceived = async () => {
    if (!window.confirm("Manually mark this payment as received? This should only be used if payment was made offline or cleared outside Square.")) return;
    try {
      await api.post(`/admin/trust-cases/${caseId}/mark-payment-received`);
      toast.success("Payment marked as received.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const docs = (c.documents || []).filter((d) => !d.is_deleted);

  const archiveCase = async () => {
    if (!window.confirm(`Archive case for ${c.client_name || c.client_email}? It will be hidden from the default admin list and the client's portal. You can unarchive later.`)) return;
    try {
      await api.post(`/admin/trust-cases/${caseId}/archive`);
      toast.success("Case archived.");
      navigate("/admin");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const unarchiveCase = async () => {
    try {
      await api.post(`/admin/trust-cases/${caseId}/unarchive`);
      toast.success("Case restored.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const deleteCase = async () => {
    const label = c.client_name || c.client_email;
    const confirm1 = window.prompt(
      `⚠️ DELETE case for ${label} permanently?\n\n` +
      `This removes the case, all messages, all uploaded documents, invites, and questions. ` +
      `This cannot be undone.\n\n` +
      `Type DELETE to confirm:`
    );
    if (confirm1 !== "DELETE") { toast.message("Cancelled — nothing was deleted."); return; }
    const alsoUser = window.confirm(
      `Also delete the client user account for ${c.client_email}? ` +
      `(Only deletes if this is their only case. Cancel to keep the user.)`
    );
    try {
      const { data } = await api.delete(`/admin/trust-cases/${caseId}`, { params: { delete_user: alsoUser } });
      const bits = [
        `Case deleted.`,
        `Messages: ${data.deleted?.messages || 0}`,
        `Documents: ${data.storage_objects_deleted || 0}`,
        data.user_deleted ? "Client user deleted." : "",
      ].filter(Boolean).join(" · ");
      toast.success(bits);
      navigate("/admin");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <Layout>
      <Link to="/admin" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-6" data-testid="admin-back-btn">
        <ArrowLeft className="h-4 w-4" /> Back to cases
      </Link>

      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Case #{c.id.slice(0, 8).toUpperCase()}
            {c.archived && <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 text-[10px]" data-testid="archived-badge">ARCHIVED</span>}
          </p>
          <h1 className="font-serif text-4xl text-navy">{c.client_name || c.client_email}</h1>
          {c.trust_name && <p className="text-navy/80 font-serif text-lg mt-0.5" data-testid="admin-trust-name">{c.trust_name}</p>}
          <p className="text-[#64748B] mt-1">{c.client_email} · {c.trust_type === "joint" ? "Joint Trust" : "Single Trust"}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={async () => {
              try {
                const res = await api.get(`/trust-cases/${caseId}/export.pdf`, { responseType: "blob" });
                const url = URL.createObjectURL(res.data);
                const a = document.createElement("a");
                a.href = url; a.download = `trust-intake-${caseId.slice(0,8)}.pdf`; a.click();
                URL.revokeObjectURL(url);
              } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
            }}
            className="btn-accent"
            data-testid="admin-download-pdf-btn">
            <Download className="h-4 w-4 inline mr-1" /> Download Intake PDF
          </button>
          {c.archived ? (
            <button onClick={unarchiveCase} className="btn-secondary" data-testid="unarchive-case-btn">
              <RefreshCw className="h-4 w-4 inline mr-1" /> Restore
            </button>
          ) : (
            <button onClick={archiveCase} className="btn-secondary" data-testid="archive-case-btn" title="Hide from admin list and client portal (reversible)">
              <Clock className="h-4 w-4 inline mr-1" /> Archive
            </button>
          )}
          <button
            onClick={deleteCase}
            className="inline-flex items-center justify-center rounded-md px-4 py-2 text-sm font-medium border-2 border-red-600 text-red-700 hover:bg-red-600 hover:text-white transition-colors"
            data-testid="delete-case-btn"
            title="Permanently delete this case (irreversible)">
            <Trash2 className="h-4 w-4 inline mr-1" /> Delete
          </button>
        </div>
      </div>

      <div className="mb-6">
        <StatusTracker status={c.status} />
      </div>

      {c.pending_invite && (
        <div className="mb-6 bg-amber-50 border border-amber-300 rounded-xl p-4 sm:p-5 flex flex-col sm:flex-row sm:items-center gap-3 justify-between" data-testid="pending-invite-banner">
          <div className="flex items-start gap-3">
            <div className="shrink-0 h-10 w-10 rounded-full bg-amber-200/60 flex items-center justify-center">
              <Clock className="h-5 w-5 text-amber-800" />
            </div>
            <div>
              <p className="font-semibold text-amber-900">Invitation pending acceptance</p>
              <p className="text-sm text-amber-900/80">
                Client <b>{c.pending_invite.email}</b> hasn't set a password yet. Expires {new Date(c.pending_invite.expires_at).toLocaleDateString()}.
              </p>
            </div>
          </div>
          <button onClick={resendInvite} disabled={resending} className="btn-accent shrink-0" data-testid="resend-invite-btn">
            <MailPlus className="h-4 w-4 inline mr-1" /> {resending ? "Sending…" : "Resend invite"}
          </button>
        </div>
      )}

      <div className="bg-white border border-[#E2E0DA] rounded-xl p-6 mb-6" data-testid="admin-status-panel">
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
          <span className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Update status</span>
          <select value={c.status} onChange={(e) => setStatus(e.target.value)}
            className="bg-white border border-input rounded-md px-3 py-2 text-sm" data-testid="admin-status-select">
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        {c.acknowledgments?.review_completed_ack && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded-md text-sm flex items-start gap-2" data-testid="admin-review-completed-banner">
            <span className="text-green-700 font-semibold">Client marked review as completed.</span>
            <span className="text-green-800/80">Ready for payment.</span>
          </div>
        )}
        {(c.pending_items || []).length > 0 && (
          <div className="mt-4 p-3 bg-amber-50 border border-amber-200 rounded-md text-sm" data-testid="admin-pending-summary">
            <p className="font-semibold text-amber-900 mb-1">Client-facing outstanding items ({(c.pending_items || []).length})</p>
            <ul className="list-disc pl-5 text-amber-900/90">
              {(c.pending_items || []).map((p, i) => (
                <li key={i}><b>{p.label}</b>{p.note && <span className="text-amber-800/80"> — {p.note}</span>}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-2 gap-6">
        <Section title={`Grantors (${c.grantors?.length || 0})`}>
          {(c.grantors || []).map((g, i) => (
            <div key={g.id} className="mb-4" data-testid={`admin-grantor-${i}`}>
              <p className="text-xs uppercase text-bronze font-semibold mb-2">Grantor {i + 1}</p>
              <KV k="Name" v={`${g.full_legal_name}${g.middle_name ? " (" + g.middle_name + ")" : ""}`} />
              <KV k="DOB" v={g.date_of_birth} />
              <KV k="SSN" v={displaySSN(g.ssn)} />
              <KV k="Email" v={g.email} />
              <KV k="Phone" v={g.phone} />
              <KV k="Marital" v={g.marital_status} />
              <KV k="Citizenship" v={g.citizenship} />
              <KV k="Address" v={`${g.address?.line1 || ""} ${g.address?.city || ""} ${g.address?.state || ""} ${g.address?.zip || ""}`} />
              {g.notes && <KV k="Notes" v={g.notes} />}
            </div>
          ))}
        </Section>

        <Section title="Trustee">
          {c.trustees?.[0] ? (() => { const t = c.trustees[0]; return (
            <div>
              <KV k="Name" v={t.full_legal_name} />
              <KV k="Relationship" v={t.relationship} />
              <KV k="Email" v={t.email} />
              <KV k="Phone" v={t.phone} />
            </div>
          ); })() : <p className="text-sm text-[#64748B]">Not added yet.</p>}
        </Section>

        <Section title={`Successor Trustees (${c.successor_trustees?.length || 0})`}>
          {(c.successor_trustees || []).map((t, i) => (
            <div key={t.id} className="mb-3" data-testid={`admin-successor-${i}`}>
              <p className="text-xs uppercase text-bronze font-semibold mb-1">Successor {i + 1}</p>
              <KV k="Name" v={t.full_legal_name} />
              <KV k="Relationship" v={t.relationship} />
              <KV k="Email" v={t.email} />
            </div>
          ))}
        </Section>

        <Section title={`Beneficiaries (${c.beneficiaries?.length || 0})`}>
          {(c.beneficiaries || []).map((b, i) => (
            <div key={b.id} className="mb-3" data-testid={`admin-beneficiary-${i}`}>
              <p className="text-xs uppercase text-bronze font-semibold mb-1">Beneficiary {i + 1}</p>
              <KV k="Name" v={b.full_legal_name} />
              <KV k="Relationship" v={b.relationship} />
              <KV k="Share" v={`${b.percentage}%`} />
              {b.contingent_name && <KV k="Contingent" v={b.contingent_name} />}
            </div>
          ))}
        </Section>

        <Section title={`Assets (${c.assets?.length || 0})`}>
          {(c.assets || []).map((a) => (
            <div key={a.id} className="mb-3" data-testid={`admin-asset-${a.id}`}>
              <KV k="Type" v={a.asset_type} />
              <KV k="Institution / Property" v={a.institution_name || a.property_address} />
              {a.account_number && <KV k="Account #" v={a.account_number} />}
              {a.estimated_value && <KV k="Est. Value" v={`$${Number(a.estimated_value).toLocaleString()}`} />}
            </div>
          ))}
        </Section>

        <Section title="EIN Workflow">
          <KV k="Trust Name" v={c.trust_name || "—"} />
          <KV k="Client Authorized" v={c.ein?.authorized ? "Yes" : "No"} />
          <KV k="Firm Will File" v={c.ein?.firm_will_file !== false ? "Yes" : "No"} />
          <KV k="EIN Requested with IRS" v={c.ein_requested ? "Yes" : "No"} />
          <div className="flex gap-2 mt-4 flex-wrap">
            {!c.ein_requested && c.ein?.authorized && (
              <button onClick={requestEIN} className="btn-secondary text-sm" data-testid="ein-request-btn">Mark EIN Requested</button>
            )}
            <label className="btn-accent text-sm cursor-pointer inline-flex items-center" data-testid="ein-letter-upload-label">
              <Upload className="h-4 w-4 inline mr-1" /> {uploadingEin ? "Uploading…" : "Upload EIN Letter (CP-575)"}
              <input ref={einInputRef} type="file" className="hidden" onChange={(e) => uploadEinLetter(e.target.files?.[0])} data-testid="ein-letter-upload" />
            </label>
          </div>
          <p className="text-xs text-[#64748B] mt-2">Only admins can upload the EIN letter. Clients will download it from their portal.</p>
          {c.ein_letter && (
            <div className="mt-3 flex items-center justify-between bg-sand-200/40 rounded-md px-3 py-2 text-sm" data-testid="ein-letter-saved">
              <span className="flex items-center gap-2"><FileText className="h-4 w-4" /> {c.ein_letter.filename}</span>
              <button onClick={() => download(c.ein_letter)} className="text-navy hover:text-bronze"><Download className="h-4 w-4" /></button>
            </div>
          )}
        </Section>

        <Section title="Payment (Zelle / Cash App / Square)">
          <p className="text-sm text-[#64748B] mb-3">
            Set the case amount for any payment method. Square invoice is optional (only for card payments).
          </p>
          <div className="flex flex-wrap gap-2 mb-4">
            <button onClick={setAmountOnly} className="btn-secondary text-sm" data-testid="set-amount-only-btn">
              {c.payment?.amount_cents ? "Update amount" : "Set payment amount"}
            </button>
            {c.payment?.claimed && c.payment?.status === "pending_verification" && (
              <button onClick={verifyPayment} className="btn-accent text-sm" data-testid="verify-payment-btn">
                <Unlock className="h-4 w-4 inline mr-1" /> Verify &amp; Approve Payment
              </button>
            )}
          </div>

          {c.payment?.claimed && (
            <div className="mb-4 p-3 bg-amber-50 border border-amber-300 rounded-md text-sm" data-testid="payment-claimed-banner">
              <p className="font-semibold text-amber-900">
                Client claims payment via <span className="uppercase">{c.payment.claimed_method}</span>
              </p>
              <p className="text-amber-900/90 text-xs mt-1">
                Submitted {c.payment.claimed_at?.slice(0, 19).replace("T", " ")}
                {c.payment.claimed_note && ` · Note: ${c.payment.claimed_note}`}
              </p>
              {c.payment.status !== "verified" && (
                <p className="text-amber-900 text-xs mt-1 font-semibold">
                  Action required: verify payment in your records, then click "Verify &amp; Approve Payment" above.
                </p>
              )}
            </div>
          )}

          {!c.payment?.invoice_id ? (
            <div>
              <p className="text-xs uppercase text-[#64748B] font-semibold mb-2">Optional: Square invoice (debit/credit card)</p>
              {invoiceOpen ? (
                <div className="space-y-3 border border-bronze/40 bg-bronze/5 rounded-lg p-4">
                  <div className="grid sm:grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs uppercase text-[#64748B] font-semibold">Amount (USD)</label>
                      <input type="number" step="0.01" min="0.01" value={invoiceAmount}
                        onChange={(e) => setInvoiceAmount(e.target.value)}
                        placeholder="0.00"
                        className="w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                        data-testid="invoice-amount-input" />
                    </div>
                    <div>
                      <label className="text-xs uppercase text-[#64748B] font-semibold">Due in (days)</label>
                      <input type="number" min="1" max="90" value={invoiceDue}
                        onChange={(e) => setInvoiceDue(e.target.value)}
                        className="w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                        data-testid="invoice-due-input" />
                    </div>
                    <div className="sm:col-span-3">
                      <label className="text-xs uppercase text-[#64748B] font-semibold">Description (optional)</label>
                      <input type="text" value={invoiceDesc}
                        onChange={(e) => setInvoiceDesc(e.target.value)}
                        placeholder="Trust preparation & filing fee"
                        className="w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                        data-testid="invoice-desc-input" />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button onClick={createInvoice} disabled={invoiceSending} className="btn-primary text-sm" data-testid="invoice-submit-btn">
                      {invoiceSending ? "Sending…" : "Create & send Square invoice"}
                    </button>
                    <button onClick={() => setInvoiceOpen(false)} className="btn-secondary text-sm">Cancel</button>
                  </div>
                </div>
              ) : (
                <button onClick={() => setInvoiceOpen(true)} className="btn-secondary text-sm" data-testid="create-invoice-btn">
                  <DL className="h-4 w-4 inline mr-1" /> Create Square invoice
                </button>
              )}
            </div>
          ) : (
            <div data-testid="payment-details">
              <KV k="Amount" v={c.payment.amount_cents ? `$${(c.payment.amount_cents/100).toLocaleString(undefined, {minimumFractionDigits: 2})}` : "—"} />
              <KV k="Status" v={c.payment.status} />
              <KV k="Square Invoice ID" v={c.payment.invoice_id} />
              <KV k="Square Status" v={c.payment.invoice_status || "—"} />
              <KV k="Due date" v={c.payment.due_date} />
              <KV k="Source" v={c.payment.source_type || "—"} />
              <KV k="Last webhook" v={c.payment.last_webhook_at?.slice(0, 19).replace("T", " ") || "—"} />
              {c.payment.risk_level && <KV k="Risk level" v={c.payment.risk_level} />}
              <div className="flex flex-wrap gap-2 mt-3">
                {c.payment.public_url && (
                  <a href={c.payment.public_url} target="_blank" rel="noreferrer" className="btn-secondary text-sm" data-testid="invoice-public-link">
                    <ExternalLink className="h-4 w-4 inline mr-1" /> Open in Square
                  </a>
                )}
                <button onClick={refreshInvoice} className="btn-secondary text-sm" data-testid="invoice-refresh-btn">
                  <RefreshCw className="h-4 w-4 inline mr-1" /> Refresh status
                </button>
                {c.payment.status !== "paid" && c.payment.status !== "paid_manual" && c.payment.status !== "verified" && (
                  <button onClick={markPaymentReceived} className="btn-accent text-sm" data-testid="mark-paid-btn">
                    Mark Square payment received (manual)
                  </button>
                )}
              </div>
              {c.payment.status === "ach_pending" && (
                <p className="text-xs text-amber-700 mt-3">ACH is pending — typically 3–5 business days to clear.</p>
              )}
            </div>
          )}

          {!c.payment?.invoice_id && c.payment?.amount_cents && (
            <div className="mt-3 text-sm" data-testid="payment-summary">
              <KV k="Amount on file" v={`$${(c.payment.amount_cents/100).toLocaleString(undefined, {minimumFractionDigits: 2})}`} />
              <KV k="Status" v={c.payment.status} />
              {c.payment.claimed_at && <KV k="Claimed at" v={c.payment.claimed_at?.slice(0, 19).replace("T", " ")} />}
              {c.payment.verified_at && <KV k="Verified at" v={c.payment.verified_at?.slice(0, 19).replace("T", " ")} />}
            </div>
          )}
        </Section>

        <Section title="Trust Draft — Secure Preview">
          {!c.trust_draft ? (
            <div>
              <p className="text-sm text-[#64748B] mb-3">
                Upload the drafted trust PDF to share a watermarked, page-by-page preview with the client.
                Printing and downloading are disabled for the client until payment is received.
              </p>
              <label className="btn-accent text-sm cursor-pointer inline-flex items-center" data-testid="trust-draft-upload-label">
                <Upload className="h-4 w-4 inline mr-1" /> {uploadingTrust ? "Uploading…" : "Upload Trust Draft PDF"}
                <input ref={trustDraftInputRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => uploadTrustDraft(e.target.files?.[0])} data-testid="trust-draft-upload-input" />
              </label>
            </div>
          ) : (
            <div>
              <KV k="File" v={c.trust_draft.filename} />
              <KV k="Pages" v={c.trust_draft.pages} />
              <KV k="Version" v={c.trust_draft.version} />
              <KV k="Uploaded" v={c.trust_draft.uploaded_at?.slice(0, 19).replace("T", " ")} />
              <KV k="Review completed by client" v={c.acknowledgments?.review_completed_ack ? "Yes" : "No"} />
              <KV k="Final unlocked" v={c.trust_unlocked ? "Yes" : "No"} />
              <div className="flex flex-wrap gap-2 mt-4">
                <a href={`/portal/trust-preview/${caseId}`} target="_blank" rel="noreferrer" className="btn-secondary text-sm" data-testid="admin-open-preview-btn">
                  <ExternalLink className="h-4 w-4 inline mr-1" /> Open client preview
                </a>
                <button onClick={downloadDraftRaw} className="btn-secondary text-sm" data-testid="admin-download-draft-raw-btn">
                  <Download className="h-4 w-4 inline mr-1" /> Download draft PDF (admin)
                </button>
                <label className="btn-secondary text-sm cursor-pointer inline-flex items-center" data-testid="trust-draft-replace-label">
                  <Upload className="h-4 w-4 inline mr-1" /> {uploadingTrust ? "Uploading…" : "Replace draft"}
                  <input ref={trustDraftInputRef} type="file" accept="application/pdf" className="hidden" onChange={(e) => uploadTrustDraft(e.target.files?.[0])} />
                </label>
                <button onClick={sendReviewReminder} className="btn-secondary text-sm" data-testid="send-review-reminder-btn">
                  <BellRing className="h-4 w-4 inline mr-1" /> Send review reminder
                </button>
                {!c.trust_unlocked ? (
                  <button onClick={unlockFinal} className="btn-accent text-sm" data-testid="unlock-final-btn">
                    <Unlock className="h-4 w-4 inline mr-1" /> Unlock Final Trust
                  </button>
                ) : (
                  <span className="inline-flex items-center gap-1 text-sm text-green-700 font-semibold">
                    <Unlock className="h-4 w-4" /> Final unlocked
                  </span>
                )}
              </div>
              <p className="text-xs text-[#64748B] mt-3"><Lock className="h-3 w-3 inline mr-1" /> Client preview: low-resolution, watermarked, anti-copy &amp; anti-print.</p>
            </div>
          )}
        </Section>

        <Section title="Document Requests from client">
          <DocRequestsPanel caseId={caseId} requests={c.requested_documents} reload={load} />
        </Section>

        <Section title={`Documents (${docs.length})`}>
          {docs.length === 0 ? <p className="text-sm text-[#64748B]">No documents uploaded.</p> : (
            <ul className="space-y-2 text-sm">
              {docs.map((d) => (
                <li key={d.id} className="flex items-center justify-between bg-sand-200/40 rounded-md px-3 py-2" data-testid={`admin-doc-${d.id}`}>
                  <span className="flex items-center gap-2 text-navy truncate">
                    <FileText className="h-4 w-4 shrink-0" />
                    <span className="truncate">{d.filename}</span>
                    <span className="text-xs text-[#64748B]">({d.doc_type})</span>
                  </span>
                  <button onClick={() => download(d)} className="text-navy hover:text-bronze" data-testid={`admin-doc-download-${d.id}`}><Download className="h-4 w-4" /></button>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Internal Notes">
          <div className="space-y-2 mb-3">
            {(c.admin_notes || []).map((n) => (
              <div key={n.id} className="bg-sand-200/40 rounded-md p-3 text-sm" data-testid={`admin-note-${n.id}`}>
                <p className="text-[#64748B] text-xs mb-1">{n.author} · {new Date(n.created_at).toLocaleString()}</p>
                <p className="text-navy whitespace-pre-wrap">{n.note}</p>
              </div>
            ))}
            {(c.admin_notes || []).length === 0 && <p className="text-sm text-[#64748B]">No notes yet.</p>}
          </div>
          <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Add an internal note…"
            className="bg-white mb-2" data-testid="admin-note-input" />
          <button onClick={addNote} className="btn-primary text-sm" data-testid="admin-note-add">
            <StickyNote className="h-4 w-4 inline mr-1" /> Add Note
          </button>
        </Section>
      </div>

      <div className="mt-6">
        <MessageThread caseId={caseId} title="Client Messages" />
      </div>
    </Layout>
  );
}
