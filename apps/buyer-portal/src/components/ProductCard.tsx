import Link from "next/link";

import type { ProductSummary } from "@/lib/api/products";

export function ProductCard({ product }: { product: ProductSummary }) {
  return (
    <Link
      href={`/products/${product.slug}`}
      className="group flex flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex aspect-square items-center justify-center bg-muted text-3xl font-semibold text-muted-foreground/40 transition-colors group-hover:text-primary/30">
        {product.name.charAt(0).toUpperCase()}
      </div>
      <div className="flex flex-col gap-1 p-4">
        <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
          {product.brand ?? "Marketplace"}
        </span>
        <span className="font-medium text-foreground group-hover:text-primary">
          {product.name}
        </span>
        {product.short_description ? (
          <span className="line-clamp-2 text-sm text-muted-foreground">
            {product.short_description}
          </span>
        ) : null}
      </div>
    </Link>
  );
}
