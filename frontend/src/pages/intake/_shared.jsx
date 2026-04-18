// Shared helpers for intake wizard
import React from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

export function Field({ id, label, required, children, hint }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs uppercase tracking-wide text-[#64748B] font-semibold">
        {label} {required && <span className="text-red-500 ml-0.5">*</span>}
      </Label>
      {children}
      {hint && <p className="text-xs text-[#94A3B8]">{hint}</p>}
    </div>
  );
}

export function Txt({ id, value, onChange, type = "text", placeholder = "", required = false, testId }) {
  return (
    <Input id={id} type={type} required={required} value={value || ""}
      onChange={(e) => onChange(e.target.value)} placeholder={placeholder}
      className="bg-white text-base" data-testid={testId || `${id}-input`} />
  );
}

export function TA({ id, value, onChange, placeholder = "", rows = 3, testId }) {
  return (
    <Textarea id={id} rows={rows} value={value || ""} onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder} className="bg-white" data-testid={testId || `${id}-textarea`} />
  );
}

// Mask SSN as XXX-XX-#### while typing
export function maskSSN(v) {
  const digits = (v || "").replace(/\D/g, "").slice(0, 9);
  if (digits.length <= 3) return digits;
  if (digits.length <= 5) return `${digits.slice(0, 3)}-${digits.slice(3)}`;
  return `${digits.slice(0, 3)}-${digits.slice(3, 5)}-${digits.slice(5)}`;
}

// Display masked (show only last 4)
export function displaySSN(v) {
  const digits = (v || "").replace(/\D/g, "");
  if (digits.length < 4) return "";
  return `XXX-XX-${digits.slice(-4)}`;
}

export function AddressFields({ addr, onChange, prefix = "addr", required = false }) {
  const update = (k, v) => onChange({ ...(addr || {}), [k]: v });
  return (
    <div className="grid sm:grid-cols-2 gap-4">
      <div className="sm:col-span-2">
        <Field id={`${prefix}-line1`} label="Address line 1" required={required}>
          <Txt id={`${prefix}-line1`} value={addr?.line1} onChange={(v) => update("line1", v)} />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field id={`${prefix}-line2`} label="Address line 2">
          <Txt id={`${prefix}-line2`} value={addr?.line2} onChange={(v) => update("line2", v)} />
        </Field>
      </div>
      <Field id={`${prefix}-city`} label="City" required={required}>
        <Txt id={`${prefix}-city`} value={addr?.city} onChange={(v) => update("city", v)} />
      </Field>
      <Field id={`${prefix}-state`} label="State" required={required}>
        <Txt id={`${prefix}-state`} value={addr?.state} onChange={(v) => update("state", v)} />
      </Field>
      <Field id={`${prefix}-zip`} label="ZIP" required={required}>
        <Txt id={`${prefix}-zip`} value={addr?.zip} onChange={(v) => update("zip", v)} />
      </Field>
      <Field id={`${prefix}-country`} label="Country">
        <Txt id={`${prefix}-country`} value={addr?.country || "USA"} onChange={(v) => update("country", v)} />
      </Field>
    </div>
  );
}

export function SectionHeader({ num, total, title, subtitle }) {
  return (
    <div className="mb-8">
      <p className="text-xs uppercase tracking-[0.2em] text-bronze font-semibold mb-2">Step {num} of {total}</p>
      <h2 className="font-serif text-3xl sm:text-4xl text-navy tracking-tight">{title}</h2>
      {subtitle && <p className="text-[#64748B] mt-2 text-lg">{subtitle}</p>}
    </div>
  );
}

export function validateRequired(obj, keys) {
  const missing = keys.filter((k) => {
    const val = k.split(".").reduce((o, kk) => (o ? o[kk] : undefined), obj);
    return val == null || val === "";
  });
  return missing;
}
