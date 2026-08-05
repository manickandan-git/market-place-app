"use client";

import { useActionState } from "react";

import { clearCartAction } from "@/lib/actions/cart";
import { initialCartActionState } from "@/lib/actions/cart-state";

export function ClearCartButton({ version }: { version: number }) {
  const [state, action, pending] = useActionState(
    clearCartAction,
    initialCartActionState,
  );

  return (
    <form action={action} className="flex flex-col items-end gap-1">
      <input type="hidden" name="version" value={version} />
      <button
        type="submit"
        disabled={pending}
        className="text-sm font-medium text-danger underline-offset-4 hover:underline disabled:opacity-50"
      >
        Clear cart
      </button>
      {!state.ok && state.message ? (
        <p className="text-xs text-danger">{state.message}</p>
      ) : null}
    </form>
  );
}
