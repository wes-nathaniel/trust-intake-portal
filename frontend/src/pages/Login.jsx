import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, Shield } from "lucide-react";
import PasswordInput from "@/components/PasswordInput";

export default function Login() {
  const { login, branding } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await login(form.email, form.password);
    setLoading(false);
    if (res.ok) {
      const from = location.state?.from?.pathname;
      // route by role from the returned user (axios returned body used by context)
      const target = from || "/";
      navigate(target, { replace: true });
    } else {
      setError(res.error);
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
          <h1 className="font-serif text-5xl leading-tight mb-4">Your legacy,<br/>in capable hands.</h1>
          <p className="text-sand/90 max-w-md text-lg">A secure, guided intake experience for your trust & estate planning.</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-8 relative overflow-hidden">
        {/* Watermark crest — sits behind the sign-in copy, slightly faded, breathing on the page */}
        <img
          src="/irongate-logo.png"
          alt=""
          aria-hidden="true"
          className="pointer-events-none select-none absolute z-0"
          style={{
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            width: "min(560px, 90%)",
            opacity: 0.06,
            filter: "drop-shadow(0 20px 40px rgba(20,30,50,0.12))",
          }}
          draggable={false}
        />
        <form onSubmit={submit} className="w-full max-w-md space-y-6 relative z-10" data-testid="login-form">
          <div className="flex items-center gap-2 text-bronze">
            <Shield className="h-5 w-5" />
            <span className="text-xs uppercase tracking-[0.2em]">Secure Sign In</span>
          </div>
          <div>
            <img
              src="/irongate-logo.png"
              alt="Iron Gate Consulting"
              data-testid="login-logo"
              className="h-36 w-36 sm:h-40 sm:w-40 mt-2 mb-4 select-none pointer-events-none"
              style={{ objectFit: "contain", filter: "drop-shadow(0 12px 24px rgba(20,30,50,0.18))" }}
              draggable={false}
            />
            <h2 className="font-serif text-4xl text-navy mb-1">IGC Trust Portal</h2>
            <p className="text-[#64748B]">Sign in to your {branding.business_name} account.</p>
          </div>
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="login-error">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="email" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Email</Label>
              <Input id="email" type="email" autoComplete="email" required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="mt-1 bg-white" data-testid="login-email-input" />
            </div>
            <div>
              <Label htmlFor="password" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Password</Label>
              <PasswordInput id="password" autoComplete="current-password" required
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="mt-1 bg-white" data-testid="login-password-input" />
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full" data-testid="login-submit-btn">
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <p className="text-sm text-center">
            <Link to="/forgot-password" className="text-navy font-medium hover:text-bronze" data-testid="login-forgot-password-link">
              Forgot your password?
            </Link>
            <span className="mx-2 text-[#CBD5E1]">·</span>
            <Link to="/forgot-email" className="text-navy font-medium hover:text-bronze" data-testid="login-forgot-email-link">
              Can't access your email?
            </Link>
          </p>
          <p className="text-sm text-center text-[#64748B]">
            New here?{" "}
            <Link to="/register" className="text-navy font-medium hover:text-bronze" data-testid="login-register-link">Create an account</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
