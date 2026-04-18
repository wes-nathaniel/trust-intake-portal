import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertCircle, UserPlus } from "lucide-react";

export default function Register() {
  const { register, branding } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    const res = await register(form.name, form.email, form.password);
    setLoading(false);
    if (res.ok) navigate("/portal", { replace: true });
    else setError(res.error);
  };

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div
        className="hidden md:block bg-cover bg-center relative"
        style={{ backgroundImage: `url(${branding.header_image_url || "https://images.unsplash.com/photo-1579455843501-99d7f76f6498?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200"})` }}
      >
        <div className="absolute inset-0 bg-navy/60" />
        <div className="absolute inset-0 flex flex-col justify-end p-12 text-white">
          <h1 className="font-serif text-5xl leading-tight mb-4">Begin your<br/>legacy plan.</h1>
          <p className="text-sand/90 max-w-md text-lg">Start a secure trust intake in minutes. We'll guide you through every step.</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-md space-y-6" data-testid="register-form">
          <div className="flex items-center gap-2 text-bronze">
            <UserPlus className="h-5 w-5" />
            <span className="text-xs uppercase tracking-[0.2em]">Create Your Account</span>
          </div>
          <div>
            <h2 className="font-serif text-4xl text-navy mb-1">Get started</h2>
            <p className="text-[#64748B]">Join {branding.business_name} to begin your trust intake.</p>
          </div>
          {error && (
            <div className="flex items-start gap-2 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid="register-error">
              <AlertCircle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
          <div className="space-y-4">
            <div>
              <Label htmlFor="name" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Full name</Label>
              <Input id="name" required value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="mt-1 bg-white" data-testid="register-name-input" />
            </div>
            <div>
              <Label htmlFor="email" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Email</Label>
              <Input id="email" type="email" required value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="mt-1 bg-white" data-testid="register-email-input" />
            </div>
            <div>
              <Label htmlFor="password" className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Password</Label>
              <Input id="password" type="password" required minLength={6} value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
                className="mt-1 bg-white" data-testid="register-password-input" />
              <p className="text-xs text-[#64748B] mt-1">Minimum 6 characters</p>
            </div>
          </div>
          <button type="submit" disabled={loading} className="btn-primary w-full" data-testid="register-submit-btn">
            {loading ? "Creating…" : "Create account"}
          </button>
          <p className="text-sm text-center text-[#64748B]">
            Already have an account?{" "}
            <Link to="/login" className="text-navy font-medium hover:text-bronze" data-testid="register-login-link">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
