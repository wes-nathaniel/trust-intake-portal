import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Inbox, LinkIcon, Archive, RefreshCw, Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";

function fmt(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString();
}

function AttachModal({ thread, onClose, onAttached }) {
  const [query, setQuery] = useState("");
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [savePhone, setSavePhone] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const { data } = await api.get("/admin/trust-cases");
        setCases(data || []);
      } catch (e) {
        toast.error(formatApiError(e.response?.data?.detail));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const filtered = cases.filter((c) => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      (c.client_name || "").toLowerCase().includes(q) ||
      (c.client_email || "").toLowerCase().includes(q) ||
      (c.id || "").toLowerCase().includes(q)
    );
  }).slice(0, 25);

  const attach = async () => {
    if (!selectedId) return toast.error("Pick a case first");
    setSubmitting(true);
    try {
      const { data } = await api.post("/admin/whatsapp/inbox/attach", {
        from_number: thread.from,
        case_id: selectedId,
        save_phone: savePhone,
      });
      toast.success(`Attached ${data.attached} message(s) to case`);
      onAttached();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-navy/50 z-50 flex items-center justify-center p-4"
      data-testid="attach-modal"
    >
      <div className="bg-white rounded-xl w-full max-w-2xl shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-[#E2E0DA]">
          <div>
            <h3 className="font-serif text-2xl text-navy">Attach to case</h3>
            <p className="text-sm text-[#64748B]">
              Sender: <span className="font-semibold">{thread.from}</span>
              {thread.profile_name && <> · {thread.profile_name}</>}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-[#64748B] hover:text-navy"
            data-testid="attach-modal-close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-5 space-y-4">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-[#64748B]" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, email, or case id…"
              className="pl-9 bg-white"
              data-testid="attach-search-input"
            />
          </div>
          <div className="max-h-80 overflow-y-auto border border-[#E2E0DA] rounded-md">
            {loading ? (
              <p className="p-4 text-sm text-[#64748B]">Loading cases…</p>
            ) : filtered.length === 0 ? (
              <p className="p-4 text-sm text-[#64748B]">No cases match.</p>
            ) : (
              <ul>
                {filtered.map((c) => (
                  <li
                    key={c.id}
                    onClick={() => setSelectedId(c.id)}
                    className={`p-3 border-b border-[#E2E0DA] cursor-pointer hover:bg-sand-200/40 ${
                      selectedId === c.id ? "bg-sand-200/60" : ""
                    }`}
                    data-testid={`attach-case-${c.id.slice(0, 8)}`}
                  >
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="font-semibold text-navy">
                        {c.client_name || "—"}
                      </span>
                      <span className="text-xs text-[#64748B]">
                        #{c.id.slice(0, 8).toUpperCase()}
                      </span>
                    </div>
                    <div className="text-xs text-[#64748B]">
                      {c.client_email} · {c.status}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={savePhone}
              onChange={(e) => setSavePhone(e.target.checked)}
              data-testid="attach-save-phone-checkbox"
            />
            Save {thread.from} as the client&apos;s phone so future replies auto-route.
          </label>
        </div>
        <div className="flex items-center justify-end gap-2 p-5 border-t border-[#E2E0DA]">
          <button
            onClick={onClose}
            className="btn-secondary text-sm"
            data-testid="attach-cancel-btn"
          >
            Cancel
          </button>
          <button
            onClick={attach}
            disabled={submitting || !selectedId}
            className="btn-primary text-sm disabled:opacity-60"
            data-testid="attach-confirm-btn"
          >
            {submitting ? "Attaching…" : "Attach messages"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminWhatsAppInbox() {
  const [threads, setThreads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [attaching, setAttaching] = useState(null); // thread being attached

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/whatsapp/inbox");
      setThreads(data.threads || []);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const archive = async (fromNumber) => {
    if (!window.confirm(`Archive all messages from ${fromNumber}?`)) return;
    try {
      await api.post("/admin/whatsapp/inbox/archive", { from_number: fromNumber });
      toast.success("Archived");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  return (
    <Layout>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-serif text-4xl text-navy flex items-center gap-3">
            <Inbox className="h-8 w-8 text-[#25D366]" />
            WhatsApp Inbox
          </h1>
          <p className="text-[#64748B] mt-1">
            Messages from senders who aren&apos;t attached to an existing case yet.
          </p>
        </div>
        <button
          onClick={load}
          className="btn-secondary text-sm"
          data-testid="inbox-refresh-btn"
        >
          <RefreshCw className="h-4 w-4 inline mr-1" /> Refresh
        </button>
      </div>

      {loading ? (
        <p className="text-[#64748B]">Loading…</p>
      ) : threads.length === 0 ? (
        <div
          className="bg-white border border-[#E2E0DA] rounded-xl p-10 text-center"
          data-testid="inbox-empty"
        >
          <Inbox className="h-10 w-10 text-[#25D366] mx-auto mb-3 opacity-60" />
          <p className="font-serif text-2xl text-navy">Inbox is clear</p>
          <p className="text-[#64748B] mt-2">
            No unmatched WhatsApp messages. Nice.
          </p>
        </div>
      ) : (
        <ul className="space-y-4" data-testid="inbox-threads">
          {threads.map((t) => (
            <li
              key={t.from}
              className="bg-white border border-[#E2E0DA] rounded-xl p-5"
              data-testid={`inbox-thread-${t.from}`}
            >
              <div className="flex items-start justify-between gap-4 mb-3">
                <div>
                  <p className="font-serif text-xl text-navy">
                    {t.profile_name || "Unknown sender"}
                  </p>
                  <p className="text-sm text-[#64748B]">
                    {t.from} · {t.messages.length} message
                    {t.messages.length > 1 ? "s" : ""} · latest {fmt(t.latest_at)}
                  </p>
                </div>
                <div className="flex gap-2 shrink-0">
                  <button
                    onClick={() => setAttaching(t)}
                    className="btn-primary text-sm"
                    data-testid={`inbox-attach-${t.from}`}
                  >
                    <LinkIcon className="h-4 w-4 inline mr-1" /> Attach to case
                  </button>
                  <button
                    onClick={() => archive(t.from)}
                    className="btn-secondary text-sm"
                    data-testid={`inbox-archive-${t.from}`}
                  >
                    <Archive className="h-4 w-4 inline mr-1" /> Archive
                  </button>
                </div>
              </div>
              <ul className="space-y-2 max-h-60 overflow-y-auto pr-1">
                {t.messages.slice().reverse().map((m) => (
                  <li
                    key={m.id}
                    className="text-sm p-3 rounded-md bg-[#F6F4F0] border border-[#E2E0DA]"
                  >
                    <div className="text-xs text-[#64748B] mb-1">{fmt(m.at)}</div>
                    <div className="text-navy whitespace-pre-wrap">{m.body}</div>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      )}

      <div className="mt-8 p-4 bg-sand-200/40 border border-bronze/30 rounded-md text-sm text-navy/80">
        <strong>Tip:</strong> To operate cases from your phone, DM the Twilio
        number directly with commands like <code>/help</code>, <code>/cases</code>,
        or <code>/case 6F96B5B7 status In Review</code>. Commands are only accepted
        from the admin WhatsApp number configured in the environment.
      </div>

      <p className="mt-4 text-sm text-[#64748B]">
        <Link to="/admin" className="text-navy hover:text-bronze font-medium">
          ← Back to cases
        </Link>
      </p>

      {attaching && (
        <AttachModal
          thread={attaching}
          onClose={() => setAttaching(null)}
          onAttached={async () => {
            setAttaching(null);
            await load();
          }}
        />
      )}
    </Layout>
  );
}
