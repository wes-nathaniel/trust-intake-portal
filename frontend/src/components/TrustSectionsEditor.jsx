import React, { useEffect, useState } from "react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Plus, Trash2, Copy, GripVertical, BookOpen, ChevronDown, ChevronUp, Save, Eye, EyeOff } from "lucide-react";
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
export default function TrustSectionsEditor({ caseId, initialSections = [], onSaved }) {
  const [sections, setSections] = useState(initialSections.length > 0 ? initialSections : []);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(initialSections.length === 0); // collapsed when already populated
  const [dirty, setDirty] = useState(false);
  const [previewOpen, setPreviewOpen] = useState({}); // { [idx]: bool }

  // Intentional: when parent loads a new case, hydrate the editor state.
  useEffect(() => {
    setSections(initialSections.length > 0 ? initialSections : []);
    setDirty(false);
  }, [initialSections]);

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
        title: src.title ? `${src.title} (copy)` : "",
        trust_html: src.trust_html || "",
        explainer_html: src.explainer_html || "",
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

  const save = async () => {
    setSaving(true);
    try {
      // Strip whitespace; allow empty rows to be filtered out if both blank
      const cleaned = sections
        .map((s) => ({
          title: (s.title || "").trim().slice(0, 160),
          trust_html: s.trust_html || "",
          explainer_html: s.explainer_html || "",
        }))
        .filter((s) => s.title || s.trust_html.trim() || s.explainer_html.trim());
      await api.put(`/admin/trust-cases/${caseId}/trust-sections`, { sections: cleaned });
      toast.success(`Saved — ${cleaned.length} article${cleaned.length === 1 ? "" : "s"}. Move the status to "Ready for Client Review" when ready.`);
      setDirty(false);
      onSaved && onSaved(cleaned);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-white border border-[#E2E0DA] rounded-xl mb-6" data-testid="trust-sections-editor">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-5 text-left"
        data-testid="trust-sections-toggle">
        <div className="flex items-center gap-3">
          <BookOpen className="h-5 w-5 text-bronze" />
          <div>
            <p className="font-serif text-lg text-navy">Trust Viewer Content</p>
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
            <div className="text-center py-8 text-sm text-[#64748B]">
              No articles yet. Click <b>Add article</b> below to start.
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
