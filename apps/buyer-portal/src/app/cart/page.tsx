import Link from "next/link";

import { getCart } from "@/lib/api/cart";
import { formatPrice } from "@/lib/format";
import { buttonPrimary } from "@/lib/ui";
import { CartItemRow } from "./CartItemRow";
import { ClearCartButton } from "./ClearCartButton";
import { SavedItemRow } from "./SavedItemRow";

export default async function CartPage() {
  const cart = await getCart();

  if (!cart || cart.items.length === 0) {
    return (
      <div className="flex flex-col items-start gap-6">
        <h1 className="text-3xl font-semibold tracking-tight">Your cart</h1>
        <div className="w-full rounded-2xl border border-dashed border-border py-16 text-center">
          <p className="text-muted-foreground">Your cart is empty.</p>
          <Link href="/products" className={buttonPrimary + " mt-4"}>
            Browse products
          </Link>
        </div>
        {cart && cart.saved_items.length > 0 ? (
          <div className="w-full">
            <h2 className="mb-3 text-lg font-medium">Saved for later</h2>
            <ul className="flex flex-col gap-3">
              {cart.saved_items.map((item) => (
                <SavedItemRow key={item.id} item={item} cartVersion={cart.version} />
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-semibold tracking-tight">Your cart</h1>
        <ClearCartButton version={cart.version} />
      </div>

      <ul className="flex flex-col divide-y divide-border rounded-2xl border border-border bg-card px-5 shadow-sm">
        {cart.items.map((item) => (
          <CartItemRow key={item.id} item={item} cartVersion={cart.version} />
        ))}
      </ul>

      <div className="flex flex-col items-end gap-4 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-muted-foreground">
          {cart.total_quantity} item{cart.total_quantity === 1 ? "" : "s"}
        </span>
        <div className="flex items-center gap-4">
          <span className="text-xl font-semibold">
            {formatPrice(cart.subtotal, cart.currency_code)}
          </span>
          <Link href="/checkout" className={buttonPrimary + " !px-6"}>
            Checkout
          </Link>
        </div>
      </div>

      {cart.saved_items.length > 0 ? (
        <div>
          <h2 className="mb-3 text-lg font-medium">Saved for later</h2>
          <ul className="flex flex-col gap-3">
            {cart.saved_items.map((item) => (
              <SavedItemRow key={item.id} item={item} cartVersion={cart.version} />
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
