import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Sparkles, Send, CheckCircle2, MessageCircle, Filter, ArrowRight } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const STATUS_META = {
  escalated: { label: "Needs your reply", bg: "bg-amber-100", text: "text-amber-900" },
  ai_answered: { label: "AI answered", bg: "bg-bronze/15", text: "text-bronze" },
  admin_replied: { label: "You replied", bg: "bg-green-100", text: "text-green-800" },
};

export default function AdminQuestions() {
  const [data, setData] = useState({ questions: [], counts: { escalated: 0, ai_answered: 0 } });
  const [filter, setFilter] = useState("escalated");
  const [loading, setLoading] = useState(true);
  const [replyDraft, setReplyDraft] = useState({});
  const [submitting, setSubmitting] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      const params = filter ? { status: filter } : {};
      const { data } = await api.get("/admin/questions", { params });
      setData(data);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [filter]);

  const reply = async (qid) => {
    const text = (replyDraft[qid] || "").trim();
    if (!text) return;
    setSubmitting(qid);
    try {
      await api.post(`/admin/questions/${qid}/reply`, { reply: text });
      toast.success("Reply sent");
      setReplyDraft({ ...replyDraft, [qid]: "" });
      await load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSubmitting(null); }
  };

  return (
    <Layout>
      <div className="mb-8">
        <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Client Questions</p>
        <h1 className="font-serif text-4xl sm:text-5xl text-navy tracking-tight">Questions Inbox</h1>
        <p className="text-[#64748B] mt-2">Answered instantly by AI when possible; anything complex shows up here for your review.</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <button onClick={() => setFilter("escalated")}
          className={`bg-white border rounded-xl p-5 text-left transition-all ${filter === "escalated" ? "border-amber-400 shadow-md" : "border-[#E2E0DA] hover:border-bronze"}`}
          data-testid="filter-escalated">
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Needs your reply</p>
          <p className="font-serif text-3xl text-amber-700 mt-1">{data.counts?.escalated || 0}</p>
        </button>
        <button onClick={() => setFilter("ai_answered")}
          className={`bg-white border rounded-xl p-5 text-left transition-all ${filter === "ai_answered" ? "border-bronze shadow-md" : "border-[#E2E0DA] hover:border-bronze"}`}
          data-testid="filter-ai-answered">
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">AI answered</p>
          <p className="font-serif text-3xl text-bronze mt-1">{data.counts?.ai_answered || 0}</p>
        </button>
        <button onClick={() => setFilter("admin_replied")}
          className={`bg-white border rounded-xl p-5 text-left transition-all ${filter === "admin_replied" ? "border-green-400 shadow-md" : "border-[#E2E0DA] hover:border-bronze"}`}
          data-testid="filter-replied">
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Replied</p>
          <p className="font-serif text-3xl text-green-700 mt-1">—</p>
        </button>
        <button onClick={() => setFilter("")}
          className={`bg-white border rounded-xl p-5 text-left transition-all ${filter === "" ? "border-navy shadow-md" : "border-[#E2E0DA] hover:border-bronze"}`}
          data-testid="filter-all">
          <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">All</p>
          <p className="font-serif text-3xl text-navy mt-1"><Filter className="h-5 w-5 inline text-[#94A3B8]" /></p>
        </button>
      </div>

      {loading ? (
        <p className="text-[#64748B]">Loading…</p>
      ) : data.questions.length === 0 ? (
        <div className="bg-white border border-[#E2E0DA] rounded-xl p-10 text-center" data-testid="admin-questions-empty">
          <MessageCircle className="h-8 w-8 mx-auto mb-2 text-[#CBD5E1]" />
          <p className="text-[#64748B]">No questions match this filter.</p>
        </div>
      ) : (
        <div className="space-y-4">
          {data.questions.map((q) => {
            const meta = STATUS_META[q.status] || { label: q.status, bg: "bg-sand-200", text: "text-navy" };
            return (
              <div key={q.id} className="bg-white border border-[#E2E0DA] rounded-xl p-5 sm:p-6" data-testid={`question-card-${q.id}`}>
                <div className="flex flex-wrap items-start justify-between gap-3 mb-2">
                  <div className="flex items-start gap-3 min-w-0 flex-1">
                    <div className="shrink-0 h-9 w-9 rounded-full bg-navy text-white text-sm font-semibold flex items-center justify-center">
                      {(q.client_name || "C").charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-navy truncate">{q.client_name}</p>
                      <p className="text-xs text-[#64748B]">{q.client_email} · {q.section_label || q.section} · {timeAgo(q.created_at)}</p>
                    </div>
                  </div>
                  <span className={`text-[11px] uppercase tracking-wider ${meta.bg} ${meta.text} rounded-full px-3 py-1 font-semibold shrink-0`}>
                    {meta.label}
                  </span>
                </div>

                <p className="text-sm text-navy/90 mt-3 whitespace-pre-wrap">{q.question}</p>

                {q.ai_response && (
                  <div className="mt-3 p-3 bg-bronze/5 border-l-2 border-bronze rounded-r-md">
                    <div className="flex items-center gap-1 mb-0.5">
                      <Sparkles className="h-3 w-3 text-bronze" />
                      <span className="text-[10px] uppercase tracking-wider text-bronze font-semibold">AI assistant {q.ai_confident ? "— answered" : "— could not answer"}</span>
                    </div>
                    <p className="text-sm text-navy/80 whitespace-pre-wrap">{q.ai_response}</p>
                  </div>
                )}

                {q.admin_reply ? (
                  <div className="mt-3 p-3 bg-green-50 border-l-2 border-green-500 rounded-r-md">
                    <div className="flex items-center gap-1 mb-0.5">
                      <CheckCircle2 className="h-3 w-3 text-green-700" />
                      <span className="text-[10px] uppercase tracking-wider text-green-800 font-semibold">{q.admin_replied_by || "Admin"} replied · {timeAgo(q.admin_replied_at)}</span>
                    </div>
                    <p className="text-sm text-navy whitespace-pre-wrap">{q.admin_reply}</p>
                  </div>
                ) : (
                  <div className="mt-4">
                    <Textarea
                      value={replyDraft[q.id] || ""}
                      onChange={(e) => setReplyDraft({ ...replyDraft, [q.id]: e.target.value })}
                      placeholder="Type your reply to the client… (sent via email + visible in their portal)"
                      rows={3}
                      className="bg-white"
                      data-testid={`question-reply-input-${q.id}`}
                    />
                    <div className="flex justify-between items-center mt-2">
                      <Link to={`/admin/cases/${q.case_id}`} className="text-xs text-bronze hover:text-bronze-dark inline-flex items-center gap-1" data-testid={`question-open-case-${q.id}`}>
                        Open case <ArrowRight className="h-3 w-3" />
                      </Link>
                      <button onClick={() => reply(q.id)} disabled={submitting === q.id || !((replyDraft[q.id] || "").trim())}
                        className="btn-primary text-sm" data-testid={`question-reply-submit-${q.id}`}>
                        <Send className="h-4 w-4 inline mr-1" /> {submitting === q.id ? "Sending…" : "Send reply"}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Layout>
  );
}
