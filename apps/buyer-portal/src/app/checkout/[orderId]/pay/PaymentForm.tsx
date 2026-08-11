"use client";

import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from "@stripe/react-stripe-js";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { FormMessage } from "@/components/FormMessage";
import { buttonPrimary } from "@/lib/ui";

// Stripe's own guidance: call loadStripe() once outside the component tree
// so the Stripe object isn't recreated on every render. The publishable
// key is effectively constant for the app's lifetime (one env var), so a
// module-level cache is safe.
let stripePromiseCache: ReturnType<typeof loadStripe> | undefined;
function getStripePromise(publishableKey: string) {
  if (!stripePromiseCache) {
    stripePromiseCache = loadStripe(publishableKey);
  }
  return stripePromiseCache;
}

function CheckoutInner({ orderId }: { orderId: string }) {
  const stripe = useStripe();
  const elements = useElements();
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!stripe || !elements) {
      return;
    }
    setSubmitting(true);
    setError(undefined);

    const { error: confirmError } = await stripe.confirmPayment({
      elements,
      // Handle the common case (no 3DS redirect needed) without leaving
      // the page; Stripe still redirects for flows that require it
      // (e.g. 3D Secure), landing back on return_url.
      redirect: "if_required",
      confirmParams: {
        return_url: `${window.location.origin}/orders/${orderId}`,
      },
    });

    if (confirmError) {
      setError(confirmError.message ?? "Payment failed. Please try again.");
      setSubmitting(false);
      return;
    }

    // Confirmed client-side, but the order's payment_status only updates
    // once payment-service's Stripe webhook fires (see PaymentForm's
    // module docstring) — the order detail page shows whatever the
    // current status is, which may briefly still say pending_payment.
    router.push(`/orders/${orderId}`);
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <PaymentElement />
      <FormMessage message={error} />
      <button
        type="submit"
        disabled={!stripe || submitting}
        className={buttonPrimary}
      >
        {submitting ? "Processing…" : "Pay now"}
      </button>
    </form>
  );
}

/**
 * Confirmation happens entirely client-side against Stripe, using only the
 * publishable key (safe to expose) and the order-scoped client_secret
 * created server-side. Authoritative order-status updates are
 * webhook-driven from payment-service, not from anything in this
 * component — see services/payment-service/README.md's "Confirmation
 * flow" section.
 */
export function PaymentForm({
  orderId,
  clientSecret,
  publishableKey,
}: {
  orderId: string;
  clientSecret: string;
  publishableKey: string;
}) {
  if (!publishableKey) {
    return (
      <FormMessage message="Payments are not configured (missing NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY)." />
    );
  }

  const stripePromise = getStripePromise(publishableKey);

  return (
    <Elements
      stripe={stripePromise}
      options={{
        clientSecret,
        appearance: {
          theme: "stripe",
          variables: {
            colorPrimary: "#4f46e5",
            borderRadius: "8px",
            fontFamily: "var(--font-geist-sans), sans-serif",
          },
        },
      }}
    >
      <CheckoutInner orderId={orderId} />
    </Elements>
  );
}
