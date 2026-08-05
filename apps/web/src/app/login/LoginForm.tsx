"use client";

import Link from "next/link";
import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { loginAction } from "@/lib/actions/auth";
import { initialAuthActionState } from "@/lib/actions/auth-state";
import { buttonPrimary, input, label as labelClass, link } from "@/lib/ui";

export function LoginForm({ next }: { next?: string }) {
  const [state, action, pending] = useActionState(
    loginAction,
    initialAuthActionState,
  );

  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next ?? ""} />
      <FormMessage message={state.ok ? undefined : state.message} />

      <div className="flex flex-col gap-1.5">
        <label htmlFor="email" className={labelClass}>
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          className={input}
        />
        <FieldError message={state.fieldErrors?.email} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="password" className={labelClass}>
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          required
          autoComplete="current-password"
          className={input}
        />
        <FieldError message={state.fieldErrors?.password} />
      </div>

      <button type="submit" disabled={pending} className={buttonPrimary + " mt-1"}>
        {pending ? "Signing in…" : "Sign in"}
      </button>

      <p className="text-center text-sm text-muted-foreground">
        No account?{" "}
        <Link href="/register" className={link}>
          Register
        </Link>
        {" · "}
        <Link href="/forgot-password" className={link}>
          Forgot password?
        </Link>
      </p>
    </form>
  );
}
