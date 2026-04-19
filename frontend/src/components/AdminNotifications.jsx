import React, { useEffect, useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, MessageCircle } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import api from "@/lib/api";

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function AdminNotifications() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ total_unread: 0, groups: [] });
  const pollRef = useRef();

  const fetchData = async () => {
    try {
      const { data } = await api.get("/admin/notifications");
      setData(data);
    } catch { /* ignore (not admin / logged out) */ }
  };

  useEffect(() => {
    fetchData();
    pollRef.current = setInterval(fetchData, 30000);
    return () => clearInterval(pollRef.current);
  }, []);

  const openCase = (caseId) => {
    setOpen(false);
    navigate(`/admin/cases/${caseId}`);
    // Messages become read after the MessageThread on case detail loads them.
    setTimeout(fetchData, 1500);
  };

  const count = data.total_unread || 0;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className="relative rounded-md p-2 hover:bg-sand-200 transition-colors"
          aria-label="Notifications"
          data-testid="admin-notifications-btn">
          <Bell className="h-5 w-5 text-navy" />
          {count > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold flex items-center justify-center"
              data-testid="admin-notifications-badge">
              {count > 99 ? "99+" : count}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0 bg-white border-[#E2E0DA]" data-testid="admin-notifications-popover">
        <div className="px-4 py-3 border-b border-[#E2E0DA] flex items-center justify-between">
          <p className="font-serif text-lg text-navy">Notifications</p>
          <span className="text-xs text-[#64748B]">{count} unread</span>
        </div>
        <div className="max-h-96 overflow-y-auto">
          {data.groups.length === 0 ? (
            <div className="px-6 py-10 text-center text-[#64748B] text-sm" data-testid="admin-notifications-empty">
              <MessageCircle className="h-8 w-8 mx-auto mb-2 text-[#CBD5E1]" />
              You're all caught up. No unread client messages.
            </div>
          ) : (
            data.groups.map((g) => (
              <button
                key={g.case_id}
                onClick={() => openCase(g.case_id)}
                className="w-full text-left px-4 py-3 border-b border-[#E2E0DA] hover:bg-sand-200/40 transition-colors"
                data-testid={`admin-notification-group-${g.case_id}`}>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <div className="min-w-0">
                    <p className="font-medium text-navy truncate">{g.client_name}</p>
                    <p className="text-xs text-[#64748B] truncate">{g.client_email} · {g.trust_type === "joint" ? "Joint" : "Single"} · {g.status}</p>
                  </div>
                  <span className="shrink-0 text-[10px] bg-bronze text-white rounded-full px-2 py-0.5 font-semibold">
                    {g.unread_count}
                  </span>
                </div>
                <p className="text-sm text-navy/90 line-clamp-2">{g.latest_message?.body}</p>
                <p className="text-[11px] text-[#94A3B8] mt-1">{timeAgo(g.latest_message?.created_at)}</p>
              </button>
            ))
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
