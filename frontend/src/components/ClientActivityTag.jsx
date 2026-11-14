/**
 * ClientActivityTag
 * Shows "Online now" (green), "Last seen {date ET}" or "Never logged in"
 * based on client_online_now, client_last_active_at, and client_last_login_at.
 * Admin / Claude only — never rendered on any client-facing page.
 */
export default function ClientActivityTag({ c, compact = false }) {
  const ET = "America/New_York";

  const fmtET = (iso) => {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("en-US", {
        timeZone: ET,
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
    } catch {
      return iso;
    }
  };

  if (c?.client_online_now) {
    return (
      <span
        className="inline-flex items-center gap-1.5 text-sm font-semibold text-emerald-700"
        data-testid="client-online-now-tag"
      >
        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        Online now
      </span>
    );
  }

  const lastSeen = c?.client_last_active_at || c?.client_last_login_at;
  if (lastSeen) {
    return (
      <span
        className="text-sm text-[#64748B]"
        data-testid="client-last-seen-tag"
        title={lastSeen}
      >
        {compact ? "Last seen " : "Last seen: "}
        <span className="text-navy font-medium">{fmtET(lastSeen)}</span>
        <span className="ml-1 text-xs text-[#94A3B8]">ET</span>
      </span>
    );
  }

  return (
    <span className="text-sm text-[#94A3B8] italic" data-testid="client-never-logged-in-tag">
      Never logged in
    </span>
  );
}
