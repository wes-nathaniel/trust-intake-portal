import React, { useEffect, useRef, useState } from "react";
import { Bold, Italic, Underline, List, ListOrdered, Heading2, Link2, Pilcrow, Quote, Undo, Redo, FileText, ChevronDown } from "lucide-react";

/**
 * Lightweight HTML-output WYSIWYG editor.
 * Uses contenteditable + document.execCommand. No external deps.
 *
 * Props:
 *  - value (string HTML), onChange (string HTML)
 *  - placeholder, rows (min visual rows ~ 8)
 *  - testId
 *  - templates: optional array of { key, title, trust_html, explain_html } for the
 *    "Insert template" dropdown. When present, the dropdown is rendered.
 *  - templateField: "trust_html" | "explain_html" — which field of each template to
 *    insert into THIS editor (defaults to "trust_html").
 */
export default function RichTextEditor({ value = "", onChange, placeholder = "Start typing…", rows = 8, testId, templates, templateField = "trust_html" }) {
  const ref = useRef(null);
  const [focused, setFocused] = useState(false);
  const [tplOpen, setTplOpen] = useState(false);
  const tplBtnRef = useRef(null);
  const savedRangeRef = useRef(null);

  // Sync external value → DOM (but only when actually different to keep cursor stable while typing)
  useEffect(() => {
    if (!ref.current) return;
    if (ref.current.innerHTML !== (value || "")) {
      ref.current.innerHTML = value || "";
    }
  }, [value]);

  const exec = (cmd, arg = null) => {
    ref.current?.focus();
    try { document.execCommand(cmd, false, arg); } catch (_) { /* noop */ }
    emit();
  };

  const wrapBlock = (tag) => {
    ref.current?.focus();
    // formatBlock requires angle brackets in some browsers, not in others
    try { document.execCommand("formatBlock", false, `<${tag}>`); } catch (_) {
      try { document.execCommand("formatBlock", false, tag); } catch (_) { /* noop */ }
    }
    emit();
  };

  const insertLink = () => {
    const url = window.prompt("Link URL (https://…)");
    if (!url) return;
    exec("createLink", url);
  };

  // Save the current selection range inside this editor so we can restore it
  // after the user clicks a toolbar element that steals focus (e.g. the
  // Templates dropdown button).
  const saveSelection = () => {
    const sel = window.getSelection && window.getSelection();
    if (!sel || sel.rangeCount === 0 || !ref.current) return;
    const range = sel.getRangeAt(0);
    if (ref.current.contains(range.commonAncestorContainer)) {
      savedRangeRef.current = range.cloneRange();
    }
  };

  const restoreSelection = () => {
    const r = savedRangeRef.current;
    if (!r || !ref.current) return;
    ref.current.focus();
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(r);
  };

  const insertTemplate = (tpl) => {
    if (!tpl) return;
    const html = (tpl[templateField] || "").trim();
    if (!html) { setTplOpen(false); return; }
    // If we have a saved range inside this editor, restore it; otherwise
    // place caret at end of editor.
    if (savedRangeRef.current) {
      restoreSelection();
    } else {
      ref.current?.focus();
      const sel = window.getSelection();
      sel.removeAllRanges();
      const r = document.createRange();
      r.selectNodeContents(ref.current);
      r.collapse(false);
      sel.addRange(r);
    }
    try {
      document.execCommand("insertHTML", false, html);
    } catch (_) {
      // Fallback: append to end
      if (ref.current) ref.current.insertAdjacentHTML("beforeend", html);
    }
    setTplOpen(false);
    savedRangeRef.current = null;
    emit();
  };

  // Close template dropdown on outside click
  useEffect(() => {
    if (!tplOpen) return;
    const onDocClick = (e) => {
      if (tplBtnRef.current && !tplBtnRef.current.contains(e.target)) {
        setTplOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [tplOpen]);

  const emit = () => {
    if (!ref.current) return;
    onChange && onChange(ref.current.innerHTML);
  };

  const onPaste = (e) => {
    // Paste as plain text to prevent rogue inline styles from Word/Pages
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData("text/plain");
    try { document.execCommand("insertText", false, text); } catch (_) {
      ref.current?.appendChild(document.createTextNode(text));
    }
    emit();
  };

  const onKeyDown = (e) => {
    // Tab inserts a tab character (not focus shift)
    if (e.key === "Tab") {
      e.preventDefault();
      try { document.execCommand("insertText", false, "    "); } catch (_) { /* noop */ }
    }
  };

  const Btn = ({ onClick, children, label, testId: tid }) => (
    <button
      type="button"
      onMouseDown={(e) => e.preventDefault()}
      onClick={onClick}
      className="p-1.5 rounded hover:bg-bronze/10 text-navy"
      title={label}
      aria-label={label}
      data-testid={tid}>
      {children}
    </button>
  );

  return (
    <div
      className={`rounded-md border bg-white transition-colors ${focused ? "border-bronze ring-1 ring-bronze/40" : "border-input"}`}
      data-testid={testId}>
      <div className="flex flex-wrap items-center gap-0.5 px-2 py-1 border-b border-[#E2E0DA] bg-sand-200/40 rounded-t-md">
        <Btn onClick={() => exec("bold")} label="Bold" testId={testId ? `${testId}-bold` : undefined}><Bold className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => exec("italic")} label="Italic" testId={testId ? `${testId}-italic` : undefined}><Italic className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => exec("underline")} label="Underline" testId={testId ? `${testId}-underline` : undefined}><Underline className="h-3.5 w-3.5" /></Btn>
        <div className="w-px h-4 bg-[#E2E0DA] mx-1" />
        <Btn onClick={() => wrapBlock("p")} label="Paragraph"><Pilcrow className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => wrapBlock("h3")} label="Subheading"><Heading2 className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => wrapBlock("blockquote")} label="Quote"><Quote className="h-3.5 w-3.5" /></Btn>
        <div className="w-px h-4 bg-[#E2E0DA] mx-1" />
        <Btn onClick={() => exec("insertUnorderedList")} label="Bulleted list"><List className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => exec("insertOrderedList")} label="Numbered list"><ListOrdered className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={insertLink} label="Insert link"><Link2 className="h-3.5 w-3.5" /></Btn>
        {templates && templates.length > 0 && (
          <div className="relative" ref={tplBtnRef}>
            <button
              type="button"
              onMouseDown={(e) => { e.preventDefault(); saveSelection(); }}
              onClick={() => setTplOpen((v) => !v)}
              className="px-2 py-1 rounded hover:bg-bronze/10 text-navy inline-flex items-center gap-1 text-xs"
              title="Insert boilerplate clause at cursor"
              aria-haspopup="menu"
              aria-expanded={tplOpen}
              data-testid={testId ? `${testId}-templates-btn` : "rte-templates-btn"}>
              <FileText className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Templates</span>
              <ChevronDown className="h-3 w-3" />
            </button>
            {tplOpen && (
              <div
                role="menu"
                className="absolute z-30 mt-1 left-0 w-64 bg-white border border-[#E2E0DA] rounded-md shadow-lg py-1"
                data-testid={testId ? `${testId}-templates-menu` : "rte-templates-menu"}>
                <div className="px-3 py-1.5 text-[10px] uppercase tracking-wide text-[#94A3B8] border-b border-[#F1EFEA]">
                  Insert boilerplate clause
                </div>
                {templates.map((tpl) => (
                  <button
                    key={tpl.key}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertTemplate(tpl)}
                    className="w-full text-left px-3 py-1.5 text-sm text-navy hover:bg-bronze/10"
                    role="menuitem"
                    data-testid={`${testId ? testId + '-' : 'rte-'}template-${tpl.key}`}>
                    {tpl.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <div className="flex-1" />
        <Btn onClick={() => exec("undo")} label="Undo"><Undo className="h-3.5 w-3.5" /></Btn>
        <Btn onClick={() => exec("redo")} label="Redo"><Redo className="h-3.5 w-3.5" /></Btn>
      </div>

      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        onInput={emit}
        onFocus={() => setFocused(true)}
        onBlur={() => { setFocused(false); saveSelection(); }}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        spellCheck
        className="rte-editor px-3 py-2 text-sm leading-relaxed outline-none prose-tight"
        style={{ minHeight: `${rows * 1.4}rem`, maxHeight: "60vh", overflowY: "auto" }}
        data-placeholder={placeholder}
      />

      {/* Minimal prose styles (kept inline so the component is portable) */}
      <style>{`
        .rte-editor[data-placeholder]:empty::before { content: attr(data-placeholder); color: #94A3B8; pointer-events: none; }
        .rte-editor p { margin: 0 0 6px 0; }
        .rte-editor h3 { font-family: Georgia, serif; font-size: 1.05rem; color: #1C252E; margin: 8px 0 4px 0; }
        .rte-editor ul, .rte-editor ol { padding-left: 1.4rem; margin: 6px 0; }
        .rte-editor li { margin: 2px 0; }
        .rte-editor blockquote { border-left: 3px solid #C5A880; padding: 4px 10px; color: #475569; font-style: italic; margin: 6px 0; }
        .rte-editor a { color: #1C252E; text-decoration: underline; }
        .rte-editor strong { font-weight: 600; }
        .rte-editor em { font-style: italic; }
        .rte-editor u { text-decoration: underline; }
      `}</style>
    </div>
  );
}
