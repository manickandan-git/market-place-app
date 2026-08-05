import "server-only";

import { apiClient } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

export type Shipment = components["schemas"]["shipping_ShipmentResponse"];

/**
 * shipping-service gates both shipment GET routes at `SellerOrAdmin`
 * (confirmed from services/shipping-service/app/routes/shipments.py) — a
 * plain buyer role gets a real 403 here, not a missing-resource 404.
 * There is currently no buyer-facing shipment read endpoint in the
 * backend at all (a genuine gap, not something to paper over client-side)
 * so this returns null on any error, including 403, and the order detail
 * page simply omits the tracking section for a buyer rather than showing
 * a broken/fake one.
 */
export async function getShipmentByOrder(orderId: string): Promise<Shipment | null> {
  const { data, error } = await apiClient.GET(
    "/api/v1/shipments/by-order/{order_id}",
    { params: { path: { order_id: orderId } } },
  );
  if (error) {
    return null;
  }
  return data;
}
