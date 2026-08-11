import Link from "next/link";

import { listAddresses } from "@/lib/api/addresses";
import { getCart } from "@/lib/api/cart";
import { formatPrice } from "@/lib/format";
import { link } from "@/lib/ui";
import { CheckoutForm } from "./CheckoutForm";

export default async function CheckoutPage() {
  const [cart, addresses] = await Promise.all([getCart(), listAddresses()]);

  if (!cart || cart.items.length === 0) {
    return (
      <div className="flex flex-col items-start gap-4">
        <h1 className="text-3xl font-semibold tracking-tight">Checkout</h1>
        <p className="text-muted-foreground">Your cart is empty.</p>
        <Link href="/products" className={link}>
          Browse products
        </Link>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-8 md:grid-cols-[1fr_320px]">
      <div>
        <h1 className="mb-6 text-3xl font-semibold tracking-tight">
          Shipping address
        </h1>
        <CheckoutForm
          cartId={cart.id}
          cartVersion={cart.version}
          addresses={addresses}
        />
      </div>

      <aside className="flex h-fit flex-col gap-3 rounded-2xl border border-border bg-card p-5 shadow-sm">
        <h2 className="font-medium">Order summary</h2>
        <ul className="flex flex-col gap-2 text-sm">
          {cart.items.map((item) => (
            <li key={item.id} className="flex justify-between gap-2">
              <span className="text-muted-foreground">
                {item.product_name} × {item.quantity}
              </span>
              <span>{formatPrice(item.line_total, item.currency_code)}</span>
            </li>
          ))}
        </ul>
        <div className="flex justify-between border-t border-border pt-3 font-semibold">
          <span>Subtotal</span>
          <span>{formatPrice(cart.subtotal, cart.currency_code)}</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Tax and shipping are calculated after you place the order.
        </p>
      </aside>
    </div>
  );
}
