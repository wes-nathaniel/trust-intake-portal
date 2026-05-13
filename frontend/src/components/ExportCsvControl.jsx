import React, { useState } from "react";
import { Download, ChevronDown, X } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

const presets = [
  { key: "all",    label: "All time",          range: () => ({ since: "", until: "" }) },
  { key: "7d",     label: "Last 7 days",       range: () => ({ since: ymdOffset(-7),  until: "" }) },
  { key: "30d",    label: "Last 30 days",      range: () => ({ since: ymdOffset(-30), until: "" }) },
  { key: "mtd",    label: "Month to date",     range: () => ({ since: ymdMonthStart(), until: "" }) },
  { key: "lastmo", label: "Previous month",    range: () => {
    const d = new Date();
    const start = new Date(d.getFullYear(), d.getMonth() - 1, 1);
    const end = new Date(d.getFullYear(), d.getMonth(), 0);
    return { since: ymd(start), until: ymd(end) };
  } },
  { key: "ytd",    label: "Year to date",      range: () => ({ since: `${new Date().getFullYear()}-01-01`, until: "" }) },
];

function ymd(d) { return d.toISOString().slice(0, 10); }
function ymdOffset(days) { const d = new Date(); d.setDate(d.getDate() + days); return ymd(d); }
function ymdMonthStart() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`; }

export default function ExportCsvControl() {
  const [open, setOpen] = useState(false);
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [downloading, setDownloading] = useState(false);

  const applyPreset = (p) => {
    const { since: s, until: u } = p.range();
    setSince(s); setUntil(u);
  };

  const doDownload = async () => {
    setDownloading(true);
    try {
      const params = new URLSearchParams();
      if (since) params.set("since", since);
      if (until) params.set("until", until);
      const qs = params.toString() ? `?${params.toString()}` : "";
      const res = await api.get(`/admin/trust-cases.csv${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      const today = new Date().toISOString().slice(0, 10).replace(/-/g, "");
      const suffix = (since || until) ? `_${since || "start"}_to_${until || "now"}` : "";
      a.href = url; a.download = `trust-cases-${today}${suffix}.csv`; a.click();
      URL.revokeObjectURL(url);
      setOpen(false);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setDownloading(false); }
  };

  return (
    <div className="relative" data-testid="export-csv-control">
      <button onClick={() => setOpen((v) => !v)} className="btn-secondary" data-testid="admin-export-csv-btn">
        <Download className="h-4 w-4 inline mr-1" /> Export CSV <ChevronDown className={`h-3 w-3 inline ml-1 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div className="absolute right-0 mt-2 w-80 bg-white border border-[#E2E0DA] rounded-xl shadow-lg z-40 p-4" data-testid="export-csv-popover">
            <div className="flex items-center justify-between mb-3">
              <p className="font-serif text-lg text-navy">Export cases</p>
              <button onClick={() => setOpen(false)} className="text-[#94A3B8] hover:text-navy" aria-label="Close" data-testid="export-csv-close">
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-[10px] uppercase tracking-wide text-[#64748B] font-semibold mb-2">Quick range</p>
            <div className="grid grid-cols-2 gap-1.5 mb-4">
              {presets.map((p) => (
                <button
                  key={p.key}
                  onClick={() => applyPreset(p)}
                  className="text-xs px-2.5 py-1.5 rounded-md border border-[#E2E0DA] hover:border-bronze hover:bg-bronze/5 text-navy text-left"
                  data-testid={`export-preset-${p.key}`}>
                  {p.label}
                </button>
              ))}
            </div>

            <p className="text-[10px] uppercase tracking-wide text-[#64748B] font-semibold mb-2">Custom range (optional)</p>
            <div className="grid grid-cols-2 gap-2 mb-4">
              <label className="block">
                <span className="text-xs text-[#64748B]">From</span>
                <input
                  type="date"
                  value={since}
                  onChange={(e) => setSince(e.target.value)}
                  className="mt-1 w-full rounded-md border border-input bg-white px-2 py-1.5 text-sm"
                  data-testid="export-csv-since-input"
                />
              </label>
              <label className="block">
                <span className="text-xs text-[#64748B]">To</span>
                <input
                  type="date"
                  value={until}
                  onChange={(e) => setUntil(e.target.value)}
                  className="mt-1 w-full rounded-md border border-input bg-white px-2 py-1.5 text-sm"
                  data-testid="export-csv-until-input"
                />
              </label>
            </div>
            <p className="text-[11px] text-[#94A3B8] mb-3">Filters by case <i>updated</i> date. Leave both blank to export everything.</p>

            <button
              onClick={doDownload}
              disabled={downloading}
              className="btn-primary w-full text-sm"
              data-testid="export-csv-download-btn">
              {downloading ? "Preparing…" : "Download CSV"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
