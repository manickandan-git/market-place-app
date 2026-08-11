import Link from "next/link";

import { listOrders } from "@/lib/api/orders";
import { formatPrice } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { buttonPrimary, link } from "@/lib/ui";

export default async function OrdersPage({
  searchParams,
}: {
  searchParams: Promise<{ page?: string }>;
}) {
  const { page: pageParam } = await searchParams;
  const page = Number(pageParam ?? "1") || 1;
  const { items, totalPages } = await listOrders(page);

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-start gap-6">
        <h1 className="text-3xl font-semibold tracking-tight">Your orders</h1>
        <div className="w-full rounded-2xl border border-dashed border-border py-16 text-center">
          <p className="text-muted-foreground">
            You haven&apos;t placed any orders yet.
          </p>
          <Link href="/products" className={buttonPrimary + " mt-4"}>
            Browse products
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-3xl font-semibold tracking-tight">Your orders</h1>
      <ul className="flex flex-col gap-3">
        {items.map((order) => (
          <li key={order.id}>
            <Link
              href={`/orders/${order.id}`}
              className="flex items-center justify-between gap-4 rounded-2xl border border-border bg-card p-5 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-md"
            >
              <div className="flex flex-col gap-1.5">
                <p className="font-medium">{order.order_number}</p>
                <p className="text-sm text-muted-foreground">
                  {new Date(order.created_at).toLocaleDateString()}
                </p>
                <StatusBadge status={order.status} />
              </div>
              <p className="font-semibold whitespace-nowrap">
                {formatPrice(order.grand_total, order.currency_code)}
              </p>
            </Link>
          </li>
        ))}
      </ul>

      {totalPages > 1 ? (
        <nav className="flex items-center justify-center gap-4 text-sm">
          {page > 1 ? (
            <Link href={`/orders?page=${page - 1}`} className={link}>
              ← Previous
            </Link>
          ) : (
            <span />
          )}
          <span className="text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          {page < totalPages ? (
            <Link href={`/orders?page=${page + 1}`} className={link}>
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
