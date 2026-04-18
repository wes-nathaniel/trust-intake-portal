import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

export default function BrandingPage() {
  const { branding, loadBranding } = useAuth();
  const [form, setForm] = useState(branding);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setForm(branding); }, [branding]);

  const set = (k, v) => setForm({ ...form, [k]: v });

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/branding", form);
      toast.success("Branding updated");
      await loadBranding();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  return (
    <Layout>
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Customization</p>
        <h1 className="font-serif text-4xl text-navy">Branding</h1>
        <p className="text-[#64748B] mt-2">Make this portal look like your firm. Changes apply to all clients.</p>
      </div>

      <div className="bg-white border border-[#E2E0DA] rounded-xl p-8 max-w-2xl space-y-5" data-testid="branding-form">
        <div>
          <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Business name</Label>
          <Input value={form.business_name || ""} onChange={(e) => set("business_name", e.target.value)}
            className="mt-1 bg-white" data-testid="branding-name-input" />
        </div>
        <div>
          <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Logo URL</Label>
          <Input value={form.logo_url || ""} onChange={(e) => set("logo_url", e.target.value)}
            placeholder="https://example.com/logo.png"
            className="mt-1 bg-white" data-testid="branding-logo-input" />
        </div>
        <div>
          <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Header image URL</Label>
          <Input value={form.header_image_url || ""} onChange={(e) => set("header_image_url", e.target.value)}
            className="mt-1 bg-white" data-testid="branding-header-input" />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Primary color</Label>
            <Input type="color" value={form.primary_color || "#1C252E"} onChange={(e) => set("primary_color", e.target.value)}
              className="mt-1 bg-white h-11" data-testid="branding-primary-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Accent color</Label>
            <Input type="color" value={form.accent_color || "#C5A880"} onChange={(e) => set("accent_color", e.target.value)}
              className="mt-1 bg-white h-11" data-testid="branding-accent-input" />
          </div>
        </div>
        <button onClick={save} disabled={saving} className="btn-primary" data-testid="branding-save-btn">
          {saving ? "Saving…" : "Save Branding"}
        </button>
      </div>
    </Layout>
  );
}
