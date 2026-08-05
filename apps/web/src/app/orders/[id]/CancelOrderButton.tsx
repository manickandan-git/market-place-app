"use client";

import { useActionState } from "react";

import { FormMessage } from "@/components/FormMessage";
import { cancelOrderAction } from "@/lib/actions/orders";
import { initialCartActionState } from "@/lib/actions/cart-state";
import { buttonDanger } from "@/lib/ui";

export function CancelOrderButton({
  orderId,
  version,
}: {
  orderId: string;
  version: number;
}) {
  const [state, action, pending] = useActionState(
    cancelOrderAction,
    initialCartActionState,
  );

  return (
    <form action={action} className="flex flex-col items-start gap-2">
      <input type="hidden" name="order_id" value={orderId} />
      <input type="hidden" name="version" value={version} />
      <input type="hidden" name="reason" value="Changed my mind" />
      <button type="submit" disabled={pending} className={buttonDanger}>
        {pending ? "Cancelling…" : "Cancel order"}
      </button>
      {!state.ok && state.message ? (
        <FormMessage message={state.message} />
      ) : null}
    </form>
  );
}
