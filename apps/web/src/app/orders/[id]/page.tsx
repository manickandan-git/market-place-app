import Link from "next/link";
import { notFound } from "next/navigation";

import { getOrder } from "@/lib/api/orders";
import { getShipmentByOrder } from "@/lib/api/shipments";
import { formatPrice } from "@/lib/format";
import { StatusBadge } from "@/components/StatusBadge";
import { buttonPrimary, card } from "@/lib/ui";
import { CancelOrderButton } from "./CancelOrderButton";

const CANCELLABLE_STATUSES = new Set(["pending_payment", "payment_authorized"]);

function label(value: string): string {
  return value.replace(/_/g, " ");
}

export default async function OrderDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const [order, shipment] = await Promise.all([
    getOrder(id),
    getShipmentByOrder(id),
  ]);

  if (!order) {
    notFound();
  }

  const address = order.shipping_address as Record<string, string | null>;

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Order {order.order_number}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Placed {new Date(order.created_at).toLocaleDateString()}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <StatusBadge status={order.status} />
          <span className="text-sm text-muted-foreground capitalize">
            Payment: {label(order.payment_status)}
          </span>
        </div>
      </div>

      {order.status === "pending_payment" ? (
        <Link
          href={`/checkout/${order.id}/pay`}
          className={buttonPrimary + " self-start"}
        >
          Complete payment
        </Link>
      ) : null}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className={card}>
          <h2 className="mb-3 font-medium">Items</h2>
          <ul className="flex flex-col gap-2">
            {order.items.map((item) => (
              <li key={item.id} className="flex justify-between text-sm">
                <span className="text-muted-foreground">
                  {item.product_name} × {item.quantity}
                </span>
                <span>{formatPrice(item.line_total, order.currency_code)}</span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-col gap-1 border-t border-border pt-3 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Subtotal</span>
              <span>{formatPrice(order.subtotal, order.currency_code)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Shipping</span>
              <span>{formatPrice(order.shipping_total, order.currency_code)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Tax</span>
              <span>{formatPrice(order.tax_total, order.currency_code)}</span>
            </div>
            <div className="flex justify-between pt-1 font-semibold">
              <span>Total</span>
              <span>{formatPrice(order.grand_total, order.currency_code)}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-6">
          <div className={card}>
            <h2 className="mb-3 font-medium">Shipping address</h2>
            <address className="not-italic text-sm leading-relaxed text-muted-foreground">
              {address.full_name}
              <br />
              {address.line1}
              {address.line2 ? (
                <>
                  <br />
                  {address.line2}
                </>
              ) : null}
              <br />
              {address.city}, {address.state_or_region} {address.postal_code}
              <br />
              {address.country_code}
            </address>
          </div>

          {shipment ? (
            <div className={card}>
              <h2 className="mb-3 font-medium">Tracking</h2>
              <p className="text-sm text-muted-foreground">
                {shipment.carrier}
                {shipment.tracking_number ? ` · ${shipment.tracking_number}` : ""}
                {" — "}
                {label(shipment.status)}
              </p>
              {shipment.events.length > 0 ? (
                <ul className="mt-2 flex flex-col gap-1 text-xs text-muted-foreground">
                  {shipment.events.map((event) => (
                    <li key={event.id}>
                      {new Date(event.occurred_at).toLocaleString()} —{" "}
                      {event.description ?? label(event.event_type)}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {CANCELLABLE_STATUSES.has(order.status) ? (
        <CancelOrderButton orderId={order.id} version={order.version} />
      ) : null}
    </div>
  );
}
