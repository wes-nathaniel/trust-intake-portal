/**
 * PaymentCard — shown in the client portal when a payment link has been sent.
 * Renders Stripe Embedded Checkout (debit card only, no Apple/Google Pay) OR
 * shows Zelle instructions with the case's reference number.
 *
 * The embedded checkout uses @stripe/react-stripe-js.
 */
import React, { useEffect, useState, useCallback } from "react";
import { loadStripe } from "@stripe/stripe-js";
import { EmbeddedCheckout, EmbeddedCheckoutProvider } from "@stripe/react-stripe-js";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { CreditCard, Smartphone, CheckCircle, AlertCircle, RefreshCw } from "lucide-react";

let _stripePromise = null;
function getStripe(pk) {
  if (!_stripePromise && pk) _stripePromise = loadStripe(pk);
  return _stripePromise;
}

function ZelleInstructions({ phone, caseRef }) {
  return (
    <div className="rounded-xl border border-[#E2E0DA] bg-[#F6F4F0] p-4 space-y-3" data-testid="zelle-instructions">
      <div className="flex items-center gap-2">
        <Smartphone className="h-5 w-5 text-[#4A90D9]" />
        <span className="font-semibold text-navy text-sm">Pay by Zelle</span>
      </div>
      <div className="text-sm text-navy space-y-2">
        <p>Open your bank app and send payment via Zelle to:</p>
        <div className="bg-white border border-[#E2E0DA] rounded-lg px-4 py-3 font-mono text-lg font-bold text-navy tracking-wide" data-testid="zelle-phone">
          {phone || "9545983681"}
        </div>
        <p>In the memo field, put your case number:</p>
        <div className="bg-white border border-[#E2E0DA] rounded-lg px-4 py-2 font-mono font-bold text-bronze text-base" data-testid="zelle-case-ref">
          {caseRef}
        </div>
        <p className="text-xs text-[#64748B]">
          After you send payment, your advisor will confirm receipt and reach out about next steps.
          You do not need to do anything else.
        </p>
      </div>
    </div>
  );
}

export default function PaymentCard({ caseId }) {
  const [session, setSession] = useState(null);   // { has_session, client_secret, amount_cents, already_paid, status }
  const [stripeConfig, setStripeConfig] = useState(null);  // { publishable_key }
  const [zelleConfig, setZelleConfig] = useState(null);    // { phone }
  const [tab, setTab] = useState("card");  // "card" | "zelle"
  const [loading, setLoading] = useState(true);
  const caseRef = `IGC-${(caseId || "").slice(0, 8).toUpperCase()}`;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sessRes, stripeRes, zelleRes] = await Promise.all([
        api.get(`/trust-cases/${caseId}/stripe/session`),
        api.get("/payments/stripe-config"),
        api.get("/payments/zelle-config"),
      ]);
      setSession(sessRes.data);
      setStripeConfig(stripeRes.data);
      setZelleConfig(zelleRes.data);
    } catch (e) {
      // If session endpoint fails it's fine — just show Zelle
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="text-sm text-[#64748B] py-6 text-center">Loading payment options…</div>;

  const paid = session?.already_paid || session?.status === "paid" || session?.status === "received_zelle";
  if (paid) {
    return (
      <div className="rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-5 flex items-center gap-3" data-testid="payment-paid-banner">
        <CheckCircle className="h-6 w-6 text-emerald-600 shrink-0" />
        <div>
          <p className="font-semibold text-emerald-900 text-sm">Payment received</p>
          <p className="text-xs text-emerald-800 mt-0.5">Your payment has been recorded. Your advisor will reach out about next steps.</p>
        </div>
      </div>
    );
  }

  const hasStripeSession = session?.has_session && session?.client_secret && stripeConfig?.publishable_key;
  const amountStr = session?.amount_cents
    ? `$${(session.amount_cents / 100).toLocaleString("en-US", { minimumFractionDigits: 2 })}`
    : null;

  return (
    <div className="space-y-4" data-testid="payment-card">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h3 className="font-serif text-lg text-navy">Payment</h3>
          {amountStr && <p className="text-sm text-[#64748B]">Amount due: <b className="text-navy">{amountStr}</b></p>}
        </div>
        <button type="button" onClick={load} className="text-xs text-[#64748B] flex items-center gap-1 min-h-[44px]" data-testid="payment-refresh-btn">
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
      </div>

      {/* Tab switcher */}
      <div className="flex border border-[#E2E0DA] rounded-lg overflow-hidden" role="tablist">
        {hasStripeSession && (
          <button type="button" role="tab" aria-selected={tab === "card"}
            onClick={() => setTab("card")}
            className={`flex-1 min-h-[48px] flex items-center justify-center gap-2 text-sm font-medium transition-colors ${tab === "card" ? "bg-navy text-white" : "bg-white text-navy hover:bg-[#F6F4F0]"}`}
            data-testid="tab-card">
            <CreditCard className="h-4 w-4" /> Pay by Debit Card
          </button>
        )}
        <button type="button" role="tab" aria-selected={tab === "zelle"}
          onClick={() => setTab("zelle")}
          className={`flex-1 min-h-[48px] flex items-center justify-center gap-2 text-sm font-medium transition-colors ${tab === "zelle" ? "bg-navy text-white" : "bg-white text-navy hover:bg-[#F6F4F0]"}`}
          data-testid="tab-zelle">
          <Smartphone className="h-4 w-4" /> Pay by Zelle
        </button>
      </div>

      {/* Stripe Embedded Checkout */}
      {tab === "card" && hasStripeSession && (
        <div data-testid="stripe-embedded-checkout">
          <p className="text-xs text-[#64748B] mb-3 flex items-center gap-1">
            <AlertCircle className="h-3.5 w-3.5" /> Debit cards only. Credit cards are not accepted.
          </p>
          <EmbeddedCheckoutProvider
            stripe={getStripe(stripeConfig.publishable_key)}
            options={{ clientSecret: session.client_secret }}>
            <EmbeddedCheckout />
          </EmbeddedCheckoutProvider>
        </div>
      )}

      {/* Zelle */}
      {tab === "zelle" && (
        <ZelleInstructions phone={zelleConfig?.phone} caseRef={caseRef} />
      )}

      {/* No Stripe session yet — show Zelle only */}
      {!hasStripeSession && tab === "card" && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-4 text-sm text-amber-900">
          Debit card payment link is not ready yet. Please use Zelle, or wait for your advisor to send a payment link.
        </div>
      )}
    </div>
  );
}
