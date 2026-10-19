import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { CheckCircle2, AlertCircle, Mail } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Confirmation landing for the email-change verification link.
 * Reads ?token= from the URL, looks up what the pending new email is,
 * then calls POST /auth/confirm-email-change on user click.
 *
 * The confirm step is a POST (not GET) so the link cannot be fired by
 * email prefetchers / anti-virus crawlers that silently probe every URL.
 */
export default function ConfirmEmailChange() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const navigate = useNavigate();
  const { branding } = useAuth();
  const [loading, setLoading] = useState(true);
  const [newEmail, setNewEmail] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) {
      setError("Missing confirmation token.");
      setLoading(false);
      return;
    }
    api
      .get(`/auth/email-change-info?token=${encodeURIComponent(token)}`)
      .then((r) => {
        setNewEmail(r.data.new_email || "");
      })
      .catch((e) => setError(formatApiError(e.response?.data?.detail) || "Could not verify this link."))
      .finally(() => setLoading(false));
  }, [token]);

  const confirm = async () => {
    setSubmitting(true);
    setError("");
    try {
      await api.post("/auth/confirm-email-change", { token });
      setConfirmed(true);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "Confirmation failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F8F6F0] p-6" data-testid="confirm-email-change-page">
      <div className="max-w-md w-full bg-white rounded-xl border border-[#E2E0DA] shadow-sm p-8">
        <img
          src="/irongate-logo.png"
          alt="Iron Gate Consulting"
          className="h-20 w-20 mb-4 mx-auto select-none pointer-events-none"
          style={{ objectFit: "contain" }}
          draggable={false}
        />
        <h1 className="font-serif text-2xl text-navy text-center mb-1">
          {confirmed ? "Email updated" : "Confirm your new email"}
        </h1>
        <p className="text-sm text-[#64748B] text-center mb-6">
          {branding?.business_name || "Iron Gate Consulting"}
        </p>

        {loading && <p className="text-center text-[#64748B]">Verifying link…</p>}

        {!loading && error && !confirmed && (
          <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="confirm-email-error">
            <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">{error}</p>
              <p className="mt-2 text-xs">
                If your link expired, sign in and request another email change from Account settings, or use{" "}
                <Link to="/forgot-email" className="underline">Can't access my email</Link>.
              </p>
            </div>
          </div>
        )}

        {!loading && !error && !confirmed && (
          <>
            <div className="rounded-md bg-sand/40 border border-[#E2E0DA] p-4 mb-5 flex items-start gap-2">
              <Mail className="h-4 w-4 mt-0.5 text-bronze shrink-0" />
              <div className="text-sm">
                <p className="text-[#64748B]">You're about to set your new login email to:</p>
                <p className="font-semibold text-navy break-all" data-testid="confirm-new-email">{newEmail}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={confirm}
              disabled={submitting}
              className="btn-primary w-full"
              data-testid="confirm-email-btn">
              {submitting ? "Confirming…" : "Confirm change"}
            </button>
            <p className="text-xs text-[#94A3B8] mt-4 text-center">
              If you didn't request this, close this tab — nothing will change.
            </p>
          </>
        )}

        {confirmed && (
          <div className="text-center space-y-4" data-testid="confirm-email-success">
            <div className="flex justify-center">
              <CheckCircle2 className="h-12 w-12 text-emerald-600" />
            </div>
            <p className="text-sm text-[#64748B]">
              Your login email is now <b className="text-navy break-all">{newEmail}</b>. Please sign in with your new email.
            </p>
            <button
              type="button"
              onClick={() => navigate("/login", { replace: true })}
              className="btn-primary w-full"
              data-testid="confirm-email-to-login-btn">
              Go to sign in
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
