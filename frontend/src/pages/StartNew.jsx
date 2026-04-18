import React from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import { Users, User, ArrowRight } from "lucide-react";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";

export default function StartNew() {
  const navigate = useNavigate();
  const create = async (trust_type) => {
    try {
      const { data } = await api.post("/trust-cases", { trust_type });
      navigate(`/intake/${data.id}`);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  return (
    <Layout>
      <h1 className="font-serif text-4xl text-navy mb-8">Start a new trust intake</h1>
      <div className="grid md:grid-cols-2 gap-6">
        <button onClick={() => create("single")} className="bg-white border border-[#E2E0DA] rounded-xl p-8 text-left hover:border-bronze hover:shadow-lg transition-all" data-testid="new-trust-single">
          <div className="h-12 w-12 rounded-full bg-sand-200 flex items-center justify-center mb-5"><User className="h-6 w-6 text-navy" /></div>
          <h3 className="font-serif text-2xl text-navy mb-2">Single Trust</h3>
          <p className="text-[#64748B] mb-4">A trust with one grantor.</p>
          <span className="inline-flex items-center text-bronze font-medium">Start <ArrowRight className="h-4 w-4 ml-1" /></span>
        </button>
        <button onClick={() => create("joint")} className="bg-white border border-[#E2E0DA] rounded-xl p-8 text-left hover:border-bronze hover:shadow-lg transition-all" data-testid="new-trust-joint">
          <div className="h-12 w-12 rounded-full bg-sand-200 flex items-center justify-center mb-5"><Users className="h-6 w-6 text-navy" /></div>
          <h3 className="font-serif text-2xl text-navy mb-2">Joint Trust</h3>
          <p className="text-[#64748B] mb-4">A trust with two grantors (spouses/partners).</p>
          <span className="inline-flex items-center text-bronze font-medium">Start <ArrowRight className="h-4 w-4 ml-1" /></span>
        </button>
      </div>
    </Layout>
  );
}
