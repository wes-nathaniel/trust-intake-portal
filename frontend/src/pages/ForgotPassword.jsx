import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Shield, Mail, ArrowLeft, CheckCircle2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";

export default function ForgotPassword() {
  const { branding } = useAuth();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: email.trim().toLowerCase() });
      setSubmitted(true);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div
        className="hidden md:block bg-cover bg-center relative"
        style={{ backgroundImage: `url(${branding.header_image_url || "https://images.unsplash.com/photo-1598139384902-5a8217874645?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"})` }}
      >
        <div className="absolute inset-0 bg-navy/60" />
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <h1 className="font-serif text-5xl leading-tight mb-4">Reset your<br/>password.</h1>
          <p className="text-sand/90 max-w-md text-lg">We'll email you a secure link to set a new password.</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-md space-y-6" data-testid="forgot-password-page">
          <div className="flex items-center gap-2 text-bronze">
            <Shield className="h-5 w-5" />
            <span className="text-xs uppercase tracking-[0.2em]">Account recovery</span>
          </div>

          {!submitted ? (
            <form onSubmit={submit} className="space-y-6" data-testid="forgot-password-form">
              <div>
                <h2 className="font-serif text-4xl text-navy mb-1">Forgot your password?</h2>
                <p className="text-[#64748B]">
                  Enter the email associated with your {branding.business_name} account and we'll send you a reset link.
                </p>
              </div>

              {error && (
                <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="forgot-password-error">
                  {error}
                </div>
              )}

              <div>
                <Label htmlFor="email" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Email</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 bg-white"
                  data-testid="forgot-password-email-input"
                />
              </div>

              <button
                type="submit"
                disabled={loading || !email.trim()}
                className="btn-primary w-full"
                data-testid="forgot-password-submit-btn">
                {loading ? "Sending…" : "Send reset link"}
              </button>

              <p className="text-sm text-center text-[#64748B]">
                <Link to="/login" className="inline-flex items-center gap-1 text-navy font-medium hover:text-bronze" data-testid="forgot-back-to-login-link">
                  <ArrowLeft className="h-4 w-4" /> Back to sign in
                </Link>
              </p>
            </form>
          ) : (
            <div className="space-y-6" data-testid="forgot-password-success">
              <div className="flex items-start gap-3 p-4 rounded-md bg-green-50 border border-green-200">
                <CheckCircle2 className="h-5 w-5 text-green-700 mt-0.5 shrink-0" />
                <div className="text-sm text-green-900">
                  <p className="font-semibold mb-1">Check your inbox</p>
                  <p>
                    If an account exists for <b>{email}</b>, we've sent a password-reset link.
                    The link is valid for one hour.
                  </p>
                </div>
              </div>

              <div className="text-sm text-[#64748B] space-y-2">
                <p className="flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  Don't see it? Check your spam folder.
                </p>
                <p>
                  Still having trouble?{" "}
                  <button
                    type="button"
                    onClick={() => { setSubmitted(false); setEmail(""); }}
                    className="text-navy font-medium hover:text-bronze underline"
                    data-testid="forgot-try-again-btn">
                    Try a different email
                  </button>
                </p>
              </div>

              <Link to="/login" className="btn-secondary w-full inline-flex items-center justify-center gap-1" data-testid="forgot-success-back-to-login-btn">
                <ArrowLeft className="h-4 w-4" /> Back to sign in
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
