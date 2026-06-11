import React, { useEffect, useRef, useState } from "react";
import { Bold, Italic, Underline, List, ListOrdered, Heading2, Link2, Pilcrow, Quote, Undo, Redo } from "lucide-react";

/**
 * Lightweight HTML-output WYSIWYG editor.
 * Uses contenteditable + document.execCommand. No external deps.
 *
 * Props:
 *  - value (string HTML), onChange (string HTML)
 *  - placeholder, rows (min visual rows ~ 8)
 *  - testId
 */
export default function RichTextEditor({ value = "", onChange, placeholder = "Start typing…", rows = 8, testId }) {
  const ref = useRef(null);
  const [focused, setFocused] = useState(false);

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
        onBlur={() => setFocused(false)}
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
