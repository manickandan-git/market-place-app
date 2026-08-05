"use client";

import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { createOrderAction } from "@/lib/actions/checkout";
import { initialCheckoutActionState } from "@/lib/actions/checkout-state";
import { buttonPrimary, input, label as labelClass } from "@/lib/ui";

export function CheckoutForm({
  cartId,
  cartVersion,
}: {
  cartId: string;
  cartVersion: number;
}) {
  const [state, action, pending] = useActionState(
    createOrderAction,
    initialCheckoutActionState,
  );

  return (
    <form
      action={action}
      className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm"
    >
      <input type="hidden" name="cart_id" value={cartId} />
      <input type="hidden" name="cart_version" value={cartVersion} />

      <FormMessage message={state.ok ? undefined : state.message} />

      <div className="flex flex-col gap-1.5">
        <label htmlFor="full_name" className={labelClass}>
          Full name
        </label>
        <input id="full_name" name="full_name" required className={input} />
        <FieldError message={state.fieldErrors?.full_name} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="line1" className={labelClass}>
          Address line 1
        </label>
        <input id="line1" name="line1" required className={input} />
        <FieldError message={state.fieldErrors?.line1} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="line2" className={labelClass}>
          Address line 2 (optional)
        </label>
        <input id="line2" name="line2" className={input} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="city" className={labelClass}>
            City
          </label>
          <input id="city" name="city" required className={input} />
          <FieldError message={state.fieldErrors?.city} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="state_or_region" className={labelClass}>
            State / region
          </label>
          <input
            id="state_or_region"
            name="state_or_region"
            required
            className={input}
          />
          <FieldError message={state.fieldErrors?.state_or_region} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="postal_code" className={labelClass}>
            Postal code
          </label>
          <input id="postal_code" name="postal_code" required className={input} />
          <FieldError message={state.fieldErrors?.postal_code} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="country_code" className={labelClass}>
            Country code
          </label>
          <input
            id="country_code"
            name="country_code"
            required
            maxLength={2}
            placeholder="US"
            className={input + " uppercase"}
          />
          <FieldError message={state.fieldErrors?.country_code} />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="phone" className={labelClass}>
          Phone (optional)
        </label>
        <input id="phone" name="phone" className={input} />
      </div>

      <button type="submit" disabled={pending} className={buttonPrimary + " mt-2"}>
        {pending ? "Placing order…" : "Place order"}
      </button>
    </form>
  );
}
