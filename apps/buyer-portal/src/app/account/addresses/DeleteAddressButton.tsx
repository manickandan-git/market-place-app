"use client";

import { useActionState } from "react";

import { deleteAddressAction } from "@/lib/actions/addresses";
import { initialCartActionState } from "@/lib/actions/cart-state";

export function DeleteAddressButton({
  addressId,
  version,
}: {
  addressId: string;
  version: number;
}) {
  const [state, action, pending] = useActionState(
    deleteAddressAction,
    initialCartActionState,
  );

  return (
    <form action={action} className="flex flex-col items-start gap-1">
      <input type="hidden" name="address_id" value={addressId} />
      <input type="hidden" name="version" value={version} />
      <button
        type="submit"
        disabled={pending}
        className="text-sm font-medium text-danger underline-offset-4 hover:underline disabled:opacity-50"
      >
        {pending ? "Removing…" : "Remove"}
      </button>
      {!state.ok && state.message ? (
        <p className="text-xs text-danger">{state.message}</p>
      ) : null}
    </form>
  );
}
