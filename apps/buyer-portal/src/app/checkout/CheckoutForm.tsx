"use client";

import { useActionState, useState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { createOrderAction } from "@/lib/actions/checkout";
import { initialCheckoutActionState } from "@/lib/actions/checkout-state";
import type { Address } from "@/lib/api/addresses";
import { buttonPrimary, input, label as labelClass, link } from "@/lib/ui";

export function CheckoutForm({
  cartId,
  cartVersion,
  addresses,
}: {
  cartId: string;
  cartVersion: number;
  addresses: Address[];
}) {
  const [state, action, pending] = useActionState(
    createOrderAction,
    initialCheckoutActionState,
  );

  const defaultAddress = addresses.find((a) => a.is_default) ?? addresses[0];
  const [selectedId, setSelectedId] = useState<string>(
    defaultAddress ? defaultAddress.id : "new",
  );
  const enteringNew = selectedId === "new" || addresses.length === 0;

  return (
    <form
      action={action}
      className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm"
    >
      <input type="hidden" name="cart_id" value={cartId} />
      <input type="hidden" name="cart_version" value={cartVersion} />
      <input type="hidden" name="address_id" value={selectedId} />

      <FormMessage message={state.ok ? undefined : state.message} />

      {addresses.length > 0 ? (
        <div className="flex flex-col gap-2">
          {addresses.map((a) => (
            <label
              key={a.id}
              className="flex cursor-pointer items-start gap-3 rounded-lg border border-border p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary/5"
            >
              <input
                type="radio"
                name="_address_choice"
                checked={selectedId === a.id}
                onChange={() => setSelectedId(a.id)}
                className="mt-1 accent-primary"
              />
              <span>
                {a.label ? <span className="font-medium">{a.label}: </span> : null}
                {a.recipient_name}, {a.address_line1}
                {a.address_line2 ? `, ${a.address_line2}` : ""}, {a.city}
                {a.state_or_region ? `, ${a.state_or_region}` : ""} {a.postal_code},{" "}
                {a.country_code}
              </span>
            </label>
          ))}
          <label className="flex cursor-pointer items-center gap-3 rounded-lg border border-border p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:bg-primary/5">
            <input
              type="radio"
              name="_address_choice"
              checked={selectedId === "new"}
              onChange={() => setSelectedId("new")}
              className="accent-primary"
            />
            Use a new address
          </label>
        </div>
      ) : null}

      {enteringNew ? (
        <>
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
              <input
                id="postal_code"
                name="postal_code"
                required
                className={input}
              />
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

          {addresses.length > 0 ? (
            <a href="/account/addresses" className={link + " text-xs"}>
              Manage saved addresses
            </a>
          ) : null}
        </>
      ) : null}

      <button type="submit" disabled={pending} className={buttonPrimary + " mt-2"}>
        {pending ? "Placing order…" : "Place order"}
      </button>
    </form>
  );
}
