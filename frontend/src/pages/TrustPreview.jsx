import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, Lock, Shield, CheckCircle2,
  AlertTriangle, Stamp, ScrollText, PhoneCall, Loader2,
} from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";
import TrustViewerTwoPanel from "@/components/TrustViewerTwoPanel";
import TrustDraftExplanationPanel from "@/components/TrustDraftExplanationPanel";

// Anti-copy / anti-print helpers
function useNoCopyAndBlurOnLeave(containerRef, setDimmed) {
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const stop = (e) => { e.preventDefault(); return false; };
    const events = ["contextmenu", "copy", "cut", "dragstart", "selectstart"];
    events.forEach((evt) => el.addEventListener(evt, stop));

    const keyBlock = (e) => {
      const k = (e.key || "").toLowerCase();
      const meta = e.ctrlKey || e.metaKey;
      if (meta && ["p", "s", "c", "u"].includes(k)) { e.preventDefault(); toast.error("Draft is locked. Printing and copying are disabled."); return false; }
      if (k === "printscreen") { setDimmed(true); toast.warning("Screenshots are disabled for draft trusts."); setTimeout(() => setDimmed(false), 1200); }
      return true;
    };
    window.addEventListener("keydown", keyBlock);

    const onBeforePrint = (e) => { e?.preventDefault?.(); toast.error("Printing is disabled for draft trusts."); };
    window.addEventListener("beforeprint", onBeforePrint);

    const onBlur = () => setDimmed(true);
    const onFocus = () => setDimmed(false);
    const onVis = () => setDimmed(document.visibilityState !== "visible");
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);

    return () => {
      events.forEach((evt) => el.removeEventListener(evt, stop));
      window.removeEventListener("keydown", keyBlock);
      window.removeEventListener("beforeprint", onBeforePrint);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [containerRef, setDimmed]);
}

