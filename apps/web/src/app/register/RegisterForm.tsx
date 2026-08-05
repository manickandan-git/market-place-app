"use client";

import Link from "next/link";
import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { registerAction } from "@/lib/actions/auth";
import { buttonPrimary, input, label as labelClass, link } from "@/lib/ui";

const initialState = { ok: true as const, verificationToken: undefined };

export function RegisterForm() {
  const [state, action, pending] = useActionState(registerAction, initialState);

  if (state.ok && state.message) {
    return (
      <div className="flex flex-col gap-4">
        <FormMessage message={state.message} tone="success" />
        {state.verificationToken ? (
          <div className="rounded-lg border border-border bg-muted p-4 text-sm">
            <p className="mb-2 text-muted-foreground">
              Dev mode: no email provider is wired up, so here&apos;s the
              verification link directly.
            </p>
            <Link
              className={link + " break-all"}
              href={`/verify-email?token=${encodeURIComponent(state.verificationToken)}`}
            >
              Verify my email
            </Link>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            Check your email for a verification link, then{" "}
            <Link href="/login" className={link}>
              sign in
            </Link>
            .
          </p>
        )}
      </div>
    );
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <FormMessage message={state.ok ? undefined : state.message} />

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="first_name" className={labelClass}>
            First name
          </label>
          <input id="first_name" name="first_name" required className={input} />
          <FieldError message={state.fieldErrors?.first_name} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="last_name" className={labelClass}>
            Last name
          </label>
          <input id="last_name" name="last_name" required className={input} />
          <FieldError message={state.fieldErrors?.last_name} />
        </div>
      </div>

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
          minLength={10}
          autoComplete="new-password"
          className={input}
        />
        <p className="text-xs text-muted-foreground">At least 10 characters.</p>
        <FieldError message={state.fieldErrors?.password} />
      </div>

      <fieldset className="flex flex-col gap-1.5">
        <legend className={labelClass}>I am a</legend>
        <div className="grid grid-cols-2 gap-2">
          <label className="flex cursor-pointer items-center justify-center rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary/10 has-[:checked]:text-primary">
            <input
              type="radio"
              name="role"
              value="BUYER"
              defaultChecked
              className="sr-only"
            />
            Buyer
          </label>
          <label className="flex cursor-pointer items-center justify-center rounded-lg border border-border px-3 py-2 text-sm font-medium transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary/10 has-[:checked]:text-primary">
            <input type="radio" name="role" value="SELLER" className="sr-only" />
            Seller
          </label>
        </div>
      </fieldset>

      <button type="submit" disabled={pending} className={buttonPrimary + " mt-1"}>
        {pending ? "Creating account…" : "Create account"}
      </button>

      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className={link}>
          Sign in
        </Link>
      </p>
    </form>
  );
}
