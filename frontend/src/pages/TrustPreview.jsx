import React, { useEffect, useRef, useState, useCallback } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, Lock, Shield, Video, CheckCircle2,
  AlertTriangle, Eye, Stamp, ScrollText,
} from "lucide-react";
import { Checkbox } from "@/components/ui/checkbox";

const ZOOM_LINK = "https://us06web.zoom.us/j/7194164805?pwd=OTkyQlQ2QXNwWm5xeTBjbDkxWklJUT09";

// Anti-copy / anti-print helpers
function useNoCopyAndBlurOnLeave(containerRef, setDimmed) {
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const stop = (e) => { e.preventDefault(); return false; };

    // Disable context menu, copy, cut, drag-start within the preview
    const events = ["contextmenu", "copy", "cut", "dragstart", "selectstart"];
    events.forEach((evt) => el.addEventListener(evt, stop));

    // Block keyboard shortcuts that try to print/save while focused
    const keyBlock = (e) => {
      const k = (e.key || "").toLowerCase();
      const meta = e.ctrlKey || e.metaKey;
      if (meta && ["p", "s", "c", "u"].includes(k)) { e.preventDefault(); toast.error("Draft is locked. Printing and copying are disabled."); return false; }
      // PrintScreen attempt (can't truly block OS, but blur and notify)
      if (k === "printscreen") { setDimmed(true); toast.warning("Screenshots are disabled for draft trusts."); setTimeout(() => setDimmed(false), 1200); }
      return true;
    };
    window.addEventListener("keydown", keyBlock);

    // Global print block while viewing preview
    const onBeforePrint = (e) => { e?.preventDefault?.(); toast.error("Printing is disabled for draft trusts."); };
    window.addEventListener("beforeprint", onBeforePrint);

    // Dim on blur / visibility change (defeats many screenshot tools)
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
  const [pageBlobUrl, setPageBlobUrl] = useState(null);
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [dimmed, setDimmed] = useState(false);
  const containerRef = useRef(null);

  // Disclosure acks
  const [trustCase, setTrustCase] = useState(null);
  const [disclosureAck, setDisclosureAck] = useState(false);
  const [stateLawsAck, setStateLawsAck] = useState(false);
  const [notarizationAck, setNotarizationAck] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [{ data: m }, { data: c }] = await Promise.all([
        api.get(`/trust-cases/${caseId}/trust-preview/meta`),
        api.get(`/trust-cases/${caseId}`),
      ]);
      setMeta(m);
      setTrustCase(c);
      const a = c.acknowledgments || {};
      setDisclosureAck(!!a.disclosure_ack);
      setStateLawsAck(!!a.state_laws_ack);
      setNotarizationAck(!!a.notarization_ack);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Could not load trust preview.");
      navigate("/portal");
    } finally { setLoading(false); }
  }, [caseId, navigate]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let current = null;
    if (!meta) return;
    setPageLoading(true);
    const fetchPage = async () => {
      try {
        const res = await api.get(`/trust-cases/${caseId}/trust-preview/page/${pageIdx}.png`, { responseType: "blob" });
        const url = URL.createObjectURL(res.data);
        current = url;
        setPageBlobUrl((prev) => { if (prev) URL.revokeObjectURL(prev); return url; });
      } catch (e) {
        toast.error("Could not load page.");
      } finally { setPageLoading(false); }
    };
    fetchPage();
    return () => { if (current) { /* keep until replaced */ } };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta?.pages, pageIdx, caseId]);

  useNoCopyAndBlurOnLeave(containerRef, setDimmed);

  const payment = trustCase?.payment || {};
  const hasInvoice = !!payment.invoice_id;
  const payUrl = payment.public_url;
  const paymentBadgeCopy = {
    none: null,
    invoice_sent: "Invoice sent — pay anytime below.",
    ach_pending: "ACH payment received — waiting for bank to clear (3–5 business days).",
    paid: "Payment received. Final trust will unlock shortly.",
    paid_manual: "Payment received. Final trust will unlock shortly.",
    canceled: "Invoice was canceled.",
    failed: "Payment failed. Please contact your agent.",
  }[payment.status] || null;

  const saveAck = async (patch) => {
    setSaving(true);
    try {
      await api.put(`/trust-cases/${caseId}/acknowledgments`, patch);
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const submitReview = async () => {
    if (!disclosureAck || !stateLawsAck || !notarizationAck) {
      toast.error("Please acknowledge all disclosures before completing review.");
      return;
    }
    setSaving(true);
    try {
      await api.put(`/trust-cases/${caseId}/acknowledgments`, {
        disclosure_ack: true, state_laws_ack: true, notarization_ack: true, review_completed_ack: true,
      });
      toast.success("Thank you for reviewing your trust. Your agent will contact you shortly.");
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  if (loading || !meta) return <Layout><p className="text-[#64748B]">Loading secure preview…</p></Layout>;

  const totalPages = meta.pages || 0;
  const reviewCompleted = !!meta.review_completed;

  return (
    <Layout>
      <Link to="/portal" className="text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1 mb-4" data-testid="preview-back">
        <ChevronLeft className="h-4 w-4" /> Back to portal
      </Link>

      <div className="mb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-1">Secure Draft Preview</p>
          <h1 className="font-serif text-3xl sm:text-4xl text-navy">{meta.trust_name || "Trust Draft"}</h1>
          <p className="text-[#64748B] text-sm mt-1">Case #{caseId.slice(0, 8).toUpperCase()} · {totalPages} page(s) · Version {meta.version}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <a href={ZOOM_LINK} target="_blank" rel="noreferrer" className="btn-secondary text-sm" data-testid="preview-zoom-btn">
            <Video className="h-4 w-4 inline mr-1" /> Schedule Review Call
          </a>
        </div>
      </div>

      <div className="mb-4 bg-navy/5 border border-navy/20 rounded-xl p-4 text-sm text-navy flex items-start gap-3" data-testid="preview-security-notice">
        <Shield className="h-5 w-5 text-bronze shrink-0 mt-0.5" />
        <div className="flex-1">
          <p className="font-semibold">This draft is locked until payment is received.</p>
          <p className="text-[#334155]">Printing, downloading, right-click, and copying are disabled. The preview is watermarked and shown in low resolution. Every page says <b>"IGC — SAMPLE ONLY — NOT VALID UNTIL PAID."</b></p>
        </div>
      </div>

      {hasInvoice && (
        <div className="mb-4 bg-bronze/10 border border-bronze/40 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center gap-3 justify-between" data-testid="preview-payment-banner">
          <div>
            <p className="font-semibold text-navy">Payment</p>
            <p className="text-sm text-[#334155]">{paymentBadgeCopy}</p>
          </div>
          {payUrl && payment.status !== "paid" && payment.status !== "paid_manual" && (
            <a href={payUrl} target="_blank" rel="noreferrer" className="btn-accent text-sm shrink-0" data-testid="preview-pay-btn">
              Pay securely with Square
            </a>
          )}
        </div>
      )}

      {/* Viewer */}
      <div
        ref={containerRef}
        className={`relative bg-navy rounded-xl overflow-hidden select-none transition-opacity duration-200 ${dimmed ? "opacity-10 blur-md" : "opacity-100"}`}
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
            <div className="absolute inset-0 flex items-center justify-center text-white/60 text-sm">
              Rendering page…
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

        {/* Overlay watermark layer (on top of image to defeat quick copy of the img alone) */}
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
          <div className="flex items-center gap-2">
            {Array.from({ length: totalPages }).map((_, i) => (
              <button
                key={i}
                onClick={() => setPageIdx(i + 1)}
                className={`h-2.5 w-2.5 rounded-full transition-colors ${pageIdx === i + 1 ? "bg-bronze" : "bg-white/30 hover:bg-white/60"}`}
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

      {/* Legal disclosures (persisted) */}
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

      {/* Review completed CTA */}
      <div className="mt-8 bg-navy text-white rounded-xl p-6 sm:p-8 flex flex-col sm:flex-row items-start sm:items-center gap-4 justify-between" data-testid="preview-review-complete-section">
        <div>
          <p className="font-serif text-2xl mb-1">{reviewCompleted ? "Thank you for reviewing your trust." : "Satisfied with your trust?"}</p>
          <p className="text-sm text-white/80">
            {reviewCompleted
              ? "Your agent has been notified and will contact you shortly about payment."
              : "When you're satisfied with the draft and have acknowledged the disclosures, press the button below. Your agent will contact you to arrange payment."}
          </p>
        </div>
        {reviewCompleted ? (
          <span className="inline-flex items-center gap-2 text-bronze font-semibold" data-testid="preview-review-completed-badge">
            <CheckCircle2 className="h-5 w-5" /> Review completed
          </span>
        ) : (
          <button onClick={submitReview} disabled={saving} className="btn-accent shrink-0" data-testid="preview-review-completed-btn">
            {saving ? "Submitting…" : "Review Completed — I Am Satisfied With My Trust"}
          </button>
        )}
      </div>

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
    </Layout>
  );
}
