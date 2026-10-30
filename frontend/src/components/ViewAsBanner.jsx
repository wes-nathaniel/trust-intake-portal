import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye, LogOut } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

// Shown on every protected page while an admin is in read-only "View as Client" mode.
export default function ViewAsBanner() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  if (!user?.view_as_admin) return null;

  const exit = async () => {
    setBusy(true);
    try { await api.post("/auth/view-as/exit"); } catch { /* cookie may already be gone */ }
    await refresh();
    const caseId = user.view_as_case_id;
    navigate(caseId ? `/admin/cases/${caseId}` : "/admin", { replace: true });
  };

  return (
    <div className="sticky top-0 z-[60] bg-amber-400 text-navy px-4 py-2 flex flex-wrap items-center justify-between gap-2 shadow" data-testid="view-as-banner">
      <p className="text-sm font-semibold flex items-center gap-2">
        <Eye className="h-4 w-4" />
        Viewing as <span data-testid="view-as-client-name">{user.name || user.email}</span> — read-only. Clients can't see this.
      </p>
      <button type="button" onClick={exit} disabled={busy}
        className="inline-flex items-center gap-1.5 bg-navy text-white text-sm px-3 py-1.5 rounded-md hover:bg-navy/90 disabled:opacity-60"
        data-testid="view-as-exit-btn">
        <LogOut className="h-4 w-4" /> {busy ? "Exiting…" : "Exit / Return to Admin"}
      </button>
    </div>
  );
}

export async function startViewAsClient(caseId, refresh, navigate, onError) {
  try {
    await api.post(`/admin/trust-cases/${caseId}/view-as-client`);
    await refresh();
    navigate("/portal");
  } catch (e) {
    onError?.(e);
  }
}
