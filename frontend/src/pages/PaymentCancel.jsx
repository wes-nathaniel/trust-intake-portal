import React from "react";
import { useNavigate } from "react-router-dom";
import { XCircle } from "lucide-react";
import Layout from "@/components/Layout";

export default function PaymentCancel() {
  const navigate = useNavigate();
  return (
    <Layout>
      <div className="max-w-2xl mx-auto py-16 text-center" data-testid="payment-cancel-page">
        <XCircle className="h-16 w-16 text-[#64748B] mx-auto mb-4" />
        <h1 className="font-serif text-3xl text-navy mb-2">Checkout canceled</h1>
        <p className="text-[#334155] mb-6">
          No worries — your case is unchanged and you can try again anytime from your portal.
        </p>
        <button onClick={() => navigate("/portal")} className="btn-primary px-6 py-3" data-testid="back-to-portal-btn">
          Return to your portal
        </button>
      </div>
    </Layout>
  );
}
