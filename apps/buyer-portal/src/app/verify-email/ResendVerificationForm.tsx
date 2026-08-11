"use client";

import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { resendVerificationAction } from "@/lib/actions/auth";
import { initialAuthActionState } from "@/lib/actions/auth-state";
import { buttonPrimary, input, label as labelClass } from "@/lib/ui";

export function ResendVerificationForm() {
  const [state, action, pending] = useActionState(
    resendVerificationAction,
    initialAuthActionState,
  );

  return (
    <form action={action} className="flex flex-col gap-3">
      {state.message ? (
        <FormMessage message={state.message} tone={state.ok ? "success" : "error"} />
      ) : null}
      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className={labelClass}>
          Email
        </label>
        <input id="email" name="email" type="email" required className={input} />
        <FieldError message={state.fieldErrors?.email} />
      </div>
      <button type="submit" disabled={pending} className={buttonPrimary}>
        {pending ? "Sending…" : "Resend verification email"}
      </button>
    </form>
  );
}
