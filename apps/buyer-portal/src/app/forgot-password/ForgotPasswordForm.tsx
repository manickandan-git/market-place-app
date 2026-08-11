"use client";

import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { forgotPasswordAction } from "@/lib/actions/auth";
import { initialAuthActionState } from "@/lib/actions/auth-state";
import { buttonPrimary, input, label as labelClass } from "@/lib/ui";

export function ForgotPasswordForm() {
  const [state, action, pending] = useActionState(
    forgotPasswordAction,
    initialAuthActionState,
  );

  if (state.ok && state.message) {
    return <FormMessage message={state.message} tone="success" />;
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <FormMessage message={state.ok ? undefined : state.message} />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className={labelClass}>
          Email
        </label>
        <input id="email" name="email" type="email" required className={input} />
        <FieldError message={state.fieldErrors?.email} />
      </div>
      <button type="submit" disabled={pending} className={buttonPrimary}>
        {pending ? "Sending…" : "Send reset instructions"}
      </button>
    </form>
  );
}
