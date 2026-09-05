import React, { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import Layout from "@/components/Layout";
import api from "@/lib/api";

/**
 * Post-Stripe-checkout landing. Polls `/api/payments/status/{session_id}`
 * every 2 seconds for up to ~40s. Once paid, redirects the client back
 * to their portal.
 */
export default function PaymentSuccess() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sessionId = params.get("session_id");
  const [status, setStatus] = useState("loading"); // loading | paid | timeout | error
  const [attempts, setAttempts] = useState(0);

  useEffect(() => {
    if (!sessionId) { setStatus("error"); return; }
    let cancelled = false;
    let timer;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (cancelled) return;
        if (data.payment_status === "paid") {
          setStatus("paid");
          setTimeout(() => navigate("/portal"), 3200);
          return;
        }
        setAttempts((n) => n + 1);
      } catch (_) { /* keep polling */ }
      if (!cancelled) timer = setTimeout(poll, 2000);
    };
    poll();
    // Hard stop after ~40s
    const stopper = setTimeout(() => {
      cancelled = true;
      setStatus((s) => (s === "paid" ? s : "timeout"));
    }, 40000);
    return () => { cancelled = true; clearTimeout(timer); clearTimeout(stopper); };
  }, [sessionId, navigate]);

  return (
    <Layout>
      <div className="max-w-2xl mx-auto py-16 text-center" data-testid="payment-success-page">
        {status === "loading" && (
          <>
            <Loader2 className="h-12 w-12 text-bronze mx-auto mb-4 animate-spin" />
            <h1 className="font-serif text-3xl text-navy mb-2">Confirming your payment…</h1>
            <p className="text-[#64748B]">
              Hang tight — this usually takes a few seconds.
              {attempts > 0 && <> (attempt {attempts + 1})</>}
            </p>
          </>
        )}
        {status === "paid" && (
          <>
            <CheckCircle2 className="h-16 w-16 text-green-600 mx-auto mb-4" />
            <h1 className="font-serif text-3xl text-navy mb-2" data-testid="payment-success-heading">Payment received!</h1>
            <p className="text-[#334155] mb-6">
              Thank you. Your final trust will be unlocked shortly and a member of our team will call you within 10 minutes.
            </p>
            <button onClick={() => navigate("/portal")} className="btn-primary px-6 py-3" data-testid="back-to-portal-btn">
              Return to your portal
            </button>
          </>
        )}
        {status === "timeout" && (
          <>
            <Loader2 className="h-12 w-12 text-amber-600 mx-auto mb-4" />
            <h1 className="font-serif text-3xl text-navy mb-2">Still processing…</h1>
            <p className="text-[#334155] mb-6">
              Your payment is taking a little longer than usual. It's safe to return to your portal — we'll update it as soon as Stripe confirms.
            </p>
            <button onClick={() => navigate("/portal")} className="btn-primary px-6 py-3">Return to your portal</button>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle className="h-12 w-12 text-red-600 mx-auto mb-4" />
            <h1 className="font-serif text-3xl text-navy mb-2">We couldn't find that session</h1>
            <p className="text-[#334155] mb-6">Please head back to your portal and start the checkout again.</p>
            <button onClick={() => navigate("/portal")} className="btn-primary px-6 py-3">Return to your portal</button>
          </>
        )}
      </div>
    </Layout>
  );
}
