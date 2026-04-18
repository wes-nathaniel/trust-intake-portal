import React, { useEffect, useState, useRef } from "react";
import api, { formatApiError } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, MessageCircle } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function MessageThread({ caseId, section = null, title = "Messages" }) {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const listRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/messages`);
      const filtered = section ? data.filter((m) => m.section === section) : data;
      setMessages(filtered);
      setTimeout(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight }), 100);
    } catch {}
  };

  useEffect(() => {
    if (caseId) load();
    // eslint-disable-next-line
  }, [caseId, section]);

  const send = async () => {
    if (!body.trim()) return;
    setLoading(true);
    try {
      await api.post(`/trust-cases/${caseId}/messages`, { body, section });
      setBody("");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl overflow-hidden flex flex-col" data-testid={`message-thread-${section || "main"}`}>
      <div className="px-5 py-3 border-b border-[#E2E0DA] bg-sand-200/40 flex items-center gap-2">
        <MessageCircle className="h-4 w-4 text-bronze" />
        <h4 className="font-serif text-lg text-navy">{title}</h4>
      </div>
      <div ref={listRef} className="flex-1 overflow-y-auto p-4 space-y-3 max-h-80" data-testid="message-list">
        {messages.length === 0 && <p className="text-sm text-[#64748B] text-center py-8">No messages yet. Send one below.</p>}
        {messages.map((m) => {
          const mine = m.sender_id === user?.id;
          return (
            <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
              <div className={`max-w-[80%] rounded-lg p-3 text-sm ${mine ? "bg-navy text-white" : "bg-sand-200 text-navy"}`}>
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[11px] uppercase tracking-wide font-semibold ${mine ? "text-bronze" : "text-bronze"}`}>
                    {m.sender_role === "admin" ? "Trust Team" : m.sender_name || "Client"}
                  </span>
                  <span className={`text-[10px] ${mine ? "text-white/60" : "text-[#64748B]"}`}>
                    {new Date(m.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="whitespace-pre-wrap">{m.body}</p>
              </div>
            </div>
          );
        })}
      </div>
      <div className="border-t border-[#E2E0DA] p-3 flex gap-2">
        <Textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="Type a message…"
          rows={2} className="bg-white resize-none" data-testid="message-input" />
        <Button onClick={send} disabled={loading || !body.trim()} className="btn-accent shrink-0 self-end" data-testid="message-send-btn">
          <Send className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
