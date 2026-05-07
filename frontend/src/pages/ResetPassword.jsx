import React, { useState, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Shield, AlertCircle, ArrowLeft, CheckCircle2 } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function ResetPassword() {
  const { branding } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") || "";

  const [pw, setPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  const issues = useMemo(() => {
    const list = [];
    if (pw.length > 0 && pw.length < 8) list.push("At least 8 characters");
    if (pw && !/[A-Za-z]/.test(pw)) list.push("Must contain a letter");
    if (pw && !/[0-9]/.test(pw)) list.push("Must contain a number");
    if (pw && confirm && pw !== confirm) list.push("Passwords don't match");
    return list;
  }, [pw, confirm]);

  const canSubmit = !!token && pw.length >= 8 && /[A-Za-z]/.test(pw) && /[0-9]/.test(pw) && pw === confirm && !loading;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!canSubmit) return;
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password: pw });
      setDone(true);
      toast.success("Password reset. Please sign in with your new password.");
      setTimeout(() => navigate("/login", { replace: true }), 2000);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail) || "Could not reset password. The link may have expired.");
    } finally {
      setLoading(false);
    }
  };

  // Missing or empty token
  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center p-8 bg-sand">
        <div className="w-full max-w-md bg-white rounded-xl border border-[#E2E0DA] p-8 text-center" data-testid="reset-password-no-token">
          <AlertCircle className="h-10 w-10 text-red-700 mx-auto mb-3" />
          <h2 className="font-serif text-2xl text-navy mb-2">Invalid reset link</h2>
          <p className="text-sm text-[#64748B] mb-6">
            This password-reset link is missing or malformed. Please request a new one.
          </p>
          <Link to="/forgot-password" className="btn-primary w-full inline-flex items-center justify-center" data-testid="reset-no-token-request-new-btn">
            Request a new reset link
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div
        className="hidden md:block bg-cover bg-center relative"
        style={{ backgroundImage: `url(${branding.header_image_url || "https://images.unsplash.com/photo-1598139384902-5a8217874645?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"})` }}
      >
        <div className="absolute inset-0 bg-navy/60" />
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <h1 className="font-serif text-5xl leading-tight mb-4">Set a new<br/>password.</h1>
          <p className="text-sand/90 max-w-md text-lg">Choose something memorable but hard to guess.</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-md space-y-6" data-testid="reset-password-page">
          <div className="flex items-center gap-2 text-bronze">
            <Shield className="h-5 w-5" />
            <span className="text-xs uppercase tracking-[0.2em]">Account recovery</span>
          </div>

          {done ? (
            <div className="space-y-4" data-testid="reset-password-success">
              <div className="flex items-start gap-3 p-4 rounded-md bg-green-50 border border-green-200">
                <CheckCircle2 className="h-5 w-5 text-green-700 mt-0.5 shrink-0" />
                <div className="text-sm text-green-900">
                  <p className="font-semibold mb-1">Password updated</p>
                  <p>Redirecting you to sign in…</p>
                </div>
              </div>
              <Link to="/login" className="btn-primary w-full inline-flex items-center justify-center" data-testid="reset-success-go-to-login-btn">
                Go to sign in
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-6" data-testid="reset-password-form">
              <div>
                <h2 className="font-serif text-4xl text-navy mb-1">Set new password</h2>
                <p className="text-[#64748B]">Enter a new password for your {branding.business_name} account.</p>
              </div>

              {error && (
                <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="reset-password-error">
                  <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <Label htmlFor="pw" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">New password</Label>
                  <Input
                    id="pw"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={pw}
                    onChange={(e) => setPw(e.target.value)}
                    className="mt-1 bg-white"
                    data-testid="reset-password-input"
                  />
                </div>
                <div>
                  <Label htmlFor="confirm" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Confirm new password</Label>
                  <Input
                    id="confirm"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={8}
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="mt-1 bg-white"
                    data-testid="reset-password-confirm-input"
                  />
                </div>

                {issues.length > 0 && (
                  <ul className="text-xs text-[#64748B] list-disc list-inside space-y-0.5" data-testid="reset-password-issues">
                    {issues.map((i) => <li key={i}>{i}</li>)}
                  </ul>
                )}
                {pw.length === 0 && (
                  <p className="text-xs text-[#64748B]">Use at least 8 characters with a letter and a number.</p>
                )}
              </div>

              <button
                type="submit"
                disabled={!canSubmit}
                className="btn-primary w-full"
                data-testid="reset-password-submit-btn">
                {loading ? "Updating…" : "Update password"}
              </button>

              <p className="text-sm text-center text-[#64748B]">
                <Link to="/login" className="inline-flex items-center gap-1 text-navy font-medium hover:text-bronze" data-testid="reset-back-to-login-link">
                  <ArrowLeft className="h-4 w-4" /> Back to sign in
                </Link>
              </p>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
