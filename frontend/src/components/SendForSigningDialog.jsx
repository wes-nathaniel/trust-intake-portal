import React, { useState, useRef } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import api, { formatApiError } from "@/lib/api";
import { toast } from "sonner";
import { FilePen, Upload } from "lucide-react";

export default function SendForSigningDialog({ open, onOpenChange, caseId, clientEmail, clientName, onSent }) {
  const [form, setForm] = useState({
    signer_email: clientEmail || "",
    signer_name: clientName || "",
    title: "",
  });
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef();

  React.useEffect(() => {
    if (open) setForm({ signer_email: clientEmail || "", signer_name: clientName || "", title: "" });
  }, [open, clientEmail, clientName]);

  const submit = async (e) => {
    e.preventDefault();
    if (!file) { toast.error("Please select a PDF file."); return; }
    setLoading(true);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("signer_email", form.signer_email);
    fd.append("signer_name", form.signer_name);
    if (form.title) fd.append("title", form.title);
    try {
      await api.post(`/admin/trust-cases/${caseId}/send-for-signing`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success("Document sent for signing");
      onSent?.();
      onOpenChange(false);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-white" data-testid="send-for-signing-dialog">
        <DialogHeader>
          <DialogTitle className="font-serif text-2xl text-navy flex items-center gap-2">
            <FilePen className="h-5 w-5 text-bronze" /> Send for signing
          </DialogTitle>
          <DialogDescription>
            Upload the final trust PDF. The client receives a Dropbox Sign email to e-sign.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Document title</Label>
            <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder={`Trust Document — Case #${(caseId || "").slice(0, 8).toUpperCase()}`}
              className="mt-1 bg-white" data-testid="sign-title-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Signer name</Label>
            <Input required value={form.signer_name}
              onChange={(e) => setForm({ ...form, signer_name: e.target.value })}
              className="mt-1 bg-white" data-testid="sign-signer-name-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Signer email</Label>
            <Input required type="email" value={form.signer_email}
              onChange={(e) => setForm({ ...form, signer_email: e.target.value })}
              className="mt-1 bg-white" data-testid="sign-signer-email-input" />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">Trust document (PDF)</Label>
            <div className="mt-1 flex items-center gap-2">
              <label className="btn-accent cursor-pointer text-sm inline-flex items-center">
                <Upload className="h-4 w-4 inline mr-1" /> {file ? "Change file" : "Choose PDF"}
                <input ref={inputRef} type="file" accept="application/pdf" className="hidden"
                  onChange={(e) => setFile(e.target.files?.[0])} data-testid="sign-file-input" />
              </label>
              {file && <span className="text-sm text-[#64748B] truncate" data-testid="sign-file-name">{file.name}</span>}
            </div>
          </div>
          <DialogFooter className="pt-2">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)} data-testid="sign-cancel-btn">Cancel</Button>
            <button type="submit" disabled={loading || !file} className="btn-primary" data-testid="sign-submit-btn">
              {loading ? "Sending…" : "Send for Signing"}
            </button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
