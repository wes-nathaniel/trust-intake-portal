import React, { useState } from "react";
import { CreditCard, Smartphone, Send, X, Copy, ExternalLink, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api, { formatApiError } from "@/lib/api";

const ZELLE = {
  phone: "954-598-3681",
  name: "Wesley Nathaniel",
};
const CASHAPP_URL = "https://cash.app/$WNate1971";

function fmtAmount(cents) {
  if (!cents) return null;
  return `$${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Payment method picker — Zelle (modal w/ instructions), Cash App (new tab), Square (existing public_url).
 * Then "I Made My Payment" button → POST /trust-cases/{id}/payment-claimed.
 *
 * Props:
 *  - caseId, payment {amount_cents, public_url, status, claimed}
 *  - onClaimed() callback after successful claim (parent reload)
 */
export default function PaymentMethodPicker({ caseId, payment = {}, onClaimed }) {
  const [zelleOpen, setZelleOpen] = useState(false);
  const [chosenMethod, setChosenMethod] = useState(null);
  const [claiming, setClaiming] = useState(false);

  const amountCents = payment.amount_cents;
  const amountStr = fmtAmount(amountCents);

  const status = payment.status;
  const isPending = status === "pending_verification";
  const isVerified = status === "verified" || status === "paid" || status === "paid_manual";

  const copy = async (text, label) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(`${label} copied`);
    } catch (e) {
      toast.error("Could not copy. Long-press to copy.");
    }
  };

  const pickZelle = () => { setChosenMethod("zelle"); setZelleOpen(true); };
  const pickCashApp = () => {
    setChosenMethod("cashapp");
    window.open(CASHAPP_URL, "_blank", "noopener,noreferrer");
  };
  const pickSquare = () => {
    if (!payment.public_url) { toast.error("Square invoice link not ready yet."); return; }
    setChosenMethod("square");
    window.open(payment.public_url, "_blank", "noopener,noreferrer");
  };

  const claimPayment = async () => {
    setClaiming(true);
    try {
      await api.post(`/trust-cases/${caseId}/payment-claimed`, {
        method: chosenMethod || "other",
      });
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

  if (!amountCents) {
    return (
      <div className="rounded-xl bg-white border border-[#E2E0DA] p-6 text-center" data-testid="payment-awaiting-amount-block">
        <p className="font-serif text-xl text-navy mb-1">Your agent is preparing your invoice</p>
        <p className="text-sm text-[#64748B]">
          Once the amount is set, you'll see your payment options here.
        </p>
      </div>
    );
  }

  return (
    <div data-testid="payment-method-picker">
      <h3 className="font-serif text-3xl text-navy mb-1 text-center">Choose Your Payment Method</h3>
      <p className="text-sm text-[#64748B] text-center max-w-2xl mx-auto mb-6">
        Select your preferred payment method below. Complete your payment, then click <b>"I Made My Payment"</b> to notify us.
      </p>
      <p className="text-center mb-6">
        <span className="inline-block px-4 py-2 rounded-full bg-bronze/15 text-navy text-sm">
          Amount due: <b className="text-lg">{amountStr}</b>
        </span>
      </p>

      <div className="grid gap-3 sm:grid-cols-3 mb-6">
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

        <button
          onClick={pickSquare}
          disabled={!payment.public_url}
          className={`rounded-xl border-2 bg-white p-5 text-left transition-all active:scale-[0.99] min-h-[120px] flex flex-col justify-between ${
            payment.public_url
              ? "border-navy/30 hover:border-navy"
              : "border-[#E2E0DA] opacity-60 cursor-not-allowed"
          }`}
          data-testid="pay-method-square">
          <div className="flex items-center gap-2 text-navy font-bold">
            <CreditCard className="h-5 w-5" />
            <span>Square</span>
          </div>
          <div>
            <p className="font-serif text-xl text-navy">Pay with Debit Card</p>
            <p className="text-xs text-[#64748B] mt-1">
              {payment.public_url ? "Secure Square payment page" : "Card option not available — your agent will enable it shortly."}
            </p>
          </div>
        </button>
      </div>

      <button
        onClick={claimPayment}
        disabled={claiming}
        className="w-full py-5 sm:py-6 rounded-xl text-white text-xl sm:text-2xl font-bold shadow-lg transition-all active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed"
        style={{ backgroundColor: "#28a745", minHeight: 64 }}
        data-testid="i-made-payment-btn">
        {claiming ? "Submitting…" : "✓  I Made My Payment"}
      </button>
      <p className="mt-3 text-center text-xs text-[#64748B]">
        Press only after you've completed payment by your chosen method. Your agent will verify and unlock your final trust.
      </p>

      {zelleOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-[60] flex items-center justify-center p-4"
          onClick={() => setZelleOpen(false)}
          data-testid="zelle-modal">
          <div className="bg-white rounded-xl p-6 sm:p-8 max-w-md w-full" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between mb-4">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] font-bold text-[#6f00ff]">Pay with Zelle</p>
                <p className="font-serif text-2xl text-navy mt-1">Send your payment</p>
              </div>
              <button
                onClick={() => setZelleOpen(false)}
                className="text-[#64748B] hover:text-navy"
                aria-label="Close"
                data-testid="zelle-close-btn">
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="rounded-lg border border-[#E2E0DA] p-3">
                <p className="text-[10px] uppercase text-[#64748B] font-bold tracking-wide">Send to</p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-lg font-mono text-navy" data-testid="zelle-phone">{ZELLE.phone}</p>
                  <button onClick={() => copy(ZELLE.phone, "Phone")} className="text-[#64748B] hover:text-navy" title="Copy" data-testid="zelle-copy-phone">
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="rounded-lg border border-[#E2E0DA] p-3">
                <p className="text-[10px] uppercase text-[#64748B] font-bold tracking-wide">Name</p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-lg text-navy" data-testid="zelle-name">{ZELLE.name}</p>
                  <button onClick={() => copy(ZELLE.name, "Name")} className="text-[#64748B] hover:text-navy" title="Copy" data-testid="zelle-copy-name">
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div className="rounded-lg border-2 border-bronze/40 bg-bronze/5 p-3">
                <p className="text-[10px] uppercase text-bronze font-bold tracking-wide">Amount</p>
                <div className="flex items-center justify-between mt-1">
                  <p className="text-2xl font-bold text-navy font-mono" data-testid="zelle-amount">{amountStr}</p>
                  <button onClick={() => copy((amountCents/100).toFixed(2), "Amount")} className="text-[#64748B] hover:text-navy" title="Copy" data-testid="zelle-copy-amount">
                    <Copy className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>

            <p className="text-xs text-[#64748B] mt-4 leading-relaxed">
              Open your bank's app or website, find the Zelle option, and send the exact amount to the phone number above.
              When done, close this window and press <b>"I Made My Payment"</b>.
            </p>

            <button
              onClick={() => setZelleOpen(false)}
              className="mt-5 w-full py-3 rounded-md bg-navy text-white font-semibold"
              data-testid="zelle-done-btn">
              I've sent the Zelle payment
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
