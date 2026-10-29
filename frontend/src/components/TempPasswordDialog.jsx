import React, { useState } from "react";
import { KeyRound, Copy, Check, X } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

// Admin: generate a one-time temporary password for a client. Shown once; never emailed.
export default function TempPasswordDialog({ email, label, onClose }) {
  const [busy, setBusy] = useState(false);
  const [temp, setTemp] = useState("");
  const [copied, setCopied] = useState(false);

  const generate = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/users/temp-password", { email });
      setTemp(data.temp_password);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(temp); setCopied(true); toast.success("Copied."); }
    catch { toast.error("Copy failed — select the password and copy it manually."); }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4" data-testid="temp-password-modal"
      onClick={(e) => e.stopPropagation()}>
      <div className="bg-white rounded-xl w-full max-w-md p-6 shadow-xl relative">
        <button type="button" onClick={onClose} className="absolute right-3 top-3 p-1 text-[#64748B] hover:text-navy"
          data-testid="temp-password-close-btn" aria-label="Close"><X className="h-4 w-4" /></button>
        <h2 className="font-serif text-2xl text-navy flex items-center gap-2 mb-2">
          <KeyRound className="h-5 w-5 text-bronze" /> Temporary password
        </h2>
        <p className="text-sm text-[#64748B] mb-4">
          For <b className="text-navy break-all">{label}</b>{label !== email ? <> ({email})</> : null}
        </p>
        {!temp ? (
          <>
            <p className="text-sm text-navy mb-5">
              This replaces the client's current password immediately. They'll be required to choose a new one the
              next time they sign in. <b>No email is sent</b> — share it with them directly.
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-[#64748B] hover:text-navy"
                data-testid="temp-password-cancel-btn">Cancel</button>
              <button type="button" onClick={generate} disabled={busy} className="btn-primary px-4 py-2 text-sm disabled:opacity-50"
                data-testid="temp-password-generate-btn">{busy ? "Generating…" : "Generate temporary password"}</button>
            </div>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2 rounded-md border border-bronze/40 bg-[#FBF8F2] px-3 py-3 mb-3">
              <code className="flex-1 text-lg font-mono tracking-wider text-navy select-all break-all" data-testid="temp-password-value">{temp}</code>
              <button type="button" onClick={copy} className="p-2 rounded hover:bg-bronze/10 text-bronze"
                data-testid="temp-password-copy-btn" title="Copy">{copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}</button>
            </div>
            <p className="text-xs text-amber-700 mb-5" data-testid="temp-password-warning">
              This password is shown only once. Copy it now — it can't be viewed again (you can always generate a new one).
            </p>
            <div className="flex justify-end">
              <button type="button" onClick={onClose} className="btn-primary px-4 py-2 text-sm" data-testid="temp-password-done-btn">Done</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
