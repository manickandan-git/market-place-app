import Link from "next/link";

import { buttonPrimary, buttonSecondary } from "@/lib/ui";

export default function Home() {
  return (
    <div className="flex flex-col items-start gap-6 py-12 sm:py-20">
      <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold tracking-wide text-primary uppercase">
        Now open
      </span>
      <h1 className="max-w-xl text-4xl font-semibold tracking-tight sm:text-5xl">
        Everything you need,{" "}
        <span className="text-primary">from sellers you trust</span>
      </h1>
      <p className="max-w-lg text-lg text-muted-foreground">
        Browse the catalog, add what you like to your cart, and check out
        securely — all in one place.
      </p>
      <div className="flex flex-wrap items-center gap-3 pt-2">
        <Link href="/products" className={buttonPrimary + " !px-6 !py-3"}>
          Browse products
        </Link>
        <Link href="/register" className={buttonSecondary + " !px-6 !py-3"}>
          Create an account
        </Link>
      </div>
    </div>
  );
}
