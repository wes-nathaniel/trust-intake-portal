import React, { useState, useEffect, useRef } from "react";
import { MessageCircle, X, Send, Loader2, AlertCircle } from "lucide-react";
import api, { formatApiError } from "@/lib/api";

/**
 * Nia — client-facing chat bubble.
 * Sits fixed bottom-right on ClientPortal / IntakeWizard / TrustPreview.
 * Persists the session_id in localStorage so refresh keeps the thread.
 */
function ensureSessionId() {
  try {
    let id = localStorage.getItem("nia_session_id");
    if (!id) {
      id = "nia-" + Math.random().toString(36).slice(2) + "-" + Date.now().toString(36);
      localStorage.setItem("nia_session_id", id);
    }
    return id;
  } catch (_) {
    return "nia-fallback-" + Date.now();
  }
}

export default function NiaChat({ caseId, clientFirstName }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadedHistory, setLoadedHistory] = useState(false);
  const sessionIdRef = useRef(ensureSessionId());
  const listRef = useRef(null);

  useEffect(() => {
    if (!open || loadedHistory) return;
    (async () => {
      try {
        const { data } = await api.get(`/nia/history/${sessionIdRef.current}`);
        setMessages(data.turns || []);
      } catch (_) { /* fine, empty */ }
      finally { setLoadedHistory(true); }
    })();
  }, [open, loadedHistory]);

  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages, open]);

  const send = async () => {
    const msg = input.trim();
    if (!msg || sending) return;
    setInput("");
    const optimistic = { role: "user", content: msg, at: new Date().toISOString() };
    setMessages((m) => [...m, optimistic]);
    setSending(true);
    try {
      const { data } = await api.post("/nia/chat", {
        message: msg,
        session_id: sessionIdRef.current,
        case_id: caseId || null,
        client_first_name: clientFirstName || null,
      });
      setMessages((m) => [
        ...m,
        { role: "assistant", content: data.reply, at: new Date().toISOString(), urgent: !!data.urgent },
      ]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: "I'm having trouble reaching my brain — please try again in a moment.",
          error: true,
        },
      ]);
    } finally { setSending(false); }
  };

  return (
    <>
      {/* Bubble */}
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-5 right-5 z-40 h-14 w-14 rounded-full bg-navy text-white shadow-xl flex items-center justify-center hover:bg-navy/90 active:scale-95 transition"
          aria-label="Chat with Nia"
          data-testid="nia-open-btn">
          <MessageCircle className="h-6 w-6" />
        </button>
      )}

      {/* Panel */}
      {open && (
        <div
          className="fixed bottom-4 right-4 z-50 w-[95vw] max-w-[380px] h-[70vh] max-h-[560px] flex flex-col rounded-2xl bg-white shadow-2xl border border-[#E2E0DA] overflow-hidden"
          data-testid="nia-panel">
          {/* Header */}
          <div className="bg-navy text-white px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-bronze flex items-center justify-center font-bold text-navy">N</div>
              <div className="leading-tight">
                <p className="font-serif text-lg">Nia</p>
                <p className="text-[10px] uppercase tracking-widest text-white/60">Iron Gate AI Assistant</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-white/70 hover:text-white" aria-label="Close" data-testid="nia-close-btn">
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Messages */}
          <div
            ref={listRef}
            className="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-[#FAF9F5]"
            data-testid="nia-messages">
            {messages.length === 0 && (
              <div className="rounded-lg bg-white border border-[#E2E0DA] p-3 text-sm text-[#334155]">
                <p className="font-serif text-lg text-navy mb-1">Hi{clientFirstName ? ` ${clientFirstName}` : ""} 👋</p>
                <p>
                  I'm Nia, Iron Gate's AI assistant. Ask me anything about your trust, what to put in a field,
                  or what happens next. If you need a human, I'll flag Wes on WhatsApp immediately.
                </p>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-navy text-white rounded-br-sm"
                      : "bg-white border border-[#E2E0DA] text-[#1C252E] rounded-bl-sm"
                  }`}>
                  {m.content}
                  {m.urgent && (
                    <div className="mt-2 flex items-center gap-1 text-[11px] text-amber-800">
                      <AlertCircle className="h-3 w-3" /> Wes has been notified — a human will follow up shortly.
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-white border border-[#E2E0DA] px-3 py-2 text-sm text-[#64748B] inline-flex items-center gap-2">
                  <Loader2 className="h-3 w-3 animate-spin" /> Nia is typing…
                </div>
              </div>
            )}
          </div>

          {/* Composer */}
          <div className="border-t border-[#E2E0DA] p-2 bg-white">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
                }}
                placeholder="Ask Nia anything about your trust…"
                className="flex-1 resize-none rounded-lg border border-[#E2E0DA] px-3 py-2 text-sm outline-none focus:border-bronze"
                rows={1}
                maxLength={2000}
                data-testid="nia-input"
              />
              <button
                onClick={send}
                disabled={!input.trim() || sending}
                className="h-10 w-10 rounded-full bg-navy text-white flex items-center justify-center disabled:opacity-40"
                aria-label="Send"
                data-testid="nia-send-btn">
                <Send className="h-4 w-4" />
              </button>
            </div>
            <p className="text-[10px] text-[#94A3B8] mt-1 px-1">
              Nia is an AI. A human from Iron Gate will always review your case.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
