import React, { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { Key, RefreshCw, Trash2, Copy, ExternalLink, ArrowLeft, Shield, AlertTriangle, CheckCircle, LogIn, Zap } from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function AdminMcpPage() {
  const [status, setStatus] = useState(null);
  const [generating, setGenerating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [newKey, setNewKey] = useState(null);
  const [zellePhone, setZellePhone] = useState("");
  const [savingZelle, setSavingZelle] = useState(false);
  const [oauthTokens, setOauthTokens] = useState([]);
  const [revokingToken, setRevokingToken] = useState(null);

  const load = async () => {
    try {
      const [mcpRes, zelleRes, tokensRes] = await Promise.all([
        api.get("/admin/mcp/status"),
        api.get("/admin/settings/zelle-phone"),
        api.get("/admin/mcp/oauth-tokens"),
      ]);
      setStatus(mcpRes.data);
      setZellePhone(zelleRes.data.phone || "");
      setOauthTokens(tokensRes.data.tokens || []);
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
      toast.success("New key generated. Copy it now.");
      load();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setGenerating(false); }
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
    } finally { setRevoking(false); }
  };

  const revokeOAuthToken = async (jti) => {
    setRevokingToken(jti);
    try {
      await api.delete(`/admin/mcp/oauth-tokens/${jti}`);
      toast.success("OAuth token revoked.");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setRevokingToken(null); }
  };

  const revokeAllOAuth = async () => {
    if (!window.confirm("Revoke ALL active OAuth tokens? Claude will need to re-authorize.")) return;
    try {
      const { data } = await api.delete("/admin/mcp/oauth-tokens");
      toast.success(`Revoked ${data.revoked} token(s).`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const copy = (val) => navigator.clipboard?.writeText(val).then(() => toast.success("Copied!"));
  const saveZelle = async () => {
    setSavingZelle(true);
    try {
      await api.patch("/admin/settings/zelle-phone", { phone: zellePhone });
      toast.success("Zelle number saved.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSavingZelle(false); }
  };

  const oauthUrl = `${BACKEND_URL}/api/mcp`;
  const mcpUrl = newKey?.mcp_url || null;

  return (
    <Layout>
      <div className="max-w-2xl mx-auto space-y-6">
        <div className="flex items-center gap-3">
          <Link to="/admin" className="text-[#64748B] hover:text-navy min-h-[44px] flex items-center" data-testid="back-btn">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <h1 className="font-serif text-3xl text-navy">Claude Connection</h1>
            <p className="text-sm text-[#64748B]">MCP server and admin settings</p>
          </div>
        </div>

        {/* OAuth method (recommended) */}
        <section className="bg-white border border-emerald-300 rounded-xl p-6 space-y-4" data-testid="mcp-oauth-section">
          <div className="flex items-center gap-2">
            <Shield className="h-5 w-5 text-emerald-700" />
            <h2 className="font-serif text-xl text-navy">OAuth Connection <span className="text-xs font-sans bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full ml-1">Recommended</span></h2>
          </div>
          <p className="text-sm text-[#64748B]">Claude connects with a short-lived token (30 days). You authorize it once and can revoke it from your phone anytime. No static secret in the URL.</p>

          <div className="rounded-lg bg-[#F6F4F0] border border-[#E2E0DA] p-3 space-y-2">
            <p className="text-xs font-semibold text-navy">OAuth MCP URL — paste this into Claude:</p>
            <div className="font-mono text-xs break-all bg-white border border-[#E2E0DA] rounded px-3 py-2" data-testid="oauth-url">{oauthUrl}</div>
            <button type="button" onClick={() => copy(oauthUrl)} className="btn-secondary min-h-[44px] flex items-center gap-2 text-sm" data-testid="copy-oauth-url-btn">
              <Copy className="h-4 w-4" /> Copy OAuth URL
            </button>
          </div>

          <div className="rounded-lg bg-[#F6F4F0] border border-[#E2E0DA] p-4 space-y-2">
            <p className="font-semibold text-sm">How to connect via OAuth (phone or desktop):</p>
            <ol className="list-decimal list-inside space-y-1.5 text-sm">
              <li>Go to <b>claude.ai</b> and log in.</li>
              <li>Tap your profile icon then <b>Integrations</b> then <b>Add integration</b>.</li>
              <li>Name it <b>IGC Trust Portal</b>. Paste the OAuth URL above.</li>
              <li>Claude will show "Authorization required" and open this page.</li>
              <li>Sign in with your admin password and tap <b>Authorize Claude</b>.</li>
              <li>Claude confirms the connection. Done.</li>
            </ol>
          </div>

          {/* Active OAuth tokens */}
          <div data-testid="oauth-tokens-list">
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-semibold text-navy">Active OAuth tokens ({oauthTokens.length})</p>
              {oauthTokens.length > 0 && (
                <button type="button" onClick={revokeAllOAuth}
                  className="text-xs text-red-600 border border-red-200 rounded-lg px-3 py-1.5 min-h-[36px] hover:bg-red-50"
                  data-testid="revoke-all-oauth-btn">
                  Revoke all
                </button>
              )}
            </div>
            {oauthTokens.length === 0 ? (
              <p className="text-sm text-[#94A3B8]">No active OAuth tokens. Authorize Claude to create one.</p>
            ) : (
              <div className="space-y-2">
                {oauthTokens.map((t) => (
                  <div key={t.jti} className="flex items-center justify-between gap-3 border border-[#E2E0DA] rounded-lg p-3 text-sm" data-testid={`oauth-token-${t.jti}`}>
                    <div className="min-w-0">
                      <p className="font-mono text-xs text-[#64748B] truncate">ID: {t.jti?.slice(0, 12)}…</p>
                      <p className="text-xs text-[#64748B]">Expires: {t.expires_at ? new Date(t.expires_at).toLocaleDateString() : "—"}</p>
                      {t.last_used_at && <p className="text-xs text-emerald-700">Last used: {new Date(t.last_used_at).toLocaleString()}</p>}
                    </div>
                    <button type="button" onClick={() => revokeOAuthToken(t.jti)} disabled={revokingToken === t.jti}
                      className="shrink-0 text-xs text-red-600 border border-red-200 rounded-lg px-3 py-1.5 min-h-[36px] hover:bg-red-50 disabled:opacity-50"
                      data-testid={`revoke-token-${t.jti}`}>
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* Legacy URL key */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 space-y-4" data-testid="mcp-key-section">
          <div className="flex items-center gap-2">
            <Key className="h-5 w-5 text-[#64748B]" />
            <h2 className="font-serif text-xl text-navy">URL Key <span className="text-xs font-sans bg-[#F6F4F0] text-[#64748B] px-2 py-0.5 rounded-full ml-1">Legacy</span></h2>
          </div>
          <p className="text-sm text-[#64748B]">Static key embedded in the URL. Use only if the OAuth method does not work with your Claude plan.</p>

          <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg ${status?.has_key ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`} data-testid="mcp-key-status">
            {status?.has_key
              ? <><CheckCircle className="h-4 w-4" /> Key active</>
              : <><AlertTriangle className="h-4 w-4" /> No active key</>}
          </div>

          {status?.has_key && (
            <div className="text-xs text-[#64748B] space-y-1">
              <p>Key ID: <span className="font-mono">{status.key_id?.slice(0, 12)}…</span></p>
              <p>Created: {status.created_at ? new Date(status.created_at).toLocaleString() : "—"}</p>
              {status.pending_proposals > 0 && (
                <p className="text-amber-700 font-semibold">
                  {status.pending_proposals} proposal(s) waiting — <Link to="/admin/mcp/proposals" className="underline">Review now</Link>
                </p>
              )}
            </div>
          )}

          {newKey && (
            <div className="border border-amber-300 bg-amber-50 rounded-xl p-4 space-y-3" data-testid="new-key-reveal">
              <p className="text-sm font-semibold text-amber-900 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Copy this key now. It will not be shown again.</p>
              <div className="bg-white border border-amber-200 rounded-lg px-3 py-3 font-mono text-sm break-all" data-testid="new-key-value">{newKey.key}</div>
              <button type="button" onClick={() => copy(newKey.key)} className="btn-secondary min-h-[44px] flex items-center gap-2 text-sm" data-testid="copy-key-btn">
                <Copy className="h-4 w-4" /> Copy key
              </button>
              {mcpUrl && (
                <div className="border-t border-amber-200 pt-3">
                  <p className="text-xs text-amber-900 font-semibold mb-1">Legacy MCP URL (key embedded):</p>
                  <div className="bg-white border border-amber-200 rounded-lg px-3 py-2 font-mono text-xs break-all" data-testid="mcp-url-value">{mcpUrl}</div>
                  <button type="button" onClick={() => copy(mcpUrl)} className="mt-2 btn-secondary min-h-[44px] flex items-center gap-2 text-sm" data-testid="copy-url-btn">
                    <Copy className="h-4 w-4" /> Copy legacy URL
                  </button>
                </div>
              )}
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
                <Trash2 className="h-4 w-4" /> {revoking ? "Revoking…" : "Revoke key"}
              </button>
            )}
          </div>
        </section>

        {/* What Claude can/cannot do */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 space-y-3" data-testid="claude-permissions">
          <h2 className="font-serif text-xl text-navy flex items-center gap-2"><Zap className="h-5 w-5" /> What Claude can do</h2>
          <div className="grid sm:grid-cols-2 gap-3 text-sm">
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4">
              <p className="font-semibold text-emerald-900 mb-2">Claude can:</p>
              <ul className="space-y-1 text-emerald-900 list-disc list-inside">
                <li>Read case data and Schedule A</li>
                <li>Read intake summaries</li>
                <li>Propose field changes (you approve)</li>
                <li>Propose messages to clients (you approve)</li>
                <li>Propose admin notes (you approve)</li>
              </ul>
            </div>
            <div className="rounded-lg bg-red-50 border border-red-200 p-4">
              <p className="font-semibold text-red-900 mb-2">Claude cannot:</p>
              <ul className="space-y-1 text-red-900 list-disc list-inside">
                <li>Release to client or change status</li>
                <li>Send email without your approval</li>
                <li>Touch payments or delete data</li>
                <li>Approve its own proposals</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Proposals quick link */}
        <section className="bg-white border border-[#E2E0DA] rounded-xl p-6 flex items-center justify-between gap-4" data-testid="proposals-link-card">
          <div>
            <h2 className="font-serif text-xl text-navy">Claude Proposals</h2>
            <p className="text-sm text-[#64748B]">Review and approve changes Claude has suggested.</p>
            {status?.pending_proposals > 0 && <p className="text-sm font-semibold text-amber-700 mt-1">{status.pending_proposals} pending</p>}
          </div>
          <Link to="/admin/mcp/proposals" className="btn-primary min-h-[48px] flex items-center gap-2 text-sm shrink-0" data-testid="go-proposals-btn">
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
