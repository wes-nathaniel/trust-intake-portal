import React, { useState, useEffect, useRef } from "react";
import api from "@/lib/api";
import { Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";

/**
 * Admin-only SSN reveal control. Renders the masked SSN by default (safe
 * for shoulder-surfing) and provides a "Show" button that fetches the full
 * plaintext SSN from the audited /reveal-ssn endpoint. Auto-hides after
 * `hideAfterSeconds` (default 30s) so the plaintext does not linger on
 * screen. Clicking Hide manually also clears it immediately.
 *
 * Every reveal is server-side logged (admin id, IP, timestamp, grantor id)
 * so the firm has an audit trail for IRS/compliance.
 */
export default function SSNReveal({ caseId, grantorId, masked, hideAfterSeconds = 30 }) {
  const [revealed, setRevealed] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const timerRef = useRef(null);

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const show = async () => {
    if (loading || revealed) return;
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/grantors/${grantorId}/reveal-ssn`);
      setRevealed(data.ssn);
      clearTimer();
      timerRef.current = setTimeout(() => setRevealed(null), hideAfterSeconds * 1000);
    } catch (e) {
      const detail = e.response?.data?.detail || "Could not reveal SSN.";
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

  const hide = () => {
    clearTimer();
    setRevealed(null);
    setError(null);
  };

  return (
    <div className="inline-flex items-center gap-2 flex-wrap" data-testid={`ssn-reveal-${grantorId}`}>
      <span className="font-mono text-navy" data-testid="ssn-value">
        {revealed || masked || "—"}
      </span>
      {revealed ? (
        <button
          type="button"
          onClick={hide}
          data-testid="ssn-hide-btn"
          className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-white bg-navy hover:bg-navy/80 px-2 py-1 rounded-full transition-colors"
          title={`Auto-hides in ${hideAfterSeconds}s`}
        >
          <EyeOff className="h-3 w-3" /> Hide
        </button>
      ) : (
        <button
          type="button"
          onClick={show}
          disabled={loading}
          data-testid="ssn-reveal-btn"
          className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-white bg-bronze hover:bg-bronze/90 disabled:opacity-50 px-2 py-1 rounded-full transition-colors"
          title="Reveals full SSN (audited, logged, and auto-hides in 30s)"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Eye className="h-3 w-3" />}
          {loading ? "Revealing…" : "Reveal SSN"}
        </button>
      )}
      {error && (
        <span className="inline-flex items-center gap-1 text-[11px] text-red-700" data-testid="ssn-reveal-error">
          <AlertCircle className="h-3 w-3" /> {error}
        </span>
      )}
    </div>
  );
}
