import React, { useState, forwardRef } from "react";
import { Input } from "@/components/ui/input";
import { Eye, EyeOff } from "lucide-react";

/**
 * Password input with a show/hide eye toggle. Drop-in replacement for
 * `<Input type="password" />` — accepts all the same props. The toggle
 * button is absolutely positioned inside the input and swaps between
 * `type="password"` and `type="text"`.
 *
 * data-testid support: when a `data-testid` is passed on the input, the
 * matching toggle button gets `<data-testid>-toggle` for E2E tests.
 */
const PasswordInput = forwardRef(function PasswordInput(
  { className = "", "data-testid": testId, ...props },
  ref
) {
  const [visible, setVisible] = useState(false);
  const toggleId = testId ? `${testId}-toggle` : undefined;
  return (
    <div className="relative">
      <Input
        ref={ref}
        type={visible ? "text" : "password"}
        className={`${className} pr-10`}
        data-testid={testId}
        {...props}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        tabIndex={-1}
        aria-label={visible ? "Hide password" : "Show password"}
        title={visible ? "Hide password" : "Show password"}
        data-testid={toggleId}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-[#64748B] hover:text-navy transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-bronze rounded"
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
});

export default PasswordInput;
