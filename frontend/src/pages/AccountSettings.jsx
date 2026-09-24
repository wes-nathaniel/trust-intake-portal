import React, { useState } from "react";
import Layout from "@/components/Layout";
import { UserCog, Mail, User as UserIcon, KeyRound, Save } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PasswordInput from "@/components/PasswordInput";

/**
 * Self-service account settings — change email + display name.
 * Requires current password to prevent a hijacked session from renaming
 * the account. Password changes happen via the existing reset-password flow.
 */
export default function AccountSettings() {
  const { user, refreshUser } = useAuth();
  const [email, setEmail] = useState(user?.email || "");
  const [name, setName] = useState(user?.name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!currentPassword) {
      toast.error("Enter your current password to confirm the change.");
      return;
    }
    setSaving(true);
    try {
      const { data } = await api.patch("/auth/me", {
        email: email.trim() || undefined,
        name: name.trim() || undefined,
        current_password: currentPassword,
      });
      if (data.changed) {
        toast.success("Account updated. If you changed your email, sign in with the new email next time.");
      } else {
        toast("Nothing changed.", { icon: "ℹ️" });
      }
      setCurrentPassword("");
      if (refreshUser) await refreshUser();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setSaving(false); }
  };

  const emailChanged = email.trim().toLowerCase() !== (user?.email || "").toLowerCase();

  return (
    <Layout>
      <div className="max-w-2xl">
        <h1 className="font-serif text-3xl text-navy mb-1 flex items-center gap-2">
          <UserCog className="h-7 w-7 text-bronze" /> Account settings
        </h1>
        <p className="text-[#64748B] mb-6">
          Update your login email or display name. You'll need your current password to confirm.
        </p>

        <form onSubmit={submit} className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6 space-y-5" data-testid="account-settings-form">
          <div>
            <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 mb-1">
              <Mail className="h-3 w-3" /> Login email
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
              data-testid="settings-email-input"
              required
            />
            {emailChanged && (
              <p className="text-xs text-amber-700 mt-1" data-testid="email-change-warning">
                You're changing your login email. After saving, sign in with <b>{email.trim()}</b>.
              </p>
            )}
          </div>

          <div>
            <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 mb-1">
              <UserIcon className="h-3 w-3" /> Display name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
              data-testid="settings-name-input"
            />
          </div>

          <div className="pt-3 border-t border-[#E2E0DA]">
            <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 mb-1">
              <KeyRound className="h-3 w-3" /> Current password (required to save)
            </label>
            <PasswordInput
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              data-testid="settings-current-password"
              placeholder="Enter your current password"
              required
            />
          </div>

          <button
            type="submit"
            disabled={saving}
            className="btn-primary px-5 py-2.5 inline-flex items-center gap-2 disabled:opacity-50"
            data-testid="settings-save-btn">
            <Save className="h-4 w-4" />
            {saving ? "Saving…" : "Save changes"}
          </button>
        </form>

        <p className="text-xs text-[#94A3B8] mt-4">
          Need to change your password? Use <a href="/forgot-password" className="text-bronze underline">Forgot Password</a> and we'll email you a reset link.
        </p>
      </div>
    </Layout>
  );
}
