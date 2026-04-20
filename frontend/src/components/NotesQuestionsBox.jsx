import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Sparkles, Send, Check, Loader2, MessageCircle } from "lucide-react";
import { toast } from "sonner";

/**
 * Section-level Notes / Questions box.
 * - Client types → submits → AI answers instantly if confident
 * - If AI isn't confident, the question is escalated (SMS if configured, email fallback)
 * - Past questions + AI answers + admin replies are shown in a thread
 */
export default function NotesQuestionsBox({ caseId, section }) {
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [latestAi, setLatestAi] = useState(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/trust-cases/${caseId}/questions`, { params: { section } });
      setItems(data || []);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    if (caseId && section) load();
    // eslint-disable-next-line
  }, [caseId, section]);

  const submit = async () => {
    if (!text.trim()) return;
    setLoading(true);
    setLatestAi(null);
    try {
      const { data } = await api.post(`/trust-cases/${caseId}/questions`, { section, question: text });
      setLatestAi(data);
      setText("");
      await load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setLoading(false); }
  };

  return (
    <div className="mt-8 border-t border-[#E2E0DA] pt-6" data-testid={`notes-questions-${section}`}>
      <div className="flex items-center gap-2 mb-1">
        <MessageCircle className="h-4 w-4 text-bronze" />
        <h4 className="font-serif text-xl text-navy">Notes / Questions About This Section <span className="text-sm text-[#64748B] font-sans">(Optional)</span></h4>
      </div>
      <p className="text-xs text-[#64748B] mb-3">Ask anything about this section. Our AI assistant answers common questions instantly; anything complex is routed directly to our team.</p>

      <div className="flex flex-col sm:flex-row gap-2">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g., Who should I pick as my trustee?"
          rows={2}
          className="bg-white flex-1 resize-none"
          data-testid={`question-input-${section}`}
        />
        <Button onClick={submit} disabled={loading || !text.trim()}
          className="btn-primary shrink-0 self-end" data-testid={`question-submit-${section}`}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : (<><Send className="h-4 w-4 mr-1" /> Ask</>)}
        </Button>
      </div>

      {latestAi && (
        <div className="mt-3 p-4 rounded-lg border border-bronze/40 bg-bronze/5" data-testid={`question-ai-response-${section}`}>
          <div className="flex items-center gap-2 mb-1">
            <Sparkles className="h-4 w-4 text-bronze" />
            <span className="text-xs uppercase tracking-wider text-bronze font-semibold">
              AI assistant {latestAi.ai_confident ? "answered" : "— routing to team"}
            </span>
            {latestAi.ai_confident && <Check className="h-3.5 w-3.5 text-green-600 ml-1" />}
          </div>
          <p className="text-sm text-navy whitespace-pre-wrap">{latestAi.ai_response}</p>
          {!latestAi.ai_confident && (
            <p className="text-xs text-[#64748B] mt-2">Your trust team has been notified and will reply in this box shortly.</p>
          )}
        </div>
      )}

      {items.length > 0 && (
        <div className="mt-5 space-y-3">
          <p className="text-xs uppercase tracking-wider text-[#64748B] font-semibold">Previous questions in this section</p>
          {items.slice().reverse().map((q) => (
            <div key={q.id} className="border border-[#E2E0DA] rounded-lg p-3" data-testid={`question-thread-item-${q.id}`}>
              <div className="flex items-start gap-2">
                <div className="shrink-0 h-6 w-6 rounded-full bg-sand-200 text-navy text-[10px] font-semibold flex items-center justify-center">
                  {(q.client_name || "C").charAt(0).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-[#64748B]">{q.client_name || "You"} · {new Date(q.created_at).toLocaleString()}</p>
                  <p className="text-sm text-navy mt-0.5 whitespace-pre-wrap">{q.question}</p>
                </div>
              </div>
              {q.ai_response && (
                <div className="mt-2 ml-8 text-sm text-navy/90 bg-bronze/5 border-l-2 border-bronze rounded-r-md px-3 py-2">
                  <div className="flex items-center gap-1 mb-0.5">
                    <Sparkles className="h-3 w-3 text-bronze" />
                    <span className="text-[10px] uppercase tracking-wider text-bronze font-semibold">AI assistant</span>
                  </div>
                  <p className="whitespace-pre-wrap">{q.ai_response}</p>
                </div>
              )}
              {q.admin_reply && (
                <div className="mt-2 ml-8 text-sm text-navy/90 bg-navy/5 border-l-2 border-navy rounded-r-md px-3 py-2">
                  <div className="flex items-center gap-1 mb-0.5">
                    <span className="text-[10px] uppercase tracking-wider text-navy font-semibold">
                      {q.admin_replied_by || "Trust team"} · reply
                    </span>
                    <span className="text-[10px] text-[#94A3B8]">· {new Date(q.admin_replied_at).toLocaleString()}</span>
                  </div>
                  <p className="whitespace-pre-wrap">{q.admin_reply}</p>
                </div>
              )}
              {!q.admin_reply && !q.ai_confident && (
                <p className="mt-2 ml-8 text-xs text-amber-700 italic">Awaiting reply from your trust team…</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
