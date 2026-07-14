import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Copy, GripVertical, BookOpen, ChevronDown, ChevronUp, Save, Eye, EyeOff, Sparkles } from "lucide-react";
import RichTextEditor from "@/components/RichTextEditor";
import { TRUST_TEMPLATES } from "@/lib/trustTemplates";

/** Lightweight single-article preview pair (mirrors the two-panel viewer styling, no scroll-sync) */
function InlineArticlePreview({ title, trust_html, explainer_html }) {
  return (
    <div className="mt-3 rounded-lg border border-bronze/30 overflow-hidden" data-testid="trust-section-inline-preview">
      <div className="bg-[#1C252E] px-3 py-1.5 text-[10px] uppercase tracking-wide text-[#D8BC92] font-semibold">
        Live preview — exactly what the client sees for this article
      </div>
      <div className="grid md:grid-cols-2 gap-0">
        <div className="p-4 bg-[#f3f3f5] border-r border-bronze/30 relative overflow-hidden">
          <div className="absolute inset-0 opacity-[0.18] pointer-events-none" style={{
            backgroundImage: "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='160'%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' transform='rotate(-30 160 80)' font-family='Arial' font-size='16' font-weight='bold' fill='%23C5A880' letter-spacing='3'%3EDRAFT%3C/text%3E%3C/svg%3E\")",
            backgroundRepeat: "repeat",
          }} />
          <div className="relative">
            {title && <p className="text-[11px] uppercase tracking-wide font-bold text-bronze mb-2">{title}</p>}
            <div className="text-[12px] leading-relaxed text-[#2a2a2a]" dangerouslySetInnerHTML={{ __html: trust_html || "<em style='color:#94A3B8'>Trust text empty…</em>" }} />
          </div>
        </div>
        <div className="p-4 bg-[#FDF8EE]">
          {title && <p className="text-[10px] uppercase tracking-wider font-bold text-bronze mb-2">{title} — Plain English</p>}
          <div className="text-[13px] leading-relaxed text-[#333]" dangerouslySetInnerHTML={{ __html: explainer_html || "<em style='color:#94A3B8'>Explainer empty…</em>" }} />
        </div>
      </div>
    </div>
  );
}

/**
 * Admin UI for the structured two-panel Trust Viewer content.
 * Side-by-side textareas per article, variable count, "+ Add Article".
 * Persists as case.trust_sections via PUT /admin/trust-cases/{id}/trust-sections.
 */
