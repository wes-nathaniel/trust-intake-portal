import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { MessageCircle, Send, ArrowDownLeft, ArrowUpRight, AlertTriangle } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";

function relTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString();
}

export default function WhatsAppPanel({ caseId, defaultTo }) {
  const [status, setStatus] = useState(null);
  const [thread, setThread] = useState([]);
  const [to, setTo] = useState(defaultTo || "");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  const load = async () => {
    try {
      const [s, t] = await Promise.all([
        api.get("/admin/whatsapp/status"),
        api.get(`/admin/trust-cases/${caseId}/whatsapp-thread`),
      ]);
      setStatus(s.data);
      setThread(t.data.thread || []);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  useEffect(() => {
    load();
  }, [caseId]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (defaultTo && !to) setTo(defaultTo);
  }, [defaultTo]);  // eslint-disable-line react-hooks/exhaustive-deps

  const send = async () => {
    if (!body.trim()) return toast.error("Message body is empty");
    setSending(true);
    try {
      const { data } = await api.post(`/admin/trust-cases/${caseId}/send-whatsapp`, {
        to: to.trim() || null,
        body: body.trim(),
      });
      toast.success(data.sent ? "WhatsApp sent" : "Logged (Twilio disabled — check config)");
      setBody("");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSending(false);
    }
  };

  return (
    <section
      className="bg-white border border-[#E2E0DA] rounded-xl p-6"
      data-testid="whatsapp-panel"
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-serif text-2xl text-navy flex items-center gap-2">
          <MessageCircle className="h-5 w-5 text-[#25D366]" />
          WhatsApp
        </h3>
        {status && (
          <span
            className={`text-xs px-2 py-1 rounded-full ${
              status.enabled
                ? "bg-green-50 text-green-700 border border-green-200"
                : "bg-amber-50 text-amber-700 border border-amber-200"
            }`}
            data-testid="whatsapp-status-badge"
          >
            {status.enabled ? "Live" : "Sandbox / disabled"}
          </span>
        )}
      </div>

      {status && !status.enabled && (
        <div className="mb-4 flex items-start gap-2 p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            WhatsApp sender is not fully configured. Set{" "}
            <code>TWILIO_WHATSAPP_FROM</code> in backend/.env (Twilio Sandbox default:{" "}
            <code>whatsapp:+14155238886</code>).
          </span>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-[220px_1fr] mb-3">
        <div>
          <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">
            To (E.164)
          </label>
          <Input
            value={to}
            onChange={(e) => setTo(e.target.value)}
            placeholder="+19545551234"
            className="mt-1 bg-white"
            data-testid="whatsapp-to-input"
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">
            Message
          </label>
          <Textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            placeholder="Hi — quick update on your trust…"
            className="mt-1 bg-white"
            data-testid="whatsapp-body-input"
          />
        </div>
      </div>
      <button
        onClick={send}
        disabled={sending || !body.trim()}
        className="btn-primary text-sm disabled:opacity-60"
        data-testid="whatsapp-send-btn"
      >
        <Send className="h-4 w-4 inline mr-1" />
        {sending ? "Sending…" : "Send WhatsApp"}
      </button>

      <div className="mt-6">
        <h4 className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">
          Thread
        </h4>
        {thread.length === 0 ? (
          <p className="text-sm text-[#64748B]">No WhatsApp activity for this case yet.</p>
        ) : (
          <ul className="space-y-2 max-h-80 overflow-y-auto pr-1" data-testid="whatsapp-thread">
            {thread.slice().reverse().map((m) => (
              <li
                key={m.id}
                className={`text-sm p-3 rounded-md border ${
                  m.direction === "inbound"
                    ? "bg-[#F6F4F0] border-[#E2E0DA]"
                    : "bg-navy/5 border-navy/10"
                }`}
                data-testid={`whatsapp-message-${m.id}`}
              >
                <div className="flex items-center gap-2 text-[#64748B] text-xs mb-1">
                  {m.direction === "inbound" ? (
                    <ArrowDownLeft className="h-3 w-3" />
                  ) : (
                    <ArrowUpRight className="h-3 w-3" />
                  )}
                  <span className="font-semibold uppercase tracking-wide">
                    {m.direction}
                  </span>
                  <span>·</span>
                  <span>{m.direction === "inbound" ? m.from : m.to}</span>
                  <span>·</span>
                  <span>{relTime(m.at)}</span>
                  {m.direction === "outbound" && !m.sent && (
                    <span className="ml-auto text-amber-700">
                      (not delivered — mock)
                    </span>
                  )}
                </div>
                <div className="text-navy whitespace-pre-wrap">{m.body}</div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
