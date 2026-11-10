import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Key, RefreshCw, Trash2, Copy, ExternalLink, ArrowLeft, Shield, AlertTriangle, CheckCircle } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function AdminMcpPage() {
  const [status, setStatus] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [newKey, setNewKey] = useState(null); // shown once after generation
  const [zellePhone, setZellePhone] = useState("");
  const [savingZelle, setSavingZelle] = useState(false);

  const load = async () => {
    try {
      const [mcpRes, zelleRes] = await Promise.all([
        api.get("/admin/mcp/status"),
        api.get("/admin/settings/zelle-phone"),
      ]);
      setStatus(mcpRes.data);
      setZellePhone(zelleRes.data.phone || "");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    }
  };

  useEffect(() => { load(); }, []);

  const generate = async () => {
    if (!window.confirm("This revokes any existing key and creates a new one. Claude will need to reconnect. Continue?")) return;
    setGenerating(true);
    setNewKey(null);
    try {
      const { data } = await api.post("/admin/mcp/generate-key");
      setNewKey(data);
      toast.success("New key generated. Copy it now — it will not be shown again.");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setGenerating(false);
    }
  };

  const revoke = async () => {
    if (!window.confirm("Revoke the current key? Claude will not be able to connect until a new key is generated.")) return;
    setRevoking(true);
    try {
      await api.delete("/admin/mcp/key");
      toast.success("Key revoked.");
      setNewKey(null);
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setRevoking(false);
    }
  };

  const copyKey = (val) => {
    navigator.clipboard?.writeText(val).then(() => toast.success("Copied!"));
  };

  const saveZelle = async () => {
    setSavingZelle(true);
    try {
      await api.patch("/admin/settings/zelle-phone", { phone: zellePhone });
      toast.success("Zelle number saved.");
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally {
      setSavingZelle(false);
    }
  };

  const mcpUrl = newKey?.mcp_url || (status?.has_key
    ? `${BACKEND_URL}/api/mcp/<your-key-here>`
    : null);

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to="/admin" className="text-[#64748B] hover:text-navy min-h-[44px] flex items-center" data-testid="back-btn">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="font-serif text-3xl text-navy">Claude Connection</h1>
            <p className="text-sm text-[#64748B]">MCP server key and admin settings</p>
          </div>
        </div>

        {/* Key status */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 space-y-4" data-testid="mcp-key-section">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2"><Key className="h-5 w-5" /> Connection Key</h2>

          <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${status?.has_key ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`} data-testid="mcp-key-status">
            {status?.has_key
              ? <><CheckCircle className="h-4 w-4" /> Key active — Claude can connect</>
              : <><AlertTriangle className="h-4 w-4" /> No active key — generate one below</>}
          </div>

          {status?.has_key && (
            <div className="text-xs text-[#64748B] space-y-1">
              <p>Key ID: <span className="font-mono">{status.key_id?.slice(0, 12)}…</span></p>
              <p>Created: {status.created_at ? new Date(status.created_at).toLocaleString() : "—"}</p>
              {status.pending_proposals > 0 && (
                <p className="text-amber-700 font-semibold">
                  {status.pending_proposals} proposal(s) waiting for your approval
                  {" "}<Link to="/admin/mcp/proposals" className="underline">Review now</Link>
                </p>
              )}
            </div>
          )}

          {/* New key reveal (shown once) */}
          {newKey && (
            <div className="border border-amber-300 bg-amber-50 rounded-xl p-4 space-y-3" data-testid="new-key-reveal">
              <p className="text-sm font-semibold text-amber-900 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" /> Copy this key now. It will not be shown again.
              </p>
              <div className="bg-white border border-amber-200 rounded-lg px-3 py-3 font-mono text-sm break-all" data-testid="new-key-value">
                {newKey.key}
              </div>
              <button type="button" onClick={() => copyKey(newKey.key)}
                className="btn-secondary min-h-[44px] flex items-center gap-2 text-sm" data-testid="copy-key-btn">
                <Copy className="h-4 w-4" /> Copy key
              </button>
              <div className="border-t border-amber-200 pt-3">
                <p className="text-xs text-amber-900 font-semibold mb-1">Your MCP server URL:</p>
                <div className="bg-white border border-amber-200 rounded-lg px-3 py-2 font-mono text-xs break-all" data-testid="mcp-url-value">
                  {newKey.mcp_url}
                </div>
                <button type="button" onClick={() => copyKey(newKey.mcp_url)}
                  className="mt-2 btn-secondary min-h-[44px] flex items-center gap-2 text-sm" data-testid="copy-url-btn">
                  <Copy className="h-4 w-4" /> Copy URL
                </button>
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-3 pt-1">
            <button type="button" onClick={generate} disabled={generating}
              className="btn-primary min-h-[48px] flex items-center gap-2 text-sm" data-testid="generate-key-btn">
              <RefreshCw className="h-4 w-4" />
              {status?.has_key ? (generating ? "Regenerating…" : "Regenerate key") : (generating ? "Generating…" : "Generate key")}
            </button>
            {status?.has_key && (
              <button type="button" onClick={revoke} disabled={revoking}
                className="btn-secondary min-h-[48px] flex items-center gap-2 text-sm text-red-600 border-red-200 hover:border-red-400"
                data-testid="revoke-key-btn">
                <Trash2 className="h-4 w-4" />
                {revoking ? "Revoking…" : "Revoke key"}
              </button>
            )}
          </div>
        </section>

        {/* Claude setup instructions */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 space-y-4" data-testid="claude-instructions">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2"><Shield className="h-5 w-5" /> How to Connect Claude</h2>

          <div className="space-y-4 text-sm text-navy">
            <div className="rounded-lg bg-[#F6F4F0] border border-[#E2E0DA] p-4 space-y-2">
              <p className="font-semibold">On Claude.ai (desktop or phone browser):</p>
              <ol className="list-decimal list-inside space-y-1.5 text-sm">
                <li>Go to <span className="font-mono text-xs">claude.ai</span> and log in.</li>
                <li>Tap your profile icon (top right), then <b>Integrations</b>.</li>
                <li>Tap <b>Add integration</b> or the <b>+</b> button.</li>
                <li>Name it: <span className="font-mono text-xs">IGC Trust Portal</span></li>
                <li>Paste the MCP server URL from above into the URL field.</li>
                <li>Tap <b>Save</b>. Claude will confirm the connection.</li>
              </ol>
            </div>

            <div className="rounded-lg bg-[#F6F4F0] border border-[#E2E0DA] p-4 space-y-2">
              <p className="font-semibold">On the Claude mobile app (iOS or Android):</p>
              <ol className="list-decimal list-inside space-y-1.5 text-sm">
                <li>Open the Claude app and tap the menu or your profile.</li>
                <li>Go to <b>Settings</b> then <b>Integrations</b>.</li>
                <li>Tap <b>Add custom integration</b>.</li>
                <li>Paste the same MCP server URL.</li>
                <li>Tap <b>Connect</b>.</li>
              </ol>
            </div>

            <div className="rounded-lg bg-blue-50 border border-blue-200 p-4 space-y-2">
              <p className="font-semibold text-blue-900">What Claude can do:</p>
              <ul className="list-disc list-inside space-y-1 text-blue-900">
                <li>Read case data and Schedule A</li>
                <li>Read intake summaries</li>
                <li>Propose field changes (you approve)</li>
                <li>Propose messages to clients (you approve and send)</li>
                <li>Propose admin notes (you approve)</li>
              </ul>
              <p className="font-semibold text-blue-900 mt-2">What Claude cannot do:</p>
              <ul className="list-disc list-inside space-y-1 text-blue-900">
                <li>Release to client or change client-visible status</li>
                <li>Send any email without your approval</li>
                <li>Touch payments, delete, or approve its own proposals</li>
              </ul>
            </div>

            <div className="rounded-lg bg-[#F6F4F0] border border-[#E2E0DA] p-4">
              <p className="font-semibold mb-1">About OAuth (future upgrade)</p>
              <p className="text-sm text-[#64748B]">
                OAuth would allow Claude to authenticate with a rotating token instead of a static key,
                and would support multiple authorized clients with separate permissions.
                That is planned as a future upgrade. For now, the static key is secure as long as
                you keep it private and revoke it if it is ever exposed.
              </p>
            </div>
          </div>
        </section>

        {/* Proposals quick link */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 flex items-center justify-between gap-4" data-testid="proposals-link-card">
          <div>
            <h2 className="font-serif text-xl text-navy">Claude Proposals</h2>
            <p className="text-sm text-[#64748B]">Review and approve changes Claude has suggested.</p>
            {status?.pending_proposals > 0 && (
              <p className="text-sm font-semibold text-amber-700 mt-1">{status.pending_proposals} pending</p>
            )}
          </div>
          <Link to="/admin/mcp/proposals"
            className="btn-primary min-h-[48px] flex items-center gap-2 text-sm shrink-0"
            data-testid="go-proposals-btn">
            <ExternalLink className="h-4 w-4" /> Open
          </Link>
        </section>

        {/* Zelle phone setting */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 space-y-4" data-testid="zelle-settings">
          <h2 className="font-serif text-xl text-navy">Zelle Phone Number</h2>
          <p className="text-sm text-[#64748B]">This number is shown to clients in the payment card when they choose Zelle.</p>
          <div className="flex gap-3 items-center">
            <input type="tel" value={zellePhone} onChange={e => setZellePhone(e.target.value)}
              placeholder="9545983681" className="rounded-lg border border-input bg-white px-3 py-2 text-sm flex-1 min-h-[44px]"
              data-testid="zelle-phone-input" />
            <button type="button" onClick={saveZelle} disabled={savingZelle}
              className="btn-primary min-h-[44px] text-sm" data-testid="save-zelle-btn">
              {savingZelle ? "Saving…" : "Save"}
            </button>
          </div>
        </section>
      </div>
    </Layout>
  );
}
