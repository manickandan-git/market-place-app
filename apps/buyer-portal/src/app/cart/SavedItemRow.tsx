"use client";

import { useActionState } from "react";

import { deleteSavedItemAction, moveToCartAction } from "@/lib/actions/cart";
import { initialCartActionState } from "@/lib/actions/cart-state";
import type { components } from "@/lib/api/schema";
import { formatPrice } from "@/lib/format";

type SavedItem = components["schemas"]["cart_SavedItemResponse"];

export function SavedItemRow({
  item,
  cartVersion,
}: {
  item: SavedItem;
  cartVersion: number;
}) {
  const [moveState, moveAction, movePending] = useActionState(
    moveToCartAction,
    initialCartActionState,
  );
  const [deleteState, deleteAction, deletePending] = useActionState(
    deleteSavedItemAction,
    initialCartActionState,
  );
  const error = !moveState.ok
    ? moveState.message
    : !deleteState.ok
      ? deleteState.message
      : undefined;

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-border bg-card p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-medium">{item.product_name}</p>
          <p className="text-sm text-muted-foreground">
            {item.variant_name} · {item.sku}
          </p>
        </div>
        <p className="font-medium">
          {formatPrice(item.unit_price, item.currency_code)}
        </p>
      </div>
      <div className="flex items-center gap-4">
        <form action={moveAction}>
          <input type="hidden" name="item_id" value={item.id} />
          <input type="hidden" name="version" value={cartVersion} />
          <button
            type="submit"
            disabled={movePending}
            className="text-sm font-medium text-primary underline-offset-4 hover:underline disabled:opacity-50"
          >
            Move to cart
          </button>
        </form>
        <form action={deleteAction}>
          <input type="hidden" name="item_id" value={item.id} />
          <input type="hidden" name="version" value={cartVersion} />
          <button
            type="submit"
            disabled={deletePending}
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
