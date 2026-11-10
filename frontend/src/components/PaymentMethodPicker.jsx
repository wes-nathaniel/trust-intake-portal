import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { CreditCard, Smartphone, Send, X, Copy, Loader2, CheckCircle2, ShieldCheck, CheckCircle } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

const CASHAPP_URL = "https://cash.app/$WNate1971";

function fmtAmount(cents) {
  if (!cents && cents !== 0) return null;
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const PRODUCTS = [
  {
    lookup_key: "basic_living_trust",
    name: "Basic Living Trust",
    price_cents: 149700,
    tagline: "Complete living trust preparation",
  },
  {
    lookup_key: "private_trust",
    name: "Private Trust",
    price_cents: 249700,
    tagline: "Enhanced privacy + advanced structuring",
  },
];

/**
 * Payment method picker — Stripe (checkout redirect), Zelle (modal), Cash App (new tab).
 * After Stripe redirect returns, our /payment/success page polls status.
 * Zelle/CashApp still flow through the manual claim → admin verify path.
 *
 * Props:
 *  - caseId
 *  - payment { amount_cents, lookup_key, status }
 *  - onClaimed() callback
 *  - defaultLookupKey (optional) — pre-select the tier admin already picked
 */
export default function PaymentMethodPicker({ caseId, payment = {}, onClaimed, defaultLookupKey }) {
  const navigate = useNavigate();
  const [zelleOpen, setZelleOpen] = useState(false);
  const [zelleContact, setZelleContact] = useState("support@igchq.com");
  const [copiedContact, setCopiedContact] = useState(false);
  const [copiedRef, setCopiedRef] = useState(false);
  const [chosenMethod, setChosenMethod] = useState(null);
  const [claiming, setClaiming] = useState(false);
  const [stripeLoading, setStripeLoading] = useState(false);
  const [tier, setTier] = useState(defaultLookupKey || payment.lookup_key || PRODUCTS[0].lookup_key);

  useEffect(() => {
    if (payment.lookup_key) setTier(payment.lookup_key);
  }, [payment.lookup_key]);

  useEffect(() => {
    api.get("/payments/zelle-config").then(r => {
      if (r.data?.contact) setZelleContact(r.data.contact);
    }).catch(() => {});
  }, []);

  const caseRef = caseId ? `IGC-${caseId.slice(0, 8).toUpperCase()}` : "";

  const selectedProduct = PRODUCTS.find((p) => p.lookup_key === tier) || PRODUCTS[0];
  const amountCents = payment.amount_cents ?? selectedProduct.price_cents;
  const amountStr = fmtAmount(amountCents);

  const status = payment.status;
  const isPending = status === "pending_verification";
  const isVerified = status === "verified" || status === "paid" || status === "paid_manual";

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch (_) {
      toast.error("Could not copy. Long-press to copy.");
    }
  };

  const startStripe = async () => {
    setStripeLoading(true);
    try {
      const { data } = await api.post(`/trust-cases/${caseId}/stripe/checkout`, {
        lookup_key: tier,
        origin_url: window.location.origin,
      });
      // Redirect immediately
      window.location.href = data.checkout_url;
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
      setStripeLoading(false);
    }
  };

  const pickZelle = () => { setChosenMethod("zelle"); setZelleOpen(true); };
  const pickCashApp = () => {
    setChosenMethod("cashapp");
    window.open(CASHAPP_URL, "_blank", "noopener,noreferrer");
  };

  const claimPayment = async () => {
    setClaiming(true);
    try {
      await api.post(`/trust-cases/${caseId}/payment-claimed`, { method: chosenMethod || "other" });
      toast.success("Thank you — your payment is now pending verification.");
      onClaimed?.();
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail));
    } finally { setClaiming(false); }
  };

  // ----- States -----
  if (isVerified) {
    return (
      <div className="rounded-xl bg-green-50 border-2 border-green-300 p-6 text-center" data-testid="payment-verified-block">
        <CheckCircle2 className="h-10 w-10 text-green-700 mx-auto mb-2" />
        <p className="font-serif text-2xl text-navy mb-1">Payment verified</p>
        <p className="text-sm text-[#334155]">Thank you. Your final trust will be unlocked shortly.</p>
      </div>
    );
  }
  if (isPending) {
    return (
      <div className="rounded-xl bg-amber-50 border-2 border-amber-300 p-6 text-center" data-testid="payment-pending-verification-block">
        <Loader2 className="h-10 w-10 text-amber-800 mx-auto mb-2 animate-spin" />
        <p className="font-serif text-2xl text-navy mb-1">Payment pending verification</p>
        <p className="text-sm text-[#334155] max-w-md mx-auto">
          Thank you, your payment has been received. Your application is now pending verification.
          You will receive another email once your payment has been fully verified and your next steps are ready.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="payment-method-picker">
      <h3 className="font-serif text-3xl text-navy mb-1 text-center">Choose Your Trust Package</h3>
      <p className="text-sm text-[#64748B] text-center max-w-2xl mx-auto mb-6">
        Select the trust that best fits your family, then pick a payment method below.
      </p>

      {/* Tier selection */}
      <div className="grid gap-3 sm:grid-cols-2 mb-6">
        {PRODUCTS.map((p) => (
          <button
            key={p.lookup_key}
            onClick={() => setTier(p.lookup_key)}
            className={`rounded-xl border-2 bg-white p-5 text-left transition-all min-h-[140px] flex flex-col justify-between ${
              tier === p.lookup_key ? "border-bronze ring-2 ring-bronze/30 bg-bronze/5" : "border-[#E2E0DA] hover:border-bronze"
            }`}
            data-testid={`tier-${p.lookup_key}`}>
            <div>
              <p className="text-xs uppercase tracking-wide text-bronze font-semibold">{p.name}</p>
              <p className="font-serif text-3xl text-navy mt-2">{fmtAmount(p.price_cents)}</p>
              <p className="text-xs text-[#64748B] mt-1">{p.tagline}</p>
            </div>
            {tier === p.lookup_key && (
              <div className="mt-3 inline-flex items-center gap-1 text-xs text-bronze font-semibold">
                <CheckCircle2 className="h-4 w-4" /> Selected
              </div>
            )}
          </button>
        ))}
      </div>

      <p className="text-center mb-6">
        <span className="inline-block px-4 py-2 rounded-full bg-bronze/15 text-navy text-sm">
          Amount due: <b className="text-lg" data-testid="amount-due">{amountStr}</b>
        </span>
      </p>

      {/* Stripe — primary CTA */}
      <button
        onClick={startStripe}
        disabled={stripeLoading}
        className="w-full mb-4 py-5 rounded-xl text-white text-lg sm:text-xl font-bold shadow-lg transition-all active:scale-[0.99] disabled:opacity-50"
        style={{ backgroundColor: "#635BFF", minHeight: 64 }}
        data-testid="pay-with-stripe-btn">
        {stripeLoading ? (
          <span className="inline-flex items-center gap-2"><Loader2 className="h-5 w-5 animate-spin" /> Opening secure checkout…</span>
        ) : (
          <span className="inline-flex items-center gap-2"><CreditCard className="h-5 w-5" /> Pay with Card — {amountStr}</span>
        )}
      </button>
      <p className="mb-6 text-center text-[11px] text-[#64748B] flex items-center justify-center gap-1">
        <ShieldCheck className="h-3 w-3" /> Secured by Stripe · Card, Apple Pay & Google Pay accepted
      </p>

      <div className="flex items-center gap-3 my-5">
        <div className="h-px flex-1 bg-[#E2E0DA]" />
        <span className="text-xs uppercase tracking-wide text-[#64748B]">or send directly</span>
        <div className="h-px flex-1 bg-[#E2E0DA]" />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 mb-6">
        <button
          onClick={pickZelle}
          className="rounded-xl border-2 border-[#6f00ff]/30 hover:border-[#6f00ff] bg-white p-5 text-left transition-all active:scale-[0.99] min-h-[120px] flex flex-col justify-between"
          data-testid="pay-method-zelle">
          <div className="flex items-center gap-2 text-[#6f00ff] font-bold">
            <Send className="h-5 w-5" />
            <span>Zelle</span>
          </div>
          <div>
            <p className="font-serif text-xl text-navy">Pay with Zelle</p>
            <p className="text-xs text-[#64748B] mt-1">Tap to view send-to details</p>
          </div>
        </button>

        <button
          onClick={pickCashApp}
          className="rounded-xl border-2 border-green-500/40 hover:border-green-600 bg-white p-5 text-left transition-all active:scale-[0.99] min-h-[120px] flex flex-col justify-between"
          data-testid="pay-method-cashapp">
          <div className="flex items-center gap-2 text-green-700 font-bold">
            <Smartphone className="h-5 w-5" />
            <span>Cash App</span>
          </div>
          <div>
            <p className="font-serif text-xl text-navy">Pay with Cash App</p>
            <p className="text-xs text-[#64748B] mt-1">Opens cash.app in a new tab</p>
          </div>
        </button>
      </div>

      {/* Manual claim (only relevant for Zelle/CashApp) */}
      {chosenMethod && chosenMethod !== "stripe" && (
        <button
          onClick={claimPayment}
          disabled={claiming}
          className="w-full py-4 rounded-xl text-white text-lg font-bold shadow-lg transition-all active:scale-[0.99] disabled:opacity-50"
          style={{ backgroundColor: "#28a745", minHeight: 56 }}
          data-testid="i-made-payment-btn">
          {claiming ? "Submitting…" : "✓  I Made My Payment (Zelle / Cash App)"}
        </button>
      )}

      {zelleOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4"
          onClick={() => setZelleOpen(false)}
          data-testid="zelle-modal">
          <div className="bg-white rounded-xl p-6 max-w-md w-full space-y-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between">
              <p className="font-serif text-2xl text-navy">Pay with Zelle</p>
              <button onClick={() => setZelleOpen(false)} className="text-[#64748B] hover:text-navy min-h-[44px] min-w-[44px] flex items-center justify-center" aria-label="Close" data-testid="zelle-close-btn">
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Send-to */}
            <div>
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Send your Zelle payment to:</p>
              <div className="flex items-center gap-3 bg-[#F6F4F0] rounded-xl border border-[#E2E0DA] px-4 py-4">
                <span className="font-mono text-lg font-bold text-navy flex-1 break-all" data-testid="zelle-contact">{zelleContact}</span>
                <button
                  onClick={async () => {
                    try { await navigator.clipboard.writeText(zelleContact); setCopiedContact(true); setTimeout(() => setCopiedContact(false), 2000); }
                    catch (_) { toast.error("Could not copy. Long-press to copy manually."); }
                  }}
                  className="shrink-0 min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg bg-navy text-white active:scale-95 transition-transform"
                  data-testid="zelle-copy-contact" aria-label="Copy email">
                  {copiedContact ? <CheckCircle className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
                </button>
              </div>
            </div>

            {/* Case reference */}
            {caseRef && (
              <div>
                <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-2">Put this in the memo or note:</p>
                <div className="flex items-center gap-3 bg-[#F6F4F0] rounded-xl border-2 border-bronze/40 px-4 py-4">
                  <span className="font-mono text-lg font-bold text-bronze flex-1" data-testid="zelle-case-ref">{caseRef}</span>
                  <button
                    onClick={async () => {
                      try { await navigator.clipboard.writeText(caseRef); setCopiedRef(true); setTimeout(() => setCopiedRef(false), 2000); }
                      catch (_) { toast.error("Could not copy. Long-press to copy manually."); }
                    }}
                    className="shrink-0 min-h-[48px] min-w-[48px] flex items-center justify-center rounded-lg bg-bronze text-white active:scale-95 transition-transform"
                    data-testid="zelle-copy-ref" aria-label="Copy case number">
                    {copiedRef ? <CheckCircle className="h-5 w-5" /> : <Copy className="h-5 w-5" />}
                  </button>
                </div>
              </div>
            )}

            {/* Amount */}
            <div className="rounded-lg border border-[#E2E0DA] bg-[#F6F4F0] px-4 py-3">
              <p className="text-[10px] uppercase text-[#64748B] font-bold tracking-wide mb-1">Amount</p>
              <p className="text-2xl font-bold text-navy font-mono" data-testid="zelle-amount">{amountStr}</p>
            </div>

            {/* Steps */}
            <div className="bg-[#F6F4F0] rounded-xl border border-[#E2E0DA] px-4 py-4">
              <p className="text-xs uppercase tracking-wide text-[#64748B] font-semibold mb-3">How to send it:</p>
              <ol className="space-y-1.5 text-sm text-navy list-none">
                <li>1. Open your bank app.</li>
                <li>2. Choose Send money with Zelle.</li>
                <li>3. Enter the email above.</li>
                <li>4. Type the case number in the note.</li>
                <li>5. Send it.</li>
              </ol>
            </div>

            <button onClick={() => setZelleOpen(false)} className="w-full py-3 rounded-xl bg-navy text-white font-semibold min-h-[48px]" data-testid="zelle-done-btn">
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
