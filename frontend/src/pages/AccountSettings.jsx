import React, { useState, useEffect } from "react";
import Layout from "@/components/Layout";
import { UserCog, Mail, User as UserIcon, KeyRound, Save, MailCheck } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import PasswordInput from "@/components/PasswordInput";
import ChangePasswordForm from "@/components/ChangePasswordForm";

/**
 * Self-service account settings.
 *   - Display-name change is instant via PATCH /auth/me (requires current password).
 *   - Email change is DUAL-CONFIRM: POST /auth/request-email-change sends a 24h
 *     verification link to the new address. The old address and admin are notified.
 *     The actual switch happens only when the user clicks the link.
 * This prevents a hijacked session from silently moving the account out of reach.
 */
export default function AccountSettings() {
  const { user, refreshUser } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [currentPassword, setCurrentPassword] = useState("");
  const [savingName, setSavingName] = useState(false);

  const [newEmail, setNewEmail] = useState("");
  const [emailPassword, setEmailPassword] = useState("");
  const [requestingEmail, setRequestingEmail] = useState(false);
  const [emailRequested, setEmailRequested] = useState(false);

  useEffect(() => {
    if (window.location.hash === "#password") {
      setTimeout(() => document.getElementById("password")?.scrollIntoView({ behavior: "smooth" }), 100);
    }
  }, []);

  const saveName = async (e) => {
    e.preventDefault();
    if (!currentPassword) {
      toast.error("Enter your current password to confirm the change.");
      return;
    }
    if (!name.trim() || name.trim() === (user?.name || "")) {
      toast("Nothing to update.", { icon: "ℹ️" });
      return;
    }
    setSavingName(true);
    try {
      const { data } = await api.patch("/auth/me", {
        name: name.trim(),
        current_password: currentPassword,
      });
      if (data.changed) toast.success("Display name updated.");
      else toast("Nothing changed.", { icon: "ℹ️" });
      setCurrentPassword("");
      if (refreshUser) await refreshUser();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setSavingName(false);
    }
  };

  const requestEmailChange = async (e) => {
    e.preventDefault();
    const target = newEmail.trim().toLowerCase();
    if (!target) {
      toast.error("Enter the new email address you'd like to use.");
      return;
    }
    if (target === (user?.email || "").toLowerCase()) {
      toast.error("That is already your login email.");
      return;
    }
    if (!emailPassword) {
      toast.error("Enter your current password to confirm the change.");
      return;
    }
    setRequestingEmail(true);
    try {
      await api.post("/auth/request-email-change", {
        new_email: target,
        current_password: emailPassword,
      });
      setEmailRequested(true);
      setEmailPassword("");
      toast.success("Confirmation link sent to the new email.");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setRequestingEmail(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-2xl">
        <h1 className="font-serif text-3xl text-navy mb-1 flex items-center gap-2">
          <UserCog className="h-7 w-7 text-bronze" /> Account settings
        </h1>
        <p className="text-[#64748B] mb-6">
          Current login email: <b className="text-navy break-all">{user?.email}</b>
        </p>

        {/* ---------- Display name ---------- */}
        <form
          onSubmit={saveName}
          className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6 space-y-5 mb-6"
          data-testid="account-settings-form">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2">
            <UserIcon className="h-5 w-5 text-bronze" /> Display name
          </h2>
          <div>
            <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 block">
              Your name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
              data-testid="settings-name-input"
            />
          </div>
          <div>
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
            disabled={savingName}
            className="btn-primary px-5 py-2.5 inline-flex items-center gap-2 disabled:opacity-50"
            data-testid="settings-save-btn">
            <Save className="h-4 w-4" />
            {savingName ? "Saving…" : "Save name"}
          </button>
        </form>

        {/* ---------- Change email (dual-confirm) ---------- */}
        <form
          onSubmit={requestEmailChange}
          className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6 space-y-5"
          data-testid="change-email-form">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2">
            <Mail className="h-5 w-5 text-bronze" /> Change login email
          </h2>
          <p className="text-sm text-[#64748B]">
            We'll send a verification link to the new address. Your login email changes only after you click that link (valid 24 hours).
          </p>

          {emailRequested ? (
            <div className="rounded-md bg-emerald-50 border border-emerald-200 p-4 flex items-start gap-2" data-testid="change-email-sent">
              <MailCheck className="h-5 w-5 text-emerald-700 mt-0.5" />
              <div className="text-sm text-emerald-900">
                <p className="font-medium">Verification link sent to <b className="break-all">{newEmail.trim().toLowerCase()}</b>.</p>
                <p className="mt-1">Open that inbox and click <i>Confirm new email</i> within 24 hours. Your current email will keep working until then.</p>
                <button
                  type="button"
                  onClick={() => { setEmailRequested(false); setNewEmail(""); }}
                  className="text-emerald-900 underline text-xs mt-2"
                  data-testid="change-email-reset-btn">
                  Request a different address instead
                </button>
              </div>
            </div>
          ) : (
            <>
              <div>
                <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-1 block">
                  New login email
                </label>
                <input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  className="w-full rounded-md border border-[#E2E0DA] px-3 py-2 focus:border-bronze outline-none"
                  data-testid="change-email-new"
                  placeholder="your.new.email@example.com"
                  required
                />
              </div>
              <div>
                <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 mb-1">
                  <KeyRound className="h-3 w-3" /> Current password
                </label>
                <PasswordInput
                  value={emailPassword}
                  onChange={(e) => setEmailPassword(e.target.value)}
                  data-testid="change-email-password"
                  placeholder="Enter your current password"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={requestingEmail}
                className="btn-primary px-5 py-2.5 inline-flex items-center gap-2 disabled:opacity-50"
                data-testid="change-email-submit-btn">
                <Mail className="h-4 w-4" />
                {requestingEmail ? "Sending link…" : "Send verification link"}
              </button>
            </>
          )}
        </form>

        {/* ---------- Change password ---------- */}
        <section id="password" className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6 space-y-5 mt-6 scroll-mt-24"
          data-testid="change-password-section">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2">
            <KeyRound className="h-5 w-5 text-bronze" /> Change password
          </h2>
          <ChangePasswordForm />
          <p className="text-xs text-[#94A3B8]">
            Forgot your current password? Use{" "}
            <a href="/forgot-password" className="text-bronze underline">Forgot Password</a>
            {" "}and we'll email you a reset link.
          </p>
        </section>
      </div>
    </Layout>
  );
}
