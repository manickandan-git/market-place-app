import "server-only";

import { apiClient } from "@/lib/api/client";
import { extractErrorMessage } from "@/lib/api/errors";
import type { components } from "@/lib/api/schema";

export type Order = components["schemas"]["order_OrderResponse"];
export type AddressInput = components["schemas"]["order_AddressSnapshot"];

export interface CreateOrderResult {
  ok: boolean;
  order?: Order;
  message?: string;
}

export async function createOrder(
  cartId: string,
  cartVersion: number,
  shippingAddress: AddressInput,
): Promise<CreateOrderResult> {
  const { data, error } = await apiClient.POST("/api/v1/orders", {
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    body: {
      cart_id: cartId,
      cart_version: cartVersion,
      shipping_address: shippingAddress,
    },
  });
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, order: data };
}

export async function getOrder(orderId: string): Promise<Order | null> {
  const { data, error } = await apiClient.GET("/api/v1/orders/{order_id}", {
    params: { path: { order_id: orderId } },
  });
  if (error) {
    return null;
  }
  return data;
}

export async function listOrders(
  page = 1,
  pageSize = 20,
): Promise<{ items: Order[]; totalPages: number; page: number }> {
  const { data, error } = await apiClient.GET("/api/v1/orders", {
    params: { query: { page, page_size: pageSize } },
  });
  if (error) {
    return { items: [], totalPages: 1, page: 1 };
  }
  // order_Page has no total_pages field (unlike product's PaginatedResponse) — derived here.
  return {
    items: data.items,
    totalPages: Math.max(1, Math.ceil(data.total_items / data.page_size)),
    page: data.page,
  };
}

/** `version` is the order's current version, sent as `If-Match` — note
 * order-service uses plain `If-Match`, not cart-service's
 * `If-Match-Version`; confirmed from the schema, each service has its own
 * concurrency-header convention. */
export async function cancelOrder(
  orderId: string,
  version: number,
  reason: string,
): Promise<CreateOrderResult> {
  const { data, error } = await apiClient.POST(
    "/api/v1/orders/{order_id}/cancel",
    {
      params: { path: { order_id: orderId }, header: { "If-Match": version } },
      body: { reason },
    },
  );
  if (error) {
    return { ok: false, message: extractErrorMessage(error) };
  }
  return { ok: true, order: data };
}