export default function TrustPreview() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const [meta, setMeta] = useState(null);
  const [pageIdx, setPageIdx] = useState(1);
  const [pageLoading, setPageLoading] = useState(false);
  const [dimmed, setDimmed] = useState(false);
  const containerRef = useRef(null);

  // Per-page in-memory blob-url cache (avoids re-downloading + re-rendering)
  const pageCacheRef = useRef({}); // { [pageNum]: blobUrl }
  const [pageBlobUrl, setPageBlobUrl] = useState(null);

  const [trustCase, setTrustCase] = useState(null);
  const [disclosureAck, setDisclosureAck] = useState(false);
  const [stateLawsAck, setStateLawsAck] = useState(false);
  const [notarizationAck, setNotarizationAck] = useState(false);
  const [saving, setSaving] = useState(false);

  // "Schedule a call" modal
  const [callOpen, setCallOpen] = useState(false);
  const [callMessage, setCallMessage] = useState(null);
  const [callNote, setCallNote] = useState("");
  const [callSending, setCallSending] = useState(false);

  // "Need to speak with an agent?" pre-review callback request modal
  const [agentCbOpen, setAgentCbOpen] = useState(false);
  const [agentCbName, setAgentCbName] = useState("");
  const [agentCbPhone, setAgentCbPhone] = useState("");
  const [agentCbNote, setAgentCbNote] = useState("");
  const [agentCbSending, setAgentCbSending] = useState(false);
  const [agentCbDone, setAgentCbDone] = useState(false);

  const load = useCallback(async () => {
    try {
      // Always load the case. Trust-preview metadata only matters for the
      // legacy PDF viewer; if it 404s (no PDF uploaded), fall through —
      // the structured two-panel viewer doesn't need it.
      const { data: c } = await api.get(`/trust-cases/${caseId}`);
      setTrustCase(c);
      const a = c.acknowledgments || {};
      setDisclosureAck(!!a.disclosure_ack);
      setStateLawsAck(!!a.state_laws_ack);
      setNotarizationAck(!!a.notarization_ack);

      const hasSections = (c.trust_sections || []).length > 0;
      if (!hasSections) {
        try {
          const { data: m } = await api.get(`/trust-cases/${caseId}/trust-preview/meta`);
          setMeta(m);
        } catch (mErr) {
          // No PDF — that's fine if structured sections exist; otherwise show error.
          toast.error("Your trust review content is being prepared. Please check back soon.");
        }
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not load trust preview.");
      navigate("/portal");
    }
  }, [caseId, navigate]);

  useEffect(() => { load(); }, [load]);

  // Fetch one page + cache it. Returns blob url.
  const fetchPage = useCallback(async (n) => {
    if (!n || n < 1) return null;
    if (pageCacheRef.current[n]) return pageCacheRef.current[n];
    try {
      const res = await api.get(`/trust-cases/${caseId}/trust-preview/page/${n}.png`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      pageCacheRef.current[n] = url;
      return url;
    } catch (e) {
      return null;
    }
  }, [caseId]);

  // Display current page (and preload neighbors)
  useEffect(() => {
    if (!meta) return;
    let cancelled = false;
    setPageLoading(true);
    (async () => {
      const url = await fetchPage(pageIdx);
      if (cancelled) return;
      setPageBlobUrl(url);
      setPageLoading(false);
      // Preload next + previous + next+1 to keep the viewer snappy
      const toPreload = [pageIdx + 1, pageIdx - 1, pageIdx + 2];
      toPreload.forEach((n) => { if (n >= 1 && n <= (meta.pages || 0)) fetchPage(n); });
    })();
    return () => { cancelled = true; };
  }, [pageIdx, meta, fetchPage]);

  // Aggressive full prefetch in the background (1 at a time) so navigation is instant
  useEffect(() => {
    if (!meta) return;
    let cancelled = false;
    (async () => {
      const total = meta.pages || 0;
      for (let n = 1; n <= total; n++) {
        if (cancelled) return;
        if (!pageCacheRef.current[n]) {
          // eslint-disable-next-line no-await-in-loop
          await fetchPage(n);
        }
      }
    })();
    return () => { cancelled = true; };
  }, [meta, fetchPage]);

  // Cleanup on unmount
  useEffect(() => {
    const ref = pageCacheRef;
    return () => {
      Object.values(ref.current || {}).forEach((u) => { try { URL.revokeObjectURL(u); } catch (_) {} });
      ref.current = {};
    };
  }, []);

  useNoCopyAndBlurOnLeave(containerRef, setDimmed);

  const payment = trustCase?.payment || {};
  const hasInvoice = !!payment.invoice_id;
  const payUrl = payment.public_url;
  const paymentBadgeCopy = {
    none: null,
    invoice_sent: "Invoice is ready — press Pay Now to complete payment.",
    ach_pending: "ACH payment received — waiting for bank to clear (3–5 business days).",
    paid: "Payment received. Your final trust will unlock shortly.",
    paid_manual: "Payment received. Your final trust will unlock shortly.",
    canceled: "Invoice was canceled. Please contact your agent.",
    failed: "Payment failed. Please contact your agent.",
  }[payment.status] || null;

  const reviewCompleted = !!meta?.review_completed;

  const saveAck = async (patch) => {
    try { await api.put(`/trust-cases/${caseId}/acknowledgments`, patch); await load(); }
    catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const submitReview = async () => {
    if (!disclosureAck || !stateLawsAck || !notarizationAck) {
      toast.error("Please acknowledge all three disclosures before completing your review.");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/trust-cases/${caseId}/acknowledgments`, {
        disclosure_ack: true, state_laws_ack: true, notarization_ack: true, review_completed_ack: true,
      });
      toast.success("Thank you for completing your review.");
      await load();
      window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const scheduleCall = async () => {
    setCallSending(true);
    try {
      const { data } = await api.post(`/trust-cases/${caseId}/schedule-call`, { note: callNote || "" });
      setCallMessage(data.message || "Thank you. A team member will call you from a 954 number within 10 minutes.");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setCallSending(false); }
  };

  const submitAgentCallback = async () => {
    const name = agentCbName.trim();
    const phone = agentCbPhone.trim();
    if (name.length < 1 || phone.length < 7) {
      toast.error("Please enter your name and a callback number.");
      return;
    }
    setAgentCbSending(true);
    try {
      await api.post(`/trust-cases/${caseId}/callback-request`, {
        name, callback_phone: phone, note: agentCbNote.trim() || undefined,
      });
      setAgentCbDone(true);
      toast.success("Thanks — your agent will call you back shortly.");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setAgentCbSending(false); }
  };

  const closeAgentCb = () => {
    setAgentCbOpen(false);
    setAgentCbDone(false);
    setAgentCbName("");
    setAgentCbPhone("");
    setAgentCbNote("");
  };

  const hasSections = (trustCase?.trust_sections || []).length > 0;
  if (!trustCase) return <Layout><p className="text-[#64748B]">Loading secure preview…</p></Layout>;
  if (!hasSections && !meta) return <Layout><p className="text-[#64748B]">Loading secure preview…</p></Layout>;

  const totalPages = (meta && meta.pages) || 0;

  return (
    <Layout>
      <Link to="/portal" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-4" data-testid="preview-back">
        <ChevronLeft className="h-4 w-4" /> Back to portal
      </Link>

      <div className="mb-6">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Secure Draft Preview</p>
        <h1 className="font-serif text-3xl sm:text-4xl text-navy">{(meta && meta.trust_name) || trustCase?.trust_name || "Trust Draft"}</h1>
        <p className="text-[#64748B] text-sm mt-1">
          Case #{caseId.slice(0, 8).toUpperCase()}
          {meta ? ` · ${totalPages} page(s) · Version ${meta.version}` : (hasSections ? ` · ${trustCase.trust_sections.length} article(s)` : "")}
        </p>
      </div>

      <div className="mb-4 bg-navy/5 border border-navy/20 rounded-xl p-4 text-sm text-navy flex items-start gap-3" data-testid="preview-security-notice">
        <Shield className="h-5 w-5 text-bronze shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold">This draft is locked until payment is received.</p>
          <p className="text-[#334155]">Printing, downloading, right-click, and copying are disabled. The preview is watermarked. Every page says <b>"IGC — SAMPLE ONLY — NOT VALID UNTIL PAID."</b></p>
        </div>
      </div>

      {hasInvoice && paymentBadgeCopy && (
        <div className="mb-4 bg-bronze/10 border border-bronze/40 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between" data-testid="preview-payment-banner">
          <div>
            <p className="font-semibold text-navy">Payment</p>
            <p className="text-sm text-[#334155]">{paymentBadgeCopy}</p>
          </div>
        </div>
      )}

      {/* Viewer: structured two-panel (preferred) OR legacy PDF page-image viewer */}
      {(trustCase?.trust_sections && trustCase.trust_sections.length > 0) ? (
        <TrustViewerTwoPanel
          sections={trustCase.trust_sections}
          caseShortId={(trustCase.id || "").slice(0, 8).toUpperCase()}
          clientName={trustCase.client_name || trustCase.client_email}
          trustName={trustCase.trust_name}
        />
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="trust-preview-side-by-side">
        <div
          ref={containerRef}
          className={`pdf-viewer-container relative bg-navy rounded-xl overflow-hidden select-none transition-opacity duration-200 ${dimmed ? "opacity-10 blur-md" : "opacity-100"}`}
          style={{ userSelect: "none", WebkitUserSelect: "none" }}
          onCopy={(e) => e.preventDefault()}
          onContextMenu={(e) => e.preventDefault()}
          data-testid="preview-viewer">

        <div className="flex items-center justify-between px-4 py-3 bg-navy/90 text-white border-b border-white/10">
          <div className="text-xs tracking-wide uppercase text-white/70 flex items-center gap-2">
            <Lock className="h-3.5 w-3.5" /> Draft Preview · Watermarked
          </div>
          <div className="text-xs text-white/70" data-testid="preview-page-counter">
            Page {pageIdx} of {totalPages}
          </div>
        </div>

        <div className="relative flex items-center justify-center bg-[#0f1620] p-4 min-h-[500px]">
          {pageLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-[#0f1620]/80 z-10" data-testid="preview-loader">
              <div className="flex items-center gap-2 text-white/80 text-sm">
                <Loader2 className="h-5 w-5 animate-spin" /> Loading page…
              </div>
            </div>
          )}
          {pageBlobUrl && (
            <img
              src={pageBlobUrl}
              alt={`Trust draft page ${pageIdx}`}
              draggable={false}
              onDragStart={(e) => e.preventDefault()}
              onContextMenu={(e) => e.preventDefault()}
              style={{
                userSelect: "none",
                WebkitUserSelect: "none",
                pointerEvents: "none",
                maxWidth: "100%",
                height: "auto",
                boxShadow: "0 8px 30px rgba(0,0,0,0.4)",
              }}
              data-testid={`preview-page-img-${pageIdx}`}
            />
          )}
        </div>

        <div
          className="pointer-events-none absolute inset-0 flex items-center justify-center"
          style={{ mixBlendMode: "multiply" }}
          aria-hidden="true">
          <div className="grid grid-cols-3 gap-12 opacity-20 rotate-[-28deg] whitespace-nowrap text-[11px] tracking-widest font-mono text-white/60">
            {Array.from({ length: 18 }).map((_, i) => (
              <span key={i}>IGC — SAMPLE ONLY — NOT VALID UNTIL PAID</span>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between px-4 py-3 bg-navy/90 border-t border-white/10">
          <button
            onClick={() => setPageIdx(Math.max(1, pageIdx - 1))}
            disabled={pageIdx <= 1}
            className="inline-flex items-center gap-1 text-white/90 hover:text-bronze text-sm disabled:opacity-40"
            data-testid="preview-prev-page">
            <ChevronLeft className="h-4 w-4" /> Previous
          </button>
          <div className="flex items-center gap-2 overflow-x-auto max-w-[60%] no-scrollbar">
            {Array.from({ length: totalPages }).map((_, i) => (
              <button
                key={i}
                onClick={() => setPageIdx(i + 1)}
                className={`h-2.5 w-2.5 rounded-full transition-colors shrink-0 ${pageIdx === i + 1 ? "bg-bronze" : "bg-white/30 hover:bg-white/60"}`}
                aria-label={`Go to page ${i + 1}`}
                data-testid={`preview-dot-${i + 1}`}
              />
            ))}
          </div>
          <button
            onClick={() => setPageIdx(Math.min(totalPages, pageIdx + 1))}
            disabled={pageIdx >= totalPages}
            className="inline-flex items-center gap-1 text-white/90 hover:text-bronze text-sm disabled:opacity-40"
            data-testid="preview-next-page">
            Next <ChevronRight className="h-4 w-4" />
          </button>
        </div>
        </div>

        <TrustDraftExplanationPanel caseId={caseId} clientName={trustCase?.client_name} currentPage={pageIdx} totalPages={totalPages} />
      </div>
      )}

      {/* Legal disclosures */}
      <div className="mt-10">
        <h3 className="font-serif text-2xl text-navy mb-4 flex items-center gap-2">
          <ScrollText className="h-5 w-5 text-bronze" /> Legal Disclosures
        </h3>
        <div className="bg-white border border-[#E2E0DA] rounded-lg p-5 space-y-4" data-testid="preview-disclosures">
          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md">
            This trust has been reviewed for accuracy and completeness through my military legal benefits.
            All documents are prepared using standardized trust templates that are commonly reviewed by military legal professionals.
            I am not an attorney and do not provide legal advice. Clients may seek independent legal counsel at any time.
          </div>
          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer">
            <Checkbox checked={disclosureAck} onCheckedChange={(v) => { setDisclosureAck(!!v); saveAck({ disclosure_ack: !!v }); }} className="mt-0.5" data-testid="preview-ack-disclosure" />
            <span className="text-sm text-navy"><b>I have read and understand this legal disclosure.</b></span>
          </label>

          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md">
            <b>State-specific advisory.</b> Trust laws vary by state. Clients are responsible for ensuring the trust meets their personal legal needs and may seek independent legal counsel in their state at any time.
          </div>
          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer">
            <Checkbox checked={stateLawsAck} onCheckedChange={(v) => { setStateLawsAck(!!v); saveAck({ state_laws_ack: !!v }); }} className="mt-0.5" data-testid="preview-ack-state-laws" />
            <span className="text-sm text-navy"><b>I acknowledge that trust laws vary by state.</b></span>
          </label>

          <div className="text-sm text-[#334155] leading-relaxed p-4 bg-sand-200/40 border border-[#E2E0DA] rounded-md flex items-start gap-2">
            <Stamp className="h-4 w-4 shrink-0 mt-0.5 text-bronze" />
            <span><b>Notarization required.</b> Your trust must be printed and notarized to become legally valid once unlocked.</span>
          </div>
          <label className="flex items-start gap-3 p-3 border border-[#E2E0DA] rounded-md cursor-pointer">
            <Checkbox checked={notarizationAck} onCheckedChange={(v) => { setNotarizationAck(!!v); saveAck({ notarization_ack: !!v }); }} className="mt-0.5" data-testid="preview-ack-notarization" />
            <span className="text-sm text-navy"><b>I understand my trust must be printed and notarized.</b></span>
          </label>
        </div>
      </div>

      {/* ===================== Complete Review (or post-review Pay / Call) ===================== */}
      {!reviewCompleted ? (
        <div className="mt-10 space-y-4" data-testid="complete-review-section">
          <button
            onClick={submitReview}
            disabled={saving || !disclosureAck || !stateLawsAck || !notarizationAck}
            className="w-full py-5 sm:py-6 rounded-xl text-white text-xl sm:text-2xl font-bold shadow-lg transition-all active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ backgroundColor: "#28a745", minHeight: 64 }}
            data-testid="complete-review-btn">
            {saving ? "Submitting…" : "✓  Complete Review"}
          </button>
          <p className="mt-1 text-center text-xs text-[#64748B]">
            {(!disclosureAck || !stateLawsAck || !notarizationAck)
              ? "Check all three disclosures above to enable this button."
              : "Pressing this button notifies your agent. They will review and send your next steps shortly."}
          </p>

          <div className="relative my-2 flex items-center gap-3" aria-hidden>
            <div className="flex-1 h-px bg-[#E2E0DA]" />
            <span className="text-[10px] uppercase tracking-[0.2em] text-[#94A3B8]">or</span>
            <div className="flex-1 h-px bg-[#E2E0DA]" />
          </div>

          <button
            onClick={() => setAgentCbOpen(true)}
            className="w-full py-4 rounded-xl border-2 border-navy/30 hover:border-navy bg-white text-navy text-lg font-semibold transition-all active:scale-[0.99] inline-flex items-center justify-center gap-2"
            style={{ minHeight: 56 }}
            data-testid="need-agent-btn">
            <PhoneCall className="h-5 w-5" /> Need to speak with an agent?
          </button>
          <p className="mt-1 text-center text-xs text-[#64748B]">
            Have questions before you complete your review? Leave your callback number and we'll reach out.
          </p>
        </div>
      ) : (
        <div className="mt-10 space-y-6" data-testid="post-review-section">
          <div className="rounded-xl bg-green-50 border border-green-300 p-6 text-center">
            <CheckCircle2 className="h-10 w-10 text-green-700 mx-auto mb-2" />
            <p className="font-serif text-2xl text-navy mb-1">Review complete</p>
            <p className="text-sm text-[#334155] max-w-lg mx-auto">
              Thank you — your agent has been notified.
            </p>
          </div>

          <div
            className="rounded-xl bg-white border border-[#E2E0DA] p-8 text-center shadow-sm"
            data-testid="payment-notice"
          >
            <p className="text-lg text-navy leading-relaxed max-w-md mx-auto">
              Your agent will send you a payment link directly. You may also request payment via Zelle.
            </p>
          </div>

          <button
            onClick={() => { setCallOpen(true); setCallMessage(null); setCallNote(""); }}
            className="w-full py-4 rounded-xl bg-navy hover:bg-navy/90 text-white text-lg font-semibold shadow-md transition-all active:scale-[0.99] inline-flex items-center justify-center gap-2"
            style={{ minHeight: 56 }}
            data-testid="schedule-call-btn">
            <PhoneCall className="h-5 w-5" /> Schedule a Call
          </button>
        </div>
      )}

      <p className="mt-8 text-center text-xs text-[#94A3B8]">
        Prepared by <b>Iron Gate Consulting</b> · Reviewed through military legal benefits
      </p>

      {dimmed && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center pointer-events-none" data-testid="preview-dimmed-overlay">
          <div className="flex items-center gap-3 px-5 py-3 bg-white rounded-full text-navy text-sm">
            <AlertTriangle className="h-4 w-4 text-red-500" />
            Preview hidden — please return to this tab to view the draft.
          </div>
        </div>
      )}

      {/* Schedule-a-call modal */}
      {callOpen && (
        <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4" onClick={() => !callSending && setCallOpen(false)} data-testid="call-modal">
          <div className="bg-white rounded-xl p-6 sm:p-8 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            {callMessage ? (
              <div className="text-center">
                <div className="mx-auto mb-3 h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                  <PhoneCall className="h-6 w-6 text-green-700" />
                </div>
                <p className="font-serif text-2xl text-navy mb-2">Call scheduled</p>
                <p className="text-sm text-[#334155] mb-5" data-testid="call-confirmation">{callMessage}</p>
                <button onClick={() => setCallOpen(false)} className="btn-primary w-full" data-testid="call-close-btn">Close</button>
              </div>
            ) : (
              <>
                <p className="font-serif text-2xl text-navy mb-1">Request a callback</p>
                <p className="text-sm text-[#64748B] mb-4">Tell us anything you'd like us to know before the call (optional).</p>
                <textarea
                  value={callNote}
                  onChange={(e) => setCallNote(e.target.value)}
                  rows={4}
                  placeholder="Questions, best time to call, etc."
                  className="w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                  data-testid="call-note-input"
                />
                <div className="mt-4 flex gap-2">
                  <button onClick={() => setCallOpen(false)} className="btn-secondary flex-1" disabled={callSending} data-testid="call-cancel-btn">Cancel</button>
                  <button onClick={scheduleCall} className="btn-primary flex-1" disabled={callSending} data-testid="call-confirm-btn">
                    {callSending ? "Requesting…" : "Request callback"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* "Need to speak with an agent?" pre-review callback modal */}
      {agentCbOpen && (
        <div className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4" onClick={() => !agentCbSending && closeAgentCb()} data-testid="agent-callback-modal">
          <div className="bg-white rounded-xl p-6 sm:p-8 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            {agentCbDone ? (
              <div className="text-center">
                <div className="mx-auto mb-3 h-12 w-12 rounded-full bg-green-100 flex items-center justify-center">
                  <CheckCircle2 className="h-6 w-6 text-green-700" />
                </div>
                <p className="font-serif text-2xl text-navy mb-2">Callback requested</p>
                <p className="text-sm text-[#334155] mb-5" data-testid="agent-callback-confirmation">
                  Thanks, <b>{agentCbName}</b>. Your agent will call you back at <b>{agentCbPhone}</b> shortly.
                </p>
                <button onClick={closeAgentCb} className="btn-primary w-full" data-testid="agent-callback-close-btn">Close</button>
              </div>
            ) : (
              <>
                <p className="font-serif text-2xl text-navy mb-1">Speak with an agent</p>
                <p className="text-sm text-[#64748B] mb-4">
                  Enter your name and a callback number. Your agent will call you back to answer questions about your trust draft.
                </p>
                <div className="space-y-3">
                  <div>
                    <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Your name</label>
                    <input
                      type="text"
                      value={agentCbName}
                      onChange={(e) => setAgentCbName(e.target.value)}
                      autoComplete="name"
                      placeholder="Jane Smith"
                      className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                      data-testid="agent-callback-name-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Best callback number</label>
                    <input
                      type="tel"
                      value={agentCbPhone}
                      onChange={(e) => setAgentCbPhone(e.target.value)}
                      autoComplete="tel"
                      placeholder="(555) 123-4567"
                      className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                      data-testid="agent-callback-phone-input"
                    />
                  </div>
                  <div>
                    <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">What would you like to discuss? (optional)</label>
                    <textarea
                      value={agentCbNote}
                      onChange={(e) => setAgentCbNote(e.target.value)}
                      rows={3}
                      placeholder="Questions about your trust, best time to reach you, etc."
                      className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                      data-testid="agent-callback-note-input"
                    />
                  </div>
                </div>
                <div className="mt-4 flex gap-2">
                  <button onClick={closeAgentCb} className="btn-secondary flex-1" disabled={agentCbSending} data-testid="agent-callback-cancel-btn">Cancel</button>
                  <button
                    onClick={submitAgentCallback}
                    className="btn-primary flex-1"
                    disabled={agentCbSending || !agentCbName.trim() || agentCbPhone.trim().length < 7}
                    data-testid="agent-callback-submit-btn">
                    {agentCbSending ? "Requesting…" : "Request callback"}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </Layout>
  );
}
