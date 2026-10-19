import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ShieldAlert, Mail, Lock } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

/**
 * Public identity-verification form for clients who've lost access to the
 * email on file. We require 4-of-4: legal name, DOB, last-4 SSN, ZIP.
 * On success the server emails a 24h verification link to the new address.
 * On any mismatch the server locks the submitter's IP for 24h and alerts Wes.
 *
 * We never tell the user whether a specific field was wrong (constant-reply
 * UX) so the form can't be used to probe which SSN last-4 belongs to a name.
 */
export default function ForgotEmail() {
  const { branding } = useAuth();
  const [form, setForm] = useState({
    full_name: "",
    date_of_birth: "",
    last4_ssn: "",
    zip: "",
    new_email: "",
  });
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!/^\d{4}$/.test(form.last4_ssn.trim())) {
      setError("Please enter the last 4 digits of your SSN (numbers only).");
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/forgot-email", {
        full_name: form.full_name.trim(),
        date_of_birth: form.date_of_birth.trim(),
        last4_ssn: form.last4_ssn.trim(),
        zip: form.zip.trim(),
        new_email: form.new_email.trim().toLowerCase(),
      });
      setDone(true);
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || "We could not verify your identity.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#F8F6F0] p-6" data-testid="forgot-email-page">
      <div className="max-w-md w-full bg-white rounded-xl border border-[#E2E0DA] shadow-sm p-8">
        <img
          src="/irongate-logo.png"
          alt="Iron Gate Consulting"
          className="h-20 w-20 mb-4 mx-auto select-none pointer-events-none"
          style={{ objectFit: "contain" }}
          draggable={false}
        />
        <h1 className="font-serif text-2xl text-navy text-center mb-1">
          Can't access your email?
        </h1>
        <p className="text-sm text-[#64748B] text-center mb-6">
          Verify your identity to switch the login email on your {branding?.business_name || "Iron Gate Consulting"} account.
        </p>

        {done ? (
          <div className="text-center space-y-4" data-testid="forgot-email-done">
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-4 text-left">
              <p className="text-sm text-emerald-900">
                If the information matched what we have on file, we've sent a confirmation link to <b className="break-all">{form.new_email}</b>. Click it within 24 hours to finish updating your login email.
              </p>
            </div>
            <Link to="/login" className="btn-primary w-full inline-block" data-testid="forgot-email-back-to-login">
              Back to sign in
            </Link>
          </div>
        ) : (
          <form onSubmit={submit} className="space-y-4" data-testid="forgot-email-form">
            {error && (
              <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="forgot-email-error">
                <ShieldAlert className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="rounded-md bg-amber-50 border border-amber-200 p-3 flex items-start gap-2">
              <Lock className="h-4 w-4 mt-0.5 text-amber-700 shrink-0" />
              <p className="text-xs text-amber-900">
                All four fields must match what's on file exactly. Three failed attempts from the same device lock recovery for 24 hours.
              </p>
            </div>

            <div>
              <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Full legal name</Label>
              <Input
                type="text" required autoComplete="name"
                value={form.full_name} onChange={set("full_name")}
                placeholder="As it appears on your trust"
                className="mt-1" data-testid="forgot-email-name" />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Date of birth</Label>
              <Input
                type="date" required
                value={form.date_of_birth} onChange={set("date_of_birth")}
                className="mt-1" data-testid="forgot-email-dob" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Last 4 of SSN</Label>
                <Input
                  type="text" required inputMode="numeric" maxLength={4} pattern="\d{4}"
                  value={form.last4_ssn}
                  onChange={(e) => setForm({ ...form, last4_ssn: e.target.value.replace(/\D/g, "").slice(0, 4) })}
                  placeholder="1234"
                  className="mt-1 tracking-widest" data-testid="forgot-email-last4" />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">ZIP on file</Label>
                <Input
                  type="text" required inputMode="numeric" maxLength={10}
                  value={form.zip} onChange={set("zip")}
                  placeholder="90210"
                  className="mt-1" data-testid="forgot-email-zip" />
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">New login email</Label>
              <Input
                type="email" required autoComplete="email"
                value={form.new_email} onChange={set("new_email")}
                placeholder="new.email@example.com"
                className="mt-1" data-testid="forgot-email-new" />
              <p className="text-xs text-[#94A3B8] mt-1 flex items-center gap-1">
                <Mail className="h-3 w-3" /> We'll send a confirmation link here.
              </p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full"
              data-testid="forgot-email-submit-btn">
              {loading ? "Verifying…" : "Verify identity & request change"}
            </button>

            <p className="text-sm text-center text-[#64748B]">
              Remembered your email?{" "}
              <Link to="/login" className="text-navy font-medium hover:text-bronze" data-testid="forgot-email-login-link">
                Back to sign in
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