export default function TrustSectionsEditor({ caseId, initialSections = [], onSaved, hasTrustDraft = false, onAutoExtracted, draftSections = null, onDraftChanged }) {
  // If a pending draft exists, we edit THAT (not the published sections).
  const editingDraft = Array.isArray(draftSections) && draftSections.length > 0;
  const [sections, setSections] = useState(
    editingDraft ? draftSections : (initialSections.length > 0 ? initialSections : [])
  );
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [autoExtracting, setAutoExtracting] = useState(false);
  const [open, setOpen] = useState(editingDraft || initialSections.length === 0);
  const [dirty, setDirty] = useState(false);
  const [previewOpen, setPreviewOpen] = useState({});

  // Intentional: when parent loads a new case or the draft state changes,
  // hydrate the editor accordingly.
  useEffect(() => {
    if (editingDraft) {
      setSections(draftSections);
    } else {
      setSections(initialSections.length > 0 ? initialSections : []);
    }
    setDirty(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSections, draftSections, editingDraft]);

  const update = (i, patch) => {
    setSections((arr) => {
      const next = arr.slice();
      next[i] = { ...next[i], ...patch };
      return next;
    });
    setDirty(true);
  };

  const addSection = () => {
    setSections((arr) => [...arr, { title: "", trust_html: "", explainer_html: "" }]);
    setDirty(true);
  };

  const removeSection = (i) => {
    if (!window.confirm("Remove this article? This cannot be undone (until you click Save).")) return;
    setSections((arr) => arr.filter((_, idx) => idx !== i));
    setDirty(true);
  };

  const duplicateSection = (i) => {
    setSections((arr) => {
      const src = arr[i];
      const copy = {
        // Preserve new canonical fields when present
        article_number: src.article_number || "",
        article_title: src.article_title || "",
        article_text: src.article_text || src.trust_html || "",
        explainer_text: src.explainer_text || src.explainer_html || "",
        // Legacy display title
        title: src.title ? `${src.title} (copy)` : "",
        trust_html: src.trust_html || src.article_text || "",
        explainer_html: src.explainer_html || src.explainer_text || "",
      };
      const next = arr.slice();
      next.splice(i + 1, 0, copy);
      return next;
    });
    setDirty(true);
  };

  const move = (i, dir) => {
    setSections((arr) => {
      const next = arr.slice();
      const j = i + dir;
      if (j < 0 || j >= next.length) return next;
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setDirty(true);
  };

  const autoExtract = async () => {
    if (sections.length > 0 && !window.confirm("This will REPLACE all existing articles with AI-extracted ones from the uploaded PDF. Continue?")) return;
    setAutoExtracting(true);
    let pollTimer = null;
    let elapsedMs = 0;
    const POLL_INTERVAL_MS = 6000;
    const MAX_POLL_MS = 4 * 60 * 1000; // 4 minutes
    try {
      // Fire-and-forget: server returns 202 immediately with a task id.
      await api.post(`/admin/trust-cases/${caseId}/trust-sections/auto-extract`);
      toast.message("AI is reading the PDF in the background — this can take up to 90 seconds.");

      // Poll the status endpoint until completed or failed.
      await new Promise((resolve, reject) => {
        const tick = async () => {
          try {
            const { data } = await api.get(
              `/admin/trust-cases/${caseId}/trust-sections/extract-status`
            );
            if (data.status === "completed") {
              const n = data.sections_count || 0;
              toast.success(
                `AI drafted ${n} article${n === 1 ? "" : "s"} from the PDF. Review below, then click "Publish to client".`
              );
              onAutoExtracted && onAutoExtracted();
              resolve();
              return;
            }
            if (data.status === "failed") {
              toast.error(data.error || "AI extraction failed. Please try again.");
              resolve();
              return;
            }
            // Still pending — surface incremental progress if available.
            if (data.batches_total > 0) {
              // Silent — the button label already conveys "working"; extra toasts would spam.
            }
            elapsedMs += POLL_INTERVAL_MS;
            if (elapsedMs >= MAX_POLL_MS) {
              toast.error(
                "AI extraction is still running after 4 minutes. Please refresh the page in a moment to see the results."
              );
              resolve();
              return;
            }
            pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
          } catch (e) {
            reject(e);
          }
        };
        pollTimer = setTimeout(tick, POLL_INTERVAL_MS);
      });
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      if (pollTimer) clearTimeout(pollTimer);
      setAutoExtracting(false);
    }
  };

  const publishDraft = async () => {
    if (dirty) {
      if (!window.confirm("You have unsaved changes to the draft. Save them first, then publish? (Cancel to save manually.)")) return;
      // caller can save then publish; for now just block
      return;
    }
    if (!window.confirm(`Publish these ${sections.length} article(s) to the client? They will immediately see the side-by-side viewer.`)) return;
    setPublishing(true);
    try {
      await api.post(`/admin/trust-cases/${caseId}/trust-sections/publish-draft`);
      toast.success("Draft published — client can now see the trust viewer.");
      onDraftChanged && onDraftChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setPublishing(false);
    }
  };

  const discardDraft = async () => {
    if (!window.confirm("Discard this AI draft? You'll lose all edits made since generation.")) return;
    setDiscarding(true);
    try {
      await api.delete(`/admin/trust-cases/${caseId}/trust-sections/draft`);
      toast.success("Draft discarded.");
      onDraftChanged && onDraftChanged();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setDiscarding(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      // Strip whitespace; allow empty rows to be filtered out if both blank.
      // Preserve BOTH new canonical fields (article_number/title/text, explainer_text)
      // AND legacy fields (title, trust_html, explainer_html). The backend
      // normalizes and stores both so any reader stays happy.
      const cleaned = sections
        .map((s) => {
          const trust = s.trust_html ?? s.article_text ?? "";
          const explain = s.explainer_html ?? s.explainer_text ?? "";
          return {
            article_number: (s.article_number || "").trim().slice(0, 20),
            article_title: (s.article_title || "").trim().slice(0, 200),
            article_text: trust,
            explainer_text: explain,
            title: (s.title || "").trim().slice(0, 200),
            trust_html: trust,
            explainer_html: explain,
          };
        })
        .filter((s) => s.title || s.article_title || s.trust_html.trim() || s.explainer_html.trim());
      const url = editingDraft
        ? `/admin/trust-cases/${caseId}/trust-sections/draft`
        : `/admin/trust-cases/${caseId}/trust-sections`;
      await api.put(url, { sections: cleaned });
      toast.success(
        editingDraft
          ? `Draft saved — ${cleaned.length} article${cleaned.length === 1 ? "" : "s"}. Click "Publish to client" when you're ready.`
          : `Saved — ${cleaned.length} article${cleaned.length === 1 ? "" : "s"}. Move the status to "Ready for Client Review" when ready.`
      );
      setDirty(false);
      if (editingDraft) {
        onDraftChanged && onDraftChanged();
      } else {
        onSaved && onSaved(cleaned);
      }
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl mb-6" data-testid="trust-sections-editor">
      {editingDraft && (
        <div className="mx-5 mt-5 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 flex items-center justify-between gap-3 flex-wrap" data-testid="trust-sections-draft-banner">
          <div className="flex items-center gap-2 min-w-0">
            <Sparkles className="h-4 w-4 text-amber-700 shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-amber-900">AI draft — pending your review</p>
              <p className="text-xs text-amber-800">
                Clients do NOT see this yet. Edit any article below, then click <b>Publish to client</b> when it's ready.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              onClick={discardDraft}
              disabled={discarding || publishing}
              className="btn-secondary text-xs"
              data-testid="trust-sections-discard-draft-btn">
              {discarding ? "Discarding…" : "Discard draft"}
            </button>
            <button
              onClick={publishDraft}
              disabled={publishing || discarding || dirty}
              className="btn-primary text-xs"
              title={dirty ? "Save your edits first" : "Make this visible to the client"}
              data-testid="trust-sections-publish-draft-btn">
              {publishing ? "Publishing…" : "Publish to client"}
            </button>
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-5 text-left"
        data-testid="trust-sections-toggle">
        <div className="flex items-center gap-3">
          <BookOpen className="h-5 w-5 text-bronze" />
          <div>
            <p className="font-serif text-lg text-navy">
              Trust Viewer Content
              {editingDraft && <span className="ml-2 text-[10px] uppercase tracking-wider bg-amber-100 text-amber-800 border border-amber-300 px-1.5 py-0.5 rounded font-sans font-semibold align-middle">Draft</span>}
            </p>
            <p className="text-xs text-[#64748B]">
              {sections.length === 0
                ? "Paste the per-article trust + plain-English text. Variable number of articles."
                : `${sections.length} article${sections.length === 1 ? "" : "s"}${dirty ? " · unsaved changes" : ""}`}
            </p>
          </div>
        </div>
        {open ? <ChevronUp className="h-4 w-4 text-[#64748B]" /> : <ChevronDown className="h-4 w-4 text-[#64748B]" />}
      </button>

      {open && (
        <div className="px-5 pb-5">
          {sections.length === 0 && (
            <div className="text-center py-8 text-sm text-[#64748B]" data-testid="trust-sections-empty">
              {hasTrustDraft ? (
                <>
                  <p className="mb-3">No articles yet. Two ways to get started:</p>
                  <div className="flex flex-col sm:flex-row gap-2 justify-center items-center">
                    <button
                      onClick={autoExtract}
                      disabled={autoExtracting}
                      className="btn-primary text-sm inline-flex items-center"
                      data-testid="trust-sections-auto-extract-btn">
                      <Sparkles className="h-4 w-4 mr-1" />
                      {autoExtracting ? "AI is reading the PDF (up to 90s)…" : "Auto-generate from PDF"}
                    </button>
                    <span className="text-xs text-[#94A3B8]">or</span>
                    <span className="text-xs">click <b>Add article</b> below to type manually</span>
                  </div>
                </>
              ) : (
                <>No articles yet. Click <b>Add article</b> below to start, or upload a trust draft PDF first for auto-extraction.</>
              )}
            </div>
          )}

          <div className="space-y-4">
            {sections.map((s, i) => (
              <div key={i} className="border border-[#E2E0DA] rounded-lg p-3 sm:p-4" data-testid={`trust-section-row-${i}`}>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <div className="flex items-center gap-2 min-w-0">
                    <GripVertical className="h-4 w-4 text-[#94A3B8]" />
                    <span className="text-xs uppercase tracking-wide text-bronze font-semibold">Article {i + 1}</span>
                    <input
                      type="text"
                      value={s.title || ""}
                      onChange={(e) => update(i, { title: e.target.value })}
                      placeholder='Title (e.g., "Article I — Identification")'
                      className="flex-1 min-w-0 ml-2 text-sm bg-white border border-input rounded-md px-2 py-1.5"
                      data-testid={`trust-section-title-${i}`}
                    />
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      onClick={() => setPreviewOpen((p) => ({ ...p, [i]: !p[i] }))}
                      className={`p-1 ${previewOpen[i] ? "text-bronze" : "text-[#64748B] hover:text-navy"}`}
                      title={previewOpen[i] ? "Hide inline preview" : "Show inline preview"}
                      data-testid={`trust-section-preview-toggle-${i}`}>
                      {previewOpen[i] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                    <button onClick={() => move(i, -1)} disabled={i === 0} className="p-1 text-[#64748B] hover:text-navy disabled:opacity-30" title="Move up" data-testid={`trust-section-up-${i}`}>
                      <ChevronUp className="h-4 w-4" />
                    </button>
                    <button onClick={() => move(i, 1)} disabled={i === sections.length - 1} className="p-1 text-[#64748B] hover:text-navy disabled:opacity-30" title="Move down" data-testid={`trust-section-down-${i}`}>
                      <ChevronDown className="h-4 w-4" />
                    </button>
                    <button onClick={() => duplicateSection(i)} className="p-1 text-[#64748B] hover:text-navy" title="Duplicate article" data-testid={`trust-section-duplicate-${i}`}>
                      <Copy className="h-4 w-4" />
                    </button>
                    <button onClick={() => removeSection(i)} className="p-1 text-red-600 hover:text-red-700" title="Remove article" data-testid={`trust-section-remove-${i}`}>
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="grid md:grid-cols-2 gap-3">
                  <div>
                    <label className="text-[10px] uppercase tracking-wide text-[#64748B] font-semibold">Trust text (left panel)</label>
                    <RichTextEditor
                      value={s.trust_html || ""}
                      onChange={(html) => update(i, { trust_html: html })}
                      placeholder="The Grantor, John A. Smith, hereby establishes…"
                      rows={8}
                      testId={`trust-section-trust-${i}`}
                      templates={TRUST_TEMPLATES}
                      templateField="trust_html"
                    />
                  </div>
                  <div>
                    <label className="text-[10px] uppercase tracking-wide text-[#64748B] font-semibold">Plain-English explainer (right panel)</label>
                    <RichTextEditor
                      value={s.explainer_html || ""}
                      onChange={(html) => update(i, { explainer_html: html })}
                      placeholder="This says you are setting up the trust…"
                      rows={8}
                      testId={`trust-section-explainer-${i}`}
                      templates={TRUST_TEMPLATES}
                      templateField="explain_html"
                    />
                  </div>
                </div>

                {previewOpen[i] && (
                  <InlineArticlePreview
                    title={s.title}
                    trust_html={s.trust_html}
                    explainer_html={s.explainer_html}
                  />
                )}
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between gap-3 mt-4 flex-wrap">
            <button onClick={addSection} className="btn-secondary text-sm" data-testid="trust-sections-add-btn">
              <Plus className="h-4 w-4 inline mr-1" /> Add article
            </button>
            <div className="flex items-center gap-2 flex-wrap">
              {dirty && <span className="text-xs text-amber-700">Unsaved changes</span>}
              <button
                type="button"
                onClick={() => {
                  if (dirty) {
                    if (!window.confirm("You have unsaved changes. The preview shows the LAST SAVED version — continue?")) return;
                  }
                  window.open(`/admin/cases/${caseId}/trust-viewer-preview`, "_blank", "noopener,noreferrer");
                }}
                className="btn-secondary text-sm"
                data-testid="trust-sections-preview-btn">
                <Eye className="h-4 w-4 inline mr-1" /> Preview as Client
              </button>
              <button onClick={save} disabled={saving} className="btn-primary text-sm" data-testid="trust-sections-save-btn">
                <Save className="h-4 w-4 inline mr-1" /> {saving ? "Saving…" : "Save Trust Viewer content"}
              </button>
            </div>
          </div>

          <p className="text-[11px] text-[#94A3B8] mt-3">
            Saving with at least one article auto-advances the case to <b>Ready for Client Review</b> and notifies the client. Use the toolbar to format text; click <Eye className="h-3 w-3 inline-block align-text-bottom" /> next to any article for an inline preview, or <b>Preview as Client</b> below for the full viewer.
          </p>
        </div>
      )}
    </div>
  );
}
