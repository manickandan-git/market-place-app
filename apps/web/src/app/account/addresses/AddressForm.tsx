"use client";

import { useActionState } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { createAddressAction } from "@/lib/actions/addresses";
import { buttonPrimary, card, input, label as labelClass } from "@/lib/ui";

const initialState = { ok: true as const };

export function AddressForm() {
  const [state, action, pending] = useActionState(
    createAddressAction,
    initialState,
  );

  return (
    <form action={action} className={card + " flex max-w-md flex-col gap-4"}>
      <FormMessage message={state.ok ? undefined : state.message} />

      <div className="flex flex-col gap-1.5">
        <label htmlFor="recipient_name" className={labelClass}>
          Recipient name
        </label>
        <input id="recipient_name" name="recipient_name" required className={input} />
        <FieldError message={state.fieldErrors?.recipient_name} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="address_line1" className={labelClass}>
          Address line 1
        </label>
        <input id="address_line1" name="address_line1" required className={input} />
        <FieldError message={state.fieldErrors?.address_line1} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="address_line2" className={labelClass}>
          Address line 2 (optional)
        </label>
        <input id="address_line2" name="address_line2" className={input} />
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
          <input id="state_or_region" name="state_or_region" className={input} />
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
        <label htmlFor="phone_number" className={labelClass}>
          Phone (optional)
        </label>
        <input id="phone_number" name="phone_number" className={input} />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="is_default"
          className="h-4 w-4 rounded border-border accent-primary"
        />
        Set as default address
      </label>

      <button
        type="submit"
        disabled={pending}
        className={buttonPrimary + " self-start"}
      >
        {pending ? "Saving…" : "Add address"}
      </button>
    </form>
  );
}
