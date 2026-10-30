import React, { useState } from "react";
import { KeyRound, Lock } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";
import PasswordInput from "@/components/PasswordInput";
import PasswordStrengthMeter from "@/components/PasswordStrengthMeter";
import { passwordScore, MIN_GOOD_SCORE } from "@/lib/passwordStrength";

const labelCls = "text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 mb-1";

export default function ChangePasswordForm({ currentLabel = "Current password", submitLabel = "Update password", onDone, testPrefix = "change-password" }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const canSave = !!current && passwordScore(next) >= MIN_GOOD_SCORE && next === confirm;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (passwordScore(next) < MIN_GOOD_SCORE) return setError("Choose a stronger password (at least “Good”).");
    if (next !== confirm) return setError("The new passwords don't match.");
    if (next === current) return setError("New password must be different from the current one.");
    setSaving(true);
    try {
      const { data } = await api.post("/auth/change-password", { current_password: current, new_password: next });
      toast.success("Password updated.");
      setCurrent(""); setNext(""); setConfirm("");
      if (onDone) await onDone(data.user);
    } catch (err) {
      setError(formatApiError(err.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" data-testid={`${testPrefix}-form`}>
      {error && (
        <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm" data-testid={`${testPrefix}-error`}>{error}</div>
      )}
      <div>
        <label className={labelCls}><KeyRound className="h-3 w-3" /> {currentLabel}</label>
        <PasswordInput value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password"
          required data-testid={`${testPrefix}-current`} />
      </div>
      <div>
        <label className={labelCls}><Lock className="h-3 w-3" /> New password (min 8 characters)</label>
        <PasswordInput value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password"
          required data-testid={`${testPrefix}-new`} />
        <PasswordStrengthMeter password={next} testId={`${testPrefix}-strength`} />
      </div>
      <div>
        <label className={labelCls}><Lock className="h-3 w-3" /> Confirm new password</label>
        <PasswordInput value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password"
          required data-testid={`${testPrefix}-confirm`} />
        {confirm && confirm !== next && (
          <p className="text-xs text-red-700 mt-1" data-testid={`${testPrefix}-mismatch`}>Passwords don't match</p>
        )}
      </div>
      <button type="submit" disabled={saving || !canSave} className="btn-primary px-5 py-2.5 inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        data-testid={`${testPrefix}-submit-btn`}>
        <KeyRound className="h-4 w-4" />
        {saving ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}
