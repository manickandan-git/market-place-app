import Link from "next/link";

import { ProductCard } from "@/components/ProductCard";
import { listCategories, listProducts } from "@/lib/api/products";
import { buttonSecondary, input, label as labelClass, link } from "@/lib/ui";

function buildPageHref(
  params: Record<string, string | undefined>,
  page: number,
): string {
  const search = new URLSearchParams();
  if (params.category_id) search.set("category_id", params.category_id);
  if (params.q) search.set("q", params.q);
  search.set("page", String(page));
  return `/products?${search.toString()}`;
}

export default async function ProductsPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string; category_id?: string; q?: string }>;
}) {
  const params = await searchParams;
  const page = Number(params.page ?? "1") || 1;

  const [{ items, totalPages, ok }, categories] = await Promise.all([
    listProducts({ page, categoryId: params.category_id, q: params.q }),
    listCategories(),
  ]);

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">Products</h1>
        <p className="mt-1 text-muted-foreground">
          Browse the full catalog from every seller.
        </p>
      </div>

      <form
        method="get"
        className="flex flex-wrap items-end gap-4 rounded-2xl border border-border bg-card p-4 shadow-sm"
      >
        <div className="flex flex-1 min-w-48 flex-col gap-1.5">
          <label htmlFor="q" className={labelClass}>
            Search
          </label>
          <input
            id="q"
            name="q"
            defaultValue={params.q ?? ""}
            placeholder="Search products…"
            className={input}
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="category_id" className={labelClass}>
            Category
          </label>
          <select
            id="category_id"
            name="category_id"
            defaultValue={params.category_id ?? ""}
            className={input}
          >
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className={buttonSecondary}>
          Filter
        </button>
      </form>

      {!ok ? (
        <div className="rounded-2xl border border-dashed border-border py-16 text-center text-muted-foreground">
          Couldn&apos;t load products right now. Please try again shortly.
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border py-16 text-center text-muted-foreground">
          No products found.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((product) => (
            <ProductCard key={product.id} product={product} />
          ))}
        </div>
      )}

      {totalPages > 1 ? (
        <nav className="flex items-center justify-center gap-4 text-sm">
          {page > 1 ? (
            <Link href={buildPageHref(params, page - 1)} className={link}>
              ← Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          {page < totalPages ? (
            <Link href={buildPageHref(params, page + 1)} className={link}>
              Next →
            </Link>
          ) : (
            <span />
          )}
        </nav>
      ) : null}
    </div>
  );
}
