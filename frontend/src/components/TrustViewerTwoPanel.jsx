import React, { useEffect, useMemo, useRef, useState } from "react";

/**
 * Two-panel trust viewer per the IGC prototype.
 *
 * Props:
 *  - sections: [{ title?, trust_html, explainer_html }] (variable count)
 *  - caseShortId: e.g. "33B4BFE5"
 *  - clientName, trustName: header context
 *
 * Behavior:
 *  - Left panel scrolls; right panel scroll-syncs to the matching section.
 *  - Click any left article → right scrolls to match + both highlight.
 *  - Right panel has NO independent scroll.
 *  - Ctrl/Cmd+P, Ctrl/Cmd+S, right-click are blocked.
 *  - "DRAFT — NOT FOR DISTRIBUTION" watermark tiles the left panel.
 *  - @media print blanks the page with a contact message.
 */
export default function TrustViewerTwoPanel({ sections = [], caseShortId, clientName, trustName }) {
  const leftRef = useRef(null);
  const rightRef = useRef(null);
  const syncingRef = useRef(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const ids = useMemo(() => sections.map((_, i) => i), [sections]);

  // ---- security: disable right-click, print, save ----
  useEffect(() => {
    const onCtx = (e) => e.preventDefault();
    const onKey = (e) => {
      const k = (e.key || "").toLowerCase();
      const meta = e.ctrlKey || e.metaKey;
      if (meta && (k === "p" || k === "s")) {
        e.preventDefault();
        if (k === "p") {
          alert(
            "Printing is not available until your trust is finalized and payment is confirmed.\n\nContact Iron Gate Consulting: wes@igcfirm.com or (954) 598-3681."
          );
        }
      }
    };
    document.addEventListener("contextmenu", onCtx);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("contextmenu", onCtx);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  // ---- scroll-sync: when left scrolls, right follows ----
  useEffect(() => {
    const left = leftRef.current;
    if (!left || !ids.length) return;
    const onScroll = () => {
      if (syncingRef.current) return;
      const viewTop = left.scrollTop + 80;
      let best = 0;
      let bestDist = Infinity;
      ids.forEach((n) => {
        const el = document.getElementById(`igc-trust-${n}`);
        if (!el) return;
        const dist = Math.abs(el.offsetTop - viewTop);
        if (dist < bestDist) { bestDist = dist; best = n; }
      });
      if (best !== activeIdx) {
        setActiveIdx(best);
        const x = document.getElementById(`igc-explain-${best}`);
        if (x && rightRef.current) {
          syncingRef.current = true;
          rightRef.current.scrollTo({ top: x.offsetTop - 20, behavior: "smooth" });
          setTimeout(() => { syncingRef.current = false; }, 700);
        }
      }
    };
    left.addEventListener("scroll", onScroll);
    return () => left.removeEventListener("scroll", onScroll);
  }, [ids, activeIdx]);

  const clickTo = (n) => {
    setActiveIdx(n);
    const t = document.getElementById(`igc-trust-${n}`);
    const x = document.getElementById(`igc-explain-${n}`);
    if (t && leftRef.current) {
      syncingRef.current = true;
      leftRef.current.scrollTo({ top: t.offsetTop - 20, behavior: "smooth" });
    }
    if (x && rightRef.current) {
      rightRef.current.scrollTo({ top: x.offsetTop - 20, behavior: "smooth" });
    }
    setTimeout(() => { syncingRef.current = false; }, 700);
  };

  if (!sections.length) {
    return (
      <div className="bg-white border border-[#E2E0DA] rounded-xl p-8 text-center text-[#64748B]">
        Your trust review content is being prepared. Please check back soon.
      </div>
    );
  }

  return (
    <div className="igc-viewer-shell" data-testid="trust-viewer-two-panel">
      <style>{styles}</style>

      {/* Header */}
      <header className="igc-vh">
        <div className="min-w-0">
          <div className="igc-vh-logo">IRON GATE CONSULTING</div>
          <div className="igc-vh-sub">
            {trustName || "Trust Document"}{caseShortId ? ` — Case #${caseShortId}` : ""} — Review Copy
          </div>
        </div>
        <div className="igc-vh-badge">⚠ Review Only — Not for Distribution</div>
      </header>

      <div className="igc-collabels">
        <div className="igc-collabel">📄 Trust Document</div>
        <div className="igc-collabel right">💡 Plain-English Explanation</div>
      </div>

      <div className="igc-panels">
        {/* LEFT */}
        <div ref={leftRef} className="igc-panel igc-panel-left" data-testid="trust-viewer-left">
          {sections.map((s, n) => (
            <div
              key={n}
              id={`igc-trust-${n}`}
              className={`igc-trust-section${activeIdx === n ? " active" : ""}`}
              onClick={() => clickTo(n)}
              data-testid={`trust-section-${n}`}>
              {s.title && (
                <h2 className="igc-trust-title"><span>{s.title}</span></h2>
              )}
              <div className="igc-trust-body" dangerouslySetInnerHTML={{ __html: s.trust_html || "" }} />
            </div>
          ))}
        </div>

        {/* RIGHT */}
        <div ref={rightRef} className="igc-panel igc-panel-right" data-testid="trust-viewer-right">
          {sections.map((s, n) => (
            <div
              key={n}
              id={`igc-explain-${n}`}
              className={`igc-explain-section${activeIdx === n ? " active" : ""}`}
              data-testid={`explain-section-${n}`}>
              {s.title && <div className="igc-explain-label">{s.title} — Plain English</div>}
              <div className="igc-explain-body" dangerouslySetInnerHTML={{ __html: s.explainer_html || "" }} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const styles = `
:root { --igc-gold:#C5A880; --igc-gold-light:#D8BC92; --igc-dark:#1C252E; --igc-cream:#FDF8EE; --igc-highlight:#fff8e1; }
.igc-viewer-shell { display:flex; flex-direction:column; height: calc(100vh - 56px); overflow:hidden; user-select:none; -webkit-user-select:none; font-family: Georgia, serif; color: var(--igc-dark); background:#e8e8e8; border-radius:12px; box-shadow: 0 8px 30px rgba(28,37,46,0.12); border:1px solid #E2E0DA; }
.igc-vh { background: var(--igc-dark); padding: 0 18px; height: 54px; display:flex; align-items:center; justify-content:space-between; gap:12px; border-bottom: 3px solid var(--igc-gold); border-top-left-radius:12px; border-top-right-radius:12px; }
.igc-vh-logo { font-size: 15px; font-weight: bold; color: var(--igc-gold-light); letter-spacing: 1px; }
.igc-vh-sub { font-size: 11px; color: #aaa; font-style: italic; }
.igc-vh-badge { background: #7B3F00; color: #FFD580; font-family: Arial, sans-serif; font-size: 10px; font-weight: bold; padding: 5px 12px; border-radius: 20px; letter-spacing: 1px; text-transform: uppercase; white-space: nowrap; }
.igc-collabels { display:grid; grid-template-columns: 1fr 1fr; background:#111827; border-bottom: 2px solid var(--igc-gold); }
.igc-collabel { padding: 6px 18px; font-family: Arial, sans-serif; font-size: 10px; font-weight: bold; letter-spacing: 1px; text-transform: uppercase; color: var(--igc-gold-light); }
.igc-collabel.right { border-left: 1px solid #2a2a3e; color: #bbb; }
.igc-panels { display:grid; grid-template-columns: 1fr 1fr; flex:1; overflow:hidden; }
.igc-panel { padding: 20px; position: relative; }
.igc-panel-left { overflow-y: auto; border-right: 2px solid var(--igc-gold); background-color:#f3f3f5; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='380' height='220'%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' transform='rotate(-30 190 110)' font-family='Arial' font-size='20' font-weight='bold' fill='rgba(197%2C168%2C128%2C0.18)' letter-spacing='3'%3EDRAFT — NOT FOR DISTRIBUTION%3C/text%3E%3C/svg%3E"); background-repeat: repeat; }
.igc-panel-right { overflow-y: auto; background: var(--igc-cream); }
.igc-trust-section { margin-bottom: 18px; padding: 14px 16px; background: rgba(255,255,255,0.95); border-left: 4px solid transparent; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.07); transition: border-color .25s, box-shadow .25s; cursor: pointer; }
.igc-trust-section.active { border-left-color: var(--igc-gold); box-shadow: 0 2px 10px rgba(197,168,128,0.28); }
.igc-trust-title { font-size: 12px; font-family: Arial, sans-serif; font-weight: bold; text-transform: uppercase; letter-spacing: .8px; color: var(--igc-dark); margin-bottom: 10px; padding-bottom: 7px; border-bottom: 1px solid #ddd; }
.igc-trust-title span { color: var(--igc-gold); }
.igc-trust-body { font-size: 12px; line-height: 1.78; color: #2a2a2a; }
.igc-trust-body p { margin-bottom: 7px; }
.igc-trust-body strong { color: var(--igc-dark); }
.igc-trust-body ul { margin: 6px 0 8px 20px; }
.igc-trust-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 11.5px; }
.igc-trust-body th { background: var(--igc-dark); color: var(--igc-gold-light); padding: 6px 10px; text-align: left; font-family: Arial, sans-serif; font-size: 11px; }
.igc-trust-body td { padding: 6px 10px; border-bottom: 1px solid #eee; color: #2a2a2a; }
.igc-explain-section { margin-bottom: 18px; padding: 14px 16px; background: #fff; border-left: 4px solid transparent; border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.06); transition: border-color .25s, background .25s, box-shadow .25s; }
.igc-explain-section.active { border-left-color: var(--igc-dark); background: var(--igc-highlight); box-shadow: 0 2px 10px rgba(28,37,46,0.12); }
.igc-explain-label { font-family: Arial, sans-serif; font-size: 10px; font-weight: bold; letter-spacing: 1.5px; text-transform: uppercase; color: var(--igc-gold); margin-bottom: 6px; }
.igc-explain-body { font-size: 13px; line-height: 1.82; color: #333; }
.igc-explain-body p { margin-bottom: 7px; }
.igc-explain-body h3 { font-size: 14px; color: var(--igc-dark); margin: 0 0 9px 0; }
.igc-explain-body .tip { margin-top: 9px; padding: 8px 12px; background: rgba(197,168,128,0.10); border-left: 3px solid var(--igc-gold); font-size: 12px; color: #555; font-style: italic; border-radius: 2px; }
@media (max-width: 768px) {
  .igc-panels { grid-template-columns: 1fr; }
  .igc-collabels { grid-template-columns: 1fr; }
  .igc-collabel.right { display: none; }
  .igc-viewer-shell { height: auto; }
  .igc-panel { overflow-y: visible !important; }
}
@media print {
  body::before { content: "This document cannot be printed until payment is confirmed. Contact Iron Gate Consulting: wes@igcfirm.com or (954) 598-3681."; display: block; font-family: Arial, sans-serif; font-size: 18px; color: #333; text-align: center; padding: 100px 40px; }
  body > * { display: none !important; }
  body::before { display: block !important; }
}
`;
