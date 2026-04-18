import React, { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { UserPlus } from "lucide-react";

export default function InviteClientDialog({ open, onOpenChange, onInvited }) {
  const [form, setForm] = useState({ name: "", email: "", trust_type: "single", message: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/admin/invite-client", form);
      toast.success("Invitation emailed");
      onInvited?.(data);
      onOpenChange(false);
      setForm({ name: "", email: "", trust_type: "single", message: "" });
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-white" data-testid="invite-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl text-navy flex items-center gap-2">
            <UserPlus className="h-5 w-5 text-bronze" /> Invite a client
          </DialogTitle>
          <DialogDescription>
            Create a case and send a branded invite email. The client sets their password via the link.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Client name</Label>
            <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              className="mt-1 bg-white" data-testid="invite-name-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Email</Label>
            <Input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="mt-1 bg-white" data-testid="invite-email-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Trust type</Label>
            <select value={form.trust_type} onChange={(e) => setForm({ ...form, trust_type: e.target.value })}
              className="w-full mt-1 rounded-md border border-input bg-white px-3 py-2 text-sm"
              data-testid="invite-type-select">
              <option value="single">Single Trust</option>
              <option value="joint">Joint Trust</option>
            </select>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} data-testid="invite-cancel-btn">Cancel</Button>
            <button type="submit" disabled={loading} className="btn-primary" data-testid="invite-submit-btn">
              {loading ? "Sending…" : "Send Invitation"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
