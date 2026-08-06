"use client";

import { useActionState } from "react";

import {
  removeItemAction,
  saveForLaterAction,
  updateQuantityAction,
} from "@/lib/actions/cart";
import { initialCartActionState } from "@/lib/actions/cart-state";
import type { CartItem } from "@/lib/api/cart";
import { formatPrice } from "@/lib/format";

export function CartItemRow({
  item,
  cartVersion,
}: {
  item: CartItem;
  cartVersion: number;
}) {
  const [updateState, updateAction, updatePending] = useActionState(
    updateQuantityAction,
    initialCartActionState,
  );
  const [removeState, removeAction, removePending] = useActionState(
    removeItemAction,
    initialCartActionState,
  );
  const [saveState, saveAction, savePending] = useActionState(
    saveForLaterAction,
    initialCartActionState,
  );

  const error = !updateState.ok
    ? updateState.message
    : !removeState.ok
      ? removeState.message
      : !saveState.ok
        ? saveState.message
        : undefined;

  return (
    <li className="flex flex-col gap-3 py-5 first:pt-0 last:pb-0">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-muted text-lg font-semibold text-muted-foreground/50">
            {item.product_name.charAt(0).toUpperCase()}
          </div>
          <div>
            <p className="font-medium">{item.product_name}</p>
            <p className="text-sm text-muted-foreground">
              {item.variant_name} · {item.sku}
            </p>
            <p className="text-sm text-muted-foreground">
              {formatPrice(item.unit_price, item.currency_code)} each
            </p>
          </div>
        </div>
        <p className="font-semibold whitespace-nowrap">
          {formatPrice(item.line_total, item.currency_code)}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <form action={updateAction} className="flex items-center gap-2">
          <input type="hidden" name="item_id" value={item.id} />
          <input type="hidden" name="version" value={cartVersion} />
          <label htmlFor={`qty-${item.id}`} className="sr-only">
            Quantity
          </label>
          <input
            id={`qty-${item.id}`}
            name="quantity"
            type="number"
            min={1}
            max={100}
            defaultValue={item.quantity}
            className="w-16 rounded-lg border border-border bg-card px-2 py-1.5 text-sm shadow-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring/30"
          />
          <button
            type="submit"
            disabled={updatePending}
            className="text-sm font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50"
          >
            Update
          </button>
        </form>

        <form action={saveAction}>
          <input type="hidden" name="item_id" value={item.id} />
          <input type="hidden" name="version" value={cartVersion} />
          <button
            type="submit"
            disabled={savePending}
            className="text-sm font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline disabled:opacity-50"
          >
            Save for later
          </button>
        </form>

        <form action={removeAction}>
          <input type="hidden" name="item_id" value={item.id} />
          <input type="hidden" name="version" value={cartVersion} />
          <button
            type="submit"
            disabled={removePending}
            className="text-sm font-medium text-danger underline-offset-4 hover:underline disabled:opacity-50"
          >
            Remove
          </button>
        </form>
      </div>

      {error ? <p className="text-xs text-danger">{error}</p> : null}
    </li>
  );
}
