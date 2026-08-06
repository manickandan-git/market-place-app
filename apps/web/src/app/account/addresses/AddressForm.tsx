"use client";

import { useActionState, useEffect, useRef } from "react";

import { FieldError, FormMessage } from "@/components/FormMessage";
import { createAddressAction, updateAddressAction } from "@/lib/actions/addresses";
import type { Address } from "@/lib/api/addresses";
import { buttonPrimary, buttonSecondary, card, input, label as labelClass } from "@/lib/ui";

const initialState = { ok: true as const };

export function AddressForm({
  address,
  onSuccess,
  onCancel,
}: {
  /** Present → edit this address (PATCH). Absent → create a new one (POST). */
  address?: Address;
  /** Called once after a real, successful submit — not on initial mount. */
  onSuccess?: () => void;
  onCancel?: () => void;
}) {
  const formAction = address ? updateAddressAction : createAddressAction;
  const [state, action, pending] = useActionState(formAction, initialState);
  const formRef = useRef<HTMLFormElement>(null);
  const wasPending = useRef(false);
  // Multiple AddressForm instances (the "add new" form plus one per address
  // being edited) can be mounted on /account/addresses at once — static ids
  // would collide across instances and break every label's htmlFor.
  const idPrefix = address ? `address-${address.id}` : "address-new";
  const fieldId = (name: string) => `${idPrefix}-${name}`;

  useEffect(() => {
    if (pending) {
      wasPending.current = true;
      return;
    }
    if (wasPending.current && state.ok) {
      wasPending.current = false;
      formRef.current?.reset();
      onSuccess?.();
    }
  }, [pending, state, onSuccess]);

  return (
    <form
      ref={formRef}
      action={action}
      className={card + " flex max-w-md flex-col gap-4"}
    >
      {address ? (
        <>
          <input type="hidden" name="address_id" value={address.id} />
          <input type="hidden" name="version" value={address.version} />
        </>
      ) : null}

      <FormMessage message={state.ok ? undefined : state.message} />

      <div className="flex flex-col gap-1.5">
        <label htmlFor={fieldId("recipient_name")} className={labelClass}>
          Recipient name
        </label>
        <input
          id={fieldId("recipient_name")}
          name="recipient_name"
          required
          defaultValue={address?.recipient_name}
          className={input}
        />
        <FieldError message={state.fieldErrors?.recipient_name} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={fieldId("address_line1")} className={labelClass}>
          Address line 1
        </label>
        <input
          id={fieldId("address_line1")}
          name="address_line1"
          required
          defaultValue={address?.address_line1}
          className={input}
        />
        <FieldError message={state.fieldErrors?.address_line1} />
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={fieldId("address_line2")} className={labelClass}>
          Address line 2 (optional)
        </label>
        <input
          id={fieldId("address_line2")}
          name="address_line2"
          defaultValue={address?.address_line2 ?? ""}
          className={input}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={fieldId("city")} className={labelClass}>
            City
          </label>
          <input
            id={fieldId("city")}
            name="city"
            required
            defaultValue={address?.city}
            className={input}
          />
          <FieldError message={state.fieldErrors?.city} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={fieldId("state_or_region")} className={labelClass}>
            State / region
          </label>
          <input
            id={fieldId("state_or_region")}
            name="state_or_region"
            required
            defaultValue={address?.state_or_region ?? ""}
            className={input}
          />
          <FieldError message={state.fieldErrors?.state_or_region} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="flex flex-col gap-1.5">
          <label htmlFor={fieldId("postal_code")} className={labelClass}>
            Postal code
          </label>
          <input
            id={fieldId("postal_code")}
            name="postal_code"
            required
            defaultValue={address?.postal_code}
            className={input}
          />
          <FieldError message={state.fieldErrors?.postal_code} />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor={fieldId("country_code")} className={labelClass}>
            Country code
          </label>
          <input
            id={fieldId("country_code")}
            name="country_code"
            required
            maxLength={2}
            placeholder="US"
            defaultValue={address?.country_code}
            className={input + " uppercase"}
          />
          <FieldError message={state.fieldErrors?.country_code} />
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor={fieldId("phone_number")} className={labelClass}>
          Phone (optional)
        </label>
        <input
          id={fieldId("phone_number")}
          name="phone_number"
          defaultValue={address?.phone_number ?? ""}
          className={input}
        />
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="is_default"
          defaultChecked={address?.is_default}
          className="h-4 w-4 rounded border-border accent-primary"
        />
        Set as default address
      </label>

      <div className="flex items-center gap-3">
        <button type="submit" disabled={pending} className={buttonPrimary}>
          {pending ? "Saving…" : address ? "Save changes" : "Add address"}
        </button>
        {onCancel ? (
          <button type="button" onClick={onCancel} className={buttonSecondary}>
            Cancel
          </button>
        ) : null}
      </div>
    </form>
  );
}
