import React, { useEffect, useState } from "react";
import { KeyRound, MessageCircle, Mail } from "lucide-react";
import api, { formatApiError } from "@/lib/api";

const KIND_LABEL = {
  temp_password_set: "Temporary password set",
  client_changed: "Client changed password",
  forgot_reset: "Reset via Forgot Password",
};

function AlertBadge({ alert }) {
  const a = alert || {};
  if (a.channel === "pending") return <span className="text-[#94A3B8]">sending…</span>;
  if (a.channel === "text") return <span className="inline-flex items-center gap-1 text-emerald-700"><MessageCircle className="h-3 w-3" /> Text sent</span>;
  if (a.channel === "whatsapp") return <span className="inline-flex items-center gap-1 text-emerald-700"><MessageCircle className="h-3 w-3" /> WhatsApp {a.status}</span>;
  if (a.channel === "email") {
    return (
      <span className={`inline-flex items-center gap-1 ${a.status === "sent" ? "text-emerald-700" : "text-red-700"}`}>
        <Mail className="h-3 w-3" /> Email {a.status}{a.whatsapp_attempted ? " (text failed)" : ""}
      </span>
    );
  }
  return <span className="text-red-700">not sent</span>;
}

export default function PasswordHistory({ caseId, refreshKey }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    api.get(`/admin/trust-cases/${caseId}/password-history`)
      .then(({ data }) => alive && setRows(data.rows || []))
      .catch((e) => alive && (setError(formatApiError(e.response?.data?.detail)), setRows([])));
    return () => { alive = false; };
  }, [caseId, refreshKey]);

  return (
    <div className="mt-3 max-w-2xl bg-white border border-[#E2E0DA] rounded-md overflow-hidden" data-testid="admin-password-history">
      <p className="px-3 py-2 text-xs uppercase tracking-wide text-[#64748B] font-semibold flex items-center gap-1 bg-sand-200/40">
        <KeyRound className="h-3 w-3" /> Password reset history
      </p>
      {rows === null ? (
        <p className="px-3 py-2 text-sm text-[#94A3B8]">Loading…</p>
      ) : error ? (
        <p className="px-3 py-2 text-sm text-red-700">{error}</p>
      ) : rows.length === 0 ? (
        <p className="px-3 py-2 text-sm text-[#94A3B8]" data-testid="admin-password-history-empty">No password changes recorded yet.</p>
      ) : (
        <table className="w-full text-xs">
          <tbody>
            {rows.map((r, i) => (
              <tr key={i} className="border-t border-[#F1EFEA]" data-testid={`admin-password-history-row-${i}`}>
                <td className="px-3 py-1.5 font-medium text-navy">{KIND_LABEL[r.kind] || r.kind}</td>
                <td className="px-3 py-1.5 text-[#64748B]">{r.created_at ? new Date(r.created_at).toLocaleString() : "—"}</td>
                <td className="px-3 py-1.5 text-[#64748B] truncate max-w-[180px]" title={r.actor_email}>by {r.actor_email}</td>
                <td className="px-3 py-1.5"><AlertBadge alert={r.alert} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
