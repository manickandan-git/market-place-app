"use client";

import Link from "next/link";
import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { resetPasswordAction } from "@/lib/actions/auth";
import { initialAuthActionState } from "@/lib/actions/auth-state";
import { buttonPrimary, input, label as labelClass, link } from "@/lib/ui";

export function ResetPasswordForm({ token }: { token: string }) {
  const [state, action, pending] = useActionState(
    resetPasswordAction,
    initialAuthActionState,
  );

  if (state.ok && state.message) {
    return (
      <div className="flex flex-col gap-4">
        <FormMessage message={state.message} tone="success" />
        <Link href="/login" className={link}>
          Sign in
        </Link>
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="token" value={token} />
      <FormMessage message={state.ok ? undefined : state.message} />
      <div className="flex flex-col gap-1.5">
        <label htmlFor="new_password" className={labelClass}>
          New password
        </label>
        <input
          id="new_password"
          name="new_password"
          type="password"
          required
          minLength={10}
          autoComplete="new-password"
          className={input}
        />
        <FieldError message={state.fieldErrors?.new_password} />
      </div>
      <button type="submit" disabled={pending} className={buttonPrimary}>
        {pending ? "Resetting…" : "Reset password"}
      </button>
    </form>
  );
}
