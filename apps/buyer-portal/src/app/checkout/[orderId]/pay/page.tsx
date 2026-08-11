import Link from "next/link";
import { notFound } from "next/navigation";

import { config } from "@/lib/config";
import { getOrder } from "@/lib/api/orders";
import { createPayment } from "@/lib/api/payments";
import { formatPrice } from "@/lib/format";
import { link } from "@/lib/ui";
import { PaymentForm } from "./PaymentForm";

export default async function PayPage({
  params,
}: {
  params: Promise<{ orderId: string }>;
}) {
  const { orderId } = await params;
  const order = await getOrder(orderId);

  if (!order) {
    notFound();
  }

  if (order.status !== "pending_payment") {
    return (
      <div className="flex flex-col items-start gap-4">
        <h1 className="text-2xl font-semibold">Order {order.order_number}</h1>
        <p className="text-muted-foreground">
          This order is {order.status.replace(/_/g, " ")} — no payment is
          needed here.
        </p>
        <Link href={`/orders/${order.id}`} className={link}>
          View order
        </Link>
      </div>
    );
  }

  const payment = await createPayment(order.id);
  if (!payment.ok || !payment.clientSecret) {
    return (
      <div className="flex flex-col items-start gap-4">
        <h1 className="text-2xl font-semibold">Order {order.order_number}</h1>
        <p className="text-danger">
          {payment.message ?? "Could not start payment. Please try again."}
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md">
      <h1 className="mb-1 text-2xl font-semibold tracking-tight">
        Pay for order {order.order_number}
      </h1>
      <p className="mb-6 text-lg font-medium text-primary">
        {formatPrice(order.grand_total, order.currency_code)}
      </p>
      <div className="rounded-2xl border border-border bg-card p-5 shadow-sm">
        <PaymentForm
          orderId={order.id}
          clientSecret={payment.clientSecret}
          publishableKey={config.stripePublishableKey}
        />
      </div>
    </div>
  );
}
