import "server-only";

import { apiClient } from "@/lib/api/client";
import { extractErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Payment = components["schemas"]["payment_PaymentResponse"];

export interface CreatePaymentResult {
  ok: boolean;
  payment?: Payment;
  clientSecret?: string | null;
  message?: string;
}

/**
 * Only ever creates a Stripe PaymentIntent — never charges anything.
 * Confirmation happens client-side with the returned client_secret via
 * Stripe.js, and authoritative order-status updates are webhook-driven
 * from payment-service, not from this call's result. See
 * services/payment-service/README.md's "Confirmation flow" section.
 */
export async function createPayment(orderId: string): Promise<CreatePaymentResult> {
  const { data, error } = await apiClient.POST("/api/v1/payments", {
    params: { header: { "idempotency-key": crypto.randomUUID() } },
    body: { order_id: orderId },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, payment: data.payment, clientSecret: data.client_secret };
}

export async function getPayment(paymentId: string): Promise<Payment | null> {
  const { data, error } = await apiClient.GET("/api/v1/payments/{payment_id}", {
    params: { path: { payment_id: paymentId } },
  });
  if (error) {
    return null;
  }
  return data;
}
