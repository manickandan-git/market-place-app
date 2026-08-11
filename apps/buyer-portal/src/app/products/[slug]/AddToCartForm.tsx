"use client";

import { useActionState, useState } from "react";

import { FormMessage } from "@/components/FormMessage";
import { addToCartFormAction } from "@/lib/actions/cart";
import { initialCartActionState } from "@/lib/actions/cart-state";
import type { ProductDetail } from "@/lib/api/products";
import { formatPrice } from "@/lib/format";
import { buttonPrimary, input as inputClass, label as labelClass } from "@/lib/ui";

export function AddToCartForm({ product }: { product: ProductDetail }) {
  const variants = (product.variants ?? []).filter((v) => v.is_active);
  const [selectedVariantId, setSelectedVariantId] = useState(
    variants[0]?.id ?? "",
  );
  const [state, action, pending] = useActionState(
    addToCartFormAction,
    initialCartActionState,
  );

  if (variants.length === 0) {
    return null;
  }

  return (
    <form action={action} className="flex flex-col gap-4">
      <input type="hidden" name="product_id" value={product.id} />
      {state.message ? (
        <FormMessage message={state.message} tone={state.ok ? "success" : "error"} />
      ) : null}

      {variants.length > 1 ? (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="variant_id" className={labelClass}>
            Option
          </label>
          <select
            id="variant_id"
            name="variant_id"
            value={selectedVariantId}
            onChange={(event) => setSelectedVariantId(event.target.value)}
            className={inputClass}
          >
            {variants.map((variant) => (
              <option key={variant.id} value={variant.id}>
                {variant.name} — {formatPrice(variant.price_amount, variant.currency_code)}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <>
          <p className="text-2xl font-semibold text-primary">
            {formatPrice(variants[0].price_amount, variants[0].currency_code)}
          </p>
          <input type="hidden" name="variant_id" value={selectedVariantId} />
        </>
      )}

      <div className="flex items-center gap-3">
        <label htmlFor="quantity" className={labelClass}>
          Qty
        </label>
        <input
          id="quantity"
          name="quantity"
          type="number"
          min={1}
          max={100}
          defaultValue={1}
          className={inputClass + " w-20"}
        />
      </div>

      <button type="submit" disabled={pending} className={buttonPrimary}>
        {pending ? "Adding…" : "Add to cart"}
      </button>
    </form>
  );
}
