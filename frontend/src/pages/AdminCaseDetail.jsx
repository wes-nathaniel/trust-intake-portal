import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import StatusTracker from "@/components/StatusTracker";
import AdminDocumentsManager from "@/components/AdminDocumentsManager";
import MessageThread from "@/components/MessageThread";
import WhatsAppPanel from "@/components/WhatsAppPanel";
import { toast } from "sonner";
import { ArrowLeft, Upload, Download, FileText, StickyNote, RefreshCw, MailPlus, Clock, BellRing, ExternalLink, Trash2, Send, CreditCard, Smartphone, ChevronDown, Lock, Unlock } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { displaySSN } from "@/pages/intake/_shared";
import DocRequestsPanel from "@/components/DocRequestsPanel";
import SSNReveal from "@/components/SSNReveal";
import TempPasswordDialog from "@/components/TempPasswordDialog";
import PasswordHistory from "@/components/PasswordHistory";
import AdminCaseFieldsEditor from "@/components/AdminCaseFieldsEditor";
import AdminAssetsPanel from "@/components/AdminAssetsPanel";
import ExplainerHealthBadge from "@/components/ExplainerHealthBadge";
import AdminErrorBoundary from "@/components/AdminErrorBoundary";
import { startViewAsClient } from "@/components/ViewAsBanner";
import ReleaseBar from "@/components/ReleaseBar";
import { useAuth } from "@/context/AuthContext";
import { Eye } from "lucide-react";

