import Link from "next/link";

import { getCurrentUser } from "@/lib/api/identity";
import { getCart } from "@/lib/api/cart";
import { logoutAction } from "@/lib/actions/auth";
import { isAuthenticated } from "@/lib/session";

export async function SiteHeader() {
  const authed = await isAuthenticated();
  const [user, cart] = await Promise.all([
    authed ? getCurrentUser() : Promise.resolve(null),
    getCart(),
  ]);

  return (
    <header className="sticky top-0 z-10 border-b border-border/80 bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-bold text-primary-foreground">
            M
          </span>
          <span className="text-lg font-semibold tracking-tight">
            Marketplace
          </span>
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          <Link
            href="/products"
            className="rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
          >
            Products
          </Link>
          <Link
            href="/cart"
            className="relative rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
          >
            Cart
            {cart && cart.total_quantity > 0 ? (
              <span className="ml-1.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-xs font-semibold text-primary-foreground">
                {cart.total_quantity}
              </span>
            ) : null}
          </Link>
          {user ? (
            <>
              <Link
                href="/orders"
                className="rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
              >
                Orders
              </Link>
              <Link
                href="/account"
                className="rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
              >
                {user.first_name}
              </Link>
              <form action={logoutAction}>
                <button
                  type="submit"
                  className="ml-1 cursor-pointer rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
                >
                  Sign out
                </button>
              </form>
            </>
          ) : (
            <>
              <Link
                href="/login"
                className="rounded-full px-3 py-2 font-medium text-foreground/70 transition-colors hover:bg-muted hover:text-foreground"
              >
                Sign in
              </Link>
              <Link
                href="/register"
                className="ml-1 rounded-full bg-primary px-4 py-2 font-medium text-primary-foreground shadow-sm transition-all hover:bg-primary-hover hover:shadow-md active:scale-[0.98]"
              >
                Sign up
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
