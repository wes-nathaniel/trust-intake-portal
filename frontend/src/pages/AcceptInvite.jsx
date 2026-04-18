import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, ShieldCheck, Loader2 } from "lucide-react";

export default function AcceptInvite() {
  const { branding, refresh } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const token = new URLSearchParams(loc.search).get("token");
  const [info, setInfo] = useState(null); // null=loading, false=invalid, object=valid
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!token) { setInfo(false); return; }
    (async () => {
      try {
        const { data } = await api.get(`/auth/invite-info`, { params: { token } });
        setInfo(data);
      } catch (e) {
        setError(formatApiError(e.response?.data?.detail) || "Invalid invitation");
        setInfo(false);
      }
    })();
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (pw.length < 6) { setError("Password must be at least 6 characters."); return; }
    if (pw !== pw2) { setError("Passwords don't match."); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post("/auth/accept-invite", { token, password: pw });
      await refresh();
      navigate(`/intake/${data.case_id}`, { replace: true });
    } catch (e) {
      setError(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setSubmitting(false); }
  };

  if (info === null) return (
    <div className="min-h-screen flex items-center justify-center">
      <Loader2 className="h-8 w-8 animate-spin text-bronze" />
    </div>
  );

  if (info === false) return (
    <div className="min-h-screen grid place-items-center p-8">
      <div className="max-w-md w-full bg-white border border-[#E2E0DA] rounded-xl p-8 text-center" data-testid="invite-invalid">
        <AlertCircle className="h-10 w-10 text-red-500 mx-auto mb-3" />
        <h2 className="font-serif text-2xl text-navy mb-2">Invitation invalid or expired</h2>
        <p className="text-[#64748B] mb-4">{error || "Please contact the firm to receive a new invitation."}</p>
        <a href="/login" className="btn-primary inline-block" data-testid="invite-invalid-login-btn">Sign in</a>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div
        className="hidden md:block bg-cover bg-center relative"
        style={{ backgroundImage: `url(${branding.header_image_url || "https://images.unsplash.com/photo-1598139384902-5a8217874645?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"})` }}
      >
        <div className="absolute inset-0 bg-navy/60" />
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <h1 className="font-serif text-5xl leading-tight mb-4">You're invited.</h1>
          <p className="text-sand/90 max-w-md text-lg">Set your password to begin your secure trust intake.</p>
        </div>
      </div>
      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-md space-y-6" data-testid="accept-invite-form">
          <div className="flex items-center gap-2 text-bronze">
            <ShieldCheck className="h-5 w-5" />
            <span className="text-xs uppercase tracking-[0.2em]">Secure Invitation</span>
          </div>
          <div>
            <h2 className="font-serif text-4xl text-navy mb-1">Welcome, {info.name}.</h2>
            <p className="text-[#64748B]">{branding.business_name} has created a case for <b>{info.email}</b>. Set a password below to begin.</p>
          </div>
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="invite-error">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" /><span>{error}</span>
            </div>
          )}
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Choose a password</Label>
            <Input type="password" required minLength={6} value={pw} onChange={(e) => setPw(e.target.value)}
              className="mt-1 bg-white" data-testid="invite-password-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Confirm password</Label>
            <Input type="password" required minLength={6} value={pw2} onChange={(e) => setPw2(e.target.value)}
              className="mt-1 bg-white" data-testid="invite-password2-input" />
          </div>
          <button type="submit" disabled={submitting} className="btn-primary w-full" data-testid="invite-submit-btn">
            {submitting ? "Activating…" : "Activate account & begin"}
          </button>
        </form>
      </div>
    </div>
  );
}