const STATUSES = ["Intake Started", "Intake In Progress", "Waiting on Documents", "In Review",
                  "Drafting Trust", "Ready for Client Review", "Ready for Payment", "Pending Payment Verification", "Payment Verified", "Completed"];

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
  const { refresh } = useAuth();
  const [c, setC] = useState(null);
  const [note, setNote] = useState("");
  const einInputRef = useRef();
  const [uploadingEin, setUploadingEin] = useState(false);
  const [resending, setResending] = useState(false);
  const [paymentLinkOpen, setPaymentLinkOpen] = useState(false);
  const [plLookupKey, setPlLookupKey] = useState("basic_living_trust");
  const [plSubject, setPlSubject] = useState("");
  const [plMessage, setPlMessage] = useState("");
  const [plSending, setPlSending] = useState(false);
  const [scheduleA, setScheduleA] = useState(null);
  const [scheduleAOpen, setScheduleAOpen] = useState(false);
  const [stripeInfo, setStripeInfo] = useState(null);

  const trustDraftInputRef = useRef();
  const [uploadingTrust, setUploadingTrust] = useState(false);
  // (typed new email + explicit "Change email" click) so this can't fire from an
  // errant click. Keeps all case data intact — only `users.email` and this case's
  // `client_email` move.
  const [emailModalOpen, setEmailModalOpen] = useState(false);
  const [tempPwOpen, setTempPwOpen] = useState(false);
  const [pwHistoryKey, setPwHistoryKey] = useState(0);
  const [newEmail, setNewEmail] = useState("");
  const [confirmEmail, setConfirmEmail] = useState("");
  const [changingEmail, setChangingEmail] = useState(false);

  const [loginsOpen, setLoginsOpen] = useState(false);
  const [loginRows, setLoginRows] = useState(null);
  const toggleLogins = async () => {
    const next = !loginsOpen;
    setLoginsOpen(next);
    if (next && loginRows === null) {
      try {
        const { data } = await api.get(`/admin/trust-cases/${caseId}/login-activity?limit=5`);
        setLoginRows(data.rows || []);
      } catch (e) {
        toast.error(formatApiError(e.response?.data?.detail));
        setLoginRows([]);
      }
    }
  };

  const load = async () => {
    try {
      const { data } = await api.get(`/admin/trust-cases/${caseId}`);
      setC(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const loadScheduleA = useCallback(async () => {
    try {
      const { data } = await api.get(`/admin/trust-cases/${caseId}/schedule-a`);
      setScheduleA(data);
    } catch (e) { /* non-critical */ }
  }, [caseId]);

  const loadStripeInfo = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/stripe/health");
      setStripeInfo(data);
    } catch (e) { /* non-critical */ }
  }, []);

  useEffect(() => { load(); loadScheduleA(); loadStripeInfo(); /* eslint-disable-next-line */ }, [caseId]);

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

  const removeClientDoc = async (d) => {
    if (!window.confirm(`Remove "${d.filename}"? The client will no longer see this file.`)) return;
    try {
      await api.delete(`/trust-cases/${caseId}/documents/${d.id}`);
      toast.success("Document removed.");
      await load();
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
      toast.success("Trust draft uploaded. It stays hidden until you release it.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setUploadingTrust(false); if (trustDraftInputRef.current) trustDraftInputRef.current.value = ""; }
  };

  const unlockFinal = async () => {
    if (!window.confirm("Unlock final trust for this client? This removes watermarks and enables download/print. No email is sent. Use Release to tell the client.")) return;
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

  const deleteDraft = async () => {
    if (!window.confirm(
      "Delete this trust draft PDF?\n\nThis will:\n" +
      "• Permanently remove the PDF from storage\n" +
      "• Clear the auto-extracted two-panel sections (published + drafts)\n" +
      "• Preserve any AI-explainer entry that was imported from this draft (marked as source removed)\n\n" +
      "This action cannot be undone."
    )) return;
    try {
      await api.delete(`/admin/trust-cases/${caseId}/trust-draft`);
      toast.success("Trust draft deleted. Case is reset — upload a new PDF when ready.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const sendPaymentLink = async () => {
    if (!plLookupKey) { toast.error("Choose a package."); return; }
    setPlSending(true);
    try {
      const origin = window.location.origin;
      await api.post(`/admin/trust-cases/${caseId}/send-payment-link`, {
        lookup_key: plLookupKey,
        origin_url: origin,
        email_subject: plSubject || undefined,
        email_message: plMessage || undefined,
      });
      toast.success("Payment link sent to client.");
      setPaymentLinkOpen(false);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setPlSending(false); }
  };

  const markZelleReceived = async () => {
    const amtStr = window.prompt(
      "Enter the amount received via Zelle (USD). No email is sent to the client. Use Release when ready.",
      c.payment?.amount_cents ? (c.payment.amount_cents / 100).toFixed(2) : ""
    );
    if (amtStr === null) return;
    const n = parseFloat(amtStr || "");
    if (!(n > 0)) { toast.error("Enter an amount greater than 0."); return; }
    try {
      await api.post(`/admin/trust-cases/${caseId}/mark-zelle-received`, { amount_cents: Math.round(n * 100) });
      toast.success("Zelle payment recorded. Use Release to tell the client.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const setAmountOnly = async () => {
    const suggested = c.payment?.suggested_amount_cents
      || ((c.intake_path || "new") === "review" ? 29700 : 99700);
    const dollars = window.prompt(
      "Set payment amount (USD). Enter a number like 997 or 1497.",
      (suggested / 100).toFixed(2)
    );
    if (dollars === null) return;
    const n = parseFloat(dollars);
    if (!(n > 0)) { toast.error("Enter a number greater than 0."); return; }
    try {
      await api.put(`/admin/trust-cases/${caseId}/payment-amount`, { amount_cents: Math.round(n * 100) });
      toast.success(`Amount set to $${n.toFixed(2)}.`);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const exportScheduleA = async (format = "csv") => {
    try {
      const res = await api.get(`/admin/trust-cases/${caseId}/schedule-a?format=${format}`, {
        responseType: format === "csv" ? "blob" : "json",
      });
      if (format === "csv") {
        const url = URL.createObjectURL(res.data);
        const a = document.createElement("a");
        a.href = url; a.download = `schedule-a-${caseId.slice(0, 8)}.csv`; a.click();
        URL.revokeObjectURL(url);
      } else {
        const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `schedule-a-${caseId.slice(0, 8)}.json`; a.click();
        URL.revokeObjectURL(url);
      }
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

  const changeClientEmail = async () => {
    const target = newEmail.trim().toLowerCase();
    const confirmTarget = confirmEmail.trim().toLowerCase();
    if (!target) { toast.error("Enter the new email."); return; }
    if (target !== confirmTarget) { toast.error("The two emails don't match."); return; }
    if (target === (c.client_email || "").toLowerCase()) {
      toast.error("That is already this client's login email.");
      return;
    }
    setChangingEmail(true);
    try {
      const { data } = await api.patch("/admin/users/change-email", {
        old_email: c.client_email,
        new_email: target,
      });
      const synced = `${data.cases_updated} case${data.cases_updated === 1 ? "" : "s"} synced`;
      if (data.courtesy_email_sent) toast.success(`Email updated → ${data.new_email} (${synced}). Courtesy email sent.`);
      else toast.warning(`Email updated → ${data.new_email} (${synced}), but the courtesy email could not be sent — please notify the client directly.`);
      setEmailModalOpen(false);
      setNewEmail("");
      setConfirmEmail("");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setChangingEmail(false);
    }
  };

  return (
    <AdminErrorBoundary>
    <Layout>
      <Link to="/admin" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-6" data-testid="admin-back-btn">
        <ArrowLeft className="h-4 w-4" /> Back to cases
      </Link>

      <div className="mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Case #{c.id.slice(0, 8).toUpperCase()}
            {c.archived && <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 text-[10px]" data-testid="archived-badge">ARCHIVED</span>}
            {(() => {
              const isReview = (c.intake_path || "new") === "review";
              const setCents = c.payment?.amount_cents;
              const setLabel = setCents ? `$${(setCents / 100).toLocaleString(undefined, { minimumFractionDigits: setCents % 100 === 0 ? 0 : 2 })}` : null;
              const cls = isReview ? "bg-bronze/15 text-bronze" : "bg-navy/10 text-navy";
              const label = isReview ? "EXISTING TRUST REVIEW" : "NEW TRUST";
              return (
                <span className={`ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${cls} text-[10px] font-semibold`} data-testid="intake-path-badge">
                  {label}{setLabel ? ` · ${setLabel}` : ""}
                </span>
              );
            })()}
          </p>
          <h1 className="font-serif text-4xl text-navy">{c.client_name || c.client_email}</h1>
          {c.trust_name && <p className="text-navy/80 font-serif text-lg mt-0.5" data-testid="admin-trust-name">{c.trust_name}</p>}
          <p className="text-[#64748B] mt-1">
            <span data-testid="admin-client-email">{c.client_email}</span>
            <button
              type="button"
              onClick={() => { setNewEmail(""); setConfirmEmail(""); setEmailModalOpen(true); }}
              className="ml-2 inline-flex items-center gap-1 text-xs text-bronze hover:text-navy underline underline-offset-4"
              data-testid="admin-change-email-btn"
              title="Change this client's login email">
              Change
            </button>
            <button
              type="button"
              onClick={() => setTempPwOpen(true)}
              className="ml-2 inline-flex items-center gap-1 text-xs text-bronze hover:text-navy underline underline-offset-4"
              data-testid="admin-temp-password-btn"
              title="Set a temporary password for this client">
              Temp password
            </button>
            <button
              type="button"
              onClick={() => startViewAsClient(c.id, refresh, navigate, (e) => toast.error(formatApiError(e.response?.data?.detail)))}
              className="ml-2 inline-flex items-center gap-1 text-xs text-bronze hover:text-navy underline underline-offset-4"
              data-testid="admin-view-as-client-btn"
              title="See the portal exactly as this client sees it (read-only)">
              <Eye className="h-3 w-3" /> View as Client
            </button>
            {c.client_phone && (
              <>
                {" · "}
                <a href={`tel:${c.client_phone}`} className="text-navy font-medium hover:text-bronze" data-testid="admin-client-phone">
                  {c.client_phone}
                </a>
              </>
            )}
            {" · "}{(c.intake_path || "new") === "review" ? "Existing Trust Review" : (c.trust_type === "joint" ? "Joint Trust" : "Single Trust")}
          </p>
          <p className="text-[#64748B] mt-1 text-sm" data-testid="admin-client-last-login">
            <button
              type="button"
              onClick={toggleLogins}
              className="text-left text-[#64748B] hover:text-navy"
              data-testid="admin-client-logins-toggle"
              aria-expanded={loginsOpen}>
              <span className="underline decoration-dotted underline-offset-4">Last login:</span>{" "}
              {c.client_last_login_at ? (
                <span className="text-navy font-medium" title={c.client_last_login_at}>
                  {new Date(c.client_last_login_at).toLocaleString()}
                </span>
              ) : (
                <span className="text-[#94A3B8] italic">never</span>
              )}
              {c.client_last_logout_at && (
                <span className="text-[#94A3B8]"> · last logout {new Date(c.client_last_logout_at).toLocaleString()}</span>
              )}
              <span className="ml-1 text-[#94A3B8]">({loginsOpen ? "hide" : "show last 5"})</span>
            </button>
          </p>
          {loginsOpen && (
            <div className="mt-2 max-w-2xl bg-white border border-[#E2E0DA] rounded-md overflow-hidden" data-testid="admin-client-logins-table">
              {loginRows === null ? (
                <p className="px-3 py-2 text-sm text-[#94A3B8]">Loading…</p>
              ) : loginRows.length === 0 ? (
                <p className="px-3 py-2 text-sm text-[#94A3B8]">No login activity recorded yet.</p>
              ) : (
                <table className="w-full text-xs">
                  <thead className="bg-sand-200/40 text-[#64748B] uppercase tracking-wide">
                    <tr>
                      <th className="text-left px-3 py-1.5 font-semibold">Kind</th>
                      <th className="text-left px-3 py-1.5 font-semibold">When</th>
                      <th className="text-left px-3 py-1.5 font-semibold">IP</th>
                      <th className="text-left px-3 py-1.5 font-semibold">User agent</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loginRows.map((r, i) => (
                      <tr key={i} className="border-t border-[#F1EFEA]" data-testid={`admin-login-row-${i}`}>
                        <td className={`px-3 py-1.5 font-medium ${r.kind === "login" ? "text-green-700" : "text-[#64748B]"}`}>{r.kind}</td>
                        <td className="px-3 py-1.5 text-navy">{r.ts ? new Date(r.ts).toLocaleString() : "—"}</td>
                        <td className="px-3 py-1.5 text-[#64748B] font-mono">{r.ip || "—"}</td>
                        <td className="px-3 py-1.5 text-[#94A3B8] truncate max-w-[260px]" title={r.user_agent}>{r.user_agent || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
          <PasswordHistory caseId={caseId} refreshKey={pwHistoryKey} />
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

      <AdminCaseFieldsEditor key={c.updated_at} c={c} onSaved={load} />
      <AdminAssetsPanel caseId={caseId} />

      {/* Schedule A */}
      {scheduleA && (scheduleA.part_i?.length > 0 || scheduleA.part_ii?.length > 0) && (
        <Section title="Schedule A — Preview">
          <p className="text-xs uppercase text-amber-700 font-semibold mb-2 tracking-wide" data-testid="schedule-a-label">PREVIEW — Not the official document</p>
          <button type="button" onClick={() => setScheduleAOpen(!scheduleAOpen)}
            className="text-sm text-navy flex items-center gap-2 min-h-[44px] mb-2"
            data-testid="schedule-a-toggle">
            <ChevronDown className={`h-4 w-4 transition-transform ${scheduleAOpen ? "rotate-180" : ""}`} />
            {scheduleAOpen ? "Hide" : "Show"} items
            ({(scheduleA.part_i?.length || 0) + (scheduleA.part_ii?.length || 0)} moved into trust)
          </button>

          {scheduleAOpen && (
            <div className="overflow-x-auto rounded-lg border border-[#E2E0DA]" data-testid="schedule-a-table">
              <table className="w-full text-xs">
                <thead className="bg-[#F6F4F0]">
                  <tr>
                    <th className="px-3 py-2 text-left text-[#64748B] font-semibold">#</th>
                    <th className="px-3 py-2 text-left text-[#64748B] font-semibold">Part</th>
                    <th className="px-3 py-2 text-left text-[#64748B] font-semibold">Description</th>
                    <th className="px-3 py-2 text-left text-[#64748B] font-semibold">Date</th>
                    <th className="px-3 py-2 text-left text-[#64748B] font-semibold">Method</th>
                  </tr>
                </thead>
                <tbody>
                  {(scheduleA.part_i || []).map((r, i) => (
                    <tr key={`i-${i}`} className="border-t border-[#E2E0DA]">
                      <td className="px-3 py-2">{r.number}</td>
                      <td className="px-3 py-2 text-[#64748B]">Part I</td>
                      <td className="px-3 py-2">{r.description_of_property}</td>
                      <td className="px-3 py-2">{r.date_delivered || "—"}</td>
                      <td className="px-3 py-2">{r.instrument_or_method_of_transfer || "—"}</td>
                    </tr>
                  ))}
                  {(scheduleA.part_ii || []).map((r, i) => (
                    <tr key={`ii-${i}`} className="border-t border-[#E2E0DA]">
                      <td className="px-3 py-2">{r.number}</td>
                      <td className="px-3 py-2 text-[#64748B]">Part II</td>
                      <td className="px-3 py-2">{r.description_of_property}</td>
                      <td className="px-3 py-2">{r.date_delivered || "—"}</td>
                      <td className="px-3 py-2">{r.instrument_or_method_of_transfer || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="flex gap-3 mt-3 flex-wrap">
            <button onClick={() => exportScheduleA("csv")} className="btn-secondary text-sm min-h-[44px] flex items-center gap-2" data-testid="export-schedule-a-csv">
              <Download className="h-4 w-4" /> Export CSV
            </button>
            <button onClick={() => exportScheduleA("json")} className="btn-secondary text-sm min-h-[44px] flex items-center gap-2" data-testid="export-schedule-a-json">
              <FileText className="h-4 w-4" /> Export JSON
            </button>
          </div>
        </Section>
      )}

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
            className="bg-white border border-input rounded-md px-3 py-2 text-base min-h-[44px]" data-testid="admin-status-select">
            {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <span className="text-xs text-[#64748B]" data-testid="admin-status-internal-note">Internal only. The client does not see this or get an email until you press Release.</span>
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
        <Section title={`Grantors (${(c.grantors || []).filter(g => g && g.id).length || 0})`}>
          {(c.grantors || []).filter(g => g && g.id).map((g, i) => (
            <div key={g.id} className="mb-4" data-testid={`admin-grantor-${i}`}>
              <p className="text-xs uppercase text-bronze font-semibold mb-2">Grantor {i + 1}</p>
              <KV k="Name" v={`${g.full_legal_name || "—"}${g.middle_name ? " (" + g.middle_name + ")" : ""}`} />
              <KV k="DOB" v={g.date_of_birth} />
              <KV k="SSN" v={<SSNReveal caseId={c.id} grantorId={g.id} masked={g.ssn} />} />
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

        <Section title="Payment">
          {/* Stripe account info (small) */}
          {stripeInfo && (
            <div className="text-xs text-[#64748B] mb-3 flex items-center gap-2 flex-wrap" data-testid="stripe-account-info">
              <CreditCard className="h-3.5 w-3.5" />
              Stripe: <b className="text-navy">{stripeInfo.business_name || stripeInfo.account_id}</b>
              {" "}&middot; {stripeInfo.mode?.toUpperCase()}
              {" "}&middot; {stripeInfo.charges_enabled ? "charges enabled" : "charges not enabled"}
              {" "}&middot; Debit only &middot; No Apple/Google Pay
            </div>
          )}

          {/* Payment status */}
          <div className="flex flex-wrap gap-2 mb-4">
            <button onClick={setAmountOnly} className="btn-secondary text-sm min-h-[44px]" data-testid="set-amount-btn">
              {c.payment?.amount_cents ? `Update amount ($${(c.payment.amount_cents/100).toFixed(2)})` : "Set payment amount"}
            </button>
            <button onClick={() => setPaymentLinkOpen(!paymentLinkOpen)} className="btn-primary text-sm min-h-[44px] flex items-center gap-2" data-testid="send-payment-link-btn">
              <Send className="h-4 w-4" /> Send payment link
            </button>
            {(!c.payment?.status || ["none","amount_set","link_sent"].includes(c.payment?.status)) && (
              <button onClick={markZelleReceived} className="btn-secondary text-sm min-h-[44px] flex items-center gap-2" data-testid="mark-zelle-btn">
                <Smartphone className="h-4 w-4" /> Mark Zelle received
              </button>
            )}
          </div>

          {/* Send payment link form */}
          {paymentLinkOpen && (
            <div className="border border-bronze/40 bg-bronze/5 rounded-xl p-4 space-y-3 mb-4" data-testid="payment-link-form">
              <p className="text-sm font-semibold text-navy">Send Stripe payment link to {c.client_email}</p>
              <p className="text-xs text-[#64748B]">Debit cards only. No credit cards, no Apple Pay, no Google Pay. Stripe Embedded Checkout.</p>
              <div>
                <label className="text-xs uppercase text-[#64748B] font-semibold">Package</label>
                <select value={plLookupKey} onChange={e => setPlLookupKey(e.target.value)}
                  className="w-full rounded-lg border border-input bg-white px-3 py-2 text-sm mt-1 min-h-[44px]"
                  data-testid="pl-package-select">
                  <option value="basic_living_trust">Basic Living Trust</option>
                  <option value="private_trust">Private Trust</option>
                </select>
              </div>
              <div>
                <label className="text-xs uppercase text-[#64748B] font-semibold">Email subject (optional)</label>
                <input type="text" value={plSubject} onChange={e => setPlSubject(e.target.value)}
                  placeholder="Your trust payment is ready"
                  className="w-full rounded-lg border border-input bg-white px-3 py-2 text-sm mt-1 min-h-[44px]"
                  data-testid="pl-subject-input" />
              </div>
              <div>
                <label className="text-xs uppercase text-[#64748B] font-semibold">Email message (optional)</label>
                <textarea value={plMessage} onChange={e => setPlMessage(e.target.value)}
                  rows={3} placeholder="Your payment is now ready. Debit cards only."
                  className="w-full rounded-lg border border-input bg-white px-3 py-2 text-sm mt-1 resize-none"
                  data-testid="pl-message-input" />
              </div>
              <div className="flex gap-3">
                <button onClick={sendPaymentLink} disabled={plSending}
                  className="btn-primary text-sm min-h-[48px] flex-1 flex items-center justify-center gap-2"
                  data-testid="pl-send-btn">
                  <Send className="h-4 w-4" /> {plSending ? "Sending…" : "Send link to client"}
                </button>
                <button onClick={() => setPaymentLinkOpen(false)} className="btn-secondary text-sm min-h-[48px]"
                  data-testid="pl-cancel-btn">Cancel</button>
              </div>
              <p className="text-xs text-[#64748B]">
                Note: Stripe sends its own automatic receipt email to the client after payment succeeds.
                You can turn this off in your Stripe Dashboard under Settings &rarr; Customer emails &rarr; Successful payments.
              </p>
            </div>
          )}

          {/* Zelle received */}
          {c.payment?.status === "received_zelle" && (
            <div className="bg-emerald-50 border border-emerald-300 rounded-lg px-4 py-3 text-sm mb-4" data-testid="zelle-received-banner">
              <p className="font-semibold text-emerald-900">Zelle payment recorded</p>
              <p className="text-xs text-emerald-800 mt-0.5">
                ${(c.payment.amount_cents / 100).toFixed(2)} received manually
                {c.payment.zelle_received_at ? ` on ${c.payment.zelle_received_at.slice(0, 10)}` : ""}
              </p>
              <p className="text-xs text-emerald-700 mt-1">Client visible status not changed. Press Release when ready.</p>
            </div>
          )}

          {/* Stripe paid */}
          {["paid","verified"].includes(c.payment?.status) && (
            <div className="bg-emerald-50 border border-emerald-300 rounded-lg px-4 py-3 text-sm mb-4" data-testid="stripe-paid-banner">
              <p className="font-semibold text-emerald-900">Stripe payment confirmed</p>
              <p className="text-xs text-emerald-800 mt-0.5">
                ${c.payment?.amount_cents ? (c.payment.amount_cents / 100).toFixed(2) : "?"}
                {c.payment?.stripe_paid_at ? ` on ${c.payment.stripe_paid_at.slice(0, 10)}` : ""}
              </p>
            </div>
          )}

          {/* Summary */}
          <div className="text-sm space-y-1">
            <div className="text-xs text-[#64748B]">
              <span className="font-semibold">Status:</span> {c.payment?.status || "none"}
              {c.payment?.amount_cents ? ` · $${(c.payment.amount_cents/100).toFixed(2)}` : ""}
              {c.payment?.link_sent_at ? ` · link sent ${c.payment.link_sent_at.slice(0,10)}` : ""}
            </div>
          </div>
        </Section>

        <Section title="Trust Draft — Secure Preview">
          {!c.trust_draft ? (
            <div>
              <p className="text-sm text-[#64748B] mb-3">
                <b>Optional fallback:</b> upload a PDF draft instead of (or in addition to) the structured viewer above.
                The structured viewer above takes precedence when populated. Printing and downloading are disabled for
                the client until payment is received.
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
              <ExplainerHealthBadge key={c.trust_draft.id} caseId={caseId} />
              <div className={`mt-3 p-3 rounded-md border text-sm flex flex-wrap items-center justify-between gap-3 ${c.trust_draft.released === false ? "bg-amber-50 border-amber-300 text-amber-900" : "bg-emerald-50 border-emerald-300 text-emerald-900"}`}
                data-testid="trust-draft-release-status">
                <span>
                  {c.trust_draft.released === false
                    ? "Hidden from client — only you can see this draft and its explainer."
                    : `Visible to client${c.trust_draft.released_at ? ` since ${c.trust_draft.released_at.slice(0, 16).replace("T", " ")}` : ""}.`}
                </span>
                {c.trust_draft.released === false && <span className="text-xs">Use the Release button at the bottom of the screen.</span>}
              </div>
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
                <button onClick={deleteDraft} className="btn-secondary text-sm text-red-700 hover:text-red-800 border-red-200 hover:border-red-300" data-testid="trust-draft-delete-btn">
                  <Trash2 className="h-4 w-4 inline mr-1" /> Delete draft
                </button>
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

        <AdminDocumentsManager
          caseId={caseId}
          docs={c.admin_documents || []}
          onChanged={() => load()}
          className="lg:col-span-2"
        />

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
                  <div className="flex items-center gap-3 shrink-0">
                    <button onClick={() => download(d)} className="text-navy hover:text-bronze" title="Download" data-testid={`admin-doc-download-${d.id}`}><Download className="h-4 w-4" /></button>
                    <button onClick={() => removeClientDoc(d)} className="text-red-600 hover:text-red-700" title="Remove document" data-testid={`admin-doc-remove-${d.id}`}><Trash2 className="h-4 w-4" /></button>
                  </div>
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
        <WhatsAppPanel caseId={caseId} defaultTo={c.grantors?.[0]?.phone || c.client_phone || ""} />
      </div>

      <div className="mt-6">
        <MessageThread caseId={caseId} title="Client Messages" />
      </div>

      {/* Admin force-change email modal — two-step typed confirmation to prevent fat-fingers */}
      {emailModalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-navy/50"
          data-testid="admin-change-email-modal"
          onClick={(e) => { if (e.target === e.currentTarget && !changingEmail) setEmailModalOpen(false); }}>
          <div className="bg-white border border-[#E2E0DA] rounded-xl shadow-2xl w-full max-w-md p-6">
            <h3 className="font-serif text-2xl text-navy mb-1">Change client login email</h3>
            <p className="text-sm text-[#64748B] mb-4">
              This replaces the client's login email everywhere. All their data stays intact — grantors, documents, payments, and messages are untouched.
            </p>
            <div className="rounded-md bg-sand/40 border border-[#E2E0DA] p-3 mb-4 text-sm">
              <p className="text-[#64748B]">Current email</p>
              <p className="font-semibold text-navy break-all" data-testid="admin-change-email-current">{c.client_email}</p>
            </div>
            <div className="space-y-3">
              <div>
                <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 block">New email</label>
                <input
                  type="email"
                  autoFocus
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  disabled={changingEmail}
                  className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
                  placeholder="client.new.email@example.com"
                  data-testid="admin-change-email-new"
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 block">Confirm new email</label>
                <input
                  type="email"
                  value={confirmEmail}
                  onChange={(e) => setConfirmEmail(e.target.value)}
                  disabled={changingEmail}
                  className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
                  placeholder="retype the new email"
                  data-testid="admin-change-email-confirm"
                />
              </div>
            </div>
            <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-xs text-amber-900 mt-4">
              A courtesy email will be sent to the new address with sign-in instructions. The change is logged for audit.
            </div>
            <div className="flex gap-2 justify-end mt-5">
              <button
                type="button"
                onClick={() => setEmailModalOpen(false)}
                disabled={changingEmail}
                className="btn-secondary"
                data-testid="admin-change-email-cancel">Cancel</button>
              <button
                type="button"
                onClick={changeClientEmail}
                disabled={changingEmail || !newEmail.trim() || newEmail.trim() !== confirmEmail.trim()}
                className="btn-primary disabled:opacity-50"
                data-testid="admin-change-email-submit">
                {changingEmail ? "Updating…" : "Change email"}
              </button>
            </div>
          </div>
        </div>
      )}
      {tempPwOpen && (
        <TempPasswordDialog email={c.client_email} label={c.client_name || c.client_email} onClose={() => { setTempPwOpen(false); setPwHistoryKey((k) => k + 1); }} />
      )}
      <ReleaseBar caseId={caseId} reloadKey={c.updated_at} onReleased={load} />
    </Layout>
    </AdminErrorBoundary>
  );
}
