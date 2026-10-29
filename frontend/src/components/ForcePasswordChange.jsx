import React from "react";
import { ShieldAlert, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import ChangePasswordForm from "@/components/ChangePasswordForm";

export default function ForcePasswordChange() {
  const { user, refresh, logout } = useAuth();
  const navigate = useNavigate();

  const signOut = async () => { await logout(); navigate("/login", { replace: true }); };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#F8F7F4]" data-testid="force-password-change-screen">
      <div className="w-full max-w-md bg-white border border-[#E2E0DA] rounded-xl p-6 sm:p-8 shadow-sm">
        <div className="flex items-center gap-2 text-bronze mb-3">
          <ShieldAlert className="h-5 w-5" />
          <span className="text-xs uppercase tracking-[0.2em] font-semibold">Action required</span>
        </div>
        <h1 className="font-serif text-3xl text-navy mb-2">Set a new password</h1>
        <p className="text-sm text-[#64748B] mb-6">
          You signed in with a temporary password. For your security, choose a new password before continuing
          {user?.email ? <> to <b className="text-navy break-all">{user.email}</b></> : null}.
        </p>
        <ChangePasswordForm currentLabel="Temporary password" submitLabel="Save & continue"
          testPrefix="force-password" onDone={refresh} />
        <button type="button" onClick={signOut}
          className="mt-6 text-sm text-[#64748B] hover:text-navy inline-flex items-center gap-1"
          data-testid="force-password-logout-btn">
          <LogOut className="h-4 w-4" /> Sign out
        </button>
      </div>
    </div>
  );
}
